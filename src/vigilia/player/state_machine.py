"""Transições de ataque, carga, guarda e parry do jogador."""

import math
from dataclasses import replace
from enum import StrEnum, auto

from vigilia.combat.attack import AttackKind
from vigilia.combat.damage import DamagePacket
from vigilia.combat.fighter import Fighter
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.types import Action, HeldState, InputEdge
from vigilia.core.timing import CHARGE_STEPS
from vigilia.model.inventory import Inventory
from vigilia.model.items import Weapon, PLAYER_WEAPON_IDS, WEAPONS
from vigilia.model.spells import SPELLS
from vigilia.model.snapshots import ControlSnapshot
from vigilia.player.movesets import AXE, LONGSWORD, for_weapon


class CombatState(StrEnum):
    READY = auto()
    CHARGING = auto()
    BLOCK = auto()
    PARRY = auto()
    HIT_REACT = auto()
    DEATH = auto()
    KNOCKDOWN = auto()


class CombatController:
    """Executa ações discretas e os buffers de combo e carga."""

    def __init__(self, fighter: Fighter, transform: Transform, inventory: Inventory | None = None, *, aim_source=None) -> None:
        self.fighter = fighter
        self.transform = transform
        self.moveset = for_weapon(fighter.weapon) if fighter.weapon.spec_id else LONGSWORD
        self.inventory = inventory
        self.aim_source = aim_source
        self.charge = 0
        self.combo_buffered = False

    @property
    def state(self) -> CombatState | AttackKind:
        fighter = self.fighter
        if not fighter.alive:
            return CombatState.DEATH
        if fighter.knockdown_steps:
            return CombatState.KNOCKDOWN
        if fighter.stagger_steps:
            return CombatState.HIT_REACT
        if fighter.attack is not None:
            return fighter.attack.definition.kind
        if fighter.parry_step >= 0:
            return CombatState.PARRY
        if self.charge:
            return CombatState.CHARGING
        return CombatState.BLOCK if fighter.blocking else CombatState.READY

    def update(self, held: HeldState, edge: InputEdge | None, facing: Vec3, *, dodging: bool,
               critical: tuple[int, Vec3, AttackKind] | None) -> None:
        """Aplica uma borda e avança a intenção antes do movimento."""
        fighter = self.fighter
        fighter.blocking = False
        if not fighter.alive or fighter.stagger_steps:
            self.charge = 0
            self.combo_buffered = False
            return
        pressed = edge.action if edge is not None and edge.pressed else None
        if dodging:
            self.charge = 0
            return
        attack = fighter.attack
        if attack is not None:
            combo = attack.definition.cancel_from
            self.combo_buffered |= pressed == Action.LIGHT and combo is not None
            if self.combo_buffered and combo is not None and attack.age >= combo:
                index = next(i for i, move in enumerate(self.moveset.light) if move.kind == attack.definition.kind)
                fighter.start(self.moveset.light[index + 1])
                self.combo_buffered = False
            return
        self.combo_buffered = False
        if fighter.parry_step >= 0:
            return
        if pressed == Action.SWAP_WEAPON and not self.charge:
            owned = [key for key in PLAYER_WEAPON_IDS if self.inventory is None or
                     (self.inventory.items.get(key, 0) and fighter.stats.meets(WEAPONS[key].requirements))]
            if self.inventory is None:
                owned = ["longsword", "axe"]
            if not owned:
                return
            current = owned.index(self.moveset.weapon.spec_id) if self.moveset.weapon.spec_id in owned else -1
            key = owned[(current + 1) % len(owned)]
            weapon = self.inventory.equip(key, fighter.stats) if self.inventory is not None else (
                AXE.weapon if key == "axe" else LONGSWORD.weapon)
            self.equip(weapon)
        if pressed == Action.CAST and not self.charge and self.inventory is not None:
            spell = next((SPELLS[key] for key in self.inventory.spells
                          if SPELLS[key].can_cast(fighter.stats, fighter.weapon.spec_id)), None)
            if spell is not None and (not spell.attack.healing or fighter.hp < fighter.max_hp):
                self._face(facing)
                fighter.start(spell.attack, aim=self.aim_source() if self.aim_source is not None else None)
            return
        if pressed == Action.PARRY and fighter.spend(18):
            self.charge = 0
            self._face(facing)
            fighter.parry_step = 0
            return
        if pressed == Action.HEAVY and not self.charge:
            self.charge = 1
        if self.charge:
            released = edge == InputEdge(Action.HEAVY, False)
            if released or self.charge >= CHARGE_STEPS:
                move = self.moveset.heavy
                power = 1 + .65 * self.charge / CHARGE_STEPS
                packet = DamagePacket(
                    physical_slash=move.packet.physical_slash * power,
                    physical_strike=move.packet.physical_strike * power,
                    physical_pierce=move.packet.physical_pierce * power,
                    fire=move.packet.fire * power, magic=move.packet.magic * power,
                    holy=move.packet.holy * power,
                    poise=move.packet.poise * power,
                )
                if fighter.start(replace(move, packet=packet)):
                    self._face(facing)
                self.charge = 0
            else:
                self.charge += 1
            return
        if pressed == Action.LIGHT:
            if critical is not None:
                victim, direction, kind = critical
                move = self.moveset.riposte if kind == AttackKind.RIPOSTE else self.moveset.backstab
                if fighter.start(move, victim):
                    self._face(direction)
                return
            running = Action.RUN in held.actions and (held.move_x or held.move_y)
            if fighter.start(self.moveset.running if running else self.moveset.light[0]):
                self._face(facing)
            return
        if Action.BLOCK in held.actions and fighter.stamina > 0:
            fighter.blocking = True
            self._face(facing)

    def _face(self, direction: Vec3) -> None:
        self.transform.yaw = math.atan2(direction.x, direction.y)

    def equip(self, weapon: Weapon) -> None:
        self.moveset = for_weapon(weapon)
        self.fighter.weapon = weapon

    def to_snapshot(self) -> ControlSnapshot:
        return ControlSnapshot(self.charge, self.combo_buffered)

    def from_snapshot(self, snapshot: ControlSnapshot) -> None:
        self.equip(self.fighter.weapon)
        self.charge, self.combo_buffered = snapshot.charge, snapshot.combo_buffered
