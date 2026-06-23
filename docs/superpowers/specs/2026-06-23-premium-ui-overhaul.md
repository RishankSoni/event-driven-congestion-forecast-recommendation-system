# Premium UI Overhaul — Design Spec

**Date:** 2026-06-23  
**Approach:** Option A — CSS-only deep overhaul via `src/ui.py`  
**Constraint:** Zero changes to business logic, data pipelines, page structure, or navigation. Pure visual enhancement.

---

## 1. Goals

Transform the existing dark-theme Streamlit app into a premium smart-city command-center aesthetic inspired by Linear, Vercel Dashboard, and Palantir Gotham — without touching any functionality.

---

## 2. Color Tokens (CSS Variables injected in `inject_css()`)

```css
--bg-base:    #0B1220;
--bg-card:    #162033;
--bg-card-2:  #1A2740;
--border:     rgba(255,255,255,0.08);
--glow-blue:  rgba(59,130,246,0.15);
--glow-red:   rgba(239,68,68,0.15);
--glow-green: rgba(34,197,94,0.15);
--glow-amber: rgba(245,158,11,0.15);
--text-1:     #F8FAFC;
--text-2:     #94A3B8;
```

Update `.streamlit/config.toml` `backgroundColor` from `#0F172A` to `#0B1220`.

---

## 3. Typography Scale

Injected via `inject_css()`, no font import needed (uses existing system sans-serif):

| Element        | Size     | Weight | Notes                              |
|----------------|----------|--------|------------------------------------|
| Page title     | 2rem     | 700    | `letter-spacing: -0.01em`          |
| Section header | 0.85rem  | 600    | UPPERCASE, `letter-spacing: 0.08em`, left blue bar |
| Card label     | 0.75rem  | 500    | UPPERCASE, `color: var(--text-2)`  |
| Body           | 0.9rem   | 400    | —                                  |

Spacing: 8px grid. Cards: `padding: 20px 24px`. Section gap: `28px`.

---

## 4. Core Components

### 4.1 Glass Cards

Applied via CSS to: `[data-testid="stForm"]`, `[data-testid="stExpander"]`, `.glass-card` class.

```
background:    #162033
backdrop-filter: blur(12px)
border:        1px solid rgba(255,255,255,0.08)
border-radius: 16px
box-shadow:    0 4px 24px rgba(0,0,0,0.4), 0 1px 0 rgba(255,255,255,0.05) inset
hover:         transform translateY(-2px), deeper shadow
transition:    200ms ease-out
```

### 4.2 KPI Metric Cards

CSS applied to `[data-testid="stMetric"]`:

- Colored top-border accent per metric type:
  - F1 / accuracy metrics → blue (`#3B82F6`)
  - AUC / congestion → green (`#22C55E`)
  - HIGH severity counts → red (`#EF4444`)
  - Conflict/warning counts → amber (`#F59E0B`)
- Value font: `1.6rem / 700`
- Subtle background tint: `rgba(accent, 0.06)`
- Border-radius: `14px`

### 4.3 Risk Gauge (replaces `st.progress()`)

`risk_gauge()` in `ui.py` renders a fully custom HTML gradient bar:

```html
<div class="risk-bar-track">
  <div class="risk-bar-fill risk-fill-{level}" style="width:{pct}%"></div>
</div>
```

- LOW:    `#16A34A → #22C55E`, `box-shadow: 0 0 8px rgba(34,197,94,0.4)`
- MEDIUM: `#D97706 → #F59E0B`, amber glow
- HIGH:   `#DC2626 → #EF4444`, red glow + `riskPulse` animation

The label becomes a pill badge with matching glow background.

### 4.4 Severity Badge (enhanced)

- `box-shadow` glow matching color per level
- Padding: `6px 18px`
- `letter-spacing: 0.1em`

### 4.5 Buttons

Primary:
```
background:    linear-gradient(135deg, #3B82F6, #2563EB)
border-radius: 10px
font-weight:   600
hover:         translateY(-1px), box-shadow: 0 4px 14px rgba(59,130,246,0.35)
active:        translateY(0)
```

Secondary/default:
```
background: rgba(255,255,255,0.05)
border:     1px solid rgba(255,255,255,0.1)
hover:      rgba(255,255,255,0.08)
```

### 4.6 Form Inputs

Applied to `stTextInput`, `stSelectbox`, `stNumberInput`, `stTextArea`:
```
height (via padding): 44px effective
border-radius: 10px
background:    rgba(255,255,255,0.04)
border:        1px solid rgba(255,255,255,0.08)
focus:         border-color: #3B82F6
               box-shadow: 0 0 0 3px rgba(59,130,246,0.18)
```

