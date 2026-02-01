import requests
import time

print("Testing API fetch-live on http://127.0.0.1:8000/api/fetch-live...")
try:
    response = requests.post("http://127.0.0.1:8000/api/fetch-live", json={})
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:200]}...")
except Exception as e:
    print(f"Error: {e}")
