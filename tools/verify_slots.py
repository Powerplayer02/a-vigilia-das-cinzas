"""Migra uma fixture sintética do schema v2 e percorre o CRUD nativo."""

import argparse
from contextlib import ExitStack
import hashlib
import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from panda3d.core import Filename
from vigilia.core.config import Config
from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.save.service import SaveService
from vigilia.save.serializers import encode
from vigilia.save.database import SCHEMA_VERSION

# Estrutura congelada da 5.1, não criada pelo migrador que estamos verificando.
V2_SCHEMA = """
CREATE TABLE metadata(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
INSERT INTO metadata VALUES('schema_version',2);
CREATE TABLE slots(id INTEGER PRIMARY KEY CHECK(id BETWEEN 1 AND 3),version INTEGER NOT NULL,timing_version INTEGER NOT NULL);
CREATE TABLE player(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);
CREATE TABLE world(slot INTEGER PRIMARY KEY REFERENCES slots(id),payload TEXT NOT NULL);
CREATE TABLE slot_metadata(slot INTEGER PRIMARY KEY REFERENCES slots(id),name TEXT NOT NULL,level INTEGER NOT NULL,playtime_sec REAL NOT NULL,area_id TEXT NOT NULL,saved_at TEXT NOT NULL);
PRAGMA user_version=2;
"""


def copy_database(source, target):
    with closing(sqlite3.connect(source)) as connection, closing(sqlite3.connect(target)) as destination:
        connection.backup(destination)


def payloads(path):
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT p.slot,p.payload,w.payload FROM player p JOIN world w ON w.slot=p.slot ORDER BY p.slot").fetchall()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/5.2a")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = Config(vsync=False)
    app = ArenaApp(config, window_type="offscreen")
    try:
        with tempfile.TemporaryDirectory(prefix="vigilia-slots-qa-") as directory, ExitStack() as cleanup:
            base = Path(directory)
            game = Game(app, config, ROOT / "assets", save_path=base / "seed.sqlite3", front_end=True, enemy_count=0)
            cleanup.callback(game.close)
            app.start(game)
            app.taskMgr.remove("vigilia-update")
            for slot, class_index in ((1, 0), (2, 3), (3, 4)):
                if slot > 1:
                    game.execute(UICommand(C.MAIN_MENU))
                game.execute(UICommand(C.NEW_GAME))
                game.execute(UICommand(C.SELECT_NEW_SLOT, str(slot)))
                screen = game.front.screen
                screen.select_class(class_index)
                screen.select_slot(slot)
                for _ in range(10):
                    screen.adjust("vigor", 1)
                screen.create()
                game.frame(1 / 60, (0, 0), (0, 0))
            game.execute(UICommand(C.MAIN_MENU))
            snapshots = {slot: game._save.load(slot) for slot in (1, 2, 3)}
            # Builds 5.1 não persistiam os agentes anônimos do Pátio.
            snapshots = {slot: replace(snapshot, world=replace(snapshot.world,
                actors=tuple(actor for actor in snapshot.world.actors if not actor.key.startswith("patio.enemy.")),
                dead_common=tuple(key for key in snapshot.world.dead_common if not key.startswith("patio.enemy."))))
                for slot, snapshot in snapshots.items()}
            legacy = base / "legacy-v2.sqlite3"
            with closing(sqlite3.connect(legacy)) as connection:
                connection.executescript(V2_SCHEMA)
                with connection:
                    for slot, snapshot in snapshots.items():
                        p, w = encode(snapshot)
                        old_world = json.loads(w)
                        old_world.pop("area_id", None)
                        old_world.pop("dormant_areas", None)
                        w = json.dumps(old_world, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                        connection.execute("INSERT INTO slots VALUES(?,?,?)", (slot, snapshot.version, snapshot.timing_version))
                        connection.execute("INSERT INTO player VALUES(?,?)", (slot, p))
                        connection.execute("INSERT INTO world VALUES(?,?)", (slot, w))
                        player = snapshot.player
                        connection.execute("INSERT INTO slot_metadata VALUES(?,?,?,?,?,?)", (
                            slot, player.character_name, player.level, player.playtime_sec, "patio_da_vigilia", "2026-11-20T12:00:00+00:00"))
            original = payloads(legacy)
            migrated = SaveService(legacy)
            backup = migrated.repository.database.backup_path
            assert backup and payloads(backup) == payloads(legacy) == original
            for slot, expected in snapshots.items():
                assert migrated.load(slot) == expected
            assert [row.class_id for row in migrated.list_slots()] == ["warrior", "mage", "cleric"]
            before_headers = migrated.list_slots()
            game._save = migrated
            game.execute(UICommand(C.CONTINUE))
            game.frame(1 / 60, (0, 0), (0, 0))
            for _ in range(2):
                app.graphicsEngine.render_frame()
            assert app.win.save_screenshot(Filename.from_os_specific(str(args.output / "existing-slot-menu.png")))
            game.front.screen.grid.select(2)
            game.front.screen.confirm()
            assert game.active_slot == 2 and game.character_class == "mage"
            game.progression.souls += 123
            migrated.save(2, game.build_snapshot())
            changed = migrated.load(2)
            assert changed.player.souls == snapshots[2].player.souls + 123
            assert migrated.load(1) == snapshots[1] and migrated.load(3) == snapshots[3]
            assert migrated.list_slots()[1].created_at == before_headers[1].created_at
            assert migrated.delete(3) and not migrated.delete(3)
            assert migrated.load(3) is None and not migrated.list_slots()[2].occupied
            assert migrated.load(1) == snapshots[1] and migrated.load(2) == changed
            migrated.create(3, snapshots[3])
            reopened = SaveService(legacy)
            assert reopened.repository.database.backup_path is None
            assert reopened.load(2) == changed and reopened.load(3) == snapshots[3]
            samples = []
            for _ in range(25):
                start = time.perf_counter()
                heads = reopened.list_slots()
                samples.append((time.perf_counter() - start) * 1000)
            assert statistics.median(samples) < 5
            with closing(sqlite3.connect(legacy)) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
                assert not connection.execute("PRAGMA foreign_key_check").fetchall()
            copy_database(backup, args.output / "fixture-v2.sqlite3")
            copy_database(legacy, args.output / "fixture-v3.sqlite3")
            report = {"result": "ok", "source_schema": 2, "target_schema": SCHEMA_VERSION,
                "payloads_preserved_byte_for_byte": True, "backup_valid": True,
                "backup_payload_sha256": hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).hexdigest(),
                "native_load_slot": 2, "native_class": game.character_class,
                "delete_isolated_and_idempotent": True, "recreate_deleted_slot": True,
                "schema_reopen_idempotent": True,
                "head_read_median_ms": round(statistics.median(samples), 4),
                "head_read_max_ms": round(max(samples), 4),
                "headers": [{"slot": row.slot, "class_id": row.class_id, "name": row.name,
                    "level": row.level, "playtime_sec": row.playtime_sec, "area_id": row.area_id,
                    "created_at": row.created_at, "updated_at": row.updated_at} for row in heads]}
            (args.output / "slots.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        app.destroy()


if __name__ == "__main__":
    main()
