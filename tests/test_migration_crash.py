"""Falha real do processo a cada DDL/DML, página do backup e commit."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from save_fixtures import version_two_database
from test_multislot import legacy_database
from test_save import full_snapshot
from vigilia.save.service import SaveService

ROOT = Path(__file__).resolve().parents[1]


def copy_database(source, destination):
    a, b = sqlite3.connect(source), sqlite3.connect(destination)
    try:
        a.backup(b)
    finally:
        a.close()
        b.close()


def worker(path, trace, stop):
    return subprocess.run([sys.executable, str(ROOT / "tests/migration_crash_worker.py"), str(path), str(trace), str(stop)],
        env=os.environ | {"PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("version", [1, 2])
def test_process_exit_at_every_migration_stage_keeps_committed_schema_and_payload(tmp_path, version, record_property):
    original = tmp_path / "source.sqlite3"
    if version == 1:
        _, expected = legacy_database(original)
    else:
        expected = version_two_database(original, {1: full_snapshot()})[1]
    discovery, trace = tmp_path / "discover.sqlite3", tmp_path / "trace.json"
    copy_database(original, discovery)
    result = worker(discovery, trace, -1)
    assert result.returncode == 0, result.stderr
    stages = json.loads(trace.read_text())
    record_property("migration_crash_checkpoints", len(stages))
    assert "after_backup" in stages and "backup.page" in stages and stages[-1] == "after_commit"
    for index, stage in enumerate(stages):
        path = tmp_path / f"crash-{index}.sqlite3"
        copy_database(original, path)
        result = worker(path, trace, index)
        assert result.returncode == 71, (stage, result.stderr)
        # Não passa pelo migrador antes de observar o rollback/recovery do SQLite.
        with sqlite3.connect(path) as connection:
            committed = 3 if stage == "after_commit" else version
            assert connection.execute("PRAGMA user_version").fetchone()[0] == committed
            assert connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == committed
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
            assert not connection.execute("PRAGMA foreign_key_check").fetchall()
            assert connection.execute("SELECT payload FROM player WHERE slot=1").fetchone()[0] == expected[0]
            assert connection.execute("SELECT payload FROM world WHERE slot=1").fetchone()[0] == expected[1]
            assert not connection.execute("SELECT name FROM sqlite_master WHERE name LIKE 'legacy_%'").fetchall()
        # Somente cópias completas recebem nome de backup; .tmp nunca é oferecido.
        backups = list(tmp_path.glob(path.name + ".before-v3*.sqlite3"))
        if index >= stages.index("after_backup"):
            assert backups
        for backup in backups:
            with sqlite3.connect(backup) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert connection.execute("PRAGMA user_version").fetchone()[0] == version
                assert connection.execute("SELECT payload FROM player").fetchone()[0] == expected[0]
        reopened = SaveService(path)
        assert reopened.load(1) is not None
        with sqlite3.connect(path) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
