"""
Self-learning brain: store and retrieve patterns in Supabase. No domains stored.
- brain_patterns: aggregated pattern_type + pattern_value with success_count / use_count
- brain_events: recent events for admin visibility (event_type, outcome, metadata, no domain)
"""
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

# Reuse Supabase client from storage (same project)
def _client():
    from utils.supabase_storage import _client as storage_client
    return storage_client()


def _table(name: str):
    return _client().table(name)


# --- Recording (called from processor) ---

def record_event(event_type: str, outcome: str, pattern_value: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
    """Append one learning event for admin visibility. No domain stored."""
    try:
        _table("brain_events").insert({
            "event_type": event_type,
            "pattern_value": pattern_value or "",
            "outcome": outcome,
            "metadata": metadata or {},
        }).execute()
        return True
    except Exception as e:
        print(f"[BRAIN] record_event failed: {e}")
        return False


def record_pattern_use(pattern_type: str, pattern_value: str, success: bool) -> bool:
    """Increment use_count and optionally success_count for a pattern (upsert)."""
    try:
        now = datetime.utcnow().isoformat()
        # Try upsert: match (pattern_type, pattern_value), then set use_count = use_count + 1, success_count = success_count + (success ? 1 : 0)
        # Supabase/PostgREST doesn't support increment in upsert easily; we do RPC or select+upsert. Use raw increment via update after insert on conflict.
        table = _table("brain_patterns")
        r = table.select("id, use_count, success_count").eq("pattern_type", pattern_type).eq("pattern_value", pattern_value).execute()
        if r.data and len(r.data) > 0:
            row = r.data[0]
            table.update({
                "use_count": (row.get("use_count") or 0) + 1,
                "success_count": (row.get("success_count") or 0) + (1 if success else 0),
                "last_used_at": now,
                "updated_at": now,
            }).eq("id", row["id"]).execute()
        else:
            table.insert({
                "pattern_type": pattern_type,
                "pattern_value": pattern_value,
                "use_count": 1,
                "success_count": 1 if success else 0,
                "last_used_at": now,
                "updated_at": now,
            }).execute()
        return True
    except Exception as e:
        print(f"[BRAIN] record_pattern_use failed: {e}")
        return False


# --- Reading for processor (optional: use learned patterns) ---

def get_top_patterns(pattern_type: str, limit: int = 50) -> List[str]:
    """Return list of pattern_value ordered by success_count desc (for use in processor)."""
    try:
        r = _table("brain_patterns").select("pattern_value").eq("pattern_type", pattern_type).order("success_count", desc=True).limit(limit).execute()
        if not r.data:
            return []
        return [row["pattern_value"] for row in r.data if row.get("pattern_value")]
    except Exception as e:
        print(f"[BRAIN] get_top_patterns failed: {e}")
        return []


# --- Admin API ---

def get_brain_stats() -> Dict[str, Any]:
    """Aggregate stats for admin dashboard."""
    try:
        patterns = _table("brain_patterns").select("pattern_type, success_count, use_count").execute()
        events = _table("brain_events").select("id").execute()
        by_type = {}
        for row in (patterns.data or []):
            t = row.get("pattern_type") or "unknown"
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_patterns": len(patterns.data or []),
            "patterns_by_type": by_type,
            "total_events": len(events.data or []),
        }
    except Exception as e:
        print(f"[BRAIN] get_brain_stats failed: {e}")
        return {"total_patterns": 0, "patterns_by_type": {}, "total_events": 0, "error": str(e)}


def get_brain_events(limit: int = 100, event_type: Optional[str] = None) -> List[Dict]:
    """Recent brain_events for admin."""
    try:
        q = _table("brain_events").select("*").order("created_at", desc=True).limit(limit)
        if event_type:
            q = q.eq("event_type", event_type)
        r = q.execute()
        return r.data or []
    except Exception as e:
        print(f"[BRAIN] get_brain_events failed: {e}")
        return []


def get_brain_patterns(pattern_type: Optional[str] = None, limit: int = 200) -> List[Dict]:
    """List patterns (optionally by type) for admin."""
    try:
        q = _table("brain_patterns").select("*").order("success_count", desc=True).limit(limit)
        if pattern_type:
            q = q.eq("pattern_type", pattern_type)
        r = q.execute()
        return r.data or []
    except Exception as e:
        print(f"[BRAIN] get_brain_patterns failed: {e}")
        return []
