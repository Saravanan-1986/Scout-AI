"""Global agent-trace store with an optional live sink.

LangGraph nodes call ``record()`` instead of passing trace lists through the
graph state. The terminal CLI registers a *sink* so every agent step is
printed the moment it happens; the full trace is injected into the final
state and persisted to MongoDB (``agent_traces`` collection).
"""

import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_lock = threading.Lock()
_steps: List[Dict[str, Any]] = []
_sink: Optional[Callable[[Dict[str, Any]], None]] = None


def set_sink(sink: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Register (or clear with None) the callback invoked for every step."""
    global _sink
    _sink = sink


def reset() -> None:
    """Clear all recorded steps (call before starting a new search run)."""
    with _lock:
        _steps.clear()


def record(agent: str, action: str, **details: Any) -> Dict[str, Any]:
    """Record one agent step and forward it to the live sink if present."""
    step: Dict[str, Any] = {
        "agent": agent,
        "action": action,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _steps.append(step)

    sink = _sink
    if sink is not None:
        try:
            sink(step)
        except Exception:
            pass  # tracing must never break the workflow
    return step


def get_trace() -> List[Dict[str, Any]]:
    """Return a copy of all steps recorded so far."""
    with _lock:
        return list(_steps)
