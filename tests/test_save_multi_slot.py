"""Criação, remoção e concorrência sem modificar os slots vizinhos."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from contextlib import contextmanager
import sqlite3
from threading import Barrier
import pytest

from test_character_creation import class_snapshot
from test_save import full_snapshot
from vigilia.save.service import SaveService
from vigilia.save.serializers import SaveFormatError


def test_list_slots_always_returns_three_ordered_destinations(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    rows = service.list_slots()
    assert [row.slot for row in rows] == [1, 2, 3]
    assert all(not row.occupied and row.class_id == row.created_at == row.updated_at == "" for row in rows)
    assert service.list() == []


def test_create_load_metadata_and_reopen_three_independent_slots(tmp_path):
    path = tmp_path / "slots.sqlite3"
    service = SaveService(path)
    identities = {1: "knight", 2: "mage", 3: "cleric"}
    originals = {slot: class_snapshot(identity) for slot, identity in identities.items()}
    for slot, snapshot in originals.items():
        service.create(slot, snapshot)
    reopened = SaveService(path)
    for row in reopened.list_slots():
        assert row.occupied and row.class_id == identities[row.slot]
        assert row.created_at == row.updated_at and row.name == "Vésper"
        assert row.level == originals[row.slot].player.level
        assert reopened.load(row.slot) == originals[row.slot]


def test_create_refuses_occupied_slot_without_changing_header_or_payload(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    first, other = class_snapshot("mage"), class_snapshot("cleric")
    service.create(2, first)
    before = service.list_slots()
    with pytest.raises(ValueError, match="slots.occupied"):
        service.create(2, other)
    assert service.load(2) == first and service.list_slots() == before


def test_invalid_snapshot_cannot_leave_a_reserved_or_partial_slot(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    with pytest.raises(SaveFormatError):
        service.create(1, replace(full_snapshot(), timing_version=999))
    assert service.load(1) is None and not any(row.occupied for row in service.list_slots())


def test_header_insert_failure_cannot_reserve_slot_or_leave_player_and_world(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    with service.repository.database.connect() as connection:
        connection.execute("CREATE TRIGGER fail_header BEFORE INSERT ON slot_metadata BEGIN SELECT RAISE(ABORT,'stop'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.create(2, class_snapshot("mage"))
    assert service.load(2) is None and not service.list_slots()[1].occupied
    with service.repository.database.connect() as connection:
        for table in ("slots", "player", "world", "slot_metadata"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_header")
    service.create(2, class_snapshot("mage"))
    assert service.load(2) == class_snapshot("mage")


def test_saving_slot_two_changes_only_its_snapshot_and_update_time(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    class ControlledTime:
        @staticmethod
        def now(zone):
            return datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("vigilia.save.repositories.datetime", ControlledTime)
    service = SaveService(tmp_path / "slots.sqlite3")
    first = full_snapshot()
    for slot in (1, 2, 3):
        service.create(slot, first)
    before = service.list_slots()
    class LaterTime:
        @staticmethod
        def now(zone):
            return datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
    monkeypatch.setattr("vigilia.save.repositories.datetime", LaterTime)
    second = replace(first, player=replace(first.player, character_name="Outro", character_class="mage", playtime_sec=7201, souls=1000))
    service.save(2, second)
    after = service.list_slots()
    assert service.load(1) == service.load(3) == first and service.load(2) == second
    assert before[0] == after[0] and before[2] == after[2]
    assert after[1].created_at == before[1].created_at and after[1].updated_at > before[1].updated_at
    assert after[1].class_id == "mage" and after[1].playtime_sec == 7201


@pytest.mark.parametrize("removed", (1, 2, 3))
def test_delete_is_isolated_complete_and_idempotent(tmp_path, removed):
    service = SaveService(tmp_path / "slots.sqlite3")
    for slot in (1, 2, 3):
        service.create(slot, full_snapshot())
    before = service.list_slots()
    assert service.delete(removed) is True
    assert service.delete(removed) is False and service.load(removed) is None
    after = service.list_slots()
    for slot in (1, 2, 3):
        if slot != removed:
            assert after[slot - 1] == before[slot - 1] and service.load(slot) == full_snapshot()
    assert not after[removed - 1].occupied and len(service.list()) == 2
    with service.repository.database.connect() as connection:
        for table, column in (("slots", "id"), ("player", "slot"), ("world", "slot"), ("slot_metadata", "slot")):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=?", (removed,)).fetchone()[0] == 0
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()


def test_delete_failure_rolls_back_rows_already_removed(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    first = full_snapshot()
    service.create(2, first)
    before = service.list_slots()
    with service.repository.database.connect() as connection:
        connection.execute("CREATE TRIGGER fail_player_delete BEFORE DELETE ON player BEGIN SELECT RAISE(ABORT,'stop'); END")
    with pytest.raises(sqlite3.IntegrityError):
        service.delete(2)
    assert service.load(2) == first and service.list_slots() == before


def test_deleted_slot_can_be_created_with_another_class(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    service.create(1, class_snapshot("mage"))
    assert service.delete(1)
    second = class_snapshot("cleric")
    service.create(1, second)
    assert service.load(1) == second and service.list_slots()[0].class_id == "cleric"


@pytest.mark.parametrize("slot", (0, 4, -1, True, "1", None))
def test_all_mutations_reject_invalid_slots(tmp_path, slot):
    service = SaveService(tmp_path / "slots.sqlite3")
    for call in (lambda: service.create(slot, full_snapshot()), lambda: service.delete(slot),
                 lambda: service.save(slot, full_snapshot()), lambda: service.load(slot)):
        with pytest.raises(ValueError):
            call()
    assert service.list() == []


def test_two_simultaneous_creates_have_exactly_one_winner(tmp_path):
    service, gate = SaveService(tmp_path / "slots.sqlite3"), Barrier(2)
    def create(identity):
        snapshot = class_snapshot(identity)
        gate.wait()
        try:
            service.create(2, snapshot)
            return identity
        except ValueError as error:
            assert str(error) == "slots.occupied"
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ("mage", "cleric")))
    winner = next(identity for identity in results if identity)
    assert sum(identity is not None for identity in results) == 1
    assert service.load(2) == class_snapshot(winner)
    assert service.list_slots()[1].class_id == winner


def test_parallel_saves_to_distinct_slots_never_mix_player_and_world(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    def save(index):
        slot = index % 3 + 1
        original = class_snapshot(("knight", "mage", "cleric")[slot - 1])
        snapshot = replace(original, player=replace(original.player, souls=index),
                           world=replace(original.world, collected_items=(str(index),)))
        service.save(slot, snapshot)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(save, range(18)))
    for slot in (1, 2, 3):
        snapshot = service.load(slot)
        assert snapshot.world.collected_items == (str(snapshot.player.souls),)
        assert snapshot.player.souls % 3 + 1 == slot


def test_header_query_never_reads_or_decodes_player_and_world(tmp_path, monkeypatch):
    service = SaveService(tmp_path / "slots.sqlite3")
    service.create(2, class_snapshot("mage"))
    def forbidden(*args):
        raise AssertionError("Cabeçalhos não decodificam snapshots")
    monkeypatch.setattr("vigilia.save.repositories.decode", forbidden)
    original, queries = service.repository.database.connect, []
    @contextmanager
    def traced():
        with original() as connection:
            connection.set_trace_callback(queries.append)
            yield connection
    monkeypatch.setattr(service.repository.database, "connect", traced)
    assert service.list_slots()[1].class_id == "mage"
    assert any("FROM slot_metadata" in sql for sql in queries)
    assert not any("FROM player" in sql or "FROM world" in sql or "JOIN" in sql for sql in queries)
