# src/ops_store.py
import sqlite3
from datetime import date, datetime, timedelta

from src import event_store, station_store
from src.event_store import _haversine_km


def get_today_events() -> list[dict]:
    """Return all non-cancelled/completed events for today (UTC date), ordered by time."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM planned_events "
            "WHERE event_date = ? AND status NOT IN ('cancelled', 'completed') "
            "ORDER BY event_time",
            (today,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_week_events(days: int = 7) -> list[dict]:
    """Return all active events in the next `days` days (today inclusive),
    ordered by date then time."""
    today = date.today()
    end = today + timedelta(days=days - 1)
    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM planned_events "
            "WHERE event_date BETWEEN ? AND ? "
            "AND status NOT IN ('cancelled', 'completed') "
            "ORDER BY event_date, event_time",
            (today.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
        ).fetchall()
    return [dict(r) for r in rows]


def _parse_time_hours(t: str) -> float:
    """Parse 'HH:MM' string to fractional hours. Returns 0.0 on failure."""
    try:
        h, m = t.split(":")
        return int(h) + int(m) / 60.0
    except Exception:
        return 0.0


def detect_conflict_pairs(events: list[dict]) -> list[tuple[dict, dict]]:
    """Return (event_A, event_B) pairs where both conditions hold:
    1. Same date AND |time_A - time_B| <= 4 hours
    2. Same corridor string OR haversine distance <= 8.0 km
    Each pair appears once (lower index first). Returns [] if < 2 events."""
    if len(events) < 2:
        return []
    pairs = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            if a.get("event_date") != b.get("event_date"):
                continue
            if abs(_parse_time_hours(a.get("event_time", "00:00"))
                   - _parse_time_hours(b.get("event_time", "00:00"))) > 4.0:
                continue
            # Spatial check
            spatial = False
            if a.get("corridor") and a.get("corridor") == b.get("corridor"):
                spatial = True
            elif (a.get("latitude") is not None and a.get("longitude") is not None
                  and b.get("latitude") is not None and b.get("longitude") is not None):
                if _haversine_km(
                    a["latitude"], a["longitude"], b["latitude"], b["longitude"]
                ) <= 8.0:
                    spatial = True
            if spatial:
                pairs.append((a, b))
    return pairs


def get_zone_utilization() -> dict[str, int]:
    """Return {zone: active_event_count} for today's active events, non-null zones only."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with sqlite3.connect(event_store.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT zone, COUNT(*) FROM planned_events "
            "WHERE event_date = ? AND status NOT IN ('cancelled', 'completed') "
            "AND zone IS NOT NULL GROUP BY zone",
            (today,),
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def optimize_multi_event(event_ids: list[str]) -> dict:
    """Given event IDs, return combined resource plan with station conflict resolution.

    Priority = estimated_attendance descending (ties: event_time ascending).
    Higher-priority events get first pick of stations.
    Station conflicts: same station in original top-3 of 2+ events.
    Resolution: lower-priority event gets next available (unclaimed) station.
    unresolvable=True if any event ends up with 0 stations after filtering.
    """
    _empty = {
        "events": [], "total_officers_min": 0, "total_officers_max": 0,
        "per_event": [], "station_conflicts": [], "unresolvable": False,
    }
    if not event_ids:
        return _empty

    with sqlite3.connect(event_store.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(event_ids))
        rows = conn.execute(
            f"SELECT * FROM planned_events WHERE event_id IN ({placeholders})",
            event_ids,
        ).fetchall()
    if not rows:
        return _empty

    events = sorted(
        [dict(r) for r in rows],
        key=lambda e: (-(e.get("estimated_attendance") or 0), e.get("event_time", "")),
    )

    total_min = sum(e.get("officer_min") or 0 for e in events)
    total_max = sum(e.get("officer_max") or 0 for e in events)

    claimed: dict[int, str] = {}        # station_code → event_id that claimed it
    original_top3: dict[str, list[int]] = {}  # event_id → original top-3 station codes

    per_event = []
    unresolvable = False

    for ev in events:
        eid = ev["event_id"]
        lat, lng = ev.get("latitude"), ev.get("longitude")

        if lat is None or lng is None:
            per_event.append({
                "event_id": eid, "event_name": ev.get("event_name", ""),
                "stations": [], "conflict_with": [],
            })
            original_top3[eid] = []
            continue

        all_ranked = station_store.rank_stations(
            lat, lng, ev.get("event_date", ""), ev.get("event_time", ""), top_n=5
        )
        original_top3[eid] = [s["station_code"] for s in all_ranked[:3]]

        available = [s for s in all_ranked if s["station_code"] not in claimed]
        assigned = available[:3]

        if not assigned and all_ranked:
            unresolvable = True

        if assigned:
            assigned = station_store.allocate_officers(assigned, ev.get("officer_min") or 0)
            for s in assigned:
                claimed[s["station_code"]] = eid

        per_event.append({
            "event_id": eid, "event_name": ev.get("event_name", ""),
            "stations": assigned, "conflict_with": [],
        })

    # Build station_conflicts from original top-3 overlaps
    station_event_map: dict[int, list[str]] = {}
    for eid, codes in original_top3.items():
        for code in codes:
            station_event_map.setdefault(code, []).append(eid)

    conflict_codes = [c for c, eids in station_event_map.items() if len(eids) >= 2]
    station_conflicts: list[dict] = []
    conflict_partners: dict[str, set[str]] = {}

    if conflict_codes:
        with sqlite3.connect(event_store.DB_PATH) as conn:
            ph = ",".join("?" * len(conflict_codes))
            name_rows = conn.execute(
                f"SELECT station_code, station_name FROM police_stations "
                f"WHERE station_code IN ({ph})",
                conflict_codes,
            ).fetchall()
        names = {r[0]: r[1] for r in name_rows}
        for code in conflict_codes:
            claiming = station_event_map[code]
            station_conflicts.append({
                "station_name": names.get(code, str(code)),
                "claimed_by": claiming,
            })
            for eid in claiming:
                conflict_partners.setdefault(eid, set()).update(
                    e for e in claiming if e != eid
                )

    for pe in per_event:
        pe["conflict_with"] = list(conflict_partners.get(pe["event_id"], set()))

    return {
        "events": events,
        "total_officers_min": total_min,
        "total_officers_max": total_max,
        "per_event": per_event,
        "station_conflicts": station_conflicts,
        "unresolvable": unresolvable,
    }
