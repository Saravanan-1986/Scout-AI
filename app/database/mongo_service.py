"""Optional MongoDB persistence for ScoutAI (sync pymongo, used by the CLI).

Everything degrades gracefully: when MongoDB is unreachable the app simply
reports that results were not saved and continues.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

APPLICATION_STATUSES = ("Saved", "Applied", "Interview", "Selected", "Rejected")


class MongoService:
    def __init__(self) -> None:
        self._client = None
        self._db = None
        self.available = False

    def connect(self) -> bool:
        try:
            import pymongo

            self._client = pymongo.MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=2500)
            self._client.admin.command("ping")
            self._db = self._client[settings.mongodb_db_name]
            self.available = True
            logger.info("[MongoDB] Connected to db '%s'.", settings.mongodb_db_name)
        except Exception as e:
            self.available = False
            logger.info("[MongoDB] Unavailable (%s) — continuing without persistence.", e)
        return self.available

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    def save_profile(self, profile: Dict[str, Any]) -> None:
        if not self.available:
            return
        doc = dict(profile)
        doc["updated_at"] = self._now()
        doc.setdefault("created_at", self._now())
        self._db.student_profiles.update_one(
            {"user_id": profile.get("user_id")}, {"$set": doc}, upsert=True
        )

    def save_opportunities(self, opportunities: List[Dict[str, Any]], user_id: str) -> int:
        if not self.available:
            return 0
        for opp in opportunities:
            doc = dict(opp)
            doc["last_saved_at"] = self._now()
            doc["discovered_for_user"] = user_id
            self._db.opportunities.update_one(
                {"source_url": opp.get("source_url")},
                {"$set": doc},
                upsert=True,
            )
        return len(opportunities)

    def save_search_history(
        self,
        user_id: str,
        search_id: str,
        query: str,
        filters: Dict[str, Any],
        opportunities_found: int,
        strong_matches: int,
    ) -> None:
        if not self.available:
            return
        self._db.search_history.insert_one(
            {
                "search_id": search_id,
                "user_id": user_id,
                "query": query,
                "filters": filters,
                "opportunities_found": opportunities_found,
                "strong_matches": strong_matches,
                "created_at": self._now(),
            }
        )

    def save_agent_trace(self, search_id: str, user_id: str, steps: List[Dict[str, Any]]) -> None:
        if not self.available:
            return
        self._db.agent_traces.insert_one(
            {"search_id": search_id, "user_id": user_id, "steps": steps, "created_at": self._now()}
        )

    def save_saved_opportunities(self, user_id: str, opportunities: List[Dict[str, Any]]) -> int:
        """Bookmark chosen opportunities (application_status starts as 'Saved')."""
        if not self.available:
            return 0
        for opp in opportunities:
            self._db.saved_opportunities.update_one(
                {"user_id": user_id, "source_url": opp.get("source_url")},
                {
                    "$set": {
                        "user_id": user_id,
                        "opportunity_title": opp.get("title"),
                        "source_name": opp.get("source_name"),
                        "source_url": opp.get("source_url"),
                        "match_score": (opp.get("match_score") or {}).get("total"),
                        "application_status": "Saved",
                        "saved_at": self._now(),
                    }
                },
                upsert=True,
            )
        return len(opportunities)

    def get_saved(self, user_id: str) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        try:
            docs = self._db.saved_opportunities.find({"user_id": user_id}).sort("saved_at", -1).limit(50)
            return list(docs)
        except Exception:
            return []

    def update_application_status(self, user_id: str, source_url: str, status: str) -> bool:
        if not self.available:
            return False
        result = self._db.saved_opportunities.update_one(
            {"user_id": user_id, "source_url": source_url},
            {"$set": {"application_status": status, "status_updated_at": self._now()}},
        )
        return result.matched_count > 0
