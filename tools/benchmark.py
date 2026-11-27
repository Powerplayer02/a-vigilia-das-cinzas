"""Mede FPS, 1% low, IA e A* com inimigos ativos e VSync opcional."""

import argparse
import cProfile
import gc
import json
import math
import statistics
import sys
import tempfile
import time
import subprocess
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vigilia.ai.pathfinding import a_star
from vigilia.core.config import Config
from vigilia.core.mathx import Vec3, Transform
from vigilia.core.events import BossArenaEnteredEvent
from vigilia.combat.events import HPChangedEvent
from vigilia.engine.app import ArenaApp
from vigilia.game import Game
from vigilia.model.stats import StatsBlock
from vigilia.world.arena import nav_grid
from vigilia.entities.components import AIStateComponent, BodyRef, NavAgentComponent


def prepare_boss_stress(game: Game) -> None:
    """Substitui os manequins por 15 agentes na forja e ativa a segunda fase."""
    boss = game.boss
    assert boss is not None
    for key, entity in list(game._actors.items()):
        if key != "player":
            game._world.destroy(entity)
            del game._actors[key]
            game._renderer._dummies[entity.id].hide()
    game._practice_target = None
    entry = Vec3(0, 25.5, 1.02)
    game._bus.publish(BossArenaEnteredEvent(boss.profile.id, boss.profile.arena, entry))
    boss.fighter.hp = boss.profile.max_hp * .45
    game._bus.publish(HPChangedEvent(boss.entity.id, boss.profile.max_hp, boss.fighter.hp, boss.profile.max_hp, "self"))
    # Começa a amostra com a condição de proximidade já carregada para observar a AoE.
    boss.close_steps = boss.profile.close_trigger_steps - 1
    points = [Vec3(x, y, .95) for y in (20, 25, 31, 34) for x in (-7, -4, 0, 4, 7)]
    for entity, point in zip(game._enemies, points):
        body = game._world.get(entity, BodyRef)
        pose = game._world.get(entity, Transform)
        nav = game._world.get(entity, NavAgentComponent)
        assert body is not None and pose is not None and nav is not None
        body.body.teleport(point)
        pose.position, nav.home, nav.patrol = point, point, (point,)
        game._previous_enemies[entity.id] = Transform(point)
    game._target = boss.entity


