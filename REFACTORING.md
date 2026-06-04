# ACubed Refactoring Recommendations

This document outlines a comprehensive refactoring strategy to improve code organization, testability, and maintainability of the ACubed project. The refactoring is organized into 5 phases, each building on the previous one.

## Current State Assessment

### ✅ What's Working Well

1. **Clean Separation of Concerns**
   - CLI (`ingest`, `features`) as entry points
   - Modular package structure (api, config, core, ingestion, features, etc.)
   - Environment detection and context bootstrap
   - Dedicated configuration management

2. **Infrastructure for Scale**
   - `ApplicationContext` for dependency injection
   - Factory patterns (`build_dataframe_factory`, `build_storage`, `build_table_config`)
   - Logging factory with consistent setup
   - Configuration-driven approach with env variables

3. **Hybrid Pipeline Strategy**
   - Python modules for logic (testable, reusable)
   - Databricks notebooks as orchestration wrappers (use Python packages as functions)
   - Good naming convention for notebooks: `ffr__[layer]__[type]__[mode]__[description]`

### ⚠️ Issues & Inefficiencies

1. **Incomplete Module Extraction**
   - Heavy lifting still in notebooks, not in Python modules
   - Notebooks contain 300+ lines of SQL + PySpark instead of importing functions
   - `acubed/ingestion/service.py` and `acubed/features/executors/materialization.py` exist but unclear what they do
   - Feature calculation logic not yet refactored into modules

2. **Inconsistent Abstraction Levels**
   - CLI calls high-level orchestrators (good)
   - But orchestrators probably call SQL notebooks, not Python functions
   - Mixing paradigms: Python CLI + Databricks notebooks + raw SQL
   - No clear contract between CLI and Databricks pipelines

3. **Package Structure Bloat**
   - Too many micro-modules without clear responsibilities:
     - `api/ffr.py` - API client
     - `cli/` - Entry points  
     - `config/` - Configuration
     - `core/bootstrap.py`, `core/runtime.py` - Unclear what goes where
     - `environment/detection.py`, `environment/secrets.py` - Should be in config
     - `dataframe/factory.py` - Only builds DuckDB/Pandas, not Spark!
     - `logging/factory.py` - Over-engineered for just getting a logger
   - Likely missing core modules: `features/`, `transformations/`, `models/`

4. **Data Models Missing**
   - No Pydantic models for ingested data (FFR API response, charts, playlist)
   - No schema definitions for tables
   - No validation between stages
   - Makes it hard to catch bugs early

5. **Unclear Feature Calculation Layer**
   - `acubed/features/executors/materialization.py` - What does it do?
   - Is it a wrapper that calls notebooks or a real feature calculation module?
   - No separate modules for: density calculation, chart features, reliability scoring
   - Each should be independently testable

6. **Testing Infrastructure Weak**
   - Only Jupyter notebooks for testing (hard to automate)
   - No pytest fixtures for common data patterns
   - No unit tests for ingestion, transformations, feature calculations

7. **Configuration Duplication**
   - Config spread across multiple files (`runtime.py`, `tables.py`)
   - Environment detection separate from config
   - No central catalog of all configuration needed

---

## Recommended Refactoring Strategy

### Phase 1: Core Data Models (Week 1)

**Objective**: Establish strong typing and validation throughout the pipeline

Create dedicated data model modules to replace loose dictionaries and SQL schemas:

```
acubed/
├── models/
│   ├── __init__.py
│   ├── game.py              # Game enums (FFR, ITG, etc.)
│   ├── ffr/
│   │   ├── __init__.py
│   │   ├── api.py           # Pydantic models for API responses
│   │   ├── chart.py         # Chart data models
│   │   ├── playlist.py      # Playlist data models
│   │   └── note.py          # Note decomposition models
│   └── schema.py            # Table schema definitions (single source of truth)
```

**Example Implementation**:

