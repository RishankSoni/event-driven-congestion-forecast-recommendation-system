# Senior Technical Review — GRIDLOCK 2.0 Demo

**Date:** 2026-06-22  
**Core Metrics:** Deployment Completeness · Operational Coverage · Planner Efficiency · Demo Narrative Score

---

## PRIORITY 1 — Demo-Breaking Risks

These will visibly fail in front of judges with no graceful recovery.

---

### [P1-A] Model cold-start takes 30–60s and happens on the first page load

**What breaks:** `load_and_train()` in `app_cache.py` runs the full pipeline — load CSV, baseline computation, tertile thresholds, LightGBM train, CV eval, test eval, SHAP explainer build, road graph load. This blocks the UI. If a judge walks up during this spinner, the "Planner Efficiency" narrative is dead before it starts.

**Reasoning:** The cache (`@st.cache_data`, `@st.cache_resource`) persists across reruns *within the same server process*. If the demo machine reboots, network drops, or Streamlit restarts, the cold path re-runs.

**Fix:** Warm the cache *before* judges arrive. Open the app, submit a test prediction end-to-end, confirm results load. Keep the browser tab open. Do not restart Streamlit during the demo.

---

### [P1-B] `data/events.csv` and `data/bengaluru_drive.graphml` are not committed — missing files crash the entire app

**What breaks:** `load_raw()` will raise `FileNotFoundError` if `data/events.csv` is absent. `get_road_graph()` fails similarly for the road network file. The app shows a raw Python traceback. No graceful fallback exists.

**Reasoning:** Both files are in `.gitignore` or simply not in the repo tree. They must be manually placed on the demo machine.

**Fix:** Pre-demo checklist — confirm both files exist at `data/events.csv` and `data/bengaluru_drive.graphml` before opening the browser. Pin exact filenames.

---

### [P1-C] Command Dashboard (page 8) is empty on a fresh environment

**What breaks:** `ops_store.get_today_events()` queries `data/events.db` for today's date. If no events have been saved with today's date, the page shows "No events planned for today." The "Operational Coverage" metric has nothing to display.

**Reasoning:** The SQLite DB is created on first `init_db()` call but starts empty. The demo flow in the README stops at "Export CSV" — it never saves an event to the calendar, so the Command Dashboard page is never populated.

**Fix:** Save 2–3 events with today's date before the demo. One HIGH severity on a busy corridor, one MEDIUM. This also lets you demonstrate the conflict detection row in the dashboard.

---

### [P1-D] Deployment Plan (page 7) is only reachable if "Recommended Stations" section has geocoded data

