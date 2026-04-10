# GridLog — Architecture

Living document. Updated as design evolves.

---

## Overview

GridLog is an intraday energy price tracker that stores every price update with
full **time-of-knowledge** history. Nothing is ever overwritten. This enables
honest backtesting: "what did the market look like at 09:00?" — without
hindsight bias.

## Stack

| Layer          | Technology                    | Role                                                      | Phase |
| -------------- | ----------------------------- | --------------------------------------------------------- | ----- |
| Data source    | ENTSO-E Transparency API      | Free European electricity market data                     | 1     |
| Metadata store | PostgreSQL 16                 | Series catalogue (dimension table)                        | 1     |
| Value store    | ClickHouse 24.x               | Time-series facts (fact table), columnar, append-only     | 1     |
| SDK            | TimeDB (`pip install timedb`) | Rebase Energy's Python SDK wrapping Postgres + ClickHouse | 1     |
| API            | FastAPI                       | Query layer → thin browser gateway (HTTP → gRPC)          | 1→2   |
| Data wrangling | pandas / Polars               | Normalize ENTSO-E XML → TimeDB TimeSeries                 | 1     |
| Infrastructure | Docker Compose                | Local Postgres + ClickHouse                               | 1     |
| gRPC service   | grpcio + protobuf             | Core data service — all business logic lives here         | 2     |
| Frontend       | Leaflet.js + D3.js            | 2D European price map with time slider                    | 2     |

## Core Concept: Time-of-Knowledge

Every price row has three temporal dimensions (managed by TimeDB):

- **`valid_time`** — the delivery hour this price is _for_ (e.g., "Wednesday 14:00–15:00")
- **`knowledge_time`** — when this value became known (publication timestamp from ENTSO-E, falling back to ingest wall clock)
- **`change_time`** — when the row was physically written (auto-managed by TimeDB)

Because `overlapping=True`, multiple values can exist for the same `valid_time`
with different `knowledge_time`s. This is the revision history. The as-of query
filters by `knowledge_time <= :as_of` to reconstruct what was known at any
point in the past.

---

## Data Model

### Postgres — Series Catalogue (dimension table)

Managed by TimeDB via `td.create()`. We don't write this SQL directly.

| Column        | Type                  | Purpose                                                 |
| ------------- | --------------------- | ------------------------------------------------------- |
| `series_id`   | BigInteger (PK, auto) | Internal identifier                                     |
| `name`        | Text                  | Series name, e.g. `"da_price"`                          |
| `unit`        | Text                  | `"EUR/MWh"`                                             |
| `labels`      | JSONB                 | `{"zone": "SE3", "resolution": "PT1H"}`                 |
| `description` | Text                  | Human-readable description                              |
| `overlapping` | Boolean               | **`true`** — enables time-of-knowledge revision history |
| `retention`   | Text                  | `"short"` (6-month TTL in ClickHouse)                   |
| `inserted_at` | Timestamptz           | Auto-populated                                          |

**Constraints:**

- Unique on `(name, labels)` — `da_price` + `{"zone": "SE3"}` is one series
- GIN index on `labels` for efficient JSONB queries
- `retention` must be one of: `short`, `medium`, `long`

**Why JSONB labels instead of dedicated columns?** Expanding to more zones or
adding `market_type: "intraday"` later requires no schema migration.

### ClickHouse — Values (fact table)

Since `overlapping=True` and `retention="short"`, TimeDB uses the
`overlapping_short` table (6-month TTL, auto-expires).

| Column           | Type                 | Purpose                                   |
| ---------------- | -------------------- | ----------------------------------------- |
| `series_id`      | UInt64               | FK to Postgres catalogue                  |
| `valid_time`     | DateTime64(3, 'UTC') | Delivery hour this price is for           |
| `knowledge_time` | DateTime64(3, 'UTC') | When this value became known              |
| `change_time`    | DateTime64(3, 'UTC') | When the row was written (auto by TimeDB) |
| `value`          | Float64              | Price in EUR/MWh                          |
| `changed_by`     | String               | Audit trail                               |
| `run_id`         | UUID                 | Groups rows from same ingest batch        |

**Engine:** `MergeTree()` \
**Sort key:** `ORDER BY (series_id, valid_time, knowledge_time, change_time)` \
**Partitioning:** Monthly on `valid_time`

**Why this sort key?** The as-of query filters on `series_id` (equality), scans
`valid_time` (range), then picks the best `knowledge_time` (max ≤ as_of). The
sort key matches this access pattern exactly — ClickHouse skips entire granules
without scanning irrelevant data.

### TimeDB Series Definition

