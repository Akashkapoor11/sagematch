import os
import sys
from pathlib import Path

# Production/default deployment uses PostgreSQL. Tests use an isolated SQLite DB.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
DATA_DIR = PROJECT_ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)
os.environ.setdefault('DATABASE_URL', f"sqlite+pysqlite:///{DATA_DIR / 'test_catalog.db'}")

sys.path.insert(0, str(BACKEND_ROOT))