```python
# acubed/models/ffr/api.py
from typing import Optional, List
from pydantic import BaseModel, Field

class SongListItem(BaseModel):
    id: int
    name: str
    swf_version: int
    note_count: int
    
class SongListResponse(BaseModel):
    songs: List[SongListItem]

# acubed/models/schema.py
from dataclasses import dataclass

@dataclass
class TableSchema:
    catalog: str
    schema_name: str
    table_name: str
    columns: dict  # {name: type}
    
BRONZE_SONGLIST = TableSchema(
    catalog="acubed",
    schema_name="ffr",
    table_name="bronze__songlist",
    columns={
        "id": "BIGINT",
        "name": "STRING",
        "swf_version": "LONG",
        "note_count": "INT",
    }
)
```

**Benefits**:
- Type safety across the entire pipeline
- Early validation of API responses
- Single source of truth for table schemas
- Easier debugging and IDE autocomplete

---

### Phase 2: Extract Feature Calculation into Modules (Week 2)

**Objective**: Move 300-line notebook cells into testable, reusable Python functions

```
acubed/
├── features/
│   ├── __init__.py
│   ├── density.py           # VerticalDensity + HorizontalDensity
│   ├── chart.py             # ChartFeatures (length, genre, etc.)
│   ├── reliability.py       # ReliabilityScorer + ordinal smoothing
│   ├── preprocessing.py     # Data quality transforms, zero-framer fixing
│   ├── materialization/
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract base for all materializers
│   │   ├── spark.py         # SparkFeatureMaterializer
│   │   └── local.py         # LocalFeatureMaterializer (for testing)
│   └── models.py            # Feature dataclasses/schemas
```

**Example Implementation**:

```python
# acubed/features/density.py
from abc import ABC, abstractmethod
from narwhals import DataFrame
from typing import Optional

class DensityCalculator(ABC):
    """Base for all density calculations."""
    
    @abstractmethod
    def calculate(self, df: DataFrame) -> DataFrame:
        pass

class VerticalDensityCalculator(DensityCalculator):
    """Calculate same-orientation note intensity."""
    
    def calculate(self, notes_df: DataFrame) -> DataFrame:
        """
        Compute vertical_density = 1 / time_delta for consecutive same-orientation notes.
        
        Args:
            notes_df: DataFrame with columns [song_id, note_id, timestamp, orientation, ...]
            
        Returns:
            DataFrame with added column: vertical_density
        """
        # Implementation using narwhals for dataframe agnosticism
        # Supports: Polars, Pandas, DuckDB, Spark (via narwhals)
        decomposed = self._decompose_multi_orientation(notes_df)
        with_prev_ts = self._add_previous_timestamp(decomposed)
        return self._calculate_density(with_prev_ts)
    
    def _decompose_multi_orientation(self, df: DataFrame) -> DataFrame:
        """Split "1001" into separate rows for each orientation."""
        ...

class HorizontalDensityCalculator(DensityCalculator):
    """Calculate temporal clustering across all orientations."""
    
    def __init__(self, window_ms: int = 117):
        self.window_ms = window_ms
    
    def calculate(self, notes_df: DataFrame) -> DataFrame:
        """
        Convolution-like weighted kernel approach.
        """
        ...
```

**Benefits**:
- Independently testable functions
- Can test locally with DuckDB before running on Databricks
- Reusable across different orchestration contexts
- Easier to debug and maintain

---

### Phase 3: Clean Up Configuration (Week 3)

**Objective**: Consolidate scattered config files into a single, validated schema

```
acubed/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Main config dataclass (merged from runtime.py, tables.py)
│   ├── defaults.py          # Default values per environment
│   ├── env_parser.py        # Parse environment variables
│   └── validators.py        # Validate config at startup
```

**Example Implementation**:

