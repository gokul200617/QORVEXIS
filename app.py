import argparse
import compileall
import importlib.util
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
REQUIREMENTS_FILE = BACKEND_DIR / "requirements.txt"
ENV_FILE = BACKEND_DIR / ".env"

REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "google.generativeai": "google-generativeai",
    "groq": "groq",
    "sqlalchemy": "SQLAlchemy",
    "uvicorn": "uvicorn",
    "pydantic_settings": "pydantic-settings",
    "psycopg2": "psycopg2-binary",
}


def module_exists(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def ensure_backend_dependencies(skip_install: bool) -> None:
    missing_packages = [
        package
        for module_name, package in REQUIRED_MODULES.items()
        if not module_exists(module_name)
    ]

    if not missing_packages:
        return

    if skip_install:
        missing = ", ".join(missing_packages)
        raise RuntimeError(
            f"Missing backend dependencies: {missing}. "
            "Run `pip install -r backend/requirements.txt` first."
        )

    print("Installing backend dependencies from backend/requirements.txt...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
    )


def compile_backend() -> None:
    print("Compiling backend Python files...")
    success = compileall.compile_dir(
        str(BACKEND_DIR / "app"),
        quiet=1,
        force=True,
    )
    if not success:
        raise RuntimeError("Backend compile check failed.")


def read_env_value(name: str) -> str | None:
    if not ENV_FILE.exists():
        return None

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")

    return None


def warn_about_supabase_connection() -> None:
    database_url = read_env_value("DATABASE_URL")
    if not database_url:
        print("Warning: DATABASE_URL is not set in backend/.env.")
        return

    parsed = urlparse(database_url)
    hostname = parsed.hostname
    if not hostname:
        print("Warning: DATABASE_URL does not include a valid database host.")
        return

    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or 5432)
    except OSError as exc:
        print(f"Warning: cannot resolve database host '{hostname}': {exc}")
        print(
            "Open Supabase Dashboard -> Connect -> Connection string and copy "
            "the Session pooler URI into backend/.env."
        )
        return

    families = {address[0] for address in addresses}
    if hostname.startswith("db.") and socket.AF_INET not in families:
        print(
            "Warning: your Supabase direct database host appears to be IPv6-only."
        )
        print(
            "If startup or /ask cannot reach the database, use Supabase Dashboard "
            "-> Connect -> Session pooler connection string in backend/.env."
        )


def stream_process_output(process: subprocess.Popen, label: str) -> None:
    if process.stdout is None:
        return

    for line in iter(process.stdout.readline, ""):
        if line:
            print(f"[{label}] {line}", end="")


def start_process(command: list[str], cwd: Path, label: str) -> subprocess.Popen:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(
        target=stream_process_output,
        args=(process, label),
        daemon=True,
    ).start()
    return process


def terminate_process(process: subprocess.Popen, label: str) -> None:
    if process.poll() is not None:
        return

    print(f"Stopping {label}...")
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def run_project(host: str, api_port: int, frontend_port: int, skip_install: bool) -> int:
    ensure_backend_dependencies(skip_install=skip_install)
    compile_backend()
    warn_about_supabase_connection()

    if api_port != 8000:
        print(
            "Note: frontend/script.js points to http://127.0.0.1:8000. "
            "Update API_BASE_URL if you use a different API port."
        )

    backend = start_process(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(api_port),
        ],
        BACKEND_DIR,
        "backend",
    )

    frontend = start_process(
        [
            sys.executable,
            "-m",
            "http.server",
            str(frontend_port),
            "--bind",
            host,
        ],
        FRONTEND_DIR,
        "frontend",
    )

    print("")
    print("Qorvexis is starting.")
    print(f"Frontend: http://{host}:{frontend_port}")
    print(f"Backend:  http://{host}:{api_port}")
    print(f"Health:   http://{host}:{api_port}/health")
    print("Press Ctrl+C to stop both services.")
    print("")

    processes = [(backend, "backend"), (frontend, "frontend")]

    try:
        while True:
            for process, label in processes:
                if process.poll() is not None:
                    print(f"{label} exited with code {process.returncode}.")
                    return process.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("")
        print("Shutdown requested.")
        return 0
    finally:
        for process, label in reversed(processes):
            terminate_process(process, label)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Qorvexis Phase 1 MVP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=5500)
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Skip automatic dependency installation.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        raise SystemExit(
            run_project(
                host=args.host,
                api_port=args.api_port,
                frontend_port=args.frontend_port,
                skip_install=args.no_install,
            )
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
