import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def post(url, data, headers={}):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method='POST')
    with urllib.request.urlopen(req, context=ctx) as f:
        return json.loads(f.read().decode())

def get(url, headers={}):
    req = urllib.request.Request(url, headers=headers, method='GET')
    with urllib.request.urlopen(req, context=ctx) as f:
        return json.loads(f.read().decode())

try:
    login_data = {'username': 'admin', 'password': 'admin', 'provider': 'db'}
    auth_resp = post('http://superset:8088/api/v1/security/login', login_data, {'Content-Type': 'application/json'})
    token = auth_resp['access_token']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    dashboards = get('http://superset:8088/api/v1/dashboard/', headers)
    for d in dashboards['result']:
        print(f"DASHBOARD: {d['id']} | {d['uuid']} | {d['dashboard_title']}")
        
    datasets = get('http://superset:8088/api/v1/dataset/', headers)
    for ds in datasets['result']:
        print(f"DATASET: {ds['id']} | {ds['table_name']}")
except Exception as e:
    print(f"ERROR: {e}")
