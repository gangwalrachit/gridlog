# GridLog

Intraday energy price logger with full **time-of-knowledge** history.

Every price update is stored with _when it was known_ — nothing is ever
overwritten. This enables honest backtesting: "what did the market look like at
09:00?" without hindsight bias.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design, data model,
and query semantics. See [PROMPTS.md](PROMPTS.md) for the decision log.

## Stack

TimescaleDB (via TimeDB, Rebase Energy's SDK) · FastAPI · ENTSO-E Transparency
API · Docker Compose

## Prerequisites

- Python 3.11+
- Docker Desktop (or Docker Engine + Compose v2)
- ENTSO-E API token ([register here](https://transparency.entsoe.eu/))

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd gridlog

# 2. Create local env file and fill in your ENTSO-E token
cp .env.example .env
$EDITOR .env

# 3. Install Python deps (editable install)
pip install -e ".[dev]"

# 4. Start TimescaleDB
docker compose up -d

# 5. Initialize TimeDB schema and register the day-ahead price series
python scripts/init_db.py
```

## Regenerating gRPC code (Phase 2)

```bash
./scripts/gen_proto.sh
```

Generated files land in `gridlog/grpc_service/generated/` (gitignored).

## Project layout

See the "Folder Structure" section of [ARCHITECTURE.md](ARCHITECTURE.md) for
the full map. Short version:

- `gridlog/` — Python package (config, entsoe, ingest, store, query, api, grpc_service)
- `proto/` — language-neutral gRPC contract
- `frontend/` — Leaflet + D3 map (Phase 2)
- `scripts/` — runnable entrypoints (`init_db.py`, `run_ingest.py`, `demo_diff.py`, …)
- `fixtures/` — saved ENTSO-E XML for the fake client and tests
