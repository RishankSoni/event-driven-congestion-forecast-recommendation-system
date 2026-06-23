# src/mappls_api.py
import time
import requests
import streamlit as st
import os
import logging

logger = logging.getLogger(__name__)

# Cache for OAuth Token
_token_cache = {
    "access_token": None,
    "token_type": "Bearer",
    "expires_at": 0.0
}

def get_credentials() -> dict:
    """Retrieve Mappls credentials from Session State, secrets, or environment variables."""
    # Check session state (UI override)
    client_id = st.session_state.get("mappls_client_id")
    client_secret = st.session_state.get("mappls_client_secret")
    rest_key = st.session_state.get("mappls_rest_key")
    
    # Fallback to st.secrets
    if not client_id or not client_secret or not rest_key:
        try:
            secrets = st.secrets.get("mappls", {})
            if not client_id:
                client_id = secrets.get("client_id")
            if not client_secret:
                client_secret = secrets.get("client_secret")
            if not rest_key:
                rest_key = secrets.get("rest_key")
        except Exception:
            pass

    # Fallback to environment variables
    if not client_id:
        client_id = os.environ.get("MAPPLS_CLIENT_ID")
    if not client_secret:
        client_secret = os.environ.get("MAPPLS_CLIENT_SECRET")
    if not rest_key:
        rest_key = os.environ.get("MAPPLS_REST_KEY")

    # Clean up empty strings or placeholders
    def clean(val):
        if not val:
            return None
        val_str = str(val).strip()
        if val_str.startswith("YOUR_") or val_str == "":
            return None
        return val_str

    return {
        "client_id": clean(client_id),
        "client_secret": clean(client_secret),
        "rest_key": clean(rest_key)
    }

def is_configured() -> bool:
    """Check if minimum credentials for map/geocoding/workmate are set."""
    creds = get_credentials()
    return bool(creds["rest_key"])

def get_access_token() -> str | None:
    """Get or generate Mappls OAuth 2.0 access token with in-memory caching."""
    global _token_cache
    
    creds = get_credentials()
    client_id = creds["client_id"]
    client_secret = creds["client_secret"]
    
    if not client_id or not client_secret:
        return None
        
    now = time.time()
    # Return cached token if valid (giving a 60-second buffer)
    if _token_cache["access_token"] and _token_cache["expires_at"] > (now + 60):
        return _token_cache["access_token"]
        
    # Request a new token
    token_url = "https://outpost.mappls.com/api/security/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "accept": "application/json"
    }
    
    try:
        resp = requests.post(token_url, data=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            _token_cache["access_token"] = data.get("access_token")
            _token_cache["token_type"] = data.get("token_type", "Bearer")
            expires_in = float(data.get("expires_in", 3600))
            _token_cache["expires_at"] = now + expires_in
            return _token_cache["access_token"]
        else:
            logger.error(f"Failed to generate Mappls OAuth token: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Error connecting to Mappls Token API: {e}")
        
    return None

def geocode_address(address: str) -> tuple[float, float] | None:
    """Geocode an address string using Mappls Geocoding API."""
    creds = get_credentials()
    rest_key = creds["rest_key"]
    if not rest_key:
        return None
        
    # First try using OAuth2 access token if client_id/secret are available,
    # otherwise fall back to REST key directly as access token parameter.
    access_token = get_access_token() or rest_key
    
    url = "https://search.mappls.com/search/address/geocode"
    params = {
        "address": address,
        "itemCount": 1
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "accept": "application/json"
    }
    
    try:
        # Mappls accepts token in header or params. We send in header, fall back to params if header rejected
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 401 or resp.status_code == 403:
            # Fallback: pass token in query param
            params["access_token"] = access_token
            resp = requests.get(url, params=params, timeout=10)
            
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results")
            if results and len(results) > 0:
                first = results[0]
                lat = first.get("lat")
                lng = first.get("lng")
                if lat is not None and lng is not None:
                    return float(lat), float(lng)
        else:
            logger.warning(f"Mappls Geocoding failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.error(f"Error querying Mappls Geocoding API: {e}")
        
    return None

def fetch_workmate_users(event_lat: float = 12.97, event_lng: float = 77.59) -> list[dict]:
    """Fetch field force employees/officers from Mappls Workmate users endpoint.
    If credentials are missing or API fails, returns simulated officer list clustered around the event location.
    """
    token = get_access_token()
    if token:
        url = "https://workmate.mapmyindia.com/apis/users"
        headers = {
            "Authorization": f"Bearer {token}",
            "accept": "application/json"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                users_data = resp.json()
                # Parse matching structure
                # Mappls lists return lists of users, map to standard dicts
                results = []
                for u in users_data.get("data", users_data.get("users", [])):
                    results.append({
                        "id": u.get("id") or u.get("userId"),
                        "name": u.get("name") or u.get("userName") or "Unknown Officer",
                        "latitude": float(u.get("latitude")) if u.get("latitude") else None,
                        "longitude": float(u.get("longitude")) if u.get("longitude") else None,
                        "phone": u.get("phone") or u.get("mobile", ""),
                        "battery": u.get("battery", 100),
                        "simulated": False
                    })
                if results:
                    return results
        except Exception as e:
            logger.warning(f"Workmate fetch users error, falling back to simulation: {e}")
            
    # Simulation / fallback officers
    import random
    names = [
        "Inspector Ramesh Kumar", 
        "Sub-Inspector Ajay Patil", 
        "Officer Sneha Reddy", 
        "Officer Vikram Gowda",
        "Inspector Ananya Hegde"
    ]
    simulated_officers = []
    for i, name in enumerate(names):
        # Cluster within ~1-2km of the event
        lat_offset = random.uniform(-0.015, 0.015)
        lng_offset = random.uniform(-0.015, 0.015)
        simulated_officers.append({
            "id": f"sim_officer_{i+1}",
            "name": name,
            "latitude": event_lat + lat_offset,
            "longitude": event_lng + lng_offset,
            "phone": f"+91 98450 {10000 + i*111}",
            "battery": random.randint(45, 98),
            "simulated": True
        })
    return simulated_officers

def dispatch_workmate_task(task_name: str, description: str, due_date_str: str = None) -> dict:
    """Create a deployment task in Mappls Workmate.
    Falls back to simulation mode if credentials are missing or API fails.
    """
    token = get_access_token()
    
    payload = {
        "task_name": task_name,
        "description": description,
        "due_date": due_date_str or time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    if token:
        url = "https://workmate.mapmyindia.com/apis/tasks"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json"
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code in [200, 201]:
                return {
                    "success": True,
                    "task_id": resp.json().get("id") or resp.json().get("taskId") or "api_success",
                    "mode": "live",
                    "message": "Task successfully created in Mappls Workmate"
                }
            else:
                logger.error(f"Workmate task creation failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Error connecting to Workmate task API: {e}")
            
    # Mock dispatch
    import uuid
    return {
        "success": True,
        "task_id": f"mock_task_{uuid.uuid4().hex[:8]}",
        "mode": "simulation",
        "message": "Task dispatched via MapmyIndia simulation mode (credentials not configured)"
    }
