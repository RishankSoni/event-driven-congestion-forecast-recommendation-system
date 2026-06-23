# pages/6_Station_Registry.py
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
from src.ui import inject_css, page_header, render_mappls_sidebar
from src import station_store
from src.app_cache import load_and_train
import src.mappls_api as mappls_api


st.set_page_config(page_title="Station Registry", layout="wide")
inject_css()
render_mappls_sidebar()

page_header("Station Registry", subtitle="Manage police station capacities and geocoding.")

load_and_train()  # ensures init_station_db() has been called

stations = station_store.get_all_stations()

tab_map, tab_table, tab_geocoding = st.tabs(["Station Map", "Station Table", "Geocoding"])

# ── Tab 1: Map ────────────────────────────────────────────────────────────────
with tab_map:
    _COLOR = {
        "geocoded":               "#28a745",
        "zone_centroid_fallback": "#fd7e14",
        "pending":                "#FF4444",
    }
    mappls_tiles = st.session_state.get("mappls_tiles_enabled", False)
    creds = mappls_api.get_credentials()
    rest_key = creds.get("rest_key")
    if mappls_tiles and rest_key:
        m = folium.Map(location=[12.97, 77.59], zoom_start=11, tiles=None)
        tile_url = f"https://apis.mappls.com/advancedmaps/v1/{rest_key}/still_map/{{z}}/{{x}}/{{y}}.png"
        folium.TileLayer(
            tiles=tile_url,
            attr="© Mappls MapmyIndia",
            name="Mappls MapmyIndia",
            overlay=False,
            control=False
        ).add_to(m)
    else:
        m = folium.Map(location=[12.97, 77.59], zoom_start=11)

    for s in stations:
        if s["latitude"] is None:
            continue
        btp_txt = f" | ✓ BTP ({s['btp_match_confidence']:.2f})" if s["has_btp_pi"] else ""
        cap_txt = f"⚠ Default" if s["capacity_source"] == "default" else "✓ Confirmed"
        popup = (
            f"<b>{s['station_name']}</b><br>"
            f"{s['dcp_zone']}<br>"
            f"Capacity: {s['capacity_officers']} officers, {s['capacity_vehicles']} vehicles "
            f"({cap_txt}){btp_txt}"
        )
        folium.CircleMarker(
            location=[s["latitude"], s["longitude"]],
            radius=6,
            color=_COLOR.get(s["location_source"], "#6c757d"),
            fill=True,
            fill_opacity=0.8,
            popup=folium.Popup(popup, max_width=250),
            tooltip=s["station_name"],
        ).add_to(m)
    st_folium(m, width=900, height=550, returned_objects=[])
    st.caption("🟢 Geocoded &nbsp;&nbsp; 🟠 Zone centroid fallback &nbsp;&nbsp; 🔴 Pending")

# ── Tab 2: Stations Table ─────────────────────────────────────────────────────
with tab_table:
    st.markdown("Edit **capacity_officers** and **capacity_vehicles** then click Save.")

    df = pd.DataFrame(stations)
    display_cols = [
        "station_code", "station_name", "dcp_zone", "acp_zone",
        "location_source", "has_btp_pi", "btp_match_confidence",
        "capacity_officers", "capacity_vehicles", "capacity_source",
    ]
    df_display = df[display_cols].copy()
    df_display["capacity_label"] = df_display["capacity_source"].map(
        {"default": "⚠ Default", "manual": "✓ Confirmed"}
    )
    df_display["btp_label"] = df_display.apply(
        lambda r: f"✓ BTP ({r['btp_match_confidence']:.2f})" if r["has_btp_pi"] else "",
        axis=1,
    )

    edited = st.data_editor(
        df_display,
        use_container_width=True,
        hide_index=True,
        disabled=[
            "station_code", "station_name", "dcp_zone", "acp_zone",
            "location_source", "has_btp_pi", "btp_match_confidence",
            "capacity_source", "capacity_label", "btp_label",
        ],
        column_config={
            "capacity_officers": st.column_config.NumberColumn("Officers", min_value=1, max_value=200),
            "capacity_vehicles": st.column_config.NumberColumn("Vehicles", min_value=0, max_value=50),
        },
    )

    if st.button("💾 Save capacity changes"):
        changed = 0
        for i, row in edited.iterrows():
            orig = df_display.iloc[i]
            if (row["capacity_officers"] != orig["capacity_officers"] or
                    row["capacity_vehicles"] != orig["capacity_vehicles"]):
                station_store.update_station_capacity(
                    int(row["station_code"]),
                    int(row["capacity_officers"]),
                    int(row["capacity_vehicles"]),
                )
                changed += 1
        if changed:
            st.success(f"Saved {changed} station(s).")
            st.rerun()
        else:
            st.info("No changes detected.")

# ── Tab 3: Geocoding ──────────────────────────────────────────────────────────
with tab_geocoding:
    summary = station_store.get_geocode_summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total",    summary["total"])
    c2.metric("Geocoded", summary["geocoded"])
    c3.metric("Fallback", summary["fallback"])
    c4.metric("Pending",  summary["pending"])

    if summary["pending"] == 0 and summary["total"] > 0:
        st.success("All stations have coordinates.")
    else:
        if "geocoding_running" not in st.session_state:
            st.session_state["geocoding_running"] = False

        if not st.session_state["geocoding_running"]:
            st.warning("Geocoding uses Nominatim at 1 request/second. For 110 stations this takes ~2 minutes.")
            if st.button("🌐 Geocode All Stations"):
                st.session_state["geocoding_running"] = True
                st.rerun()
        else:
            progress_bar = st.progress(0.0)
            status_txt   = st.empty()

            def _cb(current, total):
                progress_bar.progress(current / total)
                status_txt.text(f"Geocoding {current}/{total}…")

            result = station_store.geocode_all_stations(progress_callback=_cb)
            st.session_state["geocoding_running"] = False
            st.success(
                f"Done — {result['geocoded']} geocoded, "
                f"{result['fallback']} zone fallbacks, "
                f"{result['pending']} still pending."
            )
            st.rerun()

    st.markdown("**Reset individual station** (sets back to pending for re-geocoding):")
    reset_code = st.number_input("Station code", min_value=1, step=1, value=None)
    if st.button("Reset") and reset_code:
        station_store.reset_station_geocode(int(reset_code))
        st.success(f"Station {reset_code} reset to pending.")
        st.rerun()
