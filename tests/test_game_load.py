"""Restaurar o slot ativo precisa realmente aplicar o snapshot sob o lease."""

from vigilia.game import Game
from vigilia.save.service import SaveService
from test_save import full_snapshot


def test_f9_load_applies_snapshot_and_keeps_active_lease(tmp_path):
    game = Game.__new__(Game)
    game._save = SaveService(tmp_path / "slots.sqlite3")
    game.active_slot = 2
    applied, messages = [], []
    game.apply_snapshot = applied.append
    game._notify = messages.append
    assert not game.load_game() and not game._save.in_use(2)
    snapshot = full_snapshot()
    game._save.create(2, snapshot)
    assert game.load_game() and applied == [snapshot] and game._save.in_use(2)
    assert game.load_game() and applied == [snapshot, snapshot]
    game._save.close()


def test_failed_load_releases_only_lease_it_just_acquired(tmp_path):
    game = Game.__new__(Game)
    game._save = SaveService(tmp_path / "slots.sqlite3")
    game.active_slot = 1
    game._save.create(1, full_snapshot())
    def fail(snapshot):
        raise ValueError("incompatible area")
    game.apply_snapshot = fail
    game._notify = lambda message: None
    assert not game.load_game() and not game._save.in_use(1)
    game._save.acquire(1)
    assert not game.load_game() and game._save.in_use(1)
    game._save.close()
