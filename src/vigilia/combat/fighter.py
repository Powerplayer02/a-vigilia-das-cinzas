"""Estado ECS compartilhado por personagens que usam o combate."""

from dataclasses import dataclass, field
from collections.abc import Callable

from vigilia.combat.attack import Attack, AttackDefinition
from vigilia.combat.status import StatusEffect, StatusStack
from vigilia.core.timing import (
    FIXED_HZ, STAMINA_REGEN_DELAY_STEPS, PARRY_RECOVERY_STEPS, STAGGER_COOLDOWN_STEPS,
)
from vigilia.model.items import Weapon
from vigilia.model.items import WEAPONS
from vigilia.model.snapshots import FighterSnapshot, AttackSnapshot
from vigilia.core.mathx import Vec3
from vigilia.model.stats import ResistBlock, StatsBlock


@dataclass(slots=True)
class Fighter:
    team: int
    weapon: Weapon
    stats: StatsBlock = field(default_factory=StatsBlock)
    resist: ResistBlock = field(default_factory=ResistBlock)
    hp: float = field(init=False)
    stamina: float = field(init=False)
    poise: float = field(init=False)
    status: StatusStack = field(default_factory=StatusStack)
    regen_delay: int = 0
    attack: Attack | None = None
    parry_step: int = -1
    stagger_steps: int = 0
    riposte_steps: int = 0
    blocking: bool = False
    invulnerable: bool = False
    hit_steps: int = 0
    stagger_cooldown_steps: int = 0
    knockdown_steps: int = 0
    riposte_hits_remaining: int = 1
    body_scale: float = 1
    backstab_immune: bool = False
    status_damage_blocked: bool = False
    on_attack: Callable[[AttackDefinition], None] | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        self.restore()

    def restore(self) -> None:
        """Restaura os recursos e encerra ações e condições temporárias."""
        self.status = StatusStack()
        self.hp = self.max_hp
        self.stamina = self.stats.max_stamina
        self.poise = self.stats.max_poise
        self.regen_delay = 0
        self.attack = None
        self.parry_step = -1
        self.stagger_steps = 0
        self.riposte_steps = 0
        self.blocking = False
        self.invulnerable = False
        self.hit_steps = 0
        self.stagger_cooldown_steps = 0
        self.knockdown_steps = 0
        self.riposte_hits_remaining = 1
        self.status_damage_blocked = False

    @property
    def max_hp(self) -> float:
        return self.stats.max_hp * (.7 if StatusEffect.CURSE in self.status.active else 1)

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def spend(self, amount: float) -> bool:
        """Debita estamina caso haja saldo e suspende a regeneração."""
        if self.stamina + 1e-7 < amount:
            return False
        self.stamina = max(0, self.stamina - amount)
        self.regen_delay = STAMINA_REGEN_DELAY_STEPS
        return True

    def start(self, attack: AttackDefinition, victim: int | None = None, aim: Vec3 | None = None) -> bool:
        """Converte uma intenção em instância de ataque."""
        if not self.alive or self.stagger_steps or self.parry_step >= 0 or not self.spend(attack.stamina):
            return False
        self.attack = Attack(attack, victim=victim, aim=aim)
        if self.on_attack is not None:
            self.on_attack(attack)
        return True

    def interrupt(self, steps: int) -> None:
        """Interrompe ataque e guarda e inicia stagger."""
        self.attack = None
        self.parry_step = -1
        self.blocking = False
        self.stagger_steps = steps
        self.poise = self.stats.max_poise
        self.stagger_cooldown_steps = STAGGER_COOLDOWN_STEPS

    def tick(self) -> None:
        """Avança timers após resolver o contato do passo atual."""
        if not self.alive:
            return
        status_damage = self.status.tick()
        self.hp = max(0.0, min(self.max_hp, self.hp - (0 if self.status_damage_blocked else status_damage)))
        self.stagger_steps = max(0, self.stagger_steps - 1)
        self.riposte_steps = max(0, self.riposte_steps - 1)
        self.hit_steps = max(0, self.hit_steps - 1)
        self.stagger_cooldown_steps = max(0, self.stagger_cooldown_steps - 1)
        self.knockdown_steps = max(0, self.knockdown_steps - 1)
        if self.attack is not None:
            self.attack.age += 1
            if self.attack.age >= self.attack.definition.duration:
                self.attack = None
        if self.parry_step >= 0:
            self.parry_step += 1
            if self.parry_step >= PARRY_RECOVERY_STEPS:
                self.parry_step = -1
        if self.regen_delay:
            self.regen_delay -= 1
        elif not self.blocking:
            rate = 13 if StatusEffect.FROST in self.status.active else 30
            self.stamina = min(self.stats.max_stamina, self.stamina + rate / FIXED_HZ)
        if not self.hit_steps:
            self.poise = min(self.stats.max_poise, self.poise + 18 / FIXED_HZ)

    def to_snapshot(self, actor_keys: dict[int, str]) -> FighterSnapshot:
        """Captura recursos, condições e alvos já atingidos com IDs estáveis."""
        attack = None
        if self.attack is not None:
            attack = AttackSnapshot(
                self.attack.definition, self.attack.age,
                tuple(sorted(actor_keys[target] for target in self.attack.hit_targets if target in actor_keys)),
                actor_keys.get(self.attack.victim),
                self.attack.aim, self.attack.fired,
            )
        return FighterSnapshot(
            self.weapon.spec_id, self.weapon.upgrade, self.stats, self.resist,
            self.hp, self.stamina, self.poise,
            {effect.value: amount for effect, amount in self.status.buildup.items()},
            {effect.value: time for effect, time in self.status.active.items()},
            self.regen_delay, attack, self.parry_step, self.stagger_steps, self.riposte_steps,
            self.blocking, self.invulnerable, self.hit_steps, self.stagger_cooldown_steps,
            self.knockdown_steps, self.riposte_hits_remaining,
        )

    def from_snapshot(self, snapshot: FighterSnapshot, actor_ids: dict[str, int]) -> None:
        """Restaura um snapshot validado sem refletir atributos privados."""
        self.weapon = WEAPONS[snapshot.weapon_id].instantiate(snapshot.upgrade)
        self.stats, self.resist = snapshot.stats, snapshot.resist
        self.hp, self.stamina, self.poise = snapshot.hp, snapshot.stamina, snapshot.poise
        self.status = StatusStack(
            {StatusEffect(effect): amount for effect, amount in snapshot.buildup.items()},
            {StatusEffect(effect): time for effect, time in snapshot.active_status.items()},
        )
        attack = snapshot.attack
        self.attack = None if attack is None else Attack(
            attack.definition, attack.age, {actor_ids[key] for key in attack.hit_targets},
            actor_ids[attack.victim] if attack.victim is not None else None,
            attack.aim, attack.fired,
        )
        self.regen_delay, self.parry_step = snapshot.regen_delay, snapshot.parry_step
        self.stagger_steps, self.riposte_steps = snapshot.stagger_steps, snapshot.riposte_steps
        self.blocking, self.invulnerable = snapshot.blocking, snapshot.invulnerable
        self.hit_steps = snapshot.hit_steps
        self.stagger_cooldown_steps = snapshot.stagger_cooldown_steps
        self.knockdown_steps = snapshot.knockdown_steps
        self.riposte_hits_remaining = snapshot.riposte_hits_remaining
