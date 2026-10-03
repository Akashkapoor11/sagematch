from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)

# Production/dev default: PostgreSQL. Tests can override this with a SQLAlchemy SQLite URL.
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql+psycopg://sagematch:sagematch@localhost:5432/sagematch',
)

APP_NAME = 'SageMatch — Grounded Software Advisor'
LLM_BASE_URL = os.getenv('LLM_BASE_URL', '').rstrip('/')
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
LLM_MODEL = os.getenv('LLM_MODEL', '')
LLM_TIMEOUT = float(os.getenv('LLM_TIMEOUT', '18'))
MAX_PROBES = int(os.getenv('MAX_PROBES', '3'))
CORS_ALLOWED_ORIGINS = [x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000').split(',') if x.strip()]
REQUIRED_FIELDS = [x.strip() for x in os.getenv('REQUIRED_FIELDS', 'name,category,description').split(',') if x.strip()]

DEFAULT_ALLOWED_FIELDS = [
    'name', 'category', 'description', 'team_size_min', 'team_size_max',
    'integrations', 'features', 'deployment', 'pricing_tier', 'website'
]
