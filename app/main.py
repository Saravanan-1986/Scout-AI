import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database.models import StudentProfile
from app.database.mongodb import close_mongo_connection, connect_to_mongo, get_database
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


@app.post("/discover")
async def discover_opportunities(profile: StudentProfile):
    """POST /discover endpoint executing full LangGraph workflow for student opportunity discovery."""
    try:
        # Save or update student profile in MongoDB if database connection is available
        try:
            mongo_db = get_database()
            await mongo_db.student_profiles.update_one(
                {"user_id": profile.user_id},
                {"$set": profile.model_dump()},
                upsert=True,
            )
        except Exception as db_err:
            logger.warning(f"Skipping MongoDB save (db inactive or unreachable): {db_err}")

        initial_state: AgentState = {
            "student_profile": profile.model_dump(),
            "search_queries": [],
            "raw_search_results": [],
            "scraped_opportunities": [],
            "eligible_opportunities": [],
            "ranked_opportunities": [],
            "final_output": [],
        }

        # Invoke the compiled multi-agent LangGraph workflow
        result_state = await scout_graph.ainvoke(initial_state)

        return {
            "status": "success",
            "user_id": profile.user_id,
            "opportunities_count": len(result_state.get("final_output", [])),
            "results": result_state.get("final_output", []),
        }
    except Exception as e:
        logger.error(f"Error processing discovery request: {e}")
        raise HTTPException(status_code=500, detail=f"Discovery workflow failed: {str(e)}")
