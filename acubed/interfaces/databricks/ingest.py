import asyncio
import subprocess
import sys
from pathlib import Path

import nest_asyncio

from acubed.interfaces.cli.ingest import async_main

if __name__ == "__main__":
    package_root = Path.cwd().parent.parent.parent

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", str(package_root)]
    )

    nest_asyncio.apply()
    asyncio.run(async_main(game_id="ffr"))
