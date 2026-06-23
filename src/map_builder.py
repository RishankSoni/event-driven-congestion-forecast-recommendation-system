# src/map_builder.py
from collections import deque

import folium  # type: ignore[import]
import networkx as nx
import pandas as pd
import streamlit as st

import src.road_network as road_network
import src.mappls_api as mappls_api

_SEVERITY_COLOR  = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}
_SEVERITY_RADIUS = {"LOW": 500,     "MEDIUM": 1000,     "HIGH": 2000}


def _junction_centroid(df: pd.DataFrame, junction: str):
    """Return mean (lat, lng) of all historical events at a named junction."""
    sub: pd.DataFrame = df[df["junction"] == junction]
    sub = sub.dropna(subset=["latitude", "longitude"])
    if sub.empty:
        return None
    return (float(sub["latitude"].mean()), float(sub["longitude"].mean()))


def _corridor_centroid(df: pd.DataFrame, corridor: str):
    """Return mean (lat, lng) of all historical events on a corridor."""
    sub: pd.DataFrame = df[df["corridor"] == corridor]
    sub = sub.dropna(subset=["latitude", "longitude"])
    if sub.empty:
        return None
    return (float(sub["latitude"].mean()), float(sub["longitude"].mean()))


def _snap_to_intersection(G: nx.MultiDiGraph | None, lat: float, lng: float) -> tuple:
    """Snap a lat/lng to the nearest road intersection (node degree >= 3) via BFS.

    Walks outward from the nearest node up to 3 hops until a true junction is found.
    Falls back to the original nearest node if no degree-3 node is reachable.
    """
    if G is None:
        return (lat, lng)
    try:
        node_id = road_network.nearest_node(G, lat, lng)
        visited = {node_id}
        queue = deque([(node_id, 0)])
        while queue:
            nid, depth = queue.popleft()
            if G.degree(nid) >= 3:
                return (float(G.nodes[nid]["y"]), float(G.nodes[nid]["x"]))
            if depth < 3:
                neighbors = set(G.successors(nid)) | set(G.predecessors(nid))
                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))
        return (float(G.nodes[node_id]["y"]), float(G.nodes[node_id]["x"]))
    except Exception:
        return (lat, lng)


_DIVERSION_COLORS = ["blue", "cadetblue"]


