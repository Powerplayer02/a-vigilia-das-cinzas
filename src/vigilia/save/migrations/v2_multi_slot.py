"""Esquema 1 → 2: remove a restrição de slot único sem reserializar payloads."""

import json
from datetime import datetime, timezone


def create_schema(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
    connection.execute("CREATE TABLE slots (id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 3), version INTEGER NOT NULL, timing_version INTEGER NOT NULL)")
    for table in ("player", "world"):
        connection.execute(f"CREATE TABLE {table} (slot INTEGER PRIMARY KEY REFERENCES slots(id), payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE slot_metadata (slot INTEGER PRIMARY KEY REFERENCES slots(id), name TEXT NOT NULL, level INTEGER NOT NULL, playtime_sec REAL NOT NULL, area_id TEXT NOT NULL, saved_at TEXT NOT NULL)")


def migrate(connection):
    for table in ("slots", "player", "world"):
        connection.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")
    create_schema(connection)
    for table in ("slots", "player", "world"):
        connection.execute(f"INSERT INTO {table} SELECT * FROM legacy_{table}")
    for table in ("player", "world", "slots"):
        connection.execute(f"DROP TABLE legacy_{table}")
    for slot, payload in connection.execute("SELECT slot,payload FROM player"):
        player = json.loads(payload)
        area = "forge_arena" if player.get("motion", {}).get("position", {}).get("y", 0) >= 14 else "patio_da_vigilia"
        connection.execute("INSERT INTO slot_metadata VALUES (?,?,?,?,?,?)", (
            slot, player.get("character_name", "Vesper"), player.get("level", 1),
            player.get("playtime_sec", 0), area, datetime.now(timezone.utc).isoformat()))
