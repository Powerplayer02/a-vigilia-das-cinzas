"""Recompensas, curva por faixa e ciclo de perda e recuperação de almas."""

import pytest

from vigilia.core.mathx import Vec3
from vigilia.model.items import DUMMY_SOULS
from vigilia.model.progression import Progression, level_cost
from vigilia.model.stats import StatsBlock


def test_kill_pays_first_level_and_vigor_recalculates_hp() -> None:
    stats, progress = StatsBlock(), Progression()
    reward = progress.gain(DUMMY_SOULS, stats)
    assert reward == level_cost(1) == 88
    raised = progress.level_up(stats, "vigor")
    assert raised.vigor == stats.vigor + 1
    assert raised.max_hp == stats.max_hp + 6
    assert progress.level == 2
    assert progress.souls == 0
    assert all(level_cost(level + 1) > level_cost(level) for level in range(1, 100))


def test_invalid_level_up_does_not_consume_souls() -> None:
    progress = Progression(souls=100)
    with pytest.raises(ValueError):
        progress.level_up(StatsBlock(vigor=99), "vigor")
    with pytest.raises(ValueError):
        progress.level_up(StatsBlock(), "unknown")
    assert progress.souls == 100 and progress.level == 1
    with pytest.raises(ValueError):
        Progression().level_up(StatsBlock(), "vigor")


def test_bloodstain_recovers_once_and_next_death_replaces_it() -> None:
    progress = Progression(souls=200)
    progress.die(Vec3(4, 5, 1))
    assert progress.souls == 0
    assert progress.recover(Vec3()) == 0
    assert progress.recover(Vec3(4, 4, 1)) == 200
    assert progress.souls == 200 and progress.bloodstain is None
    assert progress.recover(Vec3(4, 5, 1)) == 0
    progress.die(Vec3(4, 5, 1))
    progress.souls = 17
    progress.die(Vec3(-1, 2, 1))
    assert progress.bloodstain.souls == 17
    progress.die(Vec3())
    assert progress.bloodstain is None


def test_luck_changes_reward_without_randomness() -> None:
    assert Progression().gain(100, StatsBlock(luck=20)) == 120
    assert Progression().gain(100, StatsBlock(luck=20)) == 120
