import requests

def get_temperature(city: str) -> float:
    """Return the current temperature for a city."""
    r = requests.get("https://api.example.com/v1/temp", params={"q": city}, timeout=5)
    r.raise_for_status()
    return r.json()["temp_c"]
