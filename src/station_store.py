# src/station_store.py
import difflib
import logging
import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from src.event_store import DB_PATH

logger = logging.getLogger(__name__)

_CSV_PATH = Path("bangalore_city_police_stations_2012.csv")
_BTP_CSV_URL = (
    "https://data.opencity.in/dataset/e3444619-12c5-43bd-9fc5-a54e83cc162f"
    "/resource/8521e8fb-168b-46fa-9faa-00faf2f2daa6"
    "/download/570ea599-d0af-4d1d-a659-381204a3d918.csv"
)

_DDL_STATIONS = """
CREATE TABLE IF NOT EXISTS police_stations (
    station_code          INTEGER PRIMARY KEY,
    station_name          TEXT NOT NULL,
    address_clean         TEXT,
    unit                  TEXT,
    dcp_zone              TEXT NOT NULL,
    acp_zone              TEXT NOT NULL,
    latitude              REAL,
    longitude             REAL,
    location_source       TEXT DEFAULT 'pending',
    has_btp_pi            INTEGER DEFAULT 0,
    btp_match_confidence  REAL,
    capacity_officers     INTEGER DEFAULT 25,
    capacity_vehicles     INTEGER DEFAULT 3,
    capacity_source       TEXT DEFAULT 'default',
    phone                 TEXT,
    geocoded_at           TEXT,
    updated_at            TEXT NOT NULL
)
"""

_DDL_CENTROIDS = """
CREATE TABLE IF NOT EXISTS zone_centroids (
    dcp_zone   TEXT PRIMARY KEY,
    latitude   REAL NOT NULL,
    longitude  REAL NOT NULL
)
"""

_NAME_STOPWORDS = {
    "ps", "p.s", "road", "main", "cross", "beedi", "layout",
    "colony", "street", "gate", "circle", "halli", "puram", "nagara",
}


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _try_geocode_strategies(
    station_name: str,
    acp_zone: str,
    geocoder,
) -> tuple[float, float] | None:
    """Try 3 progressively simpler Nominatim queries. Returns (lat, lng) or None."""
    queries = [
        f"{station_name} Police Station, {acp_zone}, Bangalore, Karnataka, India",
        f"{station_name} Police Station, Bangalore, Karnataka, India",
        f"{station_name}, Bangalore, India",
    ]
    for q in queries:
        loc = geocoder(q)
        if loc is not None:
            return (loc.latitude, loc.longitude)
    return None


def _clean_station_field(raw: str) -> tuple[str, str]:
    """Return (station_name, address_clean) from raw Station CSV field."""
    cleaned = re.sub(r"Ph\s*no\..*", "", raw, flags=re.IGNORECASE).strip()
    tokens = cleaned.split()
    name_tokens: list[str] = []
    for t in tokens:
        if not t:
            continue
        if t[0].isdigit() or t[0] in "#@":
            break
        if t.lower().strip(".,") in _NAME_STOPWORDS:
            break
        name_tokens.append(t)
        if len(name_tokens) == 2:
            break
    station_name = " ".join(name_tokens) if name_tokens else (tokens[0] if tokens else "Unknown")
    return station_name, cleaned


def _count_stations() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT COUNT(*) FROM police_stations").fetchone()[0]