class FrameProfile:
    """Acumula tempos de estágio, GC e intervalos por número de passos."""

    def __init__(self, game: Game, *, split_flip=False, hitch_directory=None, deep=False, spike_directory=None) -> None:
        self.game = game
        self.measuring = False
        self.stages = {}
        self.collections = {}
        self._gc_started = {}
        self.steps = 0
        self.previous_steps = 0
        self.intervals = {}
        self.max_path_queries_per_step = 0
        self.split_flip = split_flip
        self.hitch_directory = hitch_directory
        self._hitch = None
        self.hitch_count = 0
        self._retained_hitches = []
        from frame_recorder import FrameRecorder
        self.recorder = FrameRecorder(spike_directory, game._physics) if spike_directory else None
        self.hitches, self.gc_timeline = [], []
        self.ui_created = self.ui_text_changes = 0
        if game.ui_backend is not None:
            self._count_ui(game.ui_backend, "create", "ui_created")
            self._count_ui(game.ui_backend, "text", "ui_text_changes")
        if split_flip:
            game._app.graphicsEngine.set_auto_flip(False)
        self._wrap(game, "_fixed_step", "fixed_step")
        self._wrap(game._physics, "step", "bullet_step")
        self._wrap(game, "_evaluate_poses", "pose")
        self._wrap(game._sync, "sync", "hitbox_sync")
        self._wrap(game._combat, "resolve", "combat")
        self._wrap(game._save, "save", "save")
        self._wrap(game, "_draw_combat", "combat_presentation")
        if deep or self.recorder:
            self._wrap(game, "_notify", "notification_and_logging")
            self._wrap(game._audio, "play_sfx", "audio_sfx")
            self._wrap(game._particles, "spawn", "particle_spawn")
            self._wrap(game._contacts, "overlaps", "contact_query")
            self._wrap(game._physics, "raycast", "world_raycast")
            for handler in logging.getLogger().handlers:
                self._wrap(handler, "emit", "logging_emit")
                if self.recorder and getattr(handler, "stream", None) is not None:
                    self._wrap(handler.stream, "write", "log_stream_write")
                    self._wrap(handler.stream, "flush", "log_stream_flush")
        gc.callbacks.append(self._gc_callback)

    def _count_ui(self, backend, method, counter):
        original = getattr(backend, method)
        def measured(*args, **kwargs):
            if self.measuring:
                setattr(self, counter, getattr(self, counter) + 1)
            return original(*args, **kwargs)
        setattr(backend, method, measured)

    def _record(self, store, label, elapsed):
        record = store.setdefault(label, [0, 0.0, 0.0])
        record[0] += 1
        record[1] += elapsed
        record[2] = max(record[2], elapsed)

    def _wrap(self, owner, name, label):
        original = getattr(owner, name)

        def measured(*args, **kwargs):
            before = time.perf_counter()
            cpu_before = time.thread_time() if self.recorder else 0.
            queries = self.game.ai.path_count
            try:
                result = original(*args, **kwargs)
            finally:
                if self.recorder:
                    self.recorder.stage(label, before, cpu_before)
            if self.measuring:
                self._record(self.stages, label, time.perf_counter() - before)
                if label == "fixed_step":
                    self.steps += 1
                    self.max_path_queries_per_step = max(
                        self.max_path_queries_per_step, self.game.ai.path_count - queries)
            return result

        setattr(owner, name, measured)

    def _gc_callback(self, phase, info):
        generation = info["generation"]
        if phase == "start":
            self._gc_started[generation] = time.perf_counter()
        elif self.measuring and generation in self._gc_started:
            if self.recorder:
                self.recorder.collection(generation, self._gc_started[generation], time.perf_counter())
            self.gc_timeline.append(dict(generation=generation, start=self._gc_started[generation], end=time.perf_counter()))
            self._record(self.collections, str(generation),
                         time.perf_counter() - self._gc_started.pop(generation))

    def before_render(self, task):
        self._render_started = time.perf_counter()
        return task.cont

    def after_render(self, task):
        if self.recorder:
            self.recorder.finish(bool(self.game._app.mainWinMinimized))
        if self.measuring:
            before_flip = time.perf_counter()
            if self.split_flip:
                self._record(self.stages, "cull_draw_before_flip", before_flip - self._render_started)
        if self.split_flip:
            self.game._app.graphicsEngine.flip_frame()
        if self.measuring:
            ended = time.perf_counter()
            if self.split_flip:
                self._record(self.stages, "flip_wait", ended - before_flip)
            self._record(self.stages, "render_and_swap", ended - self._render_started)
            if ended - self._render_started > .016:
                self.hitches.append(dict(frame=self.game._app._clock.get_frame_count(),
                    start=self._render_started, end=ended, render_ms=(ended - self._render_started) * 1000,
                    minimized=bool(self.game._app.mainWinMinimized)))
        if self._hitch is not None:
            self._hitch.disable()
            if time.perf_counter() - self._hitch_started > .016:
                self._retained_hitches.append((time.perf_counter() - self._hitch_started,
                    self.game._app._clock.get_frame_count(), self._hitch))
                self._retained_hitches.sort(key=lambda row: row[0], reverse=True)
                del self._retained_hitches[8:]
                self.hitch_count += 1
            self._hitch = None
        return task.cont

    def begin_frame(self, elapsed):
        if self.measuring:
            self._record(self.intervals, str(self.previous_steps), elapsed)
        self.steps = 0
        if self.measuring and self.recorder:
            self.recorder.begin(self.game._app._clock.get_frame_count(), bool(self.game._app.mainWinMinimized), elapsed)
        if self.measuring and self.hitch_directory is not None:
            self._hitch = cProfile.Profile()
            self._hitch_started = time.perf_counter()
            self._hitch.enable()

    def end_frame(self):
        self.previous_steps = self.steps

    def report(self):
        def summary(store):
            return {label: {"count": values[0], "mean_ms": round(values[1] / values[0] * 1000, 4),
                            "max_ms": round(values[2] * 1000, 4)}
                    for label, values in store.items()}
        return {"stages": summary(self.stages), "gc": summary(self.collections),
                "frame_interval_by_previous_steps": summary(self.intervals),
                "max_path_queries_per_step": self.max_path_queries_per_step,
                "split_flip": self.split_flip, "profiled_hitches": self.hitch_count,
                "render_hitches": self.hitches, "gc_timeline": self.gc_timeline,
                "ui_created_during_measurement": self.ui_created, "ui_text_changes": self.ui_text_changes,
                "save_calls": self.stages.get("save", [0])[0]}

    def close(self):
        if self.recorder:
            self.spike_files = self.recorder.write()
        if self._retained_hitches:
            self.hitch_directory.mkdir(parents=True, exist_ok=True)
            for seconds, frame, profile in self._retained_hitches:
                profile.dump_stats(str(self.hitch_directory / f"frame-{frame:06d}-{seconds*1000:.2f}ms.prof"))
        self.measuring = False
        if self._hitch is not None:
            self._hitch.disable()
        if self.split_flip:
            self.game._app.graphicsEngine.set_auto_flip(True)
        gc.callbacks.remove(self._gc_callback)