```python
# acubed/config/settings.py
from dataclasses import dataclass
from enum import Enum
import os

@dataclass(frozen=True)
class APIConfig:
    base_url: str = "https://www.flashflashrevolution.com/api/api.php"
    playlist_url: str = "https://www.flashflashrevolution.com/game/r3/r3-playlist.php"
    timeout: int = 10
    max_retries: int = 5
    thread_pool_size: int = 4

@dataclass(frozen=True)
class StorageConfig:
    catalog: str = "acubed"
    schema: str = "ffr"
    environment: str = "local"  # local, staging, prod
    host: str = ""  # Databricks host for prod
    token: str = ""  # Databricks token for prod

@dataclass(frozen=True)
class AppConfig:
    api: APIConfig
    storage: StorageConfig
    game: str = "ffr"
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load config from environment variables."""
        api = APIConfig(
            base_url=os.getenv("FFR_API_URL", APIConfig.base_url),
            timeout=int(os.getenv("FFR_API_TIMEOUT", APIConfig.timeout)),
        )
        storage = StorageConfig(
            catalog=os.getenv("UC_CATALOG", StorageConfig.catalog),
            schema=os.getenv("UC_SCHEMA", StorageConfig.schema),
            environment=os.getenv("ENVIRONMENT", "local"),
            host=os.getenv("DATABRICKS_HOST", ""),
            token=os.getenv("DATABRICKS_TOKEN", ""),
        )
        return cls(api=api, storage=storage)
```

**Benefits**:
- Single source of truth for all configuration
- Type-safe with IDE autocomplete
- Environment-specific defaults
- Clear contract for what configuration is required

---

### Phase 4: Simplify Core Modules (Week 3)

**Objective**: Remove redundant abstractions and consolidate similar modules

**Remove/Consolidate**:
- Delete `environment/detection.py`, `environment/secrets.py` → Move to `config/`
- Simplify `logging/factory.py` → Just a single function
- Simplify `core/bootstrap.py` → Inject dependencies directly
- Delete `dataframe/factory.py` if only local dev (use in CLI when needed)

**Keep & Strengthen**:

```
acubed/
├── core/
│   ├── __init__.py
│   └── types.py             # Type hints, protocols
├── ingestion/
│   ├── __init__.py
│   ├── api_client.py        # Use existing FFRClient
│   └── service.py           # Orchestration (sync_songlist, sync_charts)
├── storage/
│   ├── __init__.py
│   ├── backend.py           # Abstract storage backend
│   ├── databricks.py        # Databricks Delta implementation
│   └── local.py             # Local DuckDB/Parquet for testing
```

**Example - Stronger FFRClient**:

```python
# acubed/api/ffr.py
from typing import List, Dict, Optional
from acubed.models.ffr.api import ChartData

class FFRClient:
    def fetch_chart(self, song_id: int) -> ChartData:
        """
        Fetch chart data with proper error handling and validation.
        
        Raises:
            ChartNotFoundError: If chart doesn't exist
            APIError: If API call fails after retries
        """
        ...
    
    def fetch_charts_batch(self, song_ids: List[int]) -> Dict[int, Optional[ChartData]]:
        """Returns dict {song_id: chart_data}, missing songs have value None."""
        ...
```

**Example - Clear Storage Interface**:

```python
# acubed/storage/backend.py
from abc import ABC, abstractmethod
from pathlib import Path
from narwhals import DataFrame

class StorageBackend(ABC):
    """Abstract storage interface supporting multiple backends."""
    
    @abstractmethod
    def read_table(self, table_name: str) -> DataFrame:
        """Read table as narwhals DataFrame (compatible with all backends)."""
        pass
    
    @abstractmethod
    def write_table(self, df: DataFrame, table_name: str, mode: str = "overwrite") -> None:
        """Write narwhals DataFrame to table."""
        pass
    
    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        pass
    
    @staticmethod
    def create(config: StorageConfig) -> "StorageBackend":
        """Factory to create backend based on config."""
        if config.environment == "local":
            return LocalStorageBackend(config)
        else:
            return DatabricksStorageBackend(config)
```

**Benefits**:
- Clearer code organization
- Easy to swap storage backends (local testing vs. Databricks production)
- Reduced file count and cognitive load
- Better IDE navigation

---

### Phase 5: Reorganize Notebook Layers (Week 4)

**Objective**: Keep notebooks THIN - they should only orchestrate Python modules

