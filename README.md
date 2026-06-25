# acubed

`acubed` ingests rhythm-game chart data through small game plugins. The code is
organized so domain contracts stay stable while each game owns its API client,
configuration, and parser.

## Layout

```text
application/      Use cases that coordinate domain objects
domain/           Framework-free chart and game contracts
infrastructure/   Environment, filesystem, storage, logging, and secrets
interfaces/       CLI and other external entry points
plugins/          Built-in game integrations
runtime/          Application composition and runtime settings
```

## Adding A Game

Create a new folder under `plugins/<game_id>/` with these files:

```text
plugins/<game_id>/
  __init__.py
  config.py
  definition.py
  parser.py
  source.py
```

`definition.py` is the discovery point. It must expose `GAME_ID` and
`build_game()`:

```python
from acubed.domain.game.definition import GameDefinition

GAME_ID = "my_game"


def build_game() -> GameDefinition:
    config = MyGameConfig()
    return GameDefinition(
        id=GAME_ID,
        name="My Game",
        config=config,
        source=MyGameSource(config),
        parser=MyGameParser(),
        required_secrets={"api_key": "MY_GAME_API_KEY"},
    )
```

Use an empty `required_secrets` mapping when the game does not need credentials.
The registry auto-discovers plugin packages, so core registry code does not need
to be edited for new games.

## Running Ingestion

## Local Development With uv

The project is managed by `uv` and targets Python 3.11 locally. Local storage
uses DuckDB.

```bash
uv sync --python 3.11 --extra local
uv run --extra local acubed-ingest --game etterna
```

The Makefile wraps the common commands:

```bash
make sync-local
make smoke
make ingest GAME=ffr
```

For local FFR ingestion, set `FFR_API_KEY`. You can use a `.env` file locally
when the `local` extra is installed.

## Databricks Free Edition

Databricks Free Edition runs on serverless compute. Install the project into a
serverless notebook or job environment as a workspace dependency, not by
installing PySpark from this project. Databricks provides the Spark runtime.

Use `databricks-requirements.txt` when adding dependencies in the Databricks
Environment side pane:

```text
-r /Workspace/path/to/acubed/databricks-requirements.txt
```

The Databricks storage adapter writes Delta tables through the active Spark
session. Configure these optional environment variables if you do not want the
defaults:

```bash
ACUBED_DATABRICKS_CATALOG=<catalog>
ACUBED_DATABRICKS_SCHEMA=<schema>
ACUBED_DATABRICKS_SECRET_SCOPE=acubed
```

If `ACUBED_DATABRICKS_CATALOG` is not set, tables are written under the schema
named for the selected game. Secrets can come from Databricks secrets or from
environment variables with the names declared by the selected game plugin.
