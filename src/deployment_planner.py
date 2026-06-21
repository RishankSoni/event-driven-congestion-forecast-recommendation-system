# src/deployment_planner.py

def _attendance_band(n: int) -> str:
    if n < 500:
        return "small"
    if n < 5000:
        return "medium"
    return "large"


def build_deployment_plan(
    event: dict,
    ranked_stations: list[dict],
    officers: dict,
    barricades: list[str],
    diversions: list[str],
) -> dict:
    """Assemble full deployment plan dict with narrative briefing."""
    attendance  = int(event.get("estimated_attendance") or 0)
    severity    = event.get("severity", "LOW")
    law_prob    = float(event.get("law_order_prob") or 0.0)
    duration_m  = round(float(event.get("expected_duration_h") or 2.0) * 60)

    qrt_recommended = law_prob > 0.5 or severity == "HIGH"
    qrt_units = (
        2 if severity == "HIGH" and attendance > 5000
        else 1 if qrt_recommended
        else 0
    )
    medical_posts = (
        2 if attendance > 2000
        else 1 if attendance >= 500
        else 0
    )
    timeline = [
        {"offset_min": -120, "label": "Station briefing and resource assembly"},
        {"offset_min": -60,  "label": "Deploy barricades and route closures"},
        {"offset_min": -30,  "label": "All units in position, radio check"},
        {"offset_min": 0,    "label": "Event start — active monitoring"},
        {"offset_min": duration_m, "label": "Begin staged withdrawal"},
    ]

    return {
        "briefing": _build_briefing(
            event, ranked_stations, officers, barricades,
            qrt_recommended, qrt_units, medical_posts,
        ),
        "stations":            ranked_stations,
        "total_officers_min":  officers["total_min"],
        "total_officers_max":  officers["total_max"],
        "barricade_positions": barricades,
        "diversion_routes":    diversions,
        "qrt_recommended":     qrt_recommended,
        "qrt_units":           qrt_units,
        "medical_posts":       medical_posts,
        "surveillance_points": [],
        "vip_protocol":        bool(event.get("has_vip", 0)),
        "timeline":            timeline,
    }


def _build_briefing(
    event: dict,
    stations: list[dict],
    officers: dict,
    barricades: list[str],
    qrt_recommended: bool,
    qrt_units: int,
    medical_posts: int,
) -> str:
    attendance = int(event.get("estimated_attendance") or 0)
    severity   = event.get("severity", "LOW")
    band       = _attendance_band(attendance)
    corridor   = event.get("corridor") or "unspecified corridor"
    evt_type   = event.get("event_type", "event")
    n_stations = len(stations)

    sentences = [
        f"For a {severity} severity {evt_type} on {corridor} with an estimated "
        f"{band} ({attendance:,} attendees),",
        f"deploy {officers['total_min']}–{officers['total_max']} officers "
        f"across {n_stations} station(s).",
    ]

    if stations:
        s1 = stations[0]
        primary = (
            f"Primary response from {s1['station_name']} "
            f"({s1['distance_km']:.1f} km, {s1['officers_allocated']} officers, "
            f"ETA {s1['response_min']} min)"
        )
        if len(stations) >= 2:
            s2 = stations[1]
            primary += (
                f" and {s2['station_name']} "
                f"({s2['distance_km']:.1f} km, {s2['officers_allocated']} officers, "
                f"ETA {s2['response_min']} min)."
            )
        else:
            primary += "."
        sentences.append(primary)

    if barricades:
        sentences.append(f"Position {len(barricades)} barricade(s) at key junctions.")
    if qrt_recommended:
        sentences.append(f"Law and order risk is elevated — {qrt_units} QRT unit(s) on standby.")
    if medical_posts > 0:
        sentences.append(f"Establish {medical_posts} medical post(s) for crowd safety.")
    if event.get("has_vip"):
        sentences.append("VIP protocol active — route pre-clearance required.")

    return " ".join(sentences)