**NEW (10-15 lines per notebook)**:

```python
# pipeline/ffr__silver__03aa__incremental__vertical-density.ipynb

# Cell 1: Imports & Config
from acubed.features.density import VerticalDensityCalculator
from acubed.config.settings import AppConfig
from acubed.storage.backend import StorageBackend

# Cell 2: Initialize
config = AppConfig.from_env()
storage = StorageBackend.create(config.storage)
calculator = VerticalDensityCalculator()

# Cell 3: Load & Transform
notes_df = storage.read_table("silver__notes-adjusted")
result_df = calculator.calculate(notes_df)

# Cell 4: Store
storage.write_table(result_df, "silver__vertical-density", mode="overwrite")
```

**OLD (300+ lines)**:
```python
# Complex SQL + PySpark scattered across many cells
# Hard to test, hard to reuse
```

**Benefits**:
- Notebooks are readable and maintainable
- Logic is centralized in Python modules
- Easy to test locally before deploying to Databricks
- Easier to add new features

---

## Refactoring Checklist

| Phase | Task | Effort | Impact | Priority |
|-------|------|--------|--------|----------|
| 1 | Create `acubed/models/ffr/api.py` for API responses | 2h | HIGH (enables validation) | 1 |
| 1 | Create `acubed/models/schema.py` for table definitions | 2h | HIGH (single source of truth) | 1 |
| 2 | Extract `VerticalDensityCalculator` from notebook | 4h | HIGH (testable, reusable) | 2 |
| 2 | Extract `HorizontalDensityCalculator` from notebook | 4h | HIGH (testable, reusable) | 2 |
| 2 | Extract `ReliabilityScorer` from notebook | 3h | MEDIUM (complex logic) | 3 |
| 2 | Extract `ChartFeaturesCalculator` from notebook | 3h | MEDIUM (logic extraction) | 3 |
| 3 | Consolidate config into `AppConfig` | 3h | MEDIUM (clarity) | 4 |
| 3 | Move environment detection into config | 1h | LOW (cleanup) | 5 |
| 4 | Abstract storage backend interface | 2h | HIGH (flexibility) | 2 |
| 5 | Add pytest fixtures for common data patterns | 4h | MEDIUM (testing) | 6 |
| 5 | Add unit tests for calculators | 6h | HIGH (confidence) | 4 |
| 5 | Simplify notebooks to use Python modules | 4h | HIGH (maintenance) | 5 |

---

## Proposed Project Structure After Refactoring

```
ACubed/
├── acubed/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── ffr.py                    # FFRClient (enhanced)
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── ingest.py                 # Entry point
│   │   └── features.py               # Entry point
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py               # Main AppConfig
│   │   ├── env_parser.py             # Parse environment
│   │   └── validators.py             # Validate at startup
│   ├── core/
│   │   ├── __init__.py
│   │   └── types.py                  # Type hints, protocols
│   ├── features/
│   │   ├── __init__.py
│   │   ├── density.py                # EXTRACTED: Density calculations
│   │   ├── chart.py                  # EXTRACTED: Chart features
│   │   ├── reliability.py            # EXTRACTED: Reliability scoring
│   │   ├── preprocessing.py          # EXTRACTED: Data quality transforms
│   │   ├── models.py                 # Feature schemas
│   │   └── materialization/
│   │       ├── __init__.py
│   │       ├── base.py               # Abstract materializer interface
│   │       ├── spark.py              # Databricks Spark implementation
│   │       └── local.py              # DuckDB implementation for testing
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── api_client.py             # FFRClient (enhanced)
│   │   ├── service.py                # Orchestration logic
│   │   └── models.py                 # Ingestion data validation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── game.py                   # Game enums
│   │   ├── ffr/
│   │   │   ├── __init__.py
│   │   │   ├── api.py                # Pydantic models for API responses
│   │   │   ├── chart.py              # Chart data models
│   │   │   └── playlist.py           # Playlist data models
│   │   └── schema.py                 # Table schema definitions
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── backend.py                # Abstract StorageBackend
│   │   ├── databricks.py             # Databricks Delta implementation
│   │   └── local.py                  # Local DuckDB/Parquet
│   └── logging.py                    # Simple logging setup
├── pipeline/
│   ├── ffr__bronze__01a__incremental__ingest-from-api.ipynb
│   ├── ffr__silver__01a__incremental__data-quality.ipynb
│   ├── ffr__silver__02a__full-refresh__zero-framer-processing.ipynb
│   ├── ffr__silver__03aa__incremental__vertical-density.ipynb
│   ├── ffr__silver__03ab__incremental__horizontal-density.ipynb
│   ├── ffr__silver__03ac__incremental__chart-features.ipynb
│   ├── ffr__gold__01__incremental__features.ipynb
│   └── README.md                     # Notebook organization guide
├── tests/
│   ├── unit/
│   │   ├── test_density.py
│   │   ├── test_chart_features.py
│   │   ├── test_reliability.py
│   │   └── test_models.py
│   ├── integration/
│   │   └── test_pipeline_local.py
│   ├── conftest.py                   # pytest fixtures
│   └── fixtures/
│       ├── sample_notes.parquet
│       └── sample_charts.json
├── pyproject.toml
├── Makefile
├── README.md
└── docs/
    ├── architecture.md               # Design decisions
    ├── data_models.md                # Pydantic models documentation
    ├── feature_engineering.md        # Feature calculations
    └── testing.md                    # How to run tests
```

