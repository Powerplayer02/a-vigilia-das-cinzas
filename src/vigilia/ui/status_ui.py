"""Status somente por IStatsQuery."""

from vigilia.core.protocols import IStatsQuery
from vigilia.ui.widgets import Label
from vigilia.ui.text_render import TITLE, SECONDARY, GOLD


class StatusUI:
    def __init__(self, backend, query: IStatsQuery):
        view = query.current()
        Label(backend, "menu.status.title", backend.t("status.level", level=view.level), (424, 146, 580, 38), parent="menu", size=TITLE, color=GOLD)
        Label(backend, "menu.status.souls", backend.t("status.souls", souls=view.souls, cost=query.next_level_cost()),
              (424, 198, 610, 28), parent="menu")
        for index, stat in enumerate(view.attributes):
            Label(backend, f"menu.status.{stat.id}", stat.name,
                  (424, 254 + index * 37, 218, 30), parent="menu")
            Label(backend, f"menu.status.{stat.id}.value", str(stat.value),
                  (654, 254 + index * 37, 62, 30), parent="menu", color=GOLD)
        derived = backend.t("status.derived", hp=f"{view.max_hp:.0f}", stamina=f"{view.max_stamina:.0f}",
                            poise=f"{view.poise:.0f}", weight=f"{view.weight:.1f}", capacity=f"{view.capacity:.0f}", mobility=view.mobility)
        Label(backend, "menu.status.derived", derived, (742, 254, 340, 180), parent="menu", size=SECONDARY)
        Label(backend, "menu.status.resistances", backend.t("status.resistances") + "\n" + "\n".join(f"{name}  {value:.1f}" for name, value in view.resistances),
              (742, 422, 340, 180), parent="menu", size=SECONDARY)
