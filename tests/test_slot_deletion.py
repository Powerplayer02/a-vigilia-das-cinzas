"""Dupla confirmação, identidade do cabeçalho e isolamento entre processos."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest
from ui_fakes import BackendFake, ActionsFake
from test_save import full_snapshot
from vigilia.core.views import SlotView, SlotDeletionView, UICommandKind as C
from vigilia.save.service import SaveService
from vigilia.save.locks import SlotInUseError, SlotChangedError
from vigilia.ui.slot_select import SlotSelect


def screen_fixture():
    backend, actions = BackendFake(), ActionsFake()
    busy = [False]
    query = SimpleNamespace(slots=lambda: [SlotView(1), SlotView(2, "Vésper", 7, 3660,
        "patio_da_vigilia", "token", True, "warrior"), SlotView(3)],
        slot_deletion=lambda slot: SlotDeletionView(slot, "Vésper", 7, "warrior", "token", 187, busy[0]),
        slot_in_use=lambda slot: busy[0])
    return SlotSelect(backend, query, actions), backend, actions, busy


@pytest.mark.parametrize("stage", [0, 1])
def test_cancel_at_either_confirmation_never_calls_repository(stage):
    screen, backend, actions, _ = screen_fixture()
    screen.request_delete(2)
    assert screen.modal.grid.index == 0
    assert "Almas no local" in backend.nodes["front.modal.body"]["text"]
    if stage:
        screen.move(dx=1)
        screen.confirm()
        assert screen.modal.grid.index == 0 and screen.stage == 1
    screen.confirm()  # Cancelar tem foco inicial nas duas etapas.
    assert screen.modal is None and not actions.commands


def test_deletion_requires_two_explicit_accepts_and_busy_slot_disables_accept():
    screen, backend, actions, busy = screen_fixture()
    original_root = screen.root
    screen.request_delete(2)
    screen.move(dx=1)
    screen.confirm()
    assert screen.stage == 1 and not actions.commands
    busy[0] = True
    screen.tick(.3)
    assert not screen.modal.accept_button.enabled
    screen.accept_delete()
    assert not actions.commands
    busy[0] = False
    screen.tick(.3)
    screen.move(dx=1)
    screen.confirm()
    assert len(actions.commands) == 1 and actions.commands[0].kind == C.DELETE_SLOT
    assert json.loads(actions.commands[0].argument) == dict(slot=2, updated_at="token")
    assert screen.modal is None and screen.root is original_root


def test_slot_strings_switch_language_in_one_tick_without_rebuilding_screen():
    screen, backend, _, _ = screen_fixture()
    root = screen.root
    backend.localizer.set_language("en_US")
    screen.tick(1 / 60)
    assert "Warrior" in backend.nodes["front.slot.2"]["text"]
    assert backend.nodes["front.delete.2"]["text"] == "Delete" and screen.root is root


def test_new_game_focuses_empty_destination_instead_of_delete_button():
    backend, actions = BackendFake(), ActionsFake()
    query = SimpleNamespace(slots=lambda: [SlotView(1, "Vésper", occupied=True), SlotView(2), SlotView(3)])
    screen = SlotSelect(backend, query, actions, empty_only=True)
    assert screen.grid.buttons[screen.grid.index].key == "front.slot.2"
    screen.confirm()
    assert actions.commands[-1].kind == C.SELECT_NEW_SLOT and actions.commands[-1].argument == "2"


WORKER = """
import sys
from pathlib import Path
from vigilia.save.service import SaveService
service = SaveService(Path(sys.argv[1]))
service.acquire(1)
print('locked', flush=True)
sys.stdin.readline()
snapshot = service.load(1)
assert snapshot.player.bloodstain_souls == 187
service.save(1, snapshot)
service.close()
print('saved', flush=True)
"""


@pytest.mark.parametrize("kill", [False, True])
def test_subprocess_slot_one_lease_does_not_block_slot_two_delete(tmp_path, kill):
    path = tmp_path / "slots.sqlite3"
    service = SaveService(path)
    snapshot = full_snapshot()
    service.create(1, snapshot)
    service.create(2, snapshot)
    env = os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    child = subprocess.Popen([sys.executable, "-c", WORKER, str(path)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        assert child.stdout.readline().strip() == "locked"
        assert service.in_use(1) and not service.in_use(2)
        with pytest.raises(SlotInUseError):
            service.delete(1)
        assert service.delete(2) and service.load(2) is None
        assert service.load(1) == snapshot
        if kill:
            child.kill()
            child.communicate(timeout=10)
        else:
            out, err = child.communicate("release\n", timeout=10)
            assert child.returncode == 0 and "saved" in out, err
        assert not service.in_use(1) and service.load(1) == snapshot
        assert service.delete(1)
        with sqlite3.connect(path) as connection:
            for table in ("slots", "player", "world", "slot_metadata"):
                assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)


def test_changed_header_refuses_stale_deletion_and_global_writer_returns_promptly(tmp_path):
    service = SaveService(tmp_path / "slots.sqlite3")
    snapshot = full_snapshot()
    service.create(2, snapshot)
    stale = service.list_slots()[1].updated_at
    service.save(2, snapshot)
    with pytest.raises(SlotChangedError):
        service.delete(2, expected_updated_at=stale)
    with sqlite3.connect(service.repository.database.path) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValueError, match="slots.busy"):
            service.delete(2)
    assert service.load(2) == snapshot and not service.in_use(2)
