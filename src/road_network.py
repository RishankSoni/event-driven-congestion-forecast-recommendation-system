# src/road_network.py
import math
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

# Bounding box for Bengaluru event data + ~0.03° buffer.
# OSMnx 2.x format: (west, south, east, north) = (min_lng, min_lat, max_lng, max_lat)
_BBOX = (77.28, 12.78, 77.80, 13.30)


def load_graph(cache_path: Path) -> nx.MultiDiGraph | None:
    """Load Bengaluru drive graph from GraphML cache.

    If the cache file is missing on disk, this function logs a warning and returns None
    to prevent downloading a massive 266MB city graph dynamically during deployment.
    """
    if cache_path.exists():
        try:
            return ox.load_graphml(cache_path)
        except Exception as e:
            logger.warning(f"Failed to load GraphML cache: {e}")
            return None
    
    # Try finding the file in a sibling directory or fallback location
    alt_paths = [
        Path("data") / cache_path.name,
        Path("../data") / cache_path.name
    ]
    for alt_path in alt_paths:
        if alt_path.exists():
            try:
                return ox.load_graphml(alt_path)
            except Exception:
                pass
                
    logger.warning(f"GraphML cache file not found at {cache_path}. Falling back to straight line / coordinate mapping.")
    return None


def nearest_node(G: nx.MultiDiGraph | None, lat: float, lng: float) -> int:
    """Snap a lat/lng coordinate to the nearest OSM node in G.

    OSMnx convention: X=longitude, Y=latitude.
    """
    if G is None:
        raise ValueError("Cannot snap to node: road network graph is not loaded.")
    return int(ox.distance.nearest_nodes(G, X=lng, Y=lat))


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def route_coords(G: nx.MultiDiGraph | None, orig_node: int, dest_node: int) -> list:
    """Return road-following (lat, lng) waypoints between two OSM node IDs via Dijkstra."""
    if G is None:
        return []
    node_ids = nx.shortest_path(G, orig_node, dest_node, weight="length")
    return [(float(G.nodes[n]["y"]), float(G.nodes[n]["x"])) for n in node_ids]


def _path_length(G: nx.MultiDiGraph, nodes: list) -> float:
    """Sum of minimum-length edge weights along a node sequence."""
    return sum(
        min(G[u][v][k].get("length", 1) for k in G[u][v])
        for u, v in zip(nodes[:-1], nodes[1:])
    )


def compute_diversions(
    G: nx.MultiDiGraph | None,
    df: pd.DataFrame,
    corridor: str,
    n_routes: int = 2,
    max_ratio: float = 1.8,
) -> list:
    """Return up to n_routes road-following diversion paths around a blocked corridor.

    Algorithm: iterative edge-penalty Dijkstra (Yen-style).
      1. Find the primary Dijkstra path (shortest route) between the corridor's
         geographic endpoints to establish the baseline length.
      2. Inflate all primary-path edges to weight 1e9 in-place, re-run Dijkstra
         to force a genuinely different road-following alternative.
      3. Restore original weights, record the alternative if its true length
         is within max_ratio of the primary.
      4. Repeat, accumulating blocked edges, to find a second route.

    Thread-safety note: edge weights are temporarily modified on the shared cached
    graph and immediately restored. Safe for single-user deployments.
    """
    if G is None:
        return []
    try:
        primary_coords = corridor_route_coords(G, df, corridor)
    except (ValueError, nx.NetworkXNoPath, nx.NodeNotFound, Exception):
        return []

    if len(primary_coords) < 2:
        return []

    start_node = nearest_node(G, primary_coords[0][0], primary_coords[0][1])
    end_node   = nearest_node(G, primary_coords[-1][0], primary_coords[-1][1])
    if start_node == end_node:
        return []

    try:
        primary_nodes = nx.dijkstra_path(G, start_node, end_node, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

    primary_len = _path_length(G, primary_nodes)
    if not primary_len:
        return []

    # Cumulative set of (u, v) edge pairs to avoid across iterations
    all_blocked: set = set(zip(primary_nodes[:-1], primary_nodes[1:]))
    routes: list = []

    for _ in range(n_routes):
        # Inflate blocked edges in-place; save originals for restore
        saved: dict = {}
        for u, v in all_blocked:
            if not G.has_edge(u, v):
                continue
            for key in list(G[u][v].keys()):
                saved[(u, v, key)] = G[u][v][key].get("length", 1)
                G[u][v][key]["length"] = 1e9

        try:
            alt_nodes = nx.dijkstra_path(G, start_node, end_node, weight="length")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            for (u, v, key), orig in saved.items():
                G[u][v][key]["length"] = orig
            break

        # Restore before measuring so _path_length uses real weights
        for (u, v, key), orig in saved.items():
            G[u][v][key]["length"] = orig

        alt_len = _path_length(G, alt_nodes)
        if alt_len > primary_len * max_ratio:
            break

        routes.append([
            (float(G.nodes[n]["y"]), float(G.nodes[n]["x"])) for n in alt_nodes
        ])
        all_blocked.update(zip(alt_nodes[:-1], alt_nodes[1:]))

    return routes


def corridor_route_coords(G: nx.MultiDiGraph | None, df: pd.DataFrame, corridor: str) -> list:
    """Return road-following waypoints along the full length of a named corridor.

    Finds the two most geographically distant historical events on the corridor,
    snaps both to OSM nodes, and returns the Dijkstra shortest path between them.
    """
    sub = (
        df[df["corridor"] == corridor]
        .dropna(subset=["latitude", "longitude"])
        .reset_index(drop=True)
    )
    if sub.empty:
        raise ValueError(f"No data for corridor '{corridor}'")
    if len(sub) > 50:
        sub = sub.sample(50, random_state=42).reset_index(drop=True)

    # Find the two most geographically distant rows (corridor start and end)
    max_dist, i_max, j_max = -1.0, 0, min(1, len(sub) - 1)
    for i in range(len(sub)):
        for j in range(i + 1, len(sub)):
            d = _haversine_km(
                float(sub.loc[i, "latitude"]), float(sub.loc[i, "longitude"]),
                float(sub.loc[j, "latitude"]), float(sub.loc[j, "longitude"]),
            )
            if d > max_dist:
                max_dist, i_max, j_max = d, i, j

    if G is None:
        # Fallback: Sort events by their coordinates to approximate the path
        sub_sorted = sub.sort_values(by=["latitude", "longitude"])
        return list(zip(sub_sorted["latitude"].astype(float), sub_sorted["longitude"].astype(float)))

    start_node = nearest_node(G, float(sub.loc[i_max, "latitude"]), float(sub.loc[i_max, "longitude"]))
    end_node   = nearest_node(G, float(sub.loc[j_max, "latitude"]), float(sub.loc[j_max, "longitude"]))
    return route_coords(G, start_node, end_node)
