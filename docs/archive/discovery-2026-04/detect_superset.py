import httpx
import json
import asyncio

async def main():
    base_url = "http://localhost:8088"
    username = "admin"
    password = "admin"
    
    print(f"Connecting to Superset at {base_url}...")
    
    async with httpx.AsyncClient() as client:
        # Login
        try:
            login_resp = await client.post(
                f"{base_url}/api/v1/security/login",
                json={"username": username, "password": password, "provider": "db"}
            )
            login_resp.raise_for_status()
            token = login_resp.json()["access_token"]
            print("Login successful.")
        except Exception as e:
            print(f"Login failed: {e}")
            return

        headers = {"Authorization": f"Bearer {token}"}
        
        # Check Dashboards
        dash_resp = await client.get(f"{base_url}/api/v1/dashboard/", headers=headers)
        dashboards = dash_resp.json().get("result", [])
        print(f"\nFound {len(dashboards)} dashboards:")
        for d in dashboards:
            print(f"- Title: {d['dashboard_title']}, UUID: {d['uuid']}, Published: {d['published']}")

        # Check Datasets
        ds_resp = await client.get(f"{base_url}/api/v1/dataset/", headers=headers)
        datasets = ds_resp.json().get("result", [])
        print(f"\nFound {len(datasets)} datasets:")
        for d in datasets:
            print(f"- Table: {d['table_name']}, ID: {d['id']}")

if __name__ == "__main__":
    asyncio.run(main())
