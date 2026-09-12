"""Run real PostgreSQL tests in temporary schemas; never touch application rows."""
import os
import sys
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
url = os.environ.get("PHASE4_TEST_DATABASE_URL") or dotenv_values(root / ".env").get("DATABASE_URL")
if not url or not url.startswith("postgresql"):
    raise SystemExit("Set PHASE4_TEST_DATABASE_URL to a local PostgreSQL database whose user can create schemas.")
os.environ["PHASE4_TEST_DATABASE_URL"] = url
# Import pytest only after resolving settings. conftest keeps normal app config on SQLite.
import pytest
raise SystemExit(pytest.main(["tests/test_phase4_postgres.py", "tests/test_phase5_postgres.py", "-q"]))
