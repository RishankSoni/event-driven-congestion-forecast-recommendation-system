# src/weather.py
import requests

def get_live_weather(lat: float, lon: float) -> dict:
    """Fetch real-time weather data for live inference from Open-Meteo API.
    
    If the API fails or times out, defaults to rain_mm = 0.0 and temperature_c = 25.0.
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,rain&timezone=auto"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        current = data["current"]
        return {
            "rain_mm": float(current.get("rain", 0.0)),
            "temperature_c": float(current.get("temperature_2m", 25.0))
        }
    except Exception:
        return {
            "rain_mm": 0.0,
            "temperature_c": 25.0
        }
