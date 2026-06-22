# tests/test_map_station_overlay.py
import folium
import pandas as pd
from unittest.mock import MagicMock

from src.map_builder import build_map


def _officer_info():
    return {"total_min": 4, "total_max": 6, "primary_min": 2, "primary_max": 4}


def _empty_df():
    return pd.DataFrame({
        "junction": pd.Series([], dtype=str),
        "latitude": pd.Series([], dtype=float),
        "longitude": pd.Series([], dtype=float),
        "corridor": pd.Series([], dtype=str),
        "requires_road_closure": pd.Series([], dtype=bool),
    })


def _call_build_map(**kwargs):
    defaults = dict(
        event_lat=12.97, event_lng=77.59, severity="LOW",
        barricade_junctions=[], diversion_corridors=[],
        officer_info=_officer_info(), train_df=_empty_df(),
        event_name="Test Event", G=MagicMock(),
    )
    defaults.update(kwargs)
    return build_map(**defaults)


def test_build_map_no_stations_renders_only_event_marker():
    m = _call_build_map()
    pin_markers = [c for c in m._children.values() if type(c) is folium.Marker]
    assert len(pin_markers) == 1  # event epicenter only


def test_build_map_station_with_coords_renders_circle_marker():
    stations = [
        {
            "station_code": 1, "station_name": "Cubbon Park PS",
            "latitude": 12.96, "longitude": 77.58,
            "location_source": "geocoded", "dcp_zone": "Central",
        },
    ]
    m = _call_build_map(stations=stations)
    circle_markers = [c for c in m._children.values() if type(c) is folium.CircleMarker]
    assert len(circle_markers) == 1


def test_build_map_station_without_coords_is_skipped():
    stations = [
        {
            "station_code": 2, "station_name": "No Coords PS",
            "latitude": None, "longitude": None,
            "location_source": "pending", "dcp_zone": "North",
        },
    ]
    m = _call_build_map(stations=stations)
    circle_markers = [c for c in m._children.values() if type(c) is folium.CircleMarker]
    assert len(circle_markers) == 0


def test_build_map_ranked_station_renders_as_pin_marker():
    stations = [
        {
            "station_code": 1, "station_name": "Cubbon Park PS",
            "latitude": 12.96, "longitude": 77.58,
            "location_source": "geocoded", "dcp_zone": "Central",
        },
    ]
    ranked = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "distance_km": 1.2, "response_min": 3},
    ]
    m = _call_build_map(stations=stations, ranked_stations=ranked)
    pin_markers = [c for c in m._children.values() if type(c) is folium.Marker]
    # event epicenter + 1 ranked station = 2 pin markers
    assert len(pin_markers) == 2


def test_build_map_ranked_station_not_rendered_as_circle():
    stations = [
        {
            "station_code": 1, "station_name": "Cubbon Park PS",
            "latitude": 12.96, "longitude": 77.58,
            "location_source": "geocoded", "dcp_zone": "Central",
        },
    ]
    ranked = [
        {"station_code": 1, "station_name": "Cubbon Park PS", "distance_km": 1.2, "response_min": 3},
    ]
    m = _call_build_map(stations=stations, ranked_stations=ranked)
    circle_markers = [c for c in m._children.values() if type(c) is folium.CircleMarker]
    assert len(circle_markers) == 0  # ranked station shown as pin, not circle


def test_build_map_existing_call_without_stations_still_works():
    m = _call_build_map()
    assert isinstance(m, folium.Map)


def test_build_map_multiple_stations_mixed_coords():
    stations = [
        {
            "station_code": 1, "station_name": "Station A",
            "latitude": 12.96, "longitude": 77.58,
            "location_source": "geocoded", "dcp_zone": "Central",
        },
        {
            "station_code": 2, "station_name": "Station B",
            "latitude": 12.95, "longitude": 77.57,
            "location_source": "zone_centroid_fallback", "dcp_zone": "East",
        },
        {
            "station_code": 3, "station_name": "No Coords",
            "latitude": None, "longitude": None,
            "location_source": "pending", "dcp_zone": "North",
        },
    ]
    m = _call_build_map(stations=stations)
    circle_markers = [c for c in m._children.values() if type(c) is folium.CircleMarker]
    assert len(circle_markers) == 2  # A and B have coords; C skipped
