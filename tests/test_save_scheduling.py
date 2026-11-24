"""Persistência síncrona só em limites seguros, usando o estado mais recente."""

from types import SimpleNamespace

from vigilia.core.events import SaveRequestedEvent
from vigilia.core.types import GameState
from vigilia.game import Game


def make_game():
    game = Game.__new__(Game)
    game._app = SimpleNamespace(state=GameState.PLAYING)
    game.active_slot = 2
    game._pending_save = None
    game.balance = 10
    game.calls, game.messages = [], []
    game._save = SimpleNamespace(save=lambda slot, snapshot: game.calls.append((slot, snapshot)))
    game.build_snapshot = lambda: game.balance
    game._notify = game.messages.append
    return game


def test_combat_coalesces_without_io_and_bonfire_saves_latest_snapshot_once():
    game = make_game()
    for reason in ("enemy_death", "death", "boss_defeated", "bloodstain", "manual"):
        game._on_save_requested(SaveRequestedEvent(1, reason))
        game._flush_save()
    assert game.calls == []
    game.balance = 75
    game._on_save_requested(SaveRequestedEvent(1, "bonfire"))
    # Outro evento no mesmo passo não apaga a permissão da fogueira.
    game._on_save_requested(SaveRequestedEvent(1, "equipment"))
    game._flush_save()
    game._flush_save()
    assert game.calls == [(2, 75)] and game._pending_save is None


def test_pause_and_transitions_are_safe_boundaries():
    for reason in ("area_change", "respawn", "main_menu"):
        game = make_game()
        game._on_save_requested(SaveRequestedEvent(1, reason))
        game._flush_save()
        assert game.calls == [(2, 10)]
        game._on_save_requested(SaveRequestedEvent(1, "enemy_death"))
        game._flush_save()
        assert len(game.calls) == 1
    game._app.state = GameState.PAUSED
    game._flush_save()
    assert len(game.calls) == 2


def test_failed_write_keeps_pending_snapshot_for_next_safe_boundary():
    game = make_game()
    def fail(*args):
        raise OSError("disco indisponível")
    game._save.save = fail
    game._on_save_requested(SaveRequestedEvent(1, "bonfire"))
    game._flush_save()
    assert game._pending_save is not None and "Falha" in game.messages[-1]
    game._save.save = lambda slot, snapshot: game.calls.append((slot, snapshot))
    game._flush_save()
    assert game.calls == []  # não tenta novamente a cada passo de combate
    game.balance = 99
    game._on_save_requested(SaveRequestedEvent(1, "area_change"))
    game._flush_save()
    assert game.calls == [(2, 99)]


def test_quit_discards_dirty_state_without_requesting_or_flushing_a_save():
    from vigilia.core.types import AppState
    game = make_game()
    events, transitions = [], []
    game._has_session = True
    game._pending_save = SaveRequestedEvent(2, "enemy_death")
    game._bus = SimpleNamespace(publish=events.append)
    game.flow = SimpleNamespace(current=AppState.PLAYING, transition=transitions.append)
    game._flush_save = lambda: (_ for _ in ()).throw(AssertionError("save no shutdown"))
    game.request_quit()
    assert not events and not game.calls
    assert game._pending_save is None and transitions == [AppState.QUIT]


def test_legacy_quit_event_is_not_a_checkpoint():
    game = make_game()
    game._on_save_requested(SaveRequestedEvent(2, "quit"))
    game._flush_save()
    assert game._pending_save is None and not game.calls


def test_checkpoint_presents_cover_before_write_and_reveals_on_failure():
    game, order = make_game(), []
    game._polish = SimpleNamespace(cover_now=lambda: order.append("black presented"),
        reveal=lambda: order.append("reveal"))
    def write(*args):
        order.append("commit")
        raise OSError("disco indisponível")
    game._save.save = write
    game._on_save_requested(SaveRequestedEvent(2, "bonfire"))
    game._flush_save()
    assert order == ["black presented", "commit", "reveal"]
    assert game._pending_save is not None
