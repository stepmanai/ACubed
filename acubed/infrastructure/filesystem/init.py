# infrastructure/filesystem/init.py

from acubed.infrastructure.filesystem.paths import DIRECTORIES


def ensure_directories():
    for d in DIRECTORIES:
        d.mkdir(parents=True, exist_ok=True)
