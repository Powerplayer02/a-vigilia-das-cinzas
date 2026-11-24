"""Migração de arquivo 4.2, isolamento de slots e leitura do cabeçalho."""

import json
import sqlite3
import time
import statistics
from dataclasses import replace

import pytest
from test_save import full_snapshot
from vigilia.save.service import SaveService
from vigilia.save.serializers import encode
from vigilia.save.database import SCHEMA_VERSION


def legacy_database(path):
    snapshot = full_snapshot()
    p, w = (json.loads(part) for part in encode(snapshot))
    for key in ("character_name", "character_class", "playtime_sec"):
        p.pop(key)
    w.pop("area_id", None)
    w.pop("dormant_areas", None)
    w.pop("bosses")
    w.pop("boss_phases")
    for fighter in [p["fighter"], *(actor["fighter"] for actor in w["actors"])]:
        for key in ("stagger_cooldown_steps", "knockdown_steps", "riposte_hits_remaining"):
            fighter.pop(key)
        if fighter["attack"]:
            for key in ("hitbox_kind", "sphere_radius_start", "sphere_radius_end", "blockable",
                        "block_damage_fraction", "knockdown_steps", "ranged"):
                fighter["attack"]["definition"].pop(key)
    payloads = json.dumps(p), json.dumps(w)
    with sqlite3.connect(path) as connection:
        connection.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value INTEGER NOT NULL);"
            "INSERT INTO metadata VALUES('schema_version',1);"
            "CREATE TABLE slots(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,timing_version INTEGER NOT NULL);"
            "CREATE TABLE player(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);"
            "CREATE TABLE world(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);PRAGMA user_version=1;")
        connection.execute("INSERT INTO slots VALUES(1,1,1)")
        connection.execute("INSERT INTO player VALUES(1,?)", (payloads[0],))
        connection.execute("INSERT INTO world VALUES(1,?)", (payloads[1],))
    return snapshot, payloads


def test_v42_file_migrates_with_backup_and_exact_payload_preservation(tmp_path):
    path = tmp_path / "old.sqlite3"
    snapshot, payloads = legacy_database(path)
    service = SaveService(path)
    assert service.load(1) == snapshot
    with service.repository.database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("SELECT payload FROM player").fetchone()[0] == payloads[0]
        assert connection.execute("SELECT payload FROM world").fetchone()[0] == payloads[1]
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    with sqlite3.connect(service.repository.database.backup_path) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert backup.execute("SELECT payload FROM player").fetchone()[0] == payloads[0]
    service.save(2, replace(snapshot, player=replace(snapshot.player, character_name="Segundo")))
    assert service.load(1) == snapshot and service.load(2).player.character_name == "Segundo"
    assert SaveService(path).repository.database.backup_path is None


def test_three_slots_empty_validation_and_creation_never_overwrites(tmp_path):
    service, original = SaveService(tmp_path / "slots.sqlite3"), full_snapshot()
    assert all(service.load(slot) is None for slot in (1, 2, 3))
    for slot in (1, 2, 3):
        service.save(slot, replace(original, player=replace(original.player, character_name=f"Vigia {slot}")), require_empty=True)
    with pytest.raises(ValueError):
        service.save(1, original, require_empty=True)
    assert service.load(1).player.character_name == "Vigia 1"
    for invalid in (0, 4, True, "1"):
        with pytest.raises(ValueError):
            service.load(invalid)


def test_head_read_never_decodes_payloads_and_median_is_under_five_ms(tmp_path, monkeypatch):
    service, original = SaveService(tmp_path / "head.sqlite3"), full_snapshot()
    for slot in (1, 2, 3):
        service.save(slot, replace(original, player=replace(original.player,
            character_name=f"Nome {slot}", playtime_sec=slot * 90)))
    def forbidden(*args):
        raise AssertionError("list() não pode desserializar snapshots")
    monkeypatch.setattr("vigilia.save.repositories.decode", forbidden)
    samples = []
    for _ in range(25):
        started = time.perf_counter()
        rows = service.repository.list()
        samples.append((time.perf_counter() - started) * 1000)
    assert len(rows) == 3 and rows[1].name == "Nome 2" and rows[1].playtime_sec == 180
    assert statistics.median(samples) < 5


def test_metadata_failure_rolls_back_player_world_and_header(tmp_path):
    service, first = SaveService(tmp_path / "atomic.sqlite3"), full_snapshot()
    service.save(2, first)
    metadata = service.list()
    with service.repository.database.connect() as connection:
        connection.execute("CREATE TRIGGER reject_metadata BEFORE UPDATE ON slot_metadata BEGIN SELECT RAISE(ABORT,'failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.save(2, replace(first, player=replace(first.player, character_name="Alterado", souls=999)))
    assert service.load(2) == first and service.list() == metadata
