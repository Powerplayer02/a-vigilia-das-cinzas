from types import SimpleNamespace
from combat_fakes import PhysicsFake
from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import HeldState, InputEdge
from vigilia.player.advanced_movement import AdvancedMovement
from vigilia.player.controller import PlayerController
from vigilia.player.movesets import LONGSWORD
from vigilia.player.state_machine import CombatController


class AgileBodyFake(PhysicsFake):
    def __init__(self):
        super().__init__()
        self.crouched, self.on_ground, self.blocked = False, True, False
        self.jump_speed = 0

    def set_crouched(self, enabled):
        if not enabled and self.blocked:
            return False
        self.crouched = enabled
        return True

    def grounded(self):
        return self.on_ground

    def jump(self, speed):
        if not self.on_ground:
            return False
        self.jump_speed, self.on_ground = speed, False
        return True


def scene():
    body, fighter, events = AgileBodyFake(), Fighter(0, LONGSWORD.weapon), []
    player = PlayerController(body, Transform())
    player.advanced = AdvancedMovement(body, emit=events.append)
    combat = CombatController(fighter, player.transform)
    combat.movement = player.advanced
    def step(action=None, held=HeldState(), pressed=True):
        edge = InputEdge(action, pressed) if action is not None else None
        combat.update(held, edge, Vec3(0, 1), dodging=player.dodging, critical=None)
        busy = fighter.attack is not None or fighter.parry_step >= 0 or combat.charge > 0
        player.update(held, edge, Vec3(0, 1), Vec3(1, 0), locked=False, fighter=fighter, busy=busy)
        return player.velocity
    return SimpleNamespace(body=body, fighter=fighter, events=events, player=player,
        movement=player.advanced, combat=combat, step=step)