```python
td.create_series(
    name="da_price",
    unit="EUR/MWh",
    labels={"zone": "SE3", "resolution": "PT1H"},
    description="ENTSO-E day-ahead hourly price for SE3",
    overlapping=True,       # enables time-of-knowledge revision history
    retention="short",      # 6-month TTL
)
```

### Data Shapes (TimeDB / TimeDataModel)

TimeDB supports four temporal shapes. We use **VERSIONED**:

| Shape         | Columns                                                | Our use?                                       |
| ------------- | ------------------------------------------------------ | ---------------------------------------------- |
| SIMPLE        | `valid_time`, `value`                                  | No — no knowledge tracking                     |
| **VERSIONED** | `knowledge_time`, `valid_time`, `value`                | **Yes** — tracks when each price was published |
| CORRECTED     | `valid_time`, `change_time`, `value`                   | No                                             |
| AUDIT         | `knowledge_time`, `change_time`, `valid_time`, `value` | No — change_time is auto-managed               |

---

## The "As-Of" Query

The core query — "what did the market look like at time X?"

```sql
SELECT
    valid_time,
    argMax(value, knowledge_time) AS price
FROM overlapping_short
WHERE series_id = :series_id
  AND valid_time BETWEEN :start AND :end
  AND knowledge_time <= :as_of
GROUP BY valid_time
ORDER BY valid_time
```

- `argMax(value, knowledge_time)` = the value from the row with the highest
  knowledge_time — but bounded by `<= :as_of`
- Remove the `knowledge_time` filter → latest-known prices
- The **diff** between these two results is the demo money shot

**Why not a materialized view?** In ClickHouse, a materialized view is a
write-time trigger (not a cache). It computes on INSERT and stores results in a
second table. Our query is parameterized by `:as_of` — a query-time input that
isn't known at write time. Therefore, query-time computation with `argMax` is
not just simpler, it's the only correct option.

---

## Knowledge-Time Resolution

How we determine `knowledge_time` for each ingested row:

1. **Primary:** Parse `createdDateTime` from the ENTSO-E XML document header —
   this is the publication timestamp
2. **Fallback:** `datetime.utcnow()` at ingest time — used when the XML field
   is missing or unreliable

The fallback is logged so we can distinguish "ENTSO-E told us when" from "we
recorded when we saw it." Both are honest; one is more precise.

```python
knowledge_time = doc.created_datetime or datetime.utcnow()
```

---

## Error Taxonomy

