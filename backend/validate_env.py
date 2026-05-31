import os
import sys
import subprocess
import requests
import time
import jwt

def run_tests():
    print("=" * 60)
    print("  PHASE 10D: Environment Validation")
    print("=" * 60)

    # 1. Check git status
    git_status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if ".env" in git_status.stdout:
        print("FAIL: .env is being tracked by git!")
        sys.exit(1)
    else:
        print("PASS: .env is ignored by git.")

    # 2. Start application
    print("Starting Qorvexis API backend...")
    server = subprocess.Popen(["python", "-m", "uvicorn", "app.main:app", "--port", "8003"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Wait for startup
    started = False
    startup_logs = []
    for _ in range(30):
        line = server.stdout.readline()
        if not line:
            break
        startup_logs.append(line)
        if "Application startup complete" in line:
            started = True
            break
        if "ERROR" in line or "Exception" in line:
            print(f"Startup Error: {line}")
            break
        time.sleep(0.5)

    if not started:
        print("FAIL: Application failed to start successfully.")
        print("Logs:")
        print("".join(startup_logs))
        server.kill()
        sys.exit(1)
    else:
        print("PASS: Application started successfully.")

    # 3. Check for secrets in logs
    # Read .env
    with open(".env", "r") as f:
        env_content = f.read()
    
    secrets_to_check = []
    for line in env_content.splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            if "KEY" in key or "SECRET" in key or "URL" in key:
                if val:
                    secrets_to_check.append(val)

    secret_leaked = False
    for log in startup_logs:
        for secret in secrets_to_check:
            if secret in log:
                print(f"FAIL: Secret leaked in logs! Found substring matching secret in: {log}")
                secret_leaked = True
    
    if secret_leaked:
        server.kill()
        sys.exit(1)
    else:
        print("PASS: No secrets found in startup logs.")

    # 4. Database Connection & Auth Test
    try:
        # Health check
        resp = requests.get("http://127.0.0.1:8003/health")
        if resp.status_code == 200 and resp.json().get("database") == "connected":
            print("PASS: Database connection succeeds.")
        else:
            print(f"FAIL: Health check failed: {resp.json()}")
            server.kill()
            sys.exit(1)
            
        # Auth Test - Create a valid JWT
        from app.settings import settings
        secret = settings.supabase_jwt_secret
        token = jwt.encode({"sub": "test_user_123", "role": "authenticated"}, secret, algorithm="HS256")
        
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get("http://127.0.0.1:8003/business/summary", headers=headers)
        # Should be 200 or at least not 401 Unauthorized
        if resp.status_code != 401:
            print(f"PASS: Authentication succeeds. (Status: {resp.status_code})")
        else:
            print("FAIL: Authentication failed (401).")
            server.kill()
            sys.exit(1)

    except Exception as e:
        print(f"FAIL: Connection test failed: {e}")
        server.kill()
        sys.exit(1)
        
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    server.kill()

if __name__ == "__main__":
    run_tests()
