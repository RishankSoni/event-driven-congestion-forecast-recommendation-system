"""
Stress test: submit 4 planned events via Playwright, screenshot each Results page.
Run while Streamlit is already running on http://localhost:8501.
"""

import re
import time
import pathlib
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

SCREENSHOT_DIR = pathlib.Path(r"C:\Users\HP\OneDrive\Pictures\Screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
APP_URL = "http://localhost:8501"

EVENTS = [
    {
        "name": "VIP State Visit – Bellary Road",
        "cause": "vip_movement",
        "corridor": "Bellary Road 1",
        "priority": "High",
        "date": "2026/07/04",
        "time_str": "09:00 AM",
        "attendance": 500,
        "vip": True,
        "road_closure": True,
        "route_based": False,
        "slug": "01_vip_bellary",
    },
    {
        "name": "Independence Day Public Rally",
        "cause": "public_event",
        "corridor": "CBD 1",
        "priority": "High",
        "date": "2026/08/15",
        "time_str": "06:00 PM",
        "attendance": 8000,
        "vip": False,
        "road_closure": False,
        "route_based": False,
        "slug": "02_rally_cbd",
    },
    {
        "name": "Bengaluru Marathon 2026",
        "cause": "procession",
        "corridor": "ORR East 1",
        "priority": "High",
        "date": "2026/10/18",
        "time_str": "06:00 AM",
        "attendance": 15000,
        "vip": False,
        "road_closure": True,
        "route_based": True,
        "start_checkpoint": "Silk Board",
        "end_checkpoint": "KR Puram",
        "stops": "Whitefield, Marathahalli",
        "slug": "03_marathon_orr",
    },
    {
        "name": "Mysore Road Metro Diversion",
        "cause": "construction",
        "corridor": "Mysore Road",
        "priority": "High",
        "date": "2026/09/01",
        "time_str": "10:00 AM",
        "attendance": 0,
        "vip": False,
        "road_closure": True,
        "route_based": False,
        "slug": "04_construction_mysore",
    },
]


def dismiss_any_popup(page) -> None:
    """Close calendar / dropdown popups by pressing Escape."""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except Exception:
        pass


def pick_selectbox(page, label: str, value: str) -> None:
    """Open a Streamlit selectbox and pick an option by typing to filter."""
    container = page.locator('[data-testid="stWidgetLabel"]').filter(
        has=page.get_by_text(label, exact=True)
    ).first.locator("xpath=../..")
    select = container.locator("div[data-baseweb='select']").first
    select.scroll_into_view_if_needed()
    select.wait_for(state="visible", timeout=15_000)
    select.click()
    time.sleep(0.6)  # let dropdown open

    # Type value to filter (baseweb select has built-in search)
    page.keyboard.type(value, delay=50)
    time.sleep(0.6)

    # Click the first matching option (filtered list should now show it)
    option = page.locator('li[role="option"]').filter(
        has_text=re.compile(f"^{re.escape(value)}$")
    ).first
    option.wait_for(state="attached", timeout=10_000)
    option.click()
    time.sleep(0.4)


def fill_text(page, label: str, value: str) -> None:
    container = page.locator('[data-testid="stWidgetLabel"]').filter(
        has=page.get_by_text(label, exact=True)
    ).first.locator("xpath=../..")
    inp = container.locator("input").first
    inp.scroll_into_view_if_needed()
    inp.wait_for(state="visible", timeout=10_000)
    inp.click(click_count=3)
    inp.fill(value)
    time.sleep(0.2)


def set_number_input(page, label: str, value: int) -> None:
    container = page.locator('[data-testid="stWidgetLabel"]').filter(
        has=page.get_by_text(label, exact=True)
    ).first.locator("xpath=../..")
    inp = container.locator("input[type='number']").first
    inp.scroll_into_view_if_needed()
    inp.click(click_count=3)
    inp.fill(str(value))
    time.sleep(0.2)


def set_date(page, date_str: str) -> None:
    """Fill the date input (label='Date') and dismiss the calendar popup."""
    container = page.locator('[data-testid="stWidgetLabel"]').filter(
        has=page.get_by_text("Date", exact=True)
    ).first.locator("xpath=../..")
    inp = container.locator("input").first
    inp.scroll_into_view_if_needed()
    inp.wait_for(state="visible", timeout=10_000)
    inp.click(click_count=3)
    inp.fill(date_str)
    # Dismiss calendar by pressing Escape then Tab to leave the field
    page.keyboard.press("Escape")
    time.sleep(0.2)
    page.keyboard.press("Tab")
    time.sleep(0.4)
    # Click event name to ensure calendar is fully closed
    try:
        page.locator('label:has-text("Event name")').first.click()
        time.sleep(0.2)
    except Exception:
        pass


def set_time(page, time_str: str) -> None:
    """Fill the Start time field. Tries multiple input strategies."""
    # Locate container
    container = page.locator('[data-testid="stWidgetLabel"]').filter(
        has=page.get_by_text("Start time", exact=True)
    ).first.locator("xpath=../..")
    container.scroll_into_view_if_needed()
    container.wait_for(state="visible", timeout=15_000)

    # Strategy 1: try input[type='text'] (baseweb time picker)
    text_inps = container.locator("input[type='text']")
    if text_inps.count() > 0:
        ti = text_inps.first
        ti.click(click_count=3)
        ti.fill(time_str)
        page.keyboard.press("Enter")
        time.sleep(0.3)
        return

    # Strategy 2: try any input inside the container
    any_inp = container.locator("input").first
    if any_inp.count() > 0:
        any_inp.click(click_count=3)
        any_inp.fill(time_str)
        page.keyboard.press("Enter")
        time.sleep(0.3)
        return

    # Strategy 3: give up on time (defaults will be used)
    print("    [warn] Could not set start time – using default")


def toggle_radio(page, label: str, option: str) -> None:
    """Click a radio button group by label (exact option match)."""
    radio_group = page.locator('[data-testid="stRadio"]').filter(
        has=page.get_by_text(label, exact=True)
    ).first
    radio_group.wait_for(state="visible", timeout=10_000)
    radio_group.locator("label").filter(
        has_text=re.compile(f"^{re.escape(option)}$")
    ).click()
    time.sleep(1.0)


def check_checkbox(page, label: str, checked: bool) -> None:
    chk_container = page.locator('[data-testid="stCheckbox"]').filter(
        has=page.get_by_text(label, exact=True)
    ).first
    chk_container.scroll_into_view_if_needed()
    chk_container.wait_for(state="visible", timeout=10_000)
    inp = chk_container.locator("input[type='checkbox']")
    if inp.is_checked() != checked:
        chk_container.locator("label").click()
    time.sleep(0.2)


def click_submit(page) -> None:
    """Click the Predict Impact / primary form submit button."""
    btn = page.locator(
        'button[kind="primaryFormSubmit"], '
        '[data-testid="stFormSubmitButton"] button[kind="primary"], '
        'button:has-text("Predict Impact")'
    ).first
    btn.scroll_into_view_if_needed()
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()


def submit_event(page, ev: dict) -> None:
    print(f"\n=== Submitting: {ev['name']} ===")

    # Navigate to Plan Event page
    page.goto(APP_URL)
    page.wait_for_load_state("networkidle", timeout=60_000)
    time.sleep(3)

    # Event type: Planned
    toggle_radio(page, "Event type", "Planned")

    # Route format
    fmt = "Route-based" if ev["route_based"] else "Venue-based"
    toggle_radio(page, "Event format", fmt)

    # Core fields
    fill_text(page, "Event name", ev["name"])
    pick_selectbox(page, "Event cause", ev["cause"])
    pick_selectbox(page, "Primary corridor", ev["corridor"])
    pick_selectbox(page, "Priority", ev["priority"])

    # Date then time (calendar must be dismissed before setting time)
    set_date(page, ev["date"])
    set_time(page, ev["time_str"])

    # Road closure checkbox
    check_checkbox(page, "Requires road closure?", ev["road_closure"])

    # Planned-event details
    set_number_input(page, "Estimated attendance", ev["attendance"])
    check_checkbox(page, "VIP presence?", ev["vip"])

    # Route checkpoints (if route-based)
    if ev["route_based"]:
        fill_text(page, "Start checkpoint", ev.get("start_checkpoint", ""))
        fill_text(page, "End checkpoint", ev.get("end_checkpoint", ""))
        fill_text(page, "Intermediate stops (comma-separated, optional)", ev.get("stops", ""))

    # Screenshot filled form
    form_ss = SCREENSHOT_DIR / f"{ev['slug']}_form.png"
    page.screenshot(path=str(form_ss), full_page=True)
    print(f"  Form : {form_ss.name}")

    # Submit
    click_submit(page)

    # Wait for Results page to load (model inference can take ~30s)
    try:
        page.wait_for_url("**/*Results*", timeout=120_000)
    except PWTimeoutError:
        pass
    page.wait_for_load_state("networkidle", timeout=120_000)
    time.sleep(5)

    # Screenshot Results page
    results_ss = SCREENSHOT_DIR / f"{ev['slug']}_results.png"
    page.screenshot(path=str(results_ss), full_page=True)
    print(f"  Results: {results_ss.name}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--window-size=1440,900", "--no-sandbox"],
        )
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(90_000)

        print("Connecting to Streamlit…")
        page.goto(APP_URL)
        page.wait_for_load_state("networkidle", timeout=120_000)
        time.sleep(4)
        print("App ready.\n")

        for ev in EVENTS:
            try:
                submit_event(page, ev)
            except Exception as exc:
                err_ss = SCREENSHOT_DIR / f"{ev['slug']}_ERROR.png"
                page.screenshot(path=str(err_ss), full_page=True)
                print(f"  ERROR: {exc}")
                print(f"  Error screenshot: {err_ss.name}")

        browser.close()
        print(f"\nAll done. Screenshots in: {SCREENSHOT_DIR}")


if __name__ == "__main__":
    main()
