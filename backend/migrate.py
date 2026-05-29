import os
import sys

# Ensure backend is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.session import engine
from sqlalchemy import text

def migrate():
    with engine.begin() as conn:
        print("Altering session_id and request_id to VARCHAR(36)...")
        conn.execute(text("ALTER TABLE token_telemetry ALTER COLUMN session_id TYPE VARCHAR(36);"))
        conn.execute(text("ALTER TABLE token_telemetry ALTER COLUMN request_id TYPE VARCHAR(36);"))
        print("Migration complete.")

if __name__ == "__main__":
    migrate()
