# tests/test_mappls.py
import unittest
from unittest.mock import patch, MagicMock
import streamlit as st
import folium

import src.mappls_api as mappls_api
from src.map_builder import build_map
import src.station_store as station_store

class TestMapplsIntegration(unittest.TestCase):

    def setUp(self):
        # Clear token cache
        mappls_api._token_cache = {
            "access_token": None,
            "token_type": "Bearer",
            "expires_at": 0.0
        }
        # Reset session state keys
        st.session_state["mappls_tiles_enabled"] = False
        st.session_state["mappls_geocoding_enabled"] = False
        st.session_state["mappls_workmate_enabled"] = False
        st.session_state["mappls_client_id"] = None
        st.session_state["mappls_client_secret"] = None
        st.session_state["mappls_rest_key"] = None

    @patch("streamlit.secrets")
    def test_get_credentials_empty(self, mock_secrets):
        mock_secrets.get.return_value = {}
        creds = mappls_api.get_credentials()
        self.assertIsNone(creds["client_id"])
        self.assertIsNone(creds["client_secret"])
        self.assertIsNone(creds["rest_key"])


    def test_get_credentials_session_state(self):
        st.session_state["mappls_client_id"] = "test_id"
        st.session_state["mappls_client_secret"] = "test_secret"
        st.session_state["mappls_rest_key"] = "test_key"
        
        creds = mappls_api.get_credentials()
        self.assertEqual(creds["client_id"], "test_id")
        self.assertEqual(creds["client_secret"], "test_secret")
        self.assertEqual(creds["rest_key"], "test_key")

    @patch("requests.post")
    def test_get_access_token_success(self, mock_post):
        st.session_state["mappls_client_id"] = "test_id"
        st.session_state["mappls_client_secret"] = "test_secret"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "mocked_access_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_post.return_value = mock_response
        
        token = mappls_api.get_access_token()
        self.assertEqual(token, "mocked_access_token")
        
        # Test caching
        token_cached = mappls_api.get_access_token()
        self.assertEqual(token_cached, "mocked_access_token")
        # requests.post should only be called once due to caching
        mock_post.assert_called_once()

    @patch("requests.get")
    def test_geocode_address_success(self, mock_get):
        st.session_state["mappls_rest_key"] = "test_rest_key"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"lat": 12.91, "lng": 77.62}
            ]
        }
        mock_get.return_value = mock_response
        
        coords = mappls_api.geocode_address("Bangalore")
        self.assertIsNotNone(coords)
        self.assertEqual(coords, (12.91, 77.62))

    def test_fetch_workmate_users_simulation(self):
        # Without credentials, it should return simulated officers
        officers = mappls_api.fetch_workmate_users(12.97, 77.59)
        self.assertEqual(len(officers), 5)
        for officer in officers:
            self.assertTrue(officer["simulated"])
            self.assertIn("sim_officer_", officer["id"])
            self.assertIsNotNone(officer["latitude"])

    def test_dispatch_workmate_task_simulation(self):
        res = mappls_api.dispatch_workmate_task("Task 1", "Desc 1")
        self.assertTrue(res["success"])
        self.assertEqual(res["mode"], "simulation")

    @patch("src.mappls_api.geocode_address")
    def test_station_store_uses_mappls_geocoding_when_enabled(self, mock_geocode):
        st.session_state["mappls_geocoding_enabled"] = True
        st.session_state["mappls_rest_key"] = "test_rest_key"
        
        mock_geocode.return_value = (12.9, 77.5)
        mock_nominatim = MagicMock()
        
        coords = station_store._try_geocode_strategies("Koramangala", "Koramangala ACP", mock_nominatim)
        
        self.assertEqual(coords, (12.9, 77.5))
        mock_geocode.assert_called()
        mock_nominatim.assert_not_called()

    @patch("src.mappls_api.geocode_address")
    def test_station_store_falls_back_to_nominatim_when_disabled(self, mock_geocode):
        st.session_state["mappls_geocoding_enabled"] = False
        st.session_state["mappls_rest_key"] = "test_rest_key"
        
        mock_geocode.return_value = (12.9, 77.5)
        mock_nominatim = MagicMock()
        
        loc_mock = MagicMock()
        loc_mock.latitude = 12.99
        loc_mock.longitude = 77.59
        mock_nominatim.return_value = loc_mock
        
        coords = station_store._try_geocode_strategies("Koramangala", "Koramangala ACP", mock_nominatim)
        
        self.assertEqual(coords, (12.99, 77.59))
        mock_geocode.assert_not_called()
        mock_nominatim.assert_called()
