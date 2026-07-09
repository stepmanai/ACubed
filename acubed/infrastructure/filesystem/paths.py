# infrastructure/filesystem/paths.py

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]

DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
CACHE_DIR = ROOT_DIR / ".cache"
DUCKDB_DIR = DATA_DIR / "duckdb"

DUCKDB_PATH = Path(os.getenv("LOCAL_DB_PATH", DUCKDB_DIR / "acubed.duckdb"))

DIRECTORIES = [DATA_DIR, MODELS_DIR, CACHE_DIR, DUCKDB_DIR]
