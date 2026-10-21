import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

# Reuse the small API fixture in the isolated PostgreSQL tests.
from test_ingestion_validation import payloads
