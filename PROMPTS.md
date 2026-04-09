# GridLog — Prompting Journal

Documents the AI-assisted development process for GridLog.
Logs key prompts, decisions, corrections, and reasoning.

> Intention: Plan before implement.

---

## Prompt 1 — Project Kickoff

**Date:** 10 April 2026
**Tool:** Claude Code

**Prompt:**
# Project: GridLog - Intraday Energy Price Tracker with Time-of-Knowledge

## Context
I am building this to demonstrate deep understanding of time-series data 
infrastructure in the energy domain, for a technical interview at Rebase Energy.
Rebase is a Python-first energy forecasting company whose core stack is:
- PostgreSQL (series metadata / catalogue)
- ClickHouse (time-series values, columnar)
- TimeDB — their open-source Python SDK wrapping both

The core concept I want to demonstrate is "time-of-knowledge" — every price 
update is stored with WHEN it was known, never overwritten. This enables honest 
backtesting: replay "what did the market look like at 09:00?" without hindsight.

## What we are building
A pipeline that:
1. Fetches real intraday electricity prices from ENTSO-E Transparency API
   (free European energy market data)
2. Stores every price update in TimeDB (PostgreSQL + ClickHouse) with full
   time-of-knowledge — nothing ever overwritten
3. FastAPI layer to query "prices as of time X" vs "latest prices"
4. A simple demo script that shows the DIFFERENCE between the two —
   this is the money shot that proves the concept

## Stack
- Python 3.11+
- TimeDB (pip install timedb) — github.com/rebase-energy/timedb
- PostgreSQL + ClickHouse via Docker Compose
- FastAPI
- ENTSO-E REST API for real European price data
- pandas for data wrangling

## How we work together — IMPORTANT
- PLAN before any code, always. Explain what, why, and how first.
- Do NOT write any code until I explicitly say "looks good, go ahead"
- After I approve, implement cleanly with comments I can explain in interview
- Keep PROMPTS.md updated — log key decisions, my corrections, what changed and why
- Keep ARCHITECTURE.md updated — living document of system design
- If you are unsure about something, ask me. Do not assume.

## My background (relevant context for your suggestions)
- 5 years at BlackRock building real-time observability platforms
- Kafka + gRPC + Protobuf + Splunk for real-time
- Hadoop + Spark + Hive for historical
- FastAPI and Python are comfortable
- I understand distributed systems and pipeline design well
- I am newer to the energy domain — explain domain concepts when relevant

## First task — DO NOT WRITE CODE YET
1. Confirm you understand the project in 5 bullet points
2. Propose the folder structure with a one-line explanation for each folder
3. Propose the Docker Compose setup (PostgreSQL + ClickHouse) and explain 
   why each service is configured the way it is
4. Flag any risks or decisions I should make before we write a single line

We plan first. Always.

**What I wanted to achieve:**
Set up a working contract with AI i.e., plan first, no code until approved,
architecture documented, AI as collaborator not autocomplete.

**Key decisions from this prompt:**
- [fill in after Claude Code responds]

