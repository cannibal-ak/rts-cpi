import httpx
import json

def discover():
    url = "http://superset:8088"
    client = httpx.Client(timeout=30.0)
    try:
        resp = client.post(f"{url}/api/v1/security/login", json={
            "username": "admin",
            "password": "admin",
            "provider": "db"
        })
        resp.raise_for_status()
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        resp = client.get(f"{url}/api/v1/dashboard/", headers=headers)
        print("DASHBOARDS_RAW:", resp.text)
        
        resp = client.get(f"{url}/api/v1/dataset/", headers=headers)
        print("DATASETS_RAW:", resp.text)
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    discover()
