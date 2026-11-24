"""Formato v2 congelado da 5.1, independente do criador de esquema atual."""

import sqlite3
import json
from vigilia.save.serializers import encode

V2_SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
INSERT INTO metadata VALUES('schema_version',2);
CREATE TABLE slots(id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 3),version INTEGER NOT NULL,timing_version INTEGER NOT NULL);
CREATE TABLE player(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);
CREATE TABLE world(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);
CREATE TABLE slot_metadata(slot INTEGER PRIMARY KEY REFERENCES slots(id),name TEXT NOT NULL,level INTEGER NOT NULL,playtime_sec REAL NOT NULL,area_id TEXT NOT NULL,saved_at TEXT NOT NULL);
PRAGMA user_version=2;
"""


def version_two_database(path, snapshots):
    payloads = {}
    with sqlite3.connect(path) as connection:
        connection.executescript(V2_SCHEMA)
        for slot, snapshot in snapshots.items():
            player, world = encode(snapshot)
            legacy_world = json.loads(world)
            legacy_world.pop("area_id", None)
            legacy_world.pop("dormant_areas", None)
            world = json.dumps(legacy_world, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            # Espaços e ordem do JSON também precisam ser preservados.
            player, world = "\n " + player + "\n", " " + world + "  "
            payloads[slot] = player, world
            connection.execute("INSERT INTO slots VALUES(?,?,?)", (slot, snapshot.version, snapshot.timing_version))
            connection.execute("INSERT INTO player VALUES(?,?)", (slot, player))
            connection.execute("INSERT INTO world VALUES(?,?)", (slot, world))
            data = snapshot.player
            area = "forge_arena" if data.motion.position.y >= 14 else "patio_da_vigilia"
            connection.execute("INSERT INTO slot_metadata VALUES(?,?,?,?,?,?)", (
                slot, data.character_name, data.level, data.playtime_sec, area, "2026-11-15T12:34:56+00:00"))
    return payloads