def isolated_pathfinding(grid=None, pairs=None, *, solvable_only=False) -> dict:
    """Mede duzentas rotas puras, fora do loop de renderização."""
    grid = nav_grid() if grid is None else grid
    cells = [(x, y) for y, row in enumerate(grid.cells) for x, free in enumerate(row) if free]
    if pairs is None:
        pairs = [(grid.to_world(cells[index % len(cells)]),
                  grid.to_world(cells[-1 - (index * 7) % len(cells)])) for index in range(200)]
    for start, goal in pairs[:10]:
        a_star(grid, start, goal)
    samples, found, missing = [], [], []
    for start, goal in pairs:
        before = time.perf_counter()
        route = a_star(grid, start, goal)
        elapsed = time.perf_counter() - before
        samples.append(elapsed)
        (found if route else missing).append(elapsed)
    selected = found if solvable_only else samples
    return {"queries": len(selected), "attempted_queries": len(samples),
            "mode": "reachable_only" if solvable_only else "mixed",
            "mean_ms": round(statistics.mean(selected) * 1000, 4) if selected else 0,
            "grid": [len(grid.cells[0]), len(grid.cells)], "reachable": len(found), "unreachable": len(missing),
            "reachable_mean_ms": round(statistics.mean(found) * 1000, 4) if found else 0,
            "unreachable_mean_ms": round(statistics.mean(missing) * 1000, 4) if missing else 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--window-type", choices=("onscreen", "offscreen"), default="onscreen", help="Offscreen somente para diagnóstico, não baseline de FPS")
    parser.add_argument("--enemies", type=int, choices=range(21))
    parser.add_argument("--boss", action="store_true", help="Vigia na fase 2, com 15 comuns por padrão")
    parser.add_argument("--final-boss", action="store_true", help="Custódio fase 3 com 20 comuns")
    parser.add_argument("--tide-boss", action="store_true", help="Abadessa na fase 2 com 20 comuns")
    parser.add_argument("--unbatched", action="store_true", help="Comparação controlada da geometria estática")
    parser.add_argument("--legacy-hud", action="store_true", help="Apresentação anterior para comparação A/B no mesmo cenário")
    parser.add_argument("--vsync", action="store_true")
    parser.add_argument("--shadow-quality", choices=("off", "low", "medium", "high"), default="medium")
    parser.add_argument("--qa-diagnostics", action="store_true", help="Flight recorder do executável e gate por build; não usar como baseline FPS")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--deep-profile", action="store_true")
    parser.add_argument("--freeze-gc", action="store_true")
    parser.add_argument("--disable-gc", action="store_true", help="Experimento isolado; não muda o jogo de produção")
    parser.add_argument("--pstats-port", type=int)
    parser.add_argument("--shader-log", action="store_true")
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--particles", type=int, choices=(0, 500), default=0)
    parser.add_argument("--fps-cap", type=int, default=0)
    parser.add_argument("--procedural-music", action="store_true", help="Gera/pré-carrega a nova partitura antes da medição")
    parser.add_argument("--procedural-sfx", action="store_true", help="Ativa os novos SFX, buses, reserva de UI e proteção de pico")
    parser.add_argument("--warmup-seconds", type=float, default=2.)
    parser.add_argument("--split-flip", action="store_true", help="GraphicsEngine: render sem auto-flip e flip_frame medido à parte")
    parser.add_argument("--hitch-directory", type=Path, help="Diagnóstico com overhead: salva cProfile apenas de frames >16ms")
    parser.add_argument("--spike-directory", type=Path, help="cProfile binário: frame >200ms e 30 anteriores; I/O após medição")
    parser.add_argument("--diagnostic-minimize-at", type=float, help="QA do contador: minimiza a janela por 1s durante a amostra; invalida FPS")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--gpu-log", type=Path)
    args = parser.parse_args()
    if sum((args.boss, args.tide_boss, args.final_boss)) > 1:
        parser.error("Selecione apenas um chefe.")
    if args.enemies is None:
        args.enemies = 15 if args.boss else 20
    if args.seconds < 1:
        parser.error("Meça por ao menos um segundo.")
    if args.qa_diagnostics and (args.hitch_directory or args.spike_directory):
        parser.error("O modo QA já possui seu próprio cProfile; não combine gravadores.")
    if args.hitch_directory and args.spike_directory:
        parser.error("Use apenas um modo cProfile por execução: --hitch-directory ou --spike-directory.")
    if args.diagnostic_minimize_at is not None and args.window_type != "onscreen":
        parser.error("O ensaio de minimização exige janela onscreen.")
    source_id = None
    try:
        from vigilia.engine.diagnostics import build_fingerprint
        source_id = build_fingerprint(ROOT)
    except ModuleNotFoundError as error:
        if error.name != "vigilia.engine.diagnostics":
            raise
    config = Config(vsync=args.vsync, shadow_quality=args.shadow_quality,
        procedural_music=args.procedural_music, procedural_sfx=args.procedural_sfx)
    if args.shader_log:
        from panda3d.core import load_prc_file_data
        load_prc_file_data("shader-diagnostic", "notify-level-glgsg debug\nnotify-timestamp true")
    if args.pstats_port:
        from panda3d.core import load_prc_file_data
        load_prc_file_data("stats-diagnostic", "want-pstats true\npstats-gpu-timing true\npstats-max-rate 1000")
    if args.tide_boss or args.final_boss:
        from vigilia.world.area import load_area
        isolated_grid = load_area(ROOT / ("data/areas/forno_da_vigilia.toml" if args.final_boss else "data/areas/pantano_das_cinzas.toml")).navigation(fog_closed=True)
        from vigilia.model.bosses import load_boss_profile
        bounds = load_boss_profile(ROOT / ("data/bosses/custodian.toml" if args.final_boss else "data/bosses/tide.toml")).bounds
        x0,y0,x1,y1 = bounds
        points = [isolated_grid.to_world((x,y)) for y,row in enumerate(isolated_grid.cells) for x,free in enumerate(row)
                  if free and x0+1 < isolated_grid.to_world((x,y)).x < x1-1 and y0+1 < isolated_grid.to_world((x,y)).y < y1-1]
        pairs = [(points[i % len(points)], points[-1 - (i*7) % len(points)]) for i in range(200)]
        isolated = isolated_pathfinding(isolated_grid, pairs, solvable_only=True)
    else:
        isolated = isolated_pathfinding(solvable_only=True)
    with tempfile.TemporaryDirectory(prefix="vigilia-benchmark-") as temporary:
        app = ArenaApp(config, window_type=args.window_type)
        app.ignore("vigilia-button-down")
        app.ignore("vigilia-button-up")
        from panda3d.core import WindowProperties
        restore_window = WindowProperties()
        restore_window.set_minimized(False)
        if args.window_type == "onscreen":
            app.win.request_properties(restore_window)
        profile = None
        qa = None
        gpu_process = gpu_file = None
        try:
            if args.pstats_port:
                from panda3d.core import PStatClient
                assert PStatClient.connect("127.0.0.1", args.pstats_port)
            if args.fps_cap:
                from panda3d.core import ClockObject
                app._clock.set_mode(ClockObject.M_limited)
                app._clock.set_frame_rate(args.fps_cap)
            if args.gpu_log:
                args.gpu_log.parent.mkdir(parents=True, exist_ok=True)
                gpu_file = args.gpu_log.open("w")
                try:
                    gpu_process = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,utilization.gpu,utilization.memory",
                        "--format=csv,noheader,nounits", "--loop-ms=500"], stdout=gpu_file,
                        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                except OSError:
                    gpu_file.close()
                    gpu_file = None
            game = Game(app, config, ROOT / "assets", save_path=Path(temporary) / "slot.sqlite3",
                        enemy_count=args.enemies, legacy_hud=args.legacy_hud)
            game._renderer.batch_statics = not args.unbatched
            app.start(game)
            if args.particles:
                pool = game._particles.pool
                original_update = pool.update
                def maintain_stress(dt, target=Vec3()):
                    original_update(dt, target)
                    missing = args.particles - pool.active_count
                    if missing > 0:
                        pool.spawn("embers", target + Vec3(0, 0, .6), count=missing)
                pool.update = maintain_stress
            # A vida elevada mantém o jogador e os vinte agentes em combate durante a amostra.
            game._fighter.stats = StatsBlock(vigor=10000)
            game._fighter.restore()
            if args.tide_boss or args.final_boss:
                entry = Vec3(240, 25.7, 1.02) if args.final_boss else Vec3(120, 27.7, 1.02)
                game.change_area("forno_da_vigilia" if args.final_boss else "pantano_das_cinzas", entry, stress_enemies=args.enemies)
                boss = game.boss
                game._bus.publish(BossArenaEnteredEvent(boss.profile.id, boss.profile.arena, entry))
                boss.fighter.hp = 1500 if args.final_boss else 1800
                game._bus.publish(HPChangedEvent(boss.entity.id, boss.profile.max_hp, boss.fighter.hp, boss.profile.max_hp, "self"))
                boss.close_steps = boss.profile.close_trigger_steps - 1
                game._target = boss.entity
                game.alert_enemies()
            elif args.boss:
                prepare_boss_stress(game)
            else:
                game._player.body.teleport(Vec3(0, -2, 1.1))
            game.keyboard("control", True)
            game.alert_enemies()
            app.taskMgr.remove("vigilia-update")
            if args.profile or args.split_flip or args.hitch_directory or args.spike_directory:
                profile = FrameProfile(game, split_flip=args.split_flip, hitch_directory=args.hitch_directory, deep=args.deep_profile, spike_directory=args.spike_directory)
                app.taskMgr.add(profile.before_render, "profile-render-start", sort=49)
                app.taskMgr.add(profile.after_render, "profile-render-end", sort=51)
            if args.qa_diagnostics:
                app.graphicsEngine.render_frame()
                app.graphicsEngine.render_frame()
                qa = game.enable_diagnostics((args.output.parent / "spikes") if args.output else None,
                    report_path=args.output.with_suffix(".diagnostics.json") if args.output else None)
            started = previous = time.perf_counter()
            samples: list[float] = []
            measuring = False
            minimized_frames = 0
            minimized_seconds = 0.
            sample_minimized = False
            injected_minimize = injected_restore = False
            measurement_start = 0.0
            boss_moves = {}
            previous_boss_attack = None
            particle_min, particle_max = 500, 0

            def observe_window(task):
                nonlocal sample_minimized
                sample_minimized = sample_minimized or bool(app.mainWinMinimized)
                return task.cont

            app.taskMgr.add(observe_window, "benchmark-window-observer", sort=52)

            def benchmark(task):
                nonlocal previous, measuring, measurement_start, previous_boss_attack, particle_min, particle_max, minimized_frames, minimized_seconds, sample_minimized, injected_minimize, injected_restore
                now = time.perf_counter()
                elapsed = now - previous
                previous = now
                previous_minimized = sample_minimized or bool(app.mainWinMinimized)
                sample_minimized = bool(app.mainWinMinimized)
                if measuring and args.diagnostic_minimize_at is not None:
                    if now - measurement_start >= args.diagnostic_minimize_at and not injected_minimize:
                        minimize = WindowProperties()
                        minimize.set_minimized(True)
                        app.win.request_properties(minimize)
                        injected_minimize = True
                    if now - measurement_start >= args.diagnostic_minimize_at + 1 and not injected_restore:
                        app.win.request_properties(restore_window)
                        injected_restore = True
                if profile is not None:
                    profile.begin_frame(elapsed)
                game.frame(elapsed, (0, 0), (0, 0))
                if (args.boss or args.tide_boss or args.final_boss) and game.boss.fighter.attack is not previous_boss_attack:
                    previous_boss_attack = game.boss.fighter.attack
                    if measuring and previous_boss_attack is not None:
                        kind = previous_boss_attack.definition.kind.value
                        boss_moves[kind] = boss_moves.get(kind, 0) + 1
                if profile is not None:
                    profile.end_frame()
                if now - started >= args.warmup_seconds and not measuring:
                    if app.mainWinMinimized:
                        app.win.request_properties(restore_window)
                        if now - started > 15:
                            raise RuntimeError("A janela está minimizada; benchmark não iniciado.")
                        return task.cont
                    gc.collect()
                    if args.freeze_gc:
                        gc.freeze()
                    if args.disable_gc:
                        gc.disable()
                    print(f"MEASUREMENT_START {time.perf_counter():.9f}", file=sys.stderr, flush=True)
                    if args.ready_file:
                        import os
                        args.ready_file.write_text(json.dumps(dict(pid=os.getpid(), perf_counter=time.perf_counter())), encoding="utf-8")
                    measurement_start = previous = time.perf_counter()
                    sample_minimized = False
                    measuring = True
                    game.ai.tick_count = game.ai.path_count = 0
                    game.ai.tick_seconds = game.ai.path_seconds = 0.0
                    if profile is not None:
                        profile.measuring = True
                    return task.cont
                if measuring:
                    if previous_minimized:
                        minimized_frames += 1
                        minimized_seconds += elapsed
                    samples.append(elapsed)
                    particle_min = min(particle_min, game._particles.pool.active_count)
                    particle_max = max(particle_max, game._particles.pool.active_count)
                if measuring and now - measurement_start >= args.seconds:
                    frame_times = sorted(samples)
                    worst = sorted(samples, reverse=True)[:max(1, math.ceil(len(samples) * .01))]
                    states = {}
                    for _, (state,) in game._world.query(AIStateComponent):
                        states[state.mode.value] = states.get(state.mode.value, 0) + 1
                    result = {
                        "renderer": app.win.get_gsg().get_driver_renderer(),
                        "window_type": args.window_type,
                        "qa_diagnostics": args.qa_diagnostics,
                        "source_build_id": qa.build_id if qa else source_id,
                        "eligible_fps_baseline": args.window_type == "onscreen" and not args.spike_directory and args.diagnostic_minimize_at is None and not args.qa_diagnostics,
                        "valid_sample": minimized_frames == 0,
                        "minimized_frames": minimized_frames,
                        "excluded_samples": dict(count=minimized_frames, total_ms=round(minimized_seconds * 1000, 3), reason="window_minimized"),
                        "exclusion_policy": "Raw timings retained; any minimized sample invalidates the run for FPS comparisons. Durations are full measured frame intervals.",
                        "timing_note": "render_and_swap spans igLoop, including any minimization sleep; PStats separates engine collectors",
                        "scenario": "final_boss_20" if args.final_boss else "tide_boss_20" if args.tide_boss else "forge_boss" if args.boss else "patio_20" if args.enemies == 20 else "patio",
                        "hud": "legacy" if args.legacy_hud else "full",
                        "contact_shadow_quality": args.shadow_quality,
                        "static_geometry_batched": not args.unbatched and hasattr(game._renderer, "finish_scene"),
                        "static_render_nodes": game._renderer.statics.get_num_children(),
                        "draw_distance": config.draw_distance,
                        "nav_grid": [len(game.ai.grid.cells[0]), len(game.ai.grid.cells)],
                        "patio_training_dummies": len(game._renderer._dummies),
                        "static_bullet_bodies": game._physics._world.get_num_rigid_bodies(),
                        "resolution": [app.win.get_x_size(), app.win.get_y_size()],
                        "vsync": config.vsync,
                        "fps_cap": args.fps_cap,
                        "warmup_seconds": args.warmup_seconds,
                        "agile_movement_enabled": getattr(game._player, "advanced", None) is not None,
                        "audio_enabled": game._audio.enabled,
                        "logging_handlers": [type(handler).__name__ for handler in logging.getLogger().handlers],
                        "diagnostic_minimization_injected": args.diagnostic_minimize_at is not None,
                        "audio_track": game._audio.track_id,
                        "particles_requested": args.particles,
                        "particles_min_max": [particle_min, particle_max],
                        "gc_mode": "disabled" if args.disable_gc else "frozen" if args.freeze_gc else "normal",
                        "enemies": args.enemies,
                        "boss_phase": game.boss.phase if args.boss or args.tide_boss or args.final_boss else None,
                        "boss_moves_started": boss_moves if args.boss or args.tide_boss or args.final_boss else None,
                        "live_enemy_bodies": sum(body.body.active for entity, (body,) in game._world.query(BodyRef)
                                                 if entity != game._entity),
                        "fsm_states": states,
                        "player_hp": round(game._fighter.hp),
                        "frames": len(samples),
                        "seconds": round(sum(samples), 3),
                        "fps": round(len(samples) / sum(samples), 2),
                        "one_percent_low_fps": round(1 / statistics.mean(worst), 2),
                        "max_frame_ms": round(max(samples) * 1000, 3),
                        "median_frame_ms": round(statistics.median(samples) * 1000, 6),
                        "p99_frame_ms": round(frame_times[math.ceil(.99 * len(frame_times)) - 1] * 1000, 6),
                        "p95_frame_ms": round(frame_times[math.ceil(.95 * len(frame_times)) - 1] * 1000, 6),
                        "percentile_method": "nearest rank",
                        "frame_times_ms": [round(value * 1000, 6) for value in samples],
                        "ai_steps": game.ai.tick_count,
                        "ai_tick_mean_ms": round(game.ai.tick_seconds / max(1, game.ai.tick_count) * 1000, 4),
                        "path_queries_live": game.ai.path_count,
                        "path_live_mean_ms": round(game.ai.path_seconds / max(1, game.ai.path_count) * 1000, 4),
                        "path_isolated": isolated,
                    }
                    if profile is not None:
                        # O frame corrente ainda não passou por render; descarta sua captura parcial.
                        if profile._hitch is not None:
                            profile._hitch.disable()
                            profile._hitch = None
                        profile.measuring = False
                        result["profile"] = profile.report()
                        if profile.recorder:
                            profile.recorder.discard()
                            result["spike_captures"] = [timestamp for timestamp, _ in profile.recorder.captures]
                    if args.output:
                        args.output.parent.mkdir(parents=True, exist_ok=True)
                        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                    app.userExit()
                return task.cont

            app.taskMgr.add(benchmark, "stress-benchmark", sort=10)
            app.run()
        finally:
            if gpu_process is not None:
                gpu_process.terminate()
                gpu_process.wait(timeout=5)
            if gpu_file is not None:
                gpu_file.close()
            if profile is not None:
                profile.close()
            if args.freeze_gc:
                gc.unfreeze()
            if args.disable_gc:
                gc.enable()
            app.destroy()
            if qa is not None and qa.quarantined:
                raise RuntimeError("Build em quarentena: " + str(qa.report_path))


if __name__ == "__main__":
    main()
