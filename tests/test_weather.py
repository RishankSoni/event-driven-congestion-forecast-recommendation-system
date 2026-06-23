# tests/test_weather.py
from unittest.mock import patch, MagicMock
from src.weather import get_live_weather

def test_get_live_weather_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "current": {
            "rain": 12.5,
            "temperature_2m": 22.8
        }
    }
    
    with patch("requests.get", return_value=mock_response) as mock_get:
        res = get_live_weather(12.97, 77.59)
        mock_get.assert_called_once()
        assert res["rain_mm"] == 12.5
        assert res["temperature_c"] == 22.8

def test_get_live_weather_failure():
    with patch("requests.get", side_effect=Exception("Timeout")) as mock_get:
        res = get_live_weather(12.97, 77.59)
        mock_get.assert_called_once()
        assert res["rain_mm"] == 0.0
        assert res["temperature_c"] == 25.0
