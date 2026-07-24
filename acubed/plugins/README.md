# Game Plugins

Each plugin is a package with four focused modules:

- `config.py` contains immutable game-specific settings.
- `source.py` fetches packs, chart references, and chart assets.
- `parser.py` turns an `AssetResponse` into a `Stepfile`.
- `definition.py` exposes a declarative `PLUGIN` for auto-discovery.

Keep game-specific API quirks in the plugin. Shared orchestration belongs in
`application/`, and framework or storage adapters belong in `infrastructure/`.
Use shared helpers for cross-plugin concerns such as environment parsing,
bounded async concurrency, and retryable HTTP requests.

Minimal `definition.py`:

```python
from acubed.domain.game.plugin import GamePlugin

from .config import ExampleConfig
from .parser import ExampleChartParser
from .source import ExampleRemoteSource

PLUGIN = GamePlugin(
    id="example",
    name="Example",
    config_factory=ExampleConfig,
    source_factory=ExampleRemoteSource,
    parser_factory=ExampleChartParser,
)
```

The source must implement `ChartSource`. It may additionally implement the
bulk, streaming, or pack-resolution protocols in
`acubed.domain.game.protocols`; the ingestion engine detects those capabilities
automatically. Parsing remains entirely game-specific.