### 4.7 Tables

Applied to `[data-testid="stDataFrame"]` and `[data-testid="stTable"]`:
- Zebra rows: odd rows `rgba(255,255,255,0.02)`
- Hover row: `rgba(59,130,246,0.06)`
- Sticky header
- Header cells: `0.7rem / uppercase / letter-spacing: 0.06em / color: var(--text-2)`
- Container: `border-radius: 12px`, `overflow: hidden`

### 4.8 AI Insight Card (new `ui.py` helper)

New function `ai_insight_card(text: str)`:
```
border-left:  3px solid #3B82F6
background:   rgba(59,130,246,0.06)
border-radius: 0 12px 12px 0
padding:      14px 18px
font-style:   italic
color:        var(--text-2)
```

Used on Results page to wrap the operational briefing/SHAP summary.

---

## 5. Sidebar

Pure CSS enhancement (no structural changes):

```
background:   rgba(15,23,42,0.85)
backdrop-filter: blur(20px)
border-right: 1px solid rgba(255,255,255,0.06)
```

Active nav item:
```
border-left:  3px solid #3B82F6
background:   rgba(59,130,246,0.10)
color tint:   #93C5FD
```

Nav label hover:
```
background:   rgba(255,255,255,0.04)
transition:   150ms ease-out
```

---

## 6. Page-Specific Treatments

### Page 1 — Plan Event
- Form columns wrapped in glass card styling (auto via CSS on `stForm`)
- Section headers upgraded to new uppercase style
- Radio buttons (`event_type`, `route_fmt`) get pill-toggle CSS: `[data-testid="stRadio"] label` gets `border-radius: 99px`, `padding: 6px 16px`, background tint on hover, and the selected option gets `background: rgba(59,130,246,0.15)` + blue text

### Page 2 — Results
- Left column becomes glass card
- Risk gauges use new gradient bars
- Severity badge gets glow
- SHAP `▲` arrows: `color: #22C55E`, `▼` arrows: `color: #EF4444`
- Map container gets `border-radius: 16px` + `overflow: hidden` card wrap

### Page 7 — Deployment Plan
- `st.info()` briefing becomes blue-tinted premium alert
- Station/timeline tables get full table treatment
- Metric cards get colored top-border accents

### Page 8 — Command Dashboard
- 4 KPI cards get colored accents: Events=blue, HIGH=red, Conflicts=amber, Geocoded=green
- Conflict warnings get red-glowing alert style

### Pages 5, 6, 9 — Repository, Registry, Optimizer
- All tables get full premium table treatment
- Expanders get glass card style

### Page 4 — Calendar
- Calendar container gets `border-radius: 16px` glass card wrap
- Event pills: severity-matched colors + `border-radius: 99px`

---

## 7. Micro-interactions & Animations

All injected as `@keyframes` in `inject_css()`. No JavaScript.

| Animation      | Trigger           | Duration    | Effect                              |
|----------------|-------------------|-------------|-------------------------------------|
| `fadeInUp`     | Page load         | 400ms       | Content fades up from 12px below    |
| `riskPulse`    | HIGH risk gauge   | 2s infinite | Red glow pulses in/out              |
| `fillBar`      | Risk bar render   | 600ms       | Bar fills from 0% to final width    |
| Hover lift     | Card/metric hover | 200ms       | `translateY(-2px)` + deeper shadow  |
| Button press   | Button `:active`  | instant     | `translateY(0)` cancels hover lift  |
| Sidebar hover  | Nav item hover    | 150ms       | Subtle bg highlight + left border   |

`fadeInUp` applied to `.main .block-container`. All transitions use `ease-out`.

No scroll-triggered animations, no JS observers, no skeleton loaders.

---

## 8. Files Changed

| File                         | Change type           |
|------------------------------|-----------------------|
| `src/ui.py`                  | Major CSS expansion + new `ai_insight_card()` helper |
| `.streamlit/config.toml`     | `backgroundColor` updated to `#0B1220` |
| `pages/2_Results.py`         | Call `ai_insight_card()` for briefing, SHAP arrow colors |
| `pages/8_Command_Dashboard.py` | KPI card color hints via CSS classes |

All other pages inherit improvements automatically via `inject_css()`. No changes to any business logic, models, or data stores.

---

## 9. Constraints

- No new Python dependencies
- No JavaScript injection
- No changes to any page's logic, routing, or data flow
- All CSS via `st.markdown(..., unsafe_allow_html=True)` in `inject_css()`
- CSS selectors target Streamlit's `data-testid` attributes and class names — documented to be stable within minor versions
- Glassmorphism `backdrop-filter` degrades gracefully in unsupported browsers (falls back to solid bg)
