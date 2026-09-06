"""E2E test of the /discover streaming endpoint using a fake graph (no network)."""
import asyncio
import json

import app.main as m


class FakeGraph:
    async def ainvoke(self, state, config=None):
        from app.graph import trace
        assert state["search_type"] == "hackathon", f"search_type not passed: {state['search_type']}"
        trace.record("planner", "generated search queries", queries=["q1", "q2"])
        await asyncio.sleep(0.4)  # simulate work while events stream
        trace.record("researcher", "searched web", query="q1")
        trace.record("recommender", "ranked top 1 opportunities")
        return {
            **state,
            "final_output": [{
                "title": "AI Hackathon 2026", "organization": "TestCorp",
                "type": "hackathon", "location": "Remote", "mode": "Online",
                "duration": "48 hours", "prize": "$1000", "deadline": "2026-12-01",
                "required_skills": ["python", "react"], "verified": True,
                "application_url": "http://apply", "source_url": "http://src",
                "eligibility_status": "ELIGIBLE", "eligibility_reason": "open to all years",
                "match_score": {"total": 88.5, "label": "Strong Match", "breakdown": {
                    "skill": {"score": 30, "max": 40, "note": "matched 2/2"},
                    "education": {"score": 10, "max": 20, "note": "neutral"},
                    "year": {"score": 15, "max": 15, "note": "ok"},
                    "cgpa": {"score": 10, "max": 10, "note": "ok"},
                    "interest": {"score": 10, "max": 10, "note": "AI match"},
                    "location": {"score": 5, "max": 5, "note": "remote"},
                }},
                "fit_explanation": "Your skills match.",
            }],
            "quality": {"enough": True},
        }


m.scout_graph = FakeGraph()

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(m.app)
resp = client.post("/discover", json={
    "user_id": "u1", "name": "Saravanan", "cgpa": 9.54, "skills": ["python"],
    "location": "Chennai", "search_type": "hackathon",
})
print("HTTP", resp.status_code)
print("content-type:", resp.headers.get("content-type"))
assert resp.status_code == 200, resp.text

types_seen = []
for line in resp.text.splitlines():
    if not line.startswith("data:"):
        continue
    ev = json.loads(line[5:])
    types_seen.append(ev["type"])
    if ev["type"] == "trace":
        print("TRACE  ", ev["step"]["agent"], "-", ev["step"]["action"])
    elif ev["type"] == "opportunity":
        it = ev["item"]
        print("OPP    ", it["title"], "|", it["match_score"]["total"], "|", it["eligibility_status"])
        assert it["match_score"]["total"] == 88.5
        assert it["match_score"]["breakdown"]["skill"]["score"] == 30
    elif ev["type"] == "done":
        print("DONE   ", ev["quality"])
    elif ev["type"] == "error":
        raise AssertionError("unexpected error event: " + str(ev))

assert types_seen[0] == "trace", "first event must be a trace step (sink works!)"
assert types_seen.count("trace") == 3, f"expected 3 trace events, got {types_seen}"
assert types_seen[-1] == "done"
assert types_seen.count("opportunity") == 1
print("ALL STREAMING TESTS PASSED")
