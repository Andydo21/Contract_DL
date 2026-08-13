import requests

url = "https://rummage-triangle-figurine.ngrok-free.dev/health"
print(f"Sending GET to {url}...")
try:
    resp = requests.get(url, timeout=30)
    print(f"Status: {resp.status_code}")
    print(resp.json())
except Exception as e:
    print(f"Error: {e}")
