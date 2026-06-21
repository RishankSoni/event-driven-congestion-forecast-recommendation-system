# src/weather.py
import requests


def get_live_weather(lat: float, lon: float) -> dict:
    """Fetch current rain and temperature from Open-Meteo for the given coordinates.

    Returns {"rain_mm": float, "temperature_c": float}.
    Falls back to dry/warm defaults if the API is unreachable or returns bad data.
    """
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,rain&timezone=auto"
        )
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        current = resp.json()["current"]
        return {
            "rain_mm":      float(current.get("rain", 0.0)),
            "temperature_c": float(current.get("temperature_2m", 25.0)),
        }
    except Exception:
        return {"rain_mm": 0.0, "temperature_c": 25.0}
