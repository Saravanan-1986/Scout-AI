"""MongoDB-backed opportunity cache (Bottleneck #12 — don't re-scrape).

Stores every extracted opportunity keyed by ``source_url`` with a timestamp.
On later searches (or re-planning rounds) a fresh cached copy is reused
instead of hitting the website again. Degrades gracefully: when MongoDB is
unreachable the cache is simply disabled and every page is scraped.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_client = None
_db = None
_checked = False


def _ensure() -> bool:
    """Lazily connect (once). Returns True when the cache is usable."""
    global _client, _db, _checked
    if _checked:
        return _db is not None
    _checked = True
    try:
        import pymongo

        _client = pymongo.MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
        _client.admin.command("ping")
        _db = _client[settings.mongodb_db_name]
        logger.info("[Cache] Opportunity cache enabled (db '%s').", settings.mongodb_db_name)
    except Exception as e:
        logger.info("[Cache] MongoDB unavailable — opportunity cache disabled (%s).", e)
        _db = None
    return _db is not None


def get_cached_opportunity(url: str, max_age_hours: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Return a recent cached opportunity for `url`, or None."""
    if not url or not _ensure():
        return None
    try:
        max_age_hours = max_age_hours or settings.cache_hours
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        doc = _db.opportunity_cache.find_one({"source_url": url, "scraped_at": {"$gte": cutoff}})
        if not doc:
            return None
        opp = dict(doc.get("opportunity") or {})
        opp.pop("_id", None)
        return opp or None
    except Exception:
        return None


def cache_opportunity(opp: Dict[str, Any]) -> None:
    """Store an extracted opportunity for future reuse (never raises)."""
    if not opp or not opp.get("source_url") or not _ensure():
        return
    try:
        _db.opportunity_cache.update_one(
            {"source_url": opp["source_url"]},
            {
                "$set": {
                    "opportunity": opp,
                    "title": opp.get("title", ""),
                    "type": opp.get("type", ""),
                    "scraped_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.debug("[Cache] store failed: %s", e)


def close() -> None:
    global _client, _db
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client, _db = None, None
