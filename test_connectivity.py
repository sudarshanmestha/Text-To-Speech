import requests

try:
    response = requests.get("https://api.msedgeservices.com", timeout=5)
    print(response.status_code)
except Exception as e:
    print(f"Error: {e}")