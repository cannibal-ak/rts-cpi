import httpx
import json

def fetch_dashboard():
    url = "http://localhost:8088"
    client = httpx.Client(timeout=30.0)
    try:
        resp = client.post(f"{url}/api/v1/security/login", json={
            "username": "admin",
            "password": "admin",
            "provider": "db"
        })
        resp.raise_for_status()
        print("LOGGED IN SUCCESSFULLY")
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        print("FETCHING DASHBOARDS...")
        resp = client.get(f"{url}/api/v1/dashboard/", headers=headers)
        print(f"FETCH STATUS: {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()["result"]
        print(f"FOUND {len(data)} DASHBOARDS")
        for d in data:
            print(f"DASHBOARD: [{d['dashboard_title']}] UUID: {d['uuid']} ID: {d['id']}")
    except Exception as e:
        print(f"ERROR: {e}")
                
    except Exception as e:
        print(f"AUTH ERROR: {e}")

if __name__ == "__main__":
    fetch_dashboard()
