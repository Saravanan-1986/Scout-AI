import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database.models import StudentProfile
from app.database.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.graph import trace
from app.graph.state import AgentState
from app.graph.workflow import scout_graph

logger = logging.getLogger("scout_ai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_to_mongo()
    except Exception as e:
        logger.warning(f"MongoDB connection skipped or failed: {e}")
    yield
    try:
        await close_mongo_connection()
    except Exception as e:
        logger.warning(f"MongoDB close connection failed: {e}")


app = FastAPI(
    title="ScoutAI Backend API",
    description="Agentic AI backend for discovering, checking eligibility, and ranking student opportunities.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DiscoverRequest(StudentProfile):
    """Web-form payload: student profile + which opportunity type to search."""
    search_type: str = "both"  # internship | hackathon | both


def _opportunity_types_for(search_type: str):
    if search_type == "internship":
        return ["internship"]
    if search_type == "hackathon":
        return ["hackathon", "coding_competition", "competition"]
    return ["internship", "hackathon", "coding_competition", "competition"]


def _build_initial_state(profile_dict: Dict[str, Any], search_type: str) -> AgentState:
    """Create the initial LangGraph state dict."""
    return {
        "student_profile": profile_dict,
        "search_type": search_type,
        "iteration": 1,
        "search_queries": [],
        "used_queries": [],
        "raw_search_results": [],
        "processed_urls": [],
        "scraped_opportunities": [],
        "eligible_opportunities": [],
        "ranked_opportunities": [],
        "quality": {},
        "final_output": [],
        "agent_trace": [],
        "errors": [],
    }


@app.post("/discover")
async def discover_opportunities(profile: DiscoverRequest, request: Request):
    """POST /discover — streamed agentic workflow matching the terminal UX.

    Yields newline-delimited JSON events:
      {"type":"trace","step":{...}}      every agent step (live)
      {"type":"opportunity","item":{...}} each ranked opportunity as it finishes
      {"type":"done","quality":{...}}    final summary
    """
    try:
        profile_dict = profile.model_dump()
        # Merge the legacy single-location field into preferred_locations.
        if profile_dict.get("location") and not profile_dict.get("preferred_locations"):
            profile_dict["preferred_locations"] = [profile_dict.pop("location")]

        search_type = (profile_dict.pop("search_type", "both") or "both").lower()
        if search_type not in ("internship", "hackathon", "both"):
            search_type = "both"
        if not profile_dict.get("opportunity_types"):
            profile_dict["opportunity_types"] = _opportunity_types_for(search_type)

        # Save or update student profile in MongoDB if the database is available
        try:
            mongo_db = get_database()
            await mongo_db.student_profiles.update_one(
                {"user_id": profile_dict["user_id"]},
                {"$set": profile_dict},
                upsert=True,
            )
        except Exception as db_err:
            logger.warning(f"Skipping MongoDB save (db inactive or unreachable): {db_err}")

        # ---- Live trace sink: forward every agent step to the SSE response ----
        # We capture steps via a thread-safe buffer that we drain periodically.
        steps: list = []
        trace.reset()

        def _sink(step: Dict[str, Any]):
            steps.append(step)

        async def event_generator():
            trace.set_sink(_sink)  # active while THIS stream is running
            try:
                initial_state = _build_initial_state(profile_dict, search_type)

                # Run the graph — it calls record() → _sink → steps.append()
                task = asyncio.create_task(
                    scout_graph.ainvoke(initial_state, config={"recursion_limit": 60})
                )

                # Poll for new trace steps and opportunities while graph runs
                flushed = 0
                while not task.done():
                    await asyncio.sleep(0.2)
                    # Flush any new trace steps
                    while len(steps) > flushed:
                        yield f"data: {json.dumps({'type': 'trace', 'step': steps[flushed]})}\n\n"
                        flushed += 1
                    # Check if client disconnected
                    if await request.is_disconnected():
                        task.cancel()
                        break

                try:
                    result_state = task.result()
                except Exception as run_err:
                    logger.error(f"Workflow error: {run_err}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(run_err)})}\n\n"
                    return

                # Flush remaining traces
                while len(steps) > flushed:
                    yield f"data: {json.dumps({'type': 'trace', 'step': steps[flushed]})}\n\n"
                    flushed += 1

                # Flush final opportunities
                final_output = result_state.get("final_output", [])
                for item in final_output:
                    yield f"data: {json.dumps({'type': 'opportunity', 'item': item})}\n\n"

                quality = result_state.get("quality", {})
                yield f"data: {json.dumps({'type': 'done', 'quality': quality, 'user_id': profile_dict['user_id']})}\n\n"

            finally:
                trace.set_sink(None)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Error processing discovery request: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery workflow failed: {str(e)}")
