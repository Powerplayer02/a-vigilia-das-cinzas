"""Protege as fronteiras dos pacotes, incluindo imports relativos e de tipagem."""

import ast
from importlib.util import resolve_name
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "vigilia"
ALLOWED = {
    "core": set(),
    "engine": {"core"},
    "model": {"core"},
    "entities": {"core", "model"},
    "combat": {"core", "model", "entities"},
    "ai": {"core", "model", "entities", "combat"},
    "player": {"core", "engine", "model", "entities", "combat"},
    "world": {"core", "engine", "model", "entities", "combat", "ai", "player"},
    "ui": {"core", "engine"},
    "save": {"core", "model"},
    "game": {"core", "engine", "model", "entities", "combat", "ai", "player", "world", "ui", "save"},
}
NATIVE = {"panda3d", "direct", "pygame", "numpy"}


def test_advanced_movement_has_no_combat_or_native_imports():
    source = SRC / 'player/advanced_movement.py'
    imports = [name for node in ast.walk(ast.parse(source.read_text(encoding='utf8')))
               for name in _imports(node, 'vigilia.player')]
    assert not any(name.startswith('vigilia.combat') or name.split('.')[0] in NATIVE for name in imports)


def test_player_does_not_add_combat_imports_for_momentum():
    allowed = {'controller.py': {'vigilia.combat.fighter'},
        'state_machine.py': {'vigilia.combat.attack', 'vigilia.combat.damage', 'vigilia.combat.fighter'}}
    for source in (SRC/'player').glob('*.py'):
        imports={name for node in ast.walk(ast.parse(source.read_text(encoding='utf8')))
            for name in _imports(node,'vigilia.player') if name.startswith('vigilia.combat')}
        assert imports==allowed.get(source.name,set())


def test_ai_has_no_import_permission_for_world_save_or_ui() -> None:
    assert ALLOWED["ai"].isdisjoint({"world", "save", "ui"})


def test_ui_only_sees_engine_and_core_contracts():
    assert ALLOWED["ui"] == {"core", "engine"}


def test_game_has_one_app_state_event_subscription():
    tree = ast.parse((SRC / "game.py").read_text(encoding="utf-8"))
    subscribers = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute) and node.func.attr == "subscribe" and node.args
        and isinstance(node.args[0], ast.Name) and node.args[0].id == "AppStateChangedEvent"]
    assert len(subscribers) == 1


def test_gameplay_has_no_direct_audio_or_particle_backend_imports():
    for layer in ("combat", "player", "world", "ai"):
        for source in (SRC / layer).glob("*.py"):
            imports = [name for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                       for name in _imports(node, f"vigilia.{layer}")]
            assert not any(name.startswith(("vigilia.engine.audio", "vigilia.engine.particles")) for name in imports)


def test_gameplay_never_calls_the_audio_player_directly():
    for layer in ("combat", "player", "world", "ai", "ui"):
        for source in (SRC / layer).glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf8"))
            assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"play_sfx", "play_music"} for node in ast.walk(tree)), source


def test_boss_and_fog_wall_have_event_only_dependencies():
    for relative, forbidden in (("ai/bosses.py", {"world", "save", "ui", "engine"}),
                                ("world/fog_wall.py", {"ai", "save", "ui"})):
        source = SRC / relative
        package = ".".join(("vigilia", *Path(relative).parts[:-1]))
        imports = [name for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                   for name in _imports(node, package)]
        assert not any(name.startswith(f"vigilia.{layer}") for name in imports for layer in forbidden)


def _imports(node: ast.AST, package: str) -> list[str]:
    if isinstance(node, ast.Import):
        return [item.name for item in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            module = resolve_name("." * node.level + module, package)
        if module == "vigilia":
            return [f"vigilia.{item.name}" for item in node.names]
        return [module]
    return []


def test_import_boundaries() -> None:
    violations = []
    for source in sorted(SRC.rglob("*.py")):
        relative = source.relative_to(SRC)
        parts = relative.with_suffix("").parts
        layer = parts[0]
        package = ".".join(("vigilia", *parts[:-1]))
        if layer == "__init__":
            assert not [name for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                        for name in _imports(node, package) if name.startswith("vigilia")]
            continue
        assert layer in ALLOWED, f"Camada desconhecida: {source}"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            for name in _imports(node, package):
                root, _, submodule = name.partition(".")
                target = submodule.split(".")[0]
                if root == "vigilia" and target != layer and target not in ALLOWED[layer]:
                    violations.append(f"{relative}:{node.lineno}: import proibido de {name}")
                if root in NATIVE and layer != "engine":
                    violations.append(f"{relative}:{node.lineno}: dependência nativa fora de engine: {name}")
    assert not violations, "\n".join(violations)