def build_map(
    event_lat: float,
    event_lng: float,
    severity: str,
    barricade_junctions: list,
    diversion_corridors: list,
    officer_info: dict,
    train_df: pd.DataFrame,
    event_name: str,
    G: nx.MultiDiGraph | None,
    corridor: str = "",
    stations: list | None = None,
    ranked_stations: list | None = None,
) -> folium.Map:
    color  = _SEVERITY_COLOR[severity]
    radius = _SEVERITY_RADIUS[severity]

    # MapmyIndia Mappls Custom Map Tiles Integration
    try:
        mappls_tiles = st.session_state.get("mappls_tiles_enabled", False)
    except Exception:
        mappls_tiles = False
    creds = mappls_api.get_credentials()
    rest_key = creds.get("rest_key")

    if mappls_tiles and rest_key:
        m = folium.Map(location=[event_lat, event_lng], zoom_start=14, tiles=None)
        tile_url = f"https://apis.mappls.com/advancedmaps/v1/{rest_key}/still_map/{{z}}/{{x}}/{{y}}.png"
        folium.TileLayer(
            tiles=tile_url,
            attr="© Mappls MapmyIndia",
            name="Mappls MapmyIndia",
            overlay=False,
            control=False
        ).add_to(m)
    else:
        m = folium.Map(location=[event_lat, event_lng], zoom_start=14)

    all_coords = [[event_lat, event_lng]]

    # Workmate live/simulated officer tracking integration
    try:
        workmate_enabled = st.session_state.get("mappls_workmate_enabled", False)
    except Exception:
        workmate_enabled = False

    if workmate_enabled:
        try:
            officers_list = mappls_api.fetch_workmate_users(event_lat, event_lng)
            for officer in officers_list:
                if officer.get("latitude") is not None and officer.get("longitude") is not None:
                    popup_content = (
                        f"<b>{officer['name']}</b><br>"
                        f"Phone: {officer['phone']}<br>"
                        f"Battery: {officer['battery']}%"
                    )
                    if officer.get("simulated"):
                        popup_content += "<br><i>(Simulated Position)</i>"
                        icon_color = "cadetblue"
                    else:
                        icon_color = "darkblue"
                    
                    folium.Marker(
                        location=[officer["latitude"], officer["longitude"]],
                        popup=folium.Popup(popup_content, max_width=200),
                        tooltip=officer["name"],
                        icon=folium.Icon(color=icon_color, icon="user"),
                    ).add_to(m)
                    all_coords.append([officer["latitude"], officer["longitude"]])
        except Exception as e:
            logger.warning(f"Error drawing Workmate officer markers: {e}")

    # Impact zone
    folium.Circle(
        location=[event_lat, event_lng],
        radius=radius,
        color=color,
        fill=True,
        fill_opacity=0.15,
        popup=f"{severity} impact zone ({radius}m radius)",
    ).add_to(m)


    # Event epicenter marker
    folium.Marker(
        location=[event_lat, event_lng],
        popup=(
            f"{event_name}<br>Severity: {severity}<br>"
            f"Officers: {officer_info['total_min']}-{officer_info['total_max']}"
        ),
        icon=folium.Icon(color=color, icon="info-sign"),
    ).add_to(m)

    # Barricade positions — snapped to real road intersections
    for junction in barricade_junctions:
        centroid = _junction_centroid(train_df, junction)
        if centroid is None:
            continue
        coords = _snap_to_intersection(G, centroid[0], centroid[1])
        folium.Marker(
            location=list(coords),
            popup=f"Barricade: {junction}",
            icon=folium.Icon(color="red", icon="remove-sign"),
        ).add_to(m)
        all_coords.append(list(coords))

    # Diversion routes — road-following alternatives computed by iterative Dijkstra
    if corridor and G is not None:
        diversion_paths = road_network.compute_diversions(G, train_df, corridor)
        for i, path in enumerate(diversion_paths):
            col = _DIVERSION_COLORS[i % len(_DIVERSION_COLORS)]
            label = f"Diversion Route {i + 1}"
            folium.PolyLine(
                locations=path,
                color=col,
                weight=5,
                opacity=0.85,
                tooltip=label,
                popup=f"{label} — road-following alternative around {corridor}",
            ).add_to(m)
            if path:
                folium.Marker(
                    location=list(path[len(path) // 2]),
                    tooltip=label,
                    icon=folium.Icon(color=col, icon="share-alt"),
                ).add_to(m)
            all_coords.extend(path)
    else:
        # Fallback when graph is None or legacy callers: draw diversion corridors as lines
        for div_corridor in diversion_corridors:
            try:
                path = road_network.corridor_route_coords(G, train_df, div_corridor)
                folium.PolyLine(
                    locations=path, color="blue", weight=5, opacity=0.8,
                    tooltip=f"Diversion → {div_corridor}",
                ).add_to(m)
                all_coords.extend(path)
            except Exception:
                pass

    # ── Station overlay ───────────────────────────────────────────────────────
    if stations:
        _SOURCE_COLOR = {
            "geocoded":               "#28a745",
            "zone_centroid_fallback": "#fd7e14",
        }
        _coords = {
            s["station_code"]: (s["latitude"], s["longitude"])
            for s in stations
            if s["latitude"] is not None
        }
        ranked_codes = {s["station_code"] for s in (ranked_stations or [])}

        # Non-ranked stations: circle markers
        for s in stations:
            if s["latitude"] is None or s["station_code"] in ranked_codes:
                continue
            folium.CircleMarker(
                location=[s["latitude"], s["longitude"]],
                radius=5,
                color=_SOURCE_COLOR.get(s["location_source"], "#6c757d"),
                fill=True,
                fill_opacity=0.7,
                popup=folium.Popup(
                    f"<b>{s['station_name']}</b><br>{s['dcp_zone']}<br>{s['location_source']}",
                    max_width=200,
                ),
                tooltip=s["station_name"],
            ).add_to(m)

        # Ranked stations: pin markers rendered on top
        for rank_idx, s in enumerate(ranked_stations or []):
            coords = _coords.get(s["station_code"])
            if coords is None:
                continue
            folium.Marker(
                location=list(coords),
                popup=folium.Popup(
                    f"<b>#{rank_idx + 1} {s['station_name']}</b><br>"
                    f"{s['distance_km']} km | {s['response_min']} min",
                    max_width=200,
                ),
                tooltip=f"#{rank_idx + 1} {s['station_name']}",
                icon=folium.Icon(color="blue", icon="home"),
            ).add_to(m)

    if len(all_coords) > 1:
        m.fit_bounds(all_coords)

    return m
