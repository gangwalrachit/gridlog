# GridLog — Interview Story

> Cheat sheet for the Rebase Energy interview.
> Structure: concept → stack → how it was built → the honest corrections → demo → what's next.

---

## 1. What is GridLog?

A **time-of-knowledge intraday price tracker** for European electricity markets.

Every price row carries three timestamps:
- `valid_time` — the delivery slot the price is *for* (e.g. Wednesday 14:00–14:15)
- `knowledge_time` — when GridLog *learned* this price (fetch time)
- `change_time` — when the row was physically written (auto-managed by TimeDB)

Because multiple `knowledge_time` values can exist for the same `valid_time`, you can ask:
*"What did the market look like at 09:00 this morning?"* — and get a historically honest answer, not today's hindsight.

This is the core problem Rebase solves in production. GridLog is a ground-up implementation of that idea using Rebase's own open-source library.

---

## 2. Why this stack — and why it maps to Rebase

| Layer | Choice | Why it mirrors Rebase |
|---|---|---|
| Storage | TimescaleDB via **TimeDB** | TimeDB is Rebase's open-source SDK — the whole point was to learn it by using it |
| Data shape | **VERSIONED** (`overlapping=True`) | Enables revision history natively; `overlapping_short` hypertable per TimeDB's design |
| Core query | `DISTINCT ON (valid_time) ORDER BY knowledge_time DESC` | TimeDB's `read_overlapping_latest(end_known=as_of)` — as-of query without materialised views |
| Service layer | **gRPC** (`prices.proto`) | Typed contract first; FastAPI is a thin HTTP→gRPC gateway, not the real service |
| Data source | **ENTSO-E Transparency API** | Real European day-ahead prices for SE3 (Sweden) — the same source production systems use |

The dual-interface architecture (gRPC core + FastAPI gateway) reflects the production pattern: external consumers call gRPC directly, browsers go through HTTP.

---

## 3. How it was built — Context Engineering

This project was built **without writing a single line of code manually**. Every file came from a prompted AI session. But the interesting part isn't the code generation — it's the discipline required to make that work across 13 sessions over 3 weeks.

**Prompt engineering** = "how do I word this question to get a good answer?"

**Context Engineering** = architecting *what the AI knows, when, and in what form* across an entire multi-step, multi-session task — so it can reason correctly without repeating mistakes or losing prior decisions.

It covers:
- **What to put in context** — not just the current task, but constraints, prior decisions, and corrections that shape it
- **How state persists across sessions** — memory files, living docs, structured decision journals
- **How corrections propagate** — when reality contradicts the model, you don't just fix the code; you update the knowledge base so the error can't recur
- **Front-loading constraints** — the "plan before implement" contract established in Session 1 shaped every session that followed

**PROMPTS.md is the artifact.** It's not a changelog. It's a running record of what was believed, what was discovered to be wrong, why the correction was made, and what lesson was extracted. A reviewer reading it can see the reasoning process, not just the output.

---

## 4. The five honest corrections (the good stories)

These are the "I was wrong and here's how I found out" moments. Each one produced a better system and a sharper mental model.

---

### Correction 1 — TimeDB is not what I thought (Prompt 4)

**What I assumed:** TimeDB wraps Postgres + ClickHouse. Designed the architecture with a dual-database stack: Postgres for series metadata, ClickHouse for the versioned fact table with `argMax` as-of queries.

**What I found:** Read the actual TimeDB source during the first test run. `timedb/db/create.py` imports `sql/pg_create_table_timescaledb.sql`. Zero ClickHouse references in the package. TimeDB is a TimescaleDB wrapper only. The as-of query is `DISTINCT ON` in pure PostgreSQL, not `argMax`.

**What changed:** Dropped the ClickHouse service. One service, one DSN, one SQL dialect. The as-of query is actually more elegant in PostgreSQL than `argMax` would have been.

**The lesson:** Before committing to an architecture based on how you *think* a library works, spend 30 seconds reading its source. `inspect.signature`, `grep`, one SQL file — would have caught this on day one.

---

### Correction 2 — `createdDateTime` is not the auction time (Prompt 8)

**What I assumed:** ENTSO-E's `<createdDateTime>` field in the XML header = when the market published these prices. Planned to use it as `knowledge_time`.

**What I found:** The fixture's `createdDateTime` was the API *response generation* time, not the auction publication time. ENTSO-E re-stamps it every time it mints an XML document. It tells you "when was this file generated for you", not "when did the market first know this price."

**What changed:** `knowledge_time = datetime.now(UTC)` at fetch start. Honest semantics: "GridLog learned this price at T." The `createdDateTime` is still captured in `batch_params` for audit, but doesn't drive storage.

**The lesson:** "Publication timestamp" in API docs rarely means what it sounds like. Verify against real data before designing a core semantic on top of it.

---

### Correction 3 — A03 compression: one fixture is not a test suite (Prompt 9)

**What I assumed:** ENTSO-E day-ahead documents have 96 `<Point>` elements for a 15-minute resolution day. Positions 1–96, contiguous.

**What I found:** The second real fetch had 95 points. Position 29 was missing. The A03 "sequential fixed size block" curve type has a compression rule: consecutive identical prices omit the duplicate — only the first slot emits an explicit `<Point>`, the rest inherit by forward-fill. My first fixture had no consecutive equal prices, so the compression never triggered and the bug never showed.

**What changed:** Parser rewritten to forward-fill. Always emits exactly `slots` rows regardless of how many explicit `<Point>` elements the source document carries.

**The lesson:** One fixture exercises one path. Before declaring an XML parser done, capture at least two real documents from the same source and diff them. Any discrepancy is compression, optional fields, or schema drift — and all three need handling.

