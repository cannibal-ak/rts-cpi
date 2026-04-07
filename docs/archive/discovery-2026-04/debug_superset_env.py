import httpx
import json
import asyncio

async def main():
    base_url = "http://localhost:8088"
    username = "admin"
    password = "admin"
    
    print(f"Connecting to Superset at {base_url}...")
    
    async with httpx.AsyncClient() as client:
        # 1. Login
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
        
        # 2. Check Dashboards (all details)
        dash_resp = await client.get(f"{base_url}/api/v1/dashboard/", headers=headers)
        data = dash_resp.json()
        dashboards = data.get("result", [])
        print(f"\nFound {len(dashboards)} dashboards total.")
        for d in dashboards:
            print(f"- ID: {d['id']}, Title: '{d['dashboard_title']}', UUID: {d['uuid']}, Published: {d['published']}")

        # 3. Check for specific titles we need
        target_titles = ["Airline CPI Dashboard", "Cruise/Ferry CPI Dashboard"]
        for title in target_titles:
            match = next((d for d in dashboards if d['dashboard_title'] == title), None)
            if match:
                print(f"✅ Found match for '{title}'")
            else:
                print(f"❌ '{title}' NOT FOUND")

        # 4. Check Datasets
        ds_resp = await client.get(f"{base_url}/api/v1/dataset/", headers=headers)
        datasets = ds_resp.json().get("result", [])
        print(f"\nFound {len(datasets)} datasets total.")
        for d in datasets:
            print(f"- ID: {d['id']}, Table: '{d['table_name']}', Database: {d['database']['database_name']}")

if __name__ == "__main__":
    asyncio.run(main())
