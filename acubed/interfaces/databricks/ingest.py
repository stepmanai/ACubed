from pathlib import Path

package_root = Path.cwd().parent.parent.parent

%pip install -e {package_root}

from acubed.interfaces.cli.ingest import async_main

await async_main(game_id="quaver")