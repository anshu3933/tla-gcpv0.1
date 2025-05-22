import os
import requests

BASE_URL = os.environ.get("API_URL", "http://localhost:8080")


def test_healthz():
    resp = requests.get(f"{BASE_URL}/healthz")
    assert resp.status_code == 200


def test_readyz():
    resp = requests.get(f"{BASE_URL}/readyz")
    assert resp.status_code == 200