---

### Correction 4 — TimeDB's `end_known` is exclusive (Prompt 12)

**What I assumed:** `get_prices_as_of(as_of=kt)` would return prices known *at or before* `kt`.

**What I found:** TimeDB's `SeriesCollection.read(end_known=T)` is strictly exclusive of T. Calling it with `as_of=kt1` (the exact knowledge_time of a batch) returned empty — the batch wasn't visible at its own timestamp.

**What changed:** Added `timedelta(microseconds=1)` inside `get_prices_as_of` before passing to TimeDB. Public contract is inclusive ("at or before T"), workaround is localised to one line with a comment explaining why.

**The lesson:** "Inclusive vs exclusive" semantics are the kind of edge case that only surface when you test with exact boundary values. The fix is trivial; the discovery requires the right test case. Also logged as a potential upstream PR to TimeDB — the right long-term fix is a library-level `as_of=` parameter with inclusive semantics.

---

### Correction 5 — Ingest window was fetching the wrong day (Prompt 13)

**What I assumed:** The original `run_ingest.py` fetched `today - 1 day`. Seemed reasonable — get yesterday's prices.

**What I found:** During demo prep, the Revisions chart showed two legend entries but a single overlapping line. The reason wasn't a chart bug — it was that both batches had identical values. Investigating why led to the real insight: **day-ahead prices are settled once at the Nord Pool auction (~13:00 CET) and never revised.** Fetching yesterday's prices produces immutable settled data. Re-fetching it produces identical snapshots.

**What changed:** `run_ingest.py` now targets the *freshest published delivery day* — tomorrow's prices after 13:00 CET (auction has cleared), today's prices before 13:00 CET (yesterday's auction, still the freshest available). Uses `ZoneInfo("Europe/Stockholm")` for DST-correct CET/CEST handling. An evening ingest and the following morning's ingest now resolve to the same delivery window, producing two snapshots of the same 96 slots with distinct `knowledge_time`s.

**The honest follow-up:** The revision values are still identical (day-ahead is final). The revision story with day-ahead is about *when GridLog captured each snapshot*, not about prices changing. True price-value revisions require an intraday source — that's Phase 2.

---

## 5. The demo (three scenes)

**Scene A — As Of (the single most important scene)**
> Zone: SE3 · Start/End: today's delivery window (pre-filled) · As Of: 1 hour before first ingest

Result: 0 rows. Same window, same zone — but GridLog hadn't fetched yet.

> As Of: 1 minute after first ingest

Result: 96 rows. *"Same delivery window. The knowledge cutoff changes everything."*

This is the time-of-knowledge concept in two API calls.

---

**Scene B — Revisions (the architecture scene)**
> Zone: SE3 · Start/End: today's delivery window

Result: 2 snapshots, 192 rows, two legend entries at different knowledge timestamps.

Lines overlap because day-ahead prices don't revise after auction — explain this directly. *"The architecture is correct; the data source doesn't revise. Intraday would produce diverging curves — that's Phase 2."*

---

**Scene C — gRPC demo (the engineering scene)**
```
python scripts/demo_grpc.py
```

Shows all three RPCs in one command. The GetAsOf section prints:
```
as_of before first snapshot  → 0 rows
as_of after  first snapshot  → 96 rows
Same delivery window. The knowledge cutoff changes everything.
```

Points to make: server spins up in a background thread (no separate terminal), reflection is enabled so `grpcurl` works for ad-hoc queries, FastAPI is a thin gateway over this same service.

---

## 6. What's next

| Item | Effort | Value |
|---|---|---|
| **Intraday (XBID) source** | Half day — one new `fetch_intraday()` method in `EntsoeClient`, new series registration; storage/query/frontend unchanged | Revision curves would show real price divergence between fetches |
| **Scheduler** | Small — APScheduler or a cron wrapper around `run_ingest.py` | Removes the manual ingest step; runs twice daily automatically |
| **Additional zones** | Trivial — `fetch_and_store` is already parameterised; adding SE1/SE4/DE-LU is a loop | Demonstrates the multi-zone architecture that's already designed |
| **TimeDB upstream PR** | Small — `end_known` inclusivity or an explicit `as_of=` param | Give back to the library that the project was built to learn |

---

## 7. One-sentence answers for likely interview questions

**"What is time-of-knowledge?"**
Every price row carries the timestamp of when it was learned — so you can reconstruct the market's state at any past moment without hindsight contamination.

**"Why not just overwrite prices when they update?"**
Because backtesting on overwritten data is always wrong — you'd be testing against prices that weren't known when the decisions were made.

**"What's the difference between Latest and As Of?"**
Latest returns the most recent snapshot per delivery slot. As Of returns what was known at a specific cutoff — the same query with a `knowledge_time ≤ cutoff` filter.

**"Why do the revision lines overlap?"**
Day-ahead prices are final after the noon auction. Two fetches of the same document produce identical values. The revision story here is about *capture timestamps*, not value divergence. Intraday prices genuinely change — that's Phase 2.

**"Why gRPC over just FastAPI?"**
The typed `.proto` contract is the real service definition. FastAPI is a browser convenience layer. External consumers — backtesting pipelines, other services — would call gRPC directly for lower latency and compile-time type safety.

**"How was AI used? Isn't this just AI-generated code?"**
The code is AI-generated, yes. What isn't trivial is the *context engineering* — maintaining a coherent, correctable knowledge base across 13 sessions so the AI reasons correctly at session 13 based on decisions made at session 1. PROMPTS.md is the artifact: every assumption, every correction, every lesson extracted. That discipline is what separates a working system from a pile of AI output.
