import asyncio
import subprocess
import sys
from pathlib import Path

import nest_asyncio

from acubed.interfaces.cli.ingest import async_main

if __name__ == "__main__":
    try:
        script_path = Path(__file__).resolve()
        package_root = script_path.parent.parent.parent.parent
    except NameError:
        package_root = Path("/Workspace/Shared/ACubed")

    print(f"Installing package from: {package_root}")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", str(package_root)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    nest_asyncio.apply()
    asyncio.run(async_main(game_id="ffr"))
