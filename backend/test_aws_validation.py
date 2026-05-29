import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://localhost:8000"

def get_json(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": True, "status": e.code, "body": e.read().decode()}
    except Exception as e:
        return {"_error": True, "exception": str(e)}

def post_json(path, data):
    req = urllib.request.Request(f"{BASE_URL}{path}", data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"_error": True, "status": e.code, "body": e.read().decode()}
    except Exception as e:
        return {"_error": True, "exception": str(e)}

def run_tests():
    print("--- STARTING VALIDATION ---")
    
    # 1. Start Validation (Already passed if we get here, but let's check /health)
    h = get_json("/health")
    print(f"Health Check: {h}")
    
    # 2. Demo Mode Validation
    print("\n--- DEMO MODE VALIDATION ---")
    demo_payload = {
        "access_key": "DEMO_ACCESS_KEY",
        "secret_key": "DEMO_SECRET_KEY",
        "region": "us-east-1",
        "name": "AWS Demo Account",
        "simulation_mode": True
    }
    demo_res = post_json("/connectors/aws/connect", demo_payload)
    print(f"Demo Connect Response: {demo_res}")
    
    # Wait for background sync to populate usage service
    time.sleep(2)
    
    summary = get_json("/connectors/aws/summary")
    print("\n--- SUMMARY VALIDATION (DEMO) ---")
    print(f"Summary keys: {list(summary.keys()) if not summary.get('_error') else summary}")
    print(f"Monthly spend: {summary.get('monthly_spend')}")
    print(f"Sync state: {summary.get('sync_state')}")
    print(f"Account Metadata: {summary.get('account_metadata')}")
    
    infra = get_json("/connectors/aws/infrastructure")
    print("\n--- INFRASTRUCTURE VALIDATION (DEMO) ---")
    print(f"Total instances: {infra.get('total_instances')}")
    
    costs = get_json("/connectors/aws/costs")
    print("\n--- COSTS VALIDATION (DEMO) ---")
    print(f"Daily spend: {costs.get('daily_spend')}")
    
    recs = get_json("/connectors/aws/recommendations")
    print("\n--- RECOMMENDATIONS VALIDATION (DEMO) ---")
    print(f"Rec count: {recs.get('recommendation_count')}")
    
    # 3. Invalid Credentials Validation
    print("\n--- INVALID CREDENTIAL VALIDATION ---")
    invalid_payload = {
        "access_key": "INVALID_KEY",
        "secret_key": "INVALID_SECRET",
        "region": "us-east-1",
        "name": "AWS Bad Account",
        "simulation_mode": False
    }
    invalid_res = post_json("/connectors/aws/connect", invalid_payload)
    print(f"Invalid Connect Response: {invalid_res}")
    
    # Wait a bit just in case
    time.sleep(1)
    
    # Summary should still be returning demo mode info or degraded gracefully (since we already connected demo)
    # Actually, the demo connector was registered. The bad one failed auth. Let's see.
    h2 = get_json("/health")
    print(f"\nSystem Health After Invalid: {h2}")

if __name__ == "__main__":
    run_tests()
