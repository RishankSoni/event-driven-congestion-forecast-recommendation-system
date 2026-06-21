# tests/test_deployment_planner.py
from src import deployment_planner


def _ev(**overrides):
    base = {
        "event_name": "Test Rally", "event_type": "procession",
        "severity": "MEDIUM", "corridor": "MG Road",
        "estimated_attendance": 1000, "has_vip": 0,
        "law_order_prob": 0.3, "congestion_prob": 0.4,
        "event_date": "2026-07-15", "event_time": "10:00",
        "expected_duration_h": 2.0,
    }
    base.update(overrides)
    return base


def _station(name="Test PS", dist=2.0, alloc=8):
    return {
        "station_name": name, "station_code": 1,
        "dcp_zone": "Central Division, Bangalore City", "acp_zone": "Cubbon Park",
        "distance_km": dist, "workload": 0, "has_btp_pi": 0,
        "btp_match_confidence": None, "capacity_officers": 25, "capacity_vehicles": 3,
        "capacity_source": "default", "score": dist, "response_min": round(dist / 30.0 * 60),
        "officers_allocated": alloc, "allocation_capped": False, "capacity_unconfirmed": True,
    }


def _officers(lo=8, hi=12):
    return {"total_min": lo, "total_max": hi,
            "primary_min": 4, "primary_max": 6, "adjacent_total": 4}


def test_briefing_contains_severity():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH"), [_station()], _officers(), [], []
    )
    assert "HIGH" in plan["briefing"]


def test_briefing_contains_station_name():
    plan = deployment_planner.build_deployment_plan(
        _ev(), [_station(name="Cubbon Park PS")], _officers(), [], []
    )
    assert "Cubbon Park PS" in plan["briefing"]


def test_briefing_qrt_above_threshold():
    plan = deployment_planner.build_deployment_plan(
        _ev(law_order_prob=0.7), [_station()], _officers(), [], []
    )
    assert "QRT" in plan["briefing"]


def test_briefing_no_qrt_below_threshold():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="LOW", law_order_prob=0.2), [_station()], _officers(), [], []
    )
    assert "QRT" not in plan["briefing"]


def test_briefing_medical_large_crowd():
    plan = deployment_planner.build_deployment_plan(
        _ev(estimated_attendance=5000), [_station()], _officers(), [], []
    )
    assert "medical post" in plan["briefing"].lower()


def test_briefing_no_medical_small_crowd():
    plan = deployment_planner.build_deployment_plan(
        _ev(estimated_attendance=200), [_station()], _officers(), [], []
    )
    assert "medical post" not in plan["briefing"].lower()


def test_briefing_vip_protocol():
    plan = deployment_planner.build_deployment_plan(
        _ev(has_vip=1), [_station()], _officers(), [], []
    )
    assert "VIP" in plan["briefing"]


def test_qrt_units_high_severity_large():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH", estimated_attendance=6000, law_order_prob=0.9),
        [_station()], _officers(), [], []
    )
    assert plan["qrt_units"] == 2


def test_qrt_units_high_severity_small():
    plan = deployment_planner.build_deployment_plan(
        _ev(severity="HIGH", estimated_attendance=1000, law_order_prob=0.9),
        [_station()], _officers(), [], []
    )
    assert plan["qrt_units"] == 1


def test_timeline_contains_five_entries():
    plan = deployment_planner.build_deployment_plan(
        _ev(expected_duration_h=3.0), [], _officers(), [], []
    )
    assert len(plan["timeline"]) == 5
    offsets = [t["offset_min"] for t in plan["timeline"]]
    assert -120 in offsets
    assert 0 in offsets
    assert 180 in offsets  # 3h = 180 min


def test_plan_structure_keys():
    plan = deployment_planner.build_deployment_plan(_ev(), [], _officers(), [], [])
    required = {
        "briefing", "stations", "total_officers_min", "total_officers_max",
        "barricade_positions", "diversion_routes", "qrt_recommended", "qrt_units",
        "medical_posts", "surveillance_points", "vip_protocol", "timeline",
    }
    assert set(plan.keys()) == required
