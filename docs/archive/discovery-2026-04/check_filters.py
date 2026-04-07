import requests
import json

base_url = "http://localhost:8000" # Assuming backend is on 8000
try:
    headers = {"X-Tenant-ID": "a0000000-0000-0000-0000-000000000001", "X-User-Roles": "TENANT_ADMIN"}
    r = requests.get(f"{base_url}/api/v1/airline/filter-metadata", headers=headers)
    print("Airline Metadata:")
    print(json.dumps(r.json(), indent=2))
    
    r = requests.get(f"{base_url}/api/v1/cfl/filter-metadata", headers=headers)
    print("\nCFL Metadata:")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
