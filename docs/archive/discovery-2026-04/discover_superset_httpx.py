import httpx
import json
import time

def discover():
    url = "http://superset:8088"
    client = httpx.Client(timeout=30.0)
    while True:
        try:
            resp = client.post(f"{url}/api/v1/security/login", json={
                "username": "admin",
                "password": "admin",
                "provider": "db"
            })
            resp.raise_for_status()
            token = resp.json()["access_token"]
            break
        except Exception as e:
            print(f"Waiting for Superset... {e}")
            time.sleep(5)
            
    headers = {"Authorization": f"Bearer {token}"}
    
    print("DASHBOARDS:")
    dashboards = client.get(f"{url}/api/v1/dashboard/", headers=headers).json()
    for d in dashboards.get("result", []):
        print(f"ID: {d['id']} | UUID: {d['uuid']} | Title: {d['dashboard_title']}")
        
    print("\nDATASETS:")
    datasets = client.get(f"{url}/api/v1/dataset/", headers=headers).json()
    for ds in datasets.get("result", []):
        print(f"ID: {ds['id']} | Table: {ds['table_name']}")

if __name__ == "__main__":
    discover()
