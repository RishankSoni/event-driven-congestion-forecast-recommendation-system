# src/map_builder.py
import folium  # type: ignore[import]
import pandas as pd

_SEVERITY_COLOR  = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}
_SEVERITY_RADIUS = {"LOW": 500,     "MEDIUM": 1000,     "HIGH": 2000}


def _junction_coords(df: pd.DataFrame, junction: str):
    sub: pd.DataFrame = df[df["junction"] == junction]  # type: ignore[assignment]
    sub = sub.dropna(subset=["latitude", "longitude"])  # type: ignore[assignment]
    if sub.empty:
        return None
    return (float(sub["latitude"].mean()), float(sub["longitude"].mean()))  # type: ignore[arg-type]


def _corridor_centroid(df: pd.DataFrame, corridor: str):
    sub: pd.DataFrame = df[df["corridor"] == corridor]  # type: ignore[assignment]
    sub = sub.dropna(subset=["latitude", "longitude"])  # type: ignore[assignment]
    if sub.empty:
        return None
    return (float(sub["latitude"].mean()), float(sub["longitude"].mean()))  # type: ignore[arg-type]


def _corridor_path(df: pd.DataFrame, corridor: str) -> list:
    """Return deduplicated lat/lng waypoints along the corridor, sorted by principal axis."""
    sub = df[df["corridor"] == corridor].dropna(subset=["latitude", "longitude"])
    if sub.empty:
        return []
    # Bin to ~100 m grid to remove duplicate hotspot clusters
    binned = sub.copy()
    binned["_lat"] = (binned["latitude"] * 1000).round() / 1000
    binned["_lng"] = (binned["longitude"] * 1000).round() / 1000
    dedup = binned.drop_duplicates(subset=["_lat", "_lng"])
    # Sort along whichever axis has more spread so the polyline follows the road
    sort_col = "_longitude" if (dedup["_lng"].max() - dedup["_lng"].min()) >= (dedup["_lat"].max() - dedup["_lat"].min()) else "_lat"
    dedup = dedup.sort_values("_lng" if sort_col == "_longitude" else "_lat")
    return [[float(r["_lat"]), float(r["_lng"])] for _, r in dedup.iterrows()]


def build_map(
    event_lat: float,
    event_lng: float,
    severity: str,
    barricade_junctions: list,
    diversion_corridors: list,
    officer_info: dict,
    train_df: pd.DataFrame,
    event_name: str = "Event",
) -> folium.Map:
    color  = _SEVERITY_COLOR[severity]
    radius = _SEVERITY_RADIUS[severity]

    m = folium.Map(location=[event_lat, event_lng], zoom_start=14)
    all_coords = [[event_lat, event_lng]]  # collected for fit_bounds

    # Impact zone
    folium.Circle(
        location=[event_lat, event_lng],
        radius=radius,
        color=color,
        fill=True,
        fill_opacity=0.15,
        popup=f"{severity} impact zone ({radius}m radius)",
    ).add_to(m)

    # Event epicenter
    folium.Marker(
        location=[event_lat, event_lng],
        popup=f"{event_name}<br>Severity: {severity}<br>"
              f"Officers: {officer_info['total_min']}-{officer_info['total_max']}",
        icon=folium.Icon(color=color, icon="info-sign"),
    ).add_to(m)

    # Barricade positions
    for junction in barricade_junctions:
        coords = _junction_coords(train_df, junction)
        if coords:
            folium.Marker(
                location=list(coords),
                popup=f"Barricade: {junction}",
                icon=folium.Icon(color="red", icon="remove-sign"),
            ).add_to(m)
            all_coords.append(list(coords))

    # Diversion routes — actual corridor path from historical event locations
    for corridor in diversion_corridors:
        path = _corridor_path(train_df, corridor)
        if not path:
            continue
        folium.PolyLine(
            locations=path,
            color="blue",
            weight=5,
            opacity=0.8,
            tooltip=f"Diversion → {corridor}",
            popup=f"Divert via: {corridor}",
        ).add_to(m)
        # Label marker at corridor centroid
        centroid = _corridor_centroid(train_df, corridor)
        if centroid:
            folium.Marker(
                location=list(centroid),
                tooltip=f"Diversion → {corridor}",
                popup=f"Diversion route: {corridor}",
                icon=folium.Icon(color="blue", icon="share-alt"),
            ).add_to(m)
            all_coords.extend(path)

    # Fit map to include all markers and corridor paths
    if len(all_coords) > 1:
        m.fit_bounds(all_coords)

    return m
