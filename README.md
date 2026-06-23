# Event-Driven Congestion Forecast & Recommendation System

**GRIDLOCK 2.0 — Theme 2 Hackathon Demo**

Predicts traffic impact severity for upcoming events and auto-generates a concrete deployment plan — before the event happens. Built on historical GRIDLOCK Bengaluru incident data, now enriched with live weather, MapmyIndia (Mappls) custom maps, and Mappls Workmate workforce automation.

---

## What It Does

Given an upcoming event (type, location, date/time), the system:

1. **Forecasts severity** — LOW / MEDIUM / HIGH — using a Gradient Boosted classifier trained on historical incident patterns
2. **Generates a deployment plan** — officer count, barricade positions, and diversion routes
3. **Renders Interactive Maps** — supports OpenStreetMap (Default) and premium MapmyIndia (Mappls) tiles, displaying the event impact zone, barricades, diversion routes, and live/simulated Workmate officer tracking pins
4. **Dispatches Tasks to Workmate** — publishes patrol tasks and barricade instructions directly to the Mappls Workmate system
5. **Surfaces evidence** — 5 most similar past events with their actual outcomes

---

## Setup & Credentials

**Prerequisites:** Python 3.10+

```bash
pip install -r requirements.txt
```

**Data:** Copy the GRIDLOCK CSV into `data/events.csv`:
```
data/events.csv   ← Astram event data_anonymized.csv
```

### MapmyIndia (Mappls) Credentials Configuration

To enable MapmyIndia (Mappls) maps, geocoding search, and Workmate workforce management, you must provide your developer keys. You can do this in three ways:

1. **Streamlit Secrets (Recommended)**: Create or edit `.streamlit/secrets.toml` with:
   ```toml
   [mappls]
   client_id = "YOUR_MAPPLS_CLIENT_ID"
   client_secret = "YOUR_MAPPLS_CLIENT_SECRET"
   rest_key = "YOUR_MAPPLS_REST_KEY"
   ```
2. **Environment Variables**: Export variables in your terminal shell:
   ```bash
   export MAPPLS_CLIENT_ID="your_client_id"
   export MAPPLS_CLIENT_SECRET="your_client_secret"
   export MAPPLS_REST_KEY="your_rest_key"
   ```
3. **UI Sidebar**: Paste them directly on-the-fly under the **MapmyIndia (Mappls)** sidebar settings panel.

*Note: If credentials are not configured or are invalid, the app runs in **Simulation Mode** (fully functional mock data, simulated officers, and simulated task dispatches) so you can still test all features.*

---

## Run

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. First load trains the model (~30–60s, cached afterwards).

---

## Mappls & Workmate Integration Architecture

### 1. Visual Tile Rendering
When **Enable Mappls Map Tiles** is active and your REST API Key is configured, the application dynamically swaps out OpenStreetMap and renders Leaflet maps overlayed with MapmyIndia's premium vector still maps using:
`https://apis.mappls.com/advancedmaps/v1/{rest_key}/still_map/{z}/{x}/{y}.png`

### 2. Search Geocoding Cascade
When **Enable Mappls Geocoding** is active, the Station Registry geocoder queries the Mappls search address endpoint:
`https://search.mappls.com/search/address/geocode`
If Mappls geocoding fails or is disabled, the system automatically falls back to Nominatim to ensure zero-downtime geocoding of police stations.

### 3. Workmate Task Dispatcher & Tracking
- **Workforce tracking**: Fetches active field force employees from Mappls Workmate (`GET /users`) and overlays their current pins on the Results impact map.
- **Action plan publishing**: Integrates a dispatch controller in the results screen that packages the primary corridor patrols and barricade placements as active Workmate tasks (`POST /tasks`) assigned to field officers.

---

## Demo Flow

1. Open the app — **Event Input** screen loads.
2. In the sidebar, expand the **MapmyIndia (Mappls)** panel. Verify that the toggles are active and status shows connected.
3. Enter event details: `Public Rally · public_event · ORR North 1 · requires road closure · Monday 18:00`.
4. Click **Predict Impact**.
5. Results screen shows **HIGH** severity badge + confidence %.
6. Map shows MapmyIndia tile layer, barricade placements, diversions, and active patrol officer user pins.
7. Under the map, review the **Workmate Dispatch** dashboard and click **Dispatch Tasks to Workmate** to publish assignments to your field force.
8. Click **View Full Deployment Plan** to download timeline spreadsheets and review resource summaries.

---

## Tests

Run the full project test suite:
```bash
pytest tests/ -v
```

Or run only the MapmyIndia Mappls integrations test suite:
```bash
pytest tests/test_mappls.py -v
```

Our test suite includes verification of:
* **Token Caching**: OAuth access tokens are cached in-memory and only requested when expired.
* **Geocoding Strategies**: Verifies Mappls search endpoints are queried first and fall back correctly.
* **Simulation Modes**: Ensures mock officers and mock tasks are safely generated if live credentials are not set.

---

## File Map

```
app.py                    Streamlit entry point
src/
  pipeline.py             load_raw(), split_data(), corridor_metadata()
  baseline.py             window counts, excess scores, severity labeling
  model.py                GBT classifier, CV/test evaluation, KNN evidence
  recommender.py          officer counts, barricades, diversion graph
  map_builder.py          Folium map with impact zone + markers + Mappls layer
  mappls_api.py           OAuth token generation, search geocoding, Workmate API client
  ui.py                   Streamlit UI styles, KPI cards, and Mappls configuration sidebar
tests/
  conftest.py             shared sample_df fixture
  test_pipeline.py
  test_baseline.py
  test_model.py
  test_recommender.py
  test_map_builder.py
  test_integration.py
  test_mappls.py          Unit tests for MapmyIndia and Workmate features
data/
  events.csv              GRIDLOCK Bengaluru incident data (not committed)
  bengaluru_drive.graphml GraphML topology of road network for routing
```

---

## Stack

| Library | Version | Purpose |
|---|---|---|
| streamlit | ≥1.32 | Web dashboard |
| folium | ≥0.16 | Interactive map |
| streamlit-folium | ≥0.20 | Folium ↔ Streamlit bridge |
| scikit-learn | ≥1.4 | GBT classifier, OrdinalEncoder, KNN |
| pandas | ≥2.1 | Data pipeline |
| numpy | ≥1.26 | Numerical operations |
| pytest | ≥8.0 | Test suite |
| requests | ≥2.31 | Mappls REST API requests |
| toml | ≥0.10 | Read secrets configuration |
| geopy | ≥2.4 | Nominatim geocoding fallback |
