"""Migração dos formatos reais, backup WAL e rollback inclusive de DDL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import sqlite3
from threading import Barrier
import pytest

from save_fixtures import version_two_database
from test_multislot import legacy_database
from test_character_creation import class_snapshot
from test_save import full_snapshot
from vigilia.save.database import SCHEMA_VERSION, Database
from vigilia.save.service import SaveService
from vigilia.save.migrations import v3_slot_headers


@pytest.mark.parametrize("ids", [(1,), (2,), (3,), (1, 2, 3), ()])
def test_schema_two_migrates_class_headers_with_exact_payloads_and_backup(tmp_path, ids):
    path = tmp_path / "previous.sqlite3"
    originals = {slot: class_snapshot(("knight", "mage", "cleric")[slot - 1]) for slot in ids}
    payloads = version_two_database(path, originals)
    service = SaveService(path)
    backup = service.repository.database.backup_path
    assert backup and backup.is_file()
    for slot in ids:
        assert service.load(slot) == originals[slot]
        row = service.list_slots()[slot - 1]
        assert row.class_id == originals[slot].player.character_class
        assert row.created_at == row.saved_at == "2026-11-15T12:34:56+00:00"
    with sqlite3.connect(path) as current, sqlite3.connect(backup) as old:
        assert current.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert old.execute("PRAGMA user_version").fetchone()[0] == 2
        for slot, (p, w) in payloads.items():
            for table, expected in (("player", p), ("world", w)):
                assert current.execute(f"SELECT payload FROM {table} WHERE slot=?", (slot,)).fetchone()[0] == expected
                assert old.execute(f"SELECT payload FROM {table} WHERE slot=?", (slot,)).fetchone()[0] == expected
        assert not current.execute("PRAGMA foreign_key_check").fetchall()
    before = service.list_slots()
    assert SaveService(path).list_slots() == before
    assert SaveService(path).repository.database.backup_path is None
    assert len(list(tmp_path.glob("*.before-v3*.sqlite3"))) == 1


def test_single_slot_schema_one_reaches_three_without_resetting_progress(tmp_path):
    path = tmp_path / "single.sqlite3"
    snapshot, payloads = legacy_database(path)
    service = SaveService(path)
    assert service.load(1) == snapshot
    assert service.list_slots()[0].class_id == "warrior"
    service.create(2, class_snapshot("mage"))
    service.create(3, class_snapshot("cleric"))
    assert service.load(1) == snapshot
    with sqlite3.connect(path) as current:
        assert current.execute("SELECT payload FROM player WHERE slot=1").fetchone()[0] == payloads[0]
        assert current.execute("SELECT payload FROM world WHERE slot=1").fetchone()[0] == payloads[1]


def test_schema_two_without_character_class_gets_legacy_default(tmp_path):
    path = tmp_path / "no_class.sqlite3"
    version_two_database(path, {1: full_snapshot()})
    with sqlite3.connect(path) as connection:
        payload = json.loads(connection.execute("SELECT payload FROM player").fetchone()[0])
        payload.pop("character_class")
        connection.execute("UPDATE player SET payload=?", (json.dumps(payload),))
    service = SaveService(path)
    assert service.list_slots()[0].class_id == service.load(1).player.character_class == "warrior"


@pytest.mark.parametrize("version", (1, 2))
def test_failure_after_ddl_restores_schema_and_payloads(tmp_path, monkeypatch, version):
    path = tmp_path / "rollback.sqlite3"
    if version == 1:
        _, expected = legacy_database(path)
    else:
        expected = version_two_database(path, {1: full_snapshot()})[1]
    original = v3_slot_headers.migrate
    def fail(connection):
        original(connection)
        raise RuntimeError("injected failure after ALTER")
    monkeypatch.setattr(v3_slot_headers, "migrate", fail)
    with pytest.raises(RuntimeError, match="injected"):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version
        assert connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == version
        assert connection.execute("SELECT payload FROM player WHERE slot=1").fetchone()[0] == expected[0]
        assert connection.execute("SELECT payload FROM world WHERE slot=1").fetchone()[0] == expected[1]
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'legacy_%'").fetchall()
        assert "class_id" not in [row[1] for row in connection.execute("PRAGMA table_info(slot_metadata)")]
    assert len(list(tmp_path.glob("*.before-v3*.sqlite3"))) == 1


def test_corrupt_json_keeps_previous_schema_and_original_payload(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    version_two_database(path, {1: full_snapshot()})
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE player SET payload='invalid json'")
    with pytest.raises(json.JSONDecodeError):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT payload FROM player").fetchone()[0] == "invalid json"


def test_incomplete_slot_is_rejected_without_fabricating_world_state(tmp_path):
    path = tmp_path / "incomplete.sqlite3"
    version_two_database(path, {1: full_snapshot()})
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM world")
    with pytest.raises(sqlite3.IntegrityError):
        Database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert not connection.execute("SELECT * FROM world").fetchall()


def test_preexisting_backup_is_never_overwritten(tmp_path):
    path = tmp_path / "previous.sqlite3"
    version_two_database(path, {1: full_snapshot()})
    existing = path.with_name(path.name + ".before-v3.sqlite3")
    existing.write_bytes(b"backup guardado pelo usuario")
    database = Database(path)
    assert existing.read_bytes() == b"backup guardado pelo usuario"
    assert database.backup_path != existing and database.backup_path.exists()


def test_backup_includes_committed_rows_still_in_wal(tmp_path):
    path = tmp_path / "wal.sqlite3"
    version_two_database(path, {1: full_snapshot()})
    with sqlite3.connect(path) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        payload = json.loads(writer.execute("SELECT payload FROM player").fetchone()[0])
        payload["souls"] = 4567
        writer.execute("UPDATE player SET payload=?", (json.dumps(payload),))
        writer.commit()
        assert path.with_name(path.name + "-wal").stat().st_size > 0
        database = Database(path)
        with sqlite3.connect(database.backup_path) as backup:
            restored = json.loads(backup.execute("SELECT payload FROM player").fetchone()[0])
            assert restored["souls"] == 4567
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 2
        assert SaveService(path).load(1).player.souls == 4567


def test_parallel_initialization_migrates_once_and_produces_one_backup(tmp_path):
    path, gate = tmp_path / "race.sqlite3", Barrier(4)
    version_two_database(path, {1: class_snapshot("mage")})
    def open_database(_):
        gate.wait()
        return SaveService(path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        services = list(pool.map(open_database, range(4)))
    assert sum(service.repository.database.backup_path is not None for service in services) == 1
    assert all(service.load(1) == class_snapshot("mage") for service in services)
    assert len(list(tmp_path.glob("*.before-v3*.sqlite3"))) == 1


def test_newer_schema_is_rejected_without_changing_file_bytes(tmp_path):
    path = tmp_path / "future.sqlite3"
    version_two_database(path, {})
    with sqlite3.connect(path) as connection:
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="mais recente"):
        Database(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*.before-v3*.sqlite3"))
