#!/usr/bin/env python3
"""Initialize TimeDB schema and register series. Run once after docker compose up."""

from gridlog.store.series import init_store, ensure_series

if __name__ == "__main__":
    print("Initializing TimeDB schema...")
    init_store()
    print("Registering series...")
    ensure_series()
    print("Done.")