**What breaks:** The "View Full Deployment Plan →" link only appears inside the Recommended Stations block. If `station_store.rank_stations()` returns an empty list (because geocoding hasn't been run via Station Registry), that link never renders. Page 7 is the richest deliverable — Operational Briefing, Timeline, QRT units, Medical posts, VIP Protocol — and judges won't see it.

**Reasoning:** `pages/2_Results.py:177` — the link to page 7 is skipped entirely when the station list is empty.

**Fix:** Pre-geocode stations from the Station Registry page before the demo. Alternatively, add a direct page link to page 7 unconditionally (below the station table, not inside the empty-state branch).

---

## PRIORITY 2 — Significant Risk / User Experience Damage

These won't crash the app but will confuse judges or expose gaps in the narrative.

---

### [P2-A] Demo narrative ends too early — 3 of the 4 pages that prove your metrics are not in the script

**What breaks:** The README demo stops at step 8 ("Export Plan CSV"). It never shows:
- Saving to the Event Calendar (closes the "deployment completeness" loop)
- The Deployment Plan page (the most operator-ready artifact — briefing, timeline, QRT, medical)
- The Command Dashboard (the "operational coverage" proof)
- The Multi-Event Optimizer (the unique differentiator when two events overlap)

**Reasoning:** Judges evaluate the narrative they're walked through, not the pages they could theoretically click. If the script ends at a CSV download, the score is capped at "basic prediction tool."

**Fix:** Extend the demo script to a 12-step narrative:
1. Enter event → Predict
2. Read severity + duration forecast
3. Read risk bars (congestion / law & order)
4. Read action plan (officers / barricades / diversions)
5. Show map
6. Show SHAP "Why HIGH?" — 2 sentences of narration
7. Show 5 similar past events
8. Click "View Full Deployment Plan →" → show page 7 (briefing + timeline)
9. Export deployment CSV
10. Go back → "Save to Event Calendar"
11. Open Command Dashboard → show today's events + conflict detection
12. Open Multi-Event Optimizer → pick 2 events → show combined assignment

---

### [P2-B] CBD 2 corridor may have zero barricades and zero diversions

**What breaks:** `barricade_positions()` (`src/recommender.py`) queries historical events on the given corridor where `requires_road_closure == True`. If CBD 2 has few or no such events, it returns `[]`. `get_diversions()` depends on the co-elevation graph — same issue. The Results page would show "0 position(s)" and "0 route(s)." This directly undermines the Deployment Completeness metric.

**Reasoning:** The demo example in both the README and the original spec uses CBD 2. Whether CBD 2 is data-rich depends entirely on the GRIDLOCK CSV. This hasn't been verified in any test.

**Fix:** Before fixing the demo script, run:
```bash
python -c "from src.pipeline import load_raw; df = load_raw(); print(df[df.corridor=='CBD 2'].shape, df[df.corridor=='CBD 2'].requires_road_closure.sum())"
```
If CBD 2 is thin, pick a different corridor for the demo that has rich barricade + diversion history.

---

### [P2-C] Folium map renders blank or throws a JS error in certain browser environments

**What breaks:** `st_folium` embeds an iframe. Corporate/locked-down browsers (or browsers with aggressive CSP) block external tile requests (OpenStreetMap). The map appears as a grey box.

**Reasoning:** This is a known Streamlit-Folium limitation in restricted network environments. Hackathon venues often have filtered WiFi.

**Fix:** Test the map on the actual demo machine on the demo network *before* the presentation. If tiles don't load, switch to `folium.TileLayer('CartoDB positron')` which has better CDN fallback, or pre-cache tiles.

---

### [P2-D] Model spec says GradientBoostingClassifier; implementation uses LightGBM — judges may probe this

**What breaks:** Not a crash, but a credibility gap. The design spec (`2026-06-16-event-driven-congestion-design.md`) specifies `GradientBoostingClassifier (scikit-learn)`. The implementation (`src/model.py`) uses `LGBMClassifier`. If a judge reads the spec and asks "why LightGBM?", an unprepared presenter stumbles.

**Fix:** Prepare a one-sentence answer: "We upgraded from sklearn GBT to LightGBM after the window sweep — it handles the categorical corridor encoding natively and trains 4× faster, which matters for the cache warm-up." Or update the spec. Either way, close the gap.

---

### [P2-E] `junction` is hardcoded to `"unknown"` — the model and barricade logic are flying blind on location

**What breaks:** `features["junction"] = "unknown"` in `pages/1_Plan_Event.py:152`. The junction field is a `CAT_COLS` feature for the LightGBM model and is also used by `barricade_positions()` to score which junctions need barricades. With "unknown" always passed, the model loses a signal and barricade selection degrades to corridor-level fallback only.

**Fix (quick):** For the demo, pre-select the corridor most associated with a known high-frequency junction and brief the presenter to note: "in production, the junction field would be auto-populated from a GIS lookup."

---

### [P2-F] "Event type" radio is outside the form — causes confusing UX

**What breaks:** `st.radio("Event type", ...)` on line 44 of `1_Plan_Event.py` is before `with st.form("event_form"):`. Elements outside a form update state immediately; elements inside only update on submit. If a judge switches "Planned → Unplanned" after filling the form, the conditional sections change before submit — visually jarring during a live demo.

**Fix:** Move the radio inside the form, or brief the presenter to set event type first before filling other fields.

---

## PRIORITY 3 — Friction and Polish

---

### [P3-A] Sidebar shows raw ML metrics immediately — judges see numbers without context

The sidebar on page 1 displays `CV macro-F1 (train): 0.637` and `Test macro-F1: X.XXX` with a caption "Baseline (majority class): ~0.22 on 3-class problem." Without narration, a judge may see "0.637" and not know whether that's good or bad.

**Fix:** Add a brief label ("3× better than chance") or save the sidebar reveal for after the prediction, when the judge is in the context of the results page.

---

### [P3-B] Results page is too dense — critical outputs compete for attention during a live scroll

The left column of page 2 has 7 distinct sections stacked vertically: severity, duration, risk bars, action plan, recommended stations, SHAP explainability, similar events. Presenters will scroll past sections before judges can read them.

**Fix:** Collapse the SHAP section to an expander by default (it currently expands inline) and move the similar-events table into an expander. This keeps the scroll path tight: severity → map → action plan → deployment plan link.

---

### [P3-C] "Save to Event Calendar" button is below the fold, easy to miss

The save functionality is at the very bottom of the results page, after the export button and Post-Event Report link. Presenters often stop at "Export Plan (CSV)" and miss it — which means the Command Dashboard stays empty.

**Fix:** Move the save button above the export button, or add a "💾 Save to Calendar" button near the top of the results page.

---

### [P3-D] Multi-Event Optimizer requires pre-saved events with today's date — hidden prerequisite

Page 9 filters by selected date. If events were saved with a different date than what the optimizer shows, it displays "No saved events." This is non-obvious.

**Fix:** When saving demo events, ensure `event_date` matches the date you will select in the optimizer. Use a consistent demo date throughout (e.g., today's date, set before the demo starts).

---

## 3 Critical Questions — Must Answer Before Moving Forward

**Q1: Is CBD 2 the right corridor for the demo?**

Run the data check in [P2-B] right now. If CBD 2 has fewer than 5 barricade events in the training set, the deployment plan will look empty. Pick the corridor where the system produces the most compelling output — not the corridor that appeared in the original spec example.

**Q2: What does your demo environment look like — fresh machine or pre-warmed?**

Specifically: will the Streamlit server be restarted between runs? Will the SQLite database be pre-populated? Will station geocoding already be done? These three answers determine which P1 issues will actually fire during the demo. You need a pre-demo checklist and a dry run on the exact machine, network, and browser you'll use in front of judges.

**Q3: What is the demo time budget, and which pages are you committing to showing?**

The full 12-step narrative in [P2-A] is the right one but takes 4–6 minutes with narration. If you have 3 minutes, the minimum viable narrative that hits all four metrics is: **Plan → Predict → Deployment Plan page (p7) → Save → Command Dashboard (p8)**. Multi-Event Optimizer (p9) is the "wow" ending if you have time. Decide this now and rehearse to time.
