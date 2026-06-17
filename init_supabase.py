import os
import psycopg2
from pathlib import Path

# Load .env
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

conn_str = os.getenv("DATABASE_URL", "")

def init_db():
    schema_path = os.path.join(os.path.dirname(__file__), "supabase", "schema.sql")
    if not os.path.exists(schema_path):
        print(f"Schema file not found at {schema_path}")
        return

    print("Reading schema.sql...")
    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # Split SQL by ; but handle DO blocks. The simplest way is to run the script or execute it directly.
    # psycopg2 can execute multi-statement SQL strings directly!
    try:
        print("Connecting to Supabase...")
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True
        cur = conn.cursor()
        
        print("Executing schema.sql...")
        cur.execute(sql)
        print("Schema initialized successfully!")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error during schema initialization: {e}")

if __name__ == "__main__":
    init_db()