---

## Why This Refactoring Matters

| Current State | Problem | Refactored State | Benefit |
|---|---|---|---|
| Notebooks = 300+ lines | Hard to test, debug, reuse | Python modules = 20-50 lines per function | Easier to maintain and test |
| No data validation | Silent failures, corruption | Pydantic models catch errors early | Catch bugs before they propagate |
| Config scattered | Hard to understand requirements | Single `AppConfig` with clear contracts | Single source of truth |
| No local testing | Can only test on Databricks | `LocalFeatureMaterializer` for fast iteration | Faster development cycle |
| Tight coupling | Hard to change storage backend | Abstract `StorageBackend` interface | Easy to swap implementations |
| Manual testing | Error-prone, no coverage | pytest suite with fixtures | Automated quality assurance |

---

## Implementation Strategy

### Recommendations for Phase Execution

**Start with Phase 1**: Data models provide immediate value without changing existing code. You can incrementally add validation to existing modules.

**Then Phase 2**: Feature extraction is the highest-impact work. Extract the most complex/frequently-modified calculations first (density, reliability).

**Phase 3 & 4**: Configuration consolidation and cleanup can happen in parallel. These are lower-risk refactorings with clear benefits.

**Phase 5**: Thin notebooks are the result of all previous phases. This should be the last phase.

### Branch Strategy

- Create feature branches for each phase (e.g., `refactor/phase-1-models`)
- Keep `refactored` branch as integration point
- Run tests in CI before merging

### Testing During Refactoring

- Use `LocalFeatureMaterializer` to test extractions locally with DuckDB
- Add pytest tests for each extracted module before removing notebook code
- Use narwhals for dataframe agnosticism (supports Polars, Pandas, DuckDB, Spark)

---

## Migration Path: Gradual Rollout

You don't need to refactor everything at once. Here's a safe migration path:

1. **Week 1**: Introduce data models alongside existing code (no breaking changes)
2. **Week 2**: Extract 1-2 feature calculators, test locally
3. **Week 3**: Consolidate config, update CLI to use new config
4. **Week 4**: Simplify high-traffic notebooks first
5. **Week 5+**: Continue extracting remaining calculations

Each week can be merged to `refactored` independently.

---

## Questions to Consider

1. **What's the most painful part of the current codebase?** → Prioritize that for extraction
2. **What calculations are changed most frequently?** → Extract those first
3. **Do you have existing unit tests?** → Reuse test patterns and add to new modules
4. **What's the target: Databricks only, or hybrid local/Databricks?** → Influences StorageBackend design