def init_station_db() -> None:
    """Create tables and seed from CSV if empty. Idempotent."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_DDL_STATIONS)
        conn.execute(_DDL_CENTROIDS)
        conn.commit()
    if _count_stations() == 0:
        _seed_from_csv()


def _seed_from_csv() -> None:
    df = pd.read_csv(_CSV_PATH)
    now = _now()
    rows = []
    for _, row in df.iterrows():
        raw = str(row["Station"])
        station_name, address_clean = _clean_station_field(raw)
        phone_m = re.search(r"Ph\s*no\.\s*([\d\s\-,]+)", raw, re.IGNORECASE)
        phone = phone_m.group(1).strip() if phone_m else None
        sc = row["Station Code"]
        station_code = int(sc) if pd.notna(sc) else int(row["Sl"])
        rows.append((
            station_code,
            station_name,
            address_clean,
            str(row["Unit"]) if pd.notna(row["Unit"]) else None,
            str(row["DCP"]),
            str(row["ACP"]),
            None, None,      # latitude, longitude
            "pending",       # location_source
            0, None,         # has_btp_pi, btp_match_confidence
            25, 3,           # capacity_officers, capacity_vehicles
            "default",       # capacity_source
            phone,
            None,            # geocoded_at
            now,             # updated_at
        ))
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO police_stations
               (station_code, station_name, address_clean, unit, dcp_zone, acp_zone,
                latitude, longitude, location_source, has_btp_pi, btp_match_confidence,
                capacity_officers, capacity_vehicles, capacity_source, phone,
                geocoded_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_all_stations(
    progress_callback=None,
    _geocoder=None,
) -> dict:
    """
    Geocode all pending stations via Nominatim, then apply zone centroid fallback,
    then enrich BTP flags. Returns summary dict.
    _geocoder: callable(query) -> location|None — injectable for testing.
    """
    if _geocoder is None:
        from geopy.geocoders import Nominatim
        from geopy.extra.rate_limiter import RateLimiter
        nom = Nominatim(user_agent="gridlock2-geocoder")
        _geocoder = RateLimiter(nom.geocode, min_delay_seconds=1)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            "SELECT station_code, station_name, address_clean, acp_zone FROM police_stations "
            "WHERE location_source = 'pending'"
        ).fetchall()

    total = len(pending)

    for i, row in enumerate(pending):
        result = _try_geocode_strategies(row["station_name"], row["acp_zone"], _geocoder)
        now = _now()
        if result is not None:
            lat, lng = result
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "UPDATE police_stations SET latitude=?, longitude=?, "
                    "location_source='geocoded', geocoded_at=?, updated_at=? "
                    "WHERE station_code=?",
                    (lat, lng, now, now, row["station_code"]),
                )
                conn.commit()
        if progress_callback:
            progress_callback(i + 1, total)

    _apply_zone_centroid_fallback()
    _compute_and_store_zone_centroids()
    _enrich_btp()

    return get_geocode_summary()


def _apply_zone_centroid_fallback() -> None:
    """Set zone centroid lat/lng for stations that failed geocoding."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        geocoded = conn.execute(
            "SELECT dcp_zone, latitude, longitude FROM police_stations "
            "WHERE location_source = 'geocoded'"
        ).fetchall()

    # Build centroid map from geocoded-only rows
    zone_lats: dict[str, list[float]] = {}
    zone_lngs: dict[str, list[float]] = {}
    for row in geocoded:
        zone_lats.setdefault(row["dcp_zone"], []).append(row["latitude"])
        zone_lngs.setdefault(row["dcp_zone"], []).append(row["longitude"])

    centroids = {
        z: (sum(zone_lats[z]) / len(zone_lats[z]),
            sum(zone_lngs[z]) / len(zone_lngs[z]))
        for z in zone_lats
    }

    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            "SELECT station_code, dcp_zone FROM police_stations "
            "WHERE location_source = 'pending'"
        ).fetchall()
        for row in pending:
            c = centroids.get(row["dcp_zone"])
            if c:
                conn.execute(
                    "UPDATE police_stations SET latitude=?, longitude=?, "
                    "location_source='zone_centroid_fallback', updated_at=? "
                    "WHERE station_code=?",
                    (c[0], c[1], now, row["station_code"]),
                )
        conn.commit()


def _compute_and_store_zone_centroids() -> None:
    """Persist DCP zone centroids from geocoded-only stations to zone_centroids table."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT dcp_zone, latitude, longitude FROM police_stations "
            "WHERE location_source = 'geocoded'"
        ).fetchall()

    zone_lats: dict[str, list[float]] = {}
    zone_lngs: dict[str, list[float]] = {}
    for row in rows:
        zone_lats.setdefault(row["dcp_zone"], []).append(row["latitude"])
        zone_lngs.setdefault(row["dcp_zone"], []).append(row["longitude"])

    with sqlite3.connect(DB_PATH) as conn:
        for zone, lats in zone_lats.items():
            lat = sum(lats) / len(lats)
            lng = sum(zone_lngs[zone]) / len(zone_lngs[zone])
            conn.execute(
                "INSERT OR REPLACE INTO zone_centroids (dcp_zone, latitude, longitude) "
                "VALUES (?, ?, ?)",
                (zone, lat, lng),
            )
        conn.commit()


def _enrich_btp_from_df(btp_df: pd.DataFrame) -> None:
    """Enrich police_stations with BTP PI flags from a loaded BTP DataFrame."""
    pi_rows = btp_df[btp_df["Officer"].str.strip() == "Police Inspector Traffic"]

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        stations = conn.execute(
            "SELECT station_code, station_name FROM police_stations"
        ).fetchall()

    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        # Reset all stations to has_btp_pi=0, btp_match_confidence=NULL before re-enrichment
        conn.execute(
            "UPDATE police_stations SET has_btp_pi=0, btp_match_confidence=NULL, updated_at=?",
            (now,),
        )
        conn.commit()
        for station in stations:
            sname = station["station_name"].lower().strip()
            best_score = 0.0
            for _, brow in pi_rows.iterrows():
                bname = str(brow["Traffic Police Station"]).lower().strip()
                # Remove common suffixes for matching
                bname_clean = re.sub(
                    r"\b(police\s+station|ps|p\.s\.?)\b", "", bname
                ).strip()
                ratio = difflib.SequenceMatcher(None, sname, bname_clean).ratio()
                if ratio > best_score:
                    best_score = ratio

            if best_score == 1.0:
                conn.execute(
                    "UPDATE police_stations SET has_btp_pi=1, btp_match_confidence=1.0, "
                    "updated_at=? WHERE station_code=?",
                    (now, station["station_code"]),
                )
            elif best_score >= 0.7:
                conn.execute(
                    "UPDATE police_stations SET has_btp_pi=1, btp_match_confidence=?, "
                    "updated_at=? WHERE station_code=?",
                    (round(best_score, 3), now, station["station_code"]),
                )
        conn.commit()


def _enrich_btp() -> None:
    """Download BTP CSV and enrich stations. Logs warning on download failure."""
    try:
        resp = requests.get(_BTP_CSV_URL, timeout=10)
        resp.raise_for_status()
        import io
        btp_df = pd.read_csv(io.StringIO(resp.text))
        _enrich_btp_from_df(btp_df)
    except Exception as exc:
        logger.warning("BTP data unavailable — traffic PI flags not set: %s", exc)


def reset_station_geocode(station_code: int) -> None:
    """Reset a station to pending so it can be re-geocoded."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE police_stations SET location_source='pending', latitude=NULL, "
            "longitude=NULL, geocoded_at=NULL, updated_at=? WHERE station_code=?",
            (_now(), station_code),
        )
        conn.commit()