| Scenario                                 | Severity | Action                                          |
| ---------------------------------------- | -------- | ----------------------------------------------- |
| XML parse failure (bad ENTSO-E response) | WARN     | Skip row, log details                           |
| Network timeout / HTTP 5xx               | WARN     | Skip cycle, retry next run                      |
| Missing `createdDateTime` in XML         | INFO     | Fall back to `datetime.utcnow()`                |
| Duplicate `(valid_time, knowledge_time)` | DEBUG    | Expected from re-fetches; deduped by ClickHouse |
| ClickHouse unreachable                   | ERROR    | Halt ingest                                     |
| Postgres unreachable                     | ERROR    | Halt ingest (can't resolve series_id)           |
| ENTSO-E returns 0 rows                   | WARN     | Log — auction may not have run yet              |

---

## Infrastructure

### Docker Compose Services

| Service      | Image                               | Ports                    | Purpose          |
| ------------ | ----------------------------------- | ------------------------ | ---------------- |
| `postgres`   | `postgres:16`                       | `5432:5432`              | Series catalogue |
| `clickhouse` | `clickhouse/clickhouse-server:24.x` | `8123:8123`, `9000:9000` | Value store      |

Both services use named volumes for persistence, health checks for readiness,
and a shared network (`gridlog-net`).

### Timezone Rule

**Everything is UTC.** All timestamps stored as `DateTime64(3, 'UTC')` in
ClickHouse and `timestamptz` in Postgres. Conversion to CET/CEST happens only
at the API/display boundary. Sweden observes DST — UTC avoids that entirely.

## Dual Interface Architecture

Phase 2 introduces gRPC as the core service layer. FastAPI narrows from "the
API" to "a thin HTTP gateway for browsers."

### Design principles

- **gRPC is the real service.** All business logic (as-of queries, latest
  queries, input validation) lives in the gRPC service, defined by a typed
  `.proto` contract (`prices.proto`). This is the single source of truth.
- **FastAPI becomes a zero-logic gateway.** It translates HTTP/REST requests
  into gRPC calls and returns the response. No query logic, no TimeDB imports,
  no direct DB access. If FastAPI disappeared, every capability still exists
  via gRPC.
- **Both interfaces expose the same two queries:**
  - `GetLatestPrices(zone, start, end)` — current best-known prices
  - `GetPricesAsOf(zone, start, end, as_of)` — prices as known at a point in time
- **External gRPC clients skip FastAPI entirely.** Python scripts, CLI tools,
  or other services call the gRPC service directly — lower latency, typed
  contract, no HTTP overhead.

### Request flow

```
  Browser (map frontend)     gRPC client
         │                        │
    HTTP/REST                   gRPC
         │                        │
  ┌─────────────┐                 │
  │   FastAPI   │ ← thin gateway  │
  │  (gateway)  │   HTTP → gRPC   │
  └──────┬──────┘                 │
         │ gRPC                   │
         └──────────┬─────────────┘
                    │
          ┌─────────────────┐
          │  gRPC Service   │ ← ALL logic here
          │  prices.proto   │
          └────────┬────────┘
                   │
          ┌─────────────────┐
          │    TimeDB       │
          │  PG + ClickHouse│
          └─────────────────┘
```

### Why this split?

In phase 1, FastAPI talks directly to TimeDB — simple, fast to build. When
gRPC arrives in phase 2, we move that logic into the gRPC service and FastAPI
becomes a passthrough. This is a clean migration: the gRPC service takes over
the query module, and FastAPI's route handlers shrink to ~3 lines each.

---

## Scope

### Phase 1 (current)

- Single bidding zone: SE3
- Day-ahead hourly prices only
- FakeEntsoeClient for development (real client when API token is approved)
- FastAPI with as-of and latest endpoints
- Demo script showing the diff

### Phase 2 (planned)

- gRPC service as core data layer (`prices.proto`)
- FastAPI narrowed to thin HTTP → gRPC gateway
- Frontend: Leaflet.js + D3.js European price map with time slider
- Additional bidding zones
- Intraday continuous prices (15-min resolution)

---

## Folder Structure

Designed for all phases upfront so we don't restructure later.

```
gridlog/
├── docker/                     # Docker Compose + init configs
│   └── clickhouse-config/      # ClickHouse users.xml overrides if needed
├── proto/                      # .proto definitions (Phase 2, but reserved now)
│   └── prices.proto
├── gridlog/                    # Python package
│   ├── config.py               # Single source of truth for env/settings (pydantic-settings)
│   ├── entsoe/                 # ENTSO-E API client (real + fake)
│   │   ├── client.py           # Real client — HTTP to ENTSO-E Transparency API
│   │   ├── fake.py             # Fixture-replay client for dev/tests
│   │   └── parser.py           # XML → normalized DataFrames
│   ├── ingest/                 # Writer path: fetch → normalize → append to TimeDB
│   │   └── pipeline.py
│   ├── store/                  # TimeDB wiring: series catalogue + value helpers
│   │   └── series.py
│   ├── query/                  # Read path: as_of() and latest() — pure logic
│   │   └── prices.py
│   ├── grpc_service/           # gRPC server (Phase 2)
│   │   ├── server.py           # gRPC server entrypoint
│   │   ├── servicer.py         # PriceServicer — implements prices.proto
│   │   └── generated/          # Auto-generated from proto/ (gitignored)
│   └── api/                    # FastAPI app
│       ├── app.py              # FastAPI instance + lifespan
│       └── routes.py           # Phase 1: calls query/ directly. Phase 2: calls gRPC
├── frontend/                   # Leaflet.js + D3.js price map (Phase 2)
│   ├── index.html
│   ├── map.js
│   └── styles.css
├── scripts/                    # Runnable entrypoints
│   ├── run_ingest.py           # Trigger ingestion
│   ├── backfill.py             # Historical backfill
│   └── demo_diff.py            # The money shot — as_of vs latest diff
├── tests/
│   ├── unit/
│   └── integration/
├── fixtures/                   # Saved ENTSO-E XML for FakeEntsoeClient + tests
├── notebooks/                  # Exploration (optional, not in package)
├── ARCHITECTURE.md
├── PROMPTS.md
├── pyproject.toml
├── docker-compose.yml          # Top-level convenience (references docker/)
└── .env.example
```

### Key structural decisions

- **`query/` is the heart.** Pure logic, no framework dependencies. Used by
  FastAPI in phase 1, by gRPC servicer in phase 2. This module never changes
  when we add interfaces.
- **`grpc_service/` and `api/` are separate interface layers.** Both are thin
  wrappers over `query/`. Neither contains business logic.
- **`proto/` at the repo root**, not inside the Python package — it's a
  language-neutral contract. Generated Python goes into
  `gridlog/grpc_service/generated/` (gitignored, rebuilt on `make proto`).
- **`frontend/` at the repo root** — it's a separate deliverable (static
  files), not a Python module.
- **`fixtures/` separated from `tests/`** — used by both `FakeEntsoeClient`
  (runtime) and tests. Not test-only data.
