"""HUD consome consultas imutáveis. Atualiza apenas propriedades alteradas."""

from vigilia.core.protocols import ICombatHUDQuery, IUIBackend
from vigilia.ui.widgets import Panel, Label, Bar, Sprite
from vigilia.ui.text_render import SECONDARY, GOLD, MUTED
from vigilia.core.palette import PALETTE


class HUD:
    def __init__(self, backend: IUIBackend, query: ICombatHUDQuery):
        self.backend, self.query = backend, query
        self.root = Panel(backend, "hud", (0, 0, 1280, 720), color=(0, 0, 0, 0))
        Panel(backend, "hud.vitals", (24, 516, 302, 180), parent="hud")
        Sprite(backend, "hud.hp_icon", "heart", (16, 10, 24, 24), parent="hud.vitals")
        self.hp_text = Label(backend, "hud.hp_text", "", (48, 14, 236, 24), parent="hud.vitals", size=SECONDARY)
        self.hp = Bar(backend, "hud.hp", (18, 41, 266, 14), PALETTE["hp"], parent="hud.vitals")
        Sprite(backend, "hud.stamina_icon", "stamina", (18, 58, 20, 20), parent="hud.vitals")
        self.stamina_text = Label(backend, "hud.stamina_text", "", (48, 59, 236, 20), parent="hud.vitals", size=SECONDARY)
        self.stamina = Bar(backend, "hud.stamina", (18, 83, 266, 9), PALETTE["stamina"], parent="hud.vitals")
        self.statuses = Label(backend, "hud.statuses", "", (18, 101, 274, 22), parent="hud.vitals", size=SECONDARY, color=GOLD)
        self.condition_icons = [Sprite(backend, f"hud.condition.{i}", name, (20+i*28, 121, 18, 18), parent="hud.vitals")
                                for i,name in enumerate(("bleed","poison","frost","curse"))]
        self.condition_state = None
        self.spell_visible = None
        Sprite(backend, "hud.soul_icon", "soul", (18, 141, 26, 26), parent="hud.vitals")
        self.souls = Label(backend, "hud.souls", "", (52, 139, 234, 28), parent="hud.vitals", color=GOLD)
        Panel(backend, "hud.equipment", (978, 446, 278, 250), parent="hud")
        Panel(backend, "hud.spell.icon", (16, 12, 50, 50), parent="hud.equipment", color=(.12, .20, .26, 1))
        self.glyph = Sprite(backend, "hud.spell.glyph", "spell", (20, 16, 42, 42), parent="hud.equipment")
        self.spell_label = Label(backend, "hud.spell.label", "", (80, 10, 184, 56), parent="hud.equipment", size=SECONDARY)
        self.cooldown = Bar(backend, "hud.spell.cooldown", (16, 68, 246, 5), PALETTE["mana"], parent="hud.equipment")
        self.spell_info = Label(backend, "hud.spell.info", "", (16, 84, 246, 32), parent="hud.equipment", size=SECONDARY)
        Panel(backend, "hud.separator", (16, 124, 246, 1), parent="hud.equipment", color=PALETTE["border"])
        Panel(backend, "hud.quick_icon", (16, 138, 48, 48), parent="hud.equipment", color=(.18, .15, .10, 1))
        Sprite(backend, "hud.quick_glyph", "flask", (20, 141, 40, 40), parent="hud.equipment")
        self.quick = Label(backend, "hud.quick", "", (80, 132, 184, 64), parent="hud.equipment", size=SECONDARY, color=MUTED)
        self.weapon_icon = Sprite(backend, "hud.weapon_icon", "sword", (18, 205, 26, 26), parent="hud.equipment")
        self.weapon = Label(backend, "hud.weapon", "", (50, 207, 214, 32), parent="hud.equipment", size=SECONDARY)
        self.message = Label(backend, "hud.message", "", (350, 560, 650, 70), parent="hud", size=SECONDARY, color=GOLD)
        self._accessibility = None
        self.boss_panel = Panel(backend, "hud.boss", (362, 636, 556, 58), parent="hud")
        self.boss_name = Label(backend, "hud.boss.name", "", (14, 4, 532, 26), parent="hud.boss")
        self.boss_hp = Bar(backend, "hud.boss.hp", (14, 40, 528, 9), PALETTE["hp"], parent="hud.boss")
        self.boss_panel.hide()
        self.boss_visible = False

    def accessibility(self, scale, contrast):
        if self._accessibility == (scale, contrast):
            return
        self._accessibility = (scale, contrast)
        if hasattr(self.backend, "scale_at"):
            self.backend.scale_at("hud.vitals", scale, "bottom_left")
            self.backend.scale_at("hud.equipment", scale, "bottom_right")
            self.backend.scale_at("hud.boss", scale, "top_center" if scale > 1.05 else "bottom_center")
            self.backend.scale_at("hud.message", min(scale, 1.2), "top_message" if scale > 1.05 else "bottom_center")
        self.backend.color("hud.hp.fill", (1, .9, .25, 1) if contrast else PALETTE["hp"])
        self.backend.color("hud.stamina.fill", (.1, .9, 1, 1) if contrast else PALETTE["stamina"])
        for panel in ("hud.vitals", "hud.equipment", "hud.boss"):
            self.backend.color(panel, (0, 0, 0, 1) if contrast else PALETTE["panel"])
        for label in ("hud.hp_text", "hud.stamina_text", "hud.quick", "hud.spell.info"):
            self.backend.color(label, (1, 1, 1, 1) if contrast else PALETTE["ink"])

    def tick(self) -> None:
        view = self.query.player_vitals()
        self.hp.set(view.hp, view.max_hp)
        self.stamina.set(view.stamina, view.max_stamina)
        tr = self.backend.t
        self.hp_text.set(tr("hud.hp", value=f"{view.hp:.0f}", maximum=f"{view.max_hp:.0f}"))
        self.stamina_text.set(tr("hud.stamina", value=f"{view.stamina:.0f}", maximum=f"{view.max_stamina:.0f}"))
        self.souls.set(tr("hud.souls", value=f"{view.souls:,}".replace(",", ".")))
        self.weapon.set(view.weapon)
        self.quick.set(tr("hud.quick") + "\n" + (view.quick_item if view.quick_count else tr("hud.empty")) +
            (f" ×{view.quick_count}" if view.quick_count else ""))
        spell = bool(view.spell_name)
        if spell != self.spell_visible:
            self.spell_visible = spell
            self.glyph.show() if spell else self.glyph.hide()
        self.spell_label.set(tr("hud.spell") + (f" [{view.spell_hint}]" if view.spell_hint else "") + "\n" +
            (view.spell_name if spell else tr("hud.spell.empty")))
        self.glyph.set("healing" if view.spell_kind == "healing" else "spell")
        self.weapon_icon.set(view.weapon_icon)
        self.cooldown.set(view.spell_remaining, view.spell_duration)
        state = (f"{view.spell_remaining:.1f}s" if view.spell_remaining else tr("hud.spell.ready") if view.spell_ready
                 else tr("hud.spell.no_stamina") if view.stamina < view.spell_stamina else tr("hud.spell.busy"))
        self.spell_info.set(tr("hud.spell.resource", cost=f"{view.spell_stamina:.0f}", state=state) if spell else "")
        self.message.set(view.message)
        statuses = self.query.active_statuses()
        active = frozenset(status.id for status in statuses)
        if active != self.condition_state:
            self.condition_state = active
            for icon, name in zip(self.condition_icons, ("bleed","poison","frost","curse")):
                icon.show() if name in active else icon.hide()
        self.statuses.set("   ".join(
            f"[{status.icon}] {status.stacks}×" if status.stacks else f"[{status.icon}] {status.buildup:.0f}%"
            for status in statuses))
        boss = self.query.active_boss()
        if (boss is not None) != self.boss_visible:
            self.boss_panel.show() if boss is not None else self.boss_panel.hide()
            self.boss_visible = boss is not None
        if boss is not None:
            self.boss_name.set(tr("hud.boss", name=boss.name, phase=boss.phase))
            self.boss_hp.set(boss.hp, boss.max_hp)