def get_geocode_summary() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT location_source, COUNT(*) FROM police_stations GROUP BY location_source"
        ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    return {
        "geocoded": counts.get("geocoded", 0),
        "fallback": counts.get("zone_centroid_fallback", 0),
        "pending":  counts.get("pending", 0),
        "total":    sum(counts.values()),
    }


# ── Ranking + Allocation ───────────────────────────────────────────────────────

_RANK_WEIGHTS = {
    "btp_boost":        2.0,
    "workload_penalty": 1.5,
}

_WORKLOAD_SQL = """
    SELECT COUNT(*) FROM planned_events
    WHERE zone = :dcp_zone
      AND status NOT IN ('cancelled', 'completed')
"""


def rank_stations(
    event_lat: float,
    event_lng: float,
    event_date: str = "",
    event_time: str = "",
    top_n: int = 5,
) -> list[dict]:
    """Rank geocoded stations by score = distance - btp_boost + workload_penalty.
    Returns [] if fewer than 2 stations are geocoded."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM police_stations WHERE latitude IS NOT NULL"
        ).fetchall()

    if len(rows) < 2:
        return []

    scored: list[dict] = []
    with sqlite3.connect(DB_PATH) as conn:
        for row in rows:
            dist = _haversine_km(event_lat, event_lng, row["latitude"], row["longitude"])
            try:
                workload = conn.execute(
                    _WORKLOAD_SQL,
                    {"dcp_zone": row["dcp_zone"]},
                ).fetchone()[0]
            except sqlite3.OperationalError:
                # planned_events table does not exist yet
                workload = 0
            score = (
                dist
                - row["has_btp_pi"] * _RANK_WEIGHTS["btp_boost"]
                + workload * _RANK_WEIGHTS["workload_penalty"]
            )
            scored.append({
                "station_name":         row["station_name"],
                "station_code":         row["station_code"],
                "dcp_zone":             row["dcp_zone"],
                "acp_zone":             row["acp_zone"],
                "distance_km":          round(dist, 2),
                "workload":             workload,
                "has_btp_pi":           row["has_btp_pi"],
                "btp_match_confidence": row["btp_match_confidence"],
                "capacity_officers":    row["capacity_officers"],
                "capacity_vehicles":    row["capacity_vehicles"],
                "capacity_source":      row["capacity_source"],
                "score":                round(score, 3),
                "response_min":         round(dist / 30.0 * 60),
                "officers_allocated":   0,
                "allocation_capped":    False,
                "capacity_unconfirmed": False,
            })

    scored.sort(key=lambda x: x["score"])
    return scored[:top_n]


def allocate_officers(stations: list[dict], total_officers: int) -> list[dict]:
    """Inverse-distance weighted officer allocation.
    Cap only applied for capacity_source == 'manual'. Both branches set all 3 keys."""
    if not stations:
        return stations

    dists   = [max(s["distance_km"], 0.1) for s in stations]
    weights = [1.0 / d for d in dists]
    total_w = sum(weights)

    for s, w in zip(stations, weights):
        raw = round(total_officers * w / total_w)
        if s["capacity_source"] == "manual":
            s["officers_allocated"]   = min(raw, s["capacity_officers"])
            s["allocation_capped"]    = raw > s["capacity_officers"]
            s["capacity_unconfirmed"] = False
        else:
            s["officers_allocated"]   = raw
            s["allocation_capped"]    = False
            s["capacity_unconfirmed"] = True

    return stations


def update_station_capacity(station_code: int, officers: int, vehicles: int) -> None:
    now = _now()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """UPDATE police_stations
               SET capacity_officers=?, capacity_vehicles=?,
                   capacity_source='manual', updated_at=?
               WHERE station_code=?""",
            (officers, vehicles, now, station_code),
        )
        conn.commit()


def get_all_stations() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM police_stations ORDER BY dcp_zone, station_name"
        ).fetchall()
    return [dict(r) for r in rows]
