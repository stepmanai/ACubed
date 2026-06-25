# Game Plugins

Each plugin implements the game contracts in `acubed.domain.game.protocols`:

- `config.py` contains immutable game-specific settings.
- `source.py` fetches packs, chart references, and chart assets.
- `parser.py` turns an `AssetResponse` into a `Stepfile`.
- `definition.py` exposes `GAME_ID` and `build_game()` for auto-discovery.

Keep game-specific API quirks in the plugin. Shared orchestration belongs in
`application/`, and framework or storage adapters belong in `infrastructure/`.
