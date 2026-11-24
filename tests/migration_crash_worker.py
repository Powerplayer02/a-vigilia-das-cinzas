"""Instrumentação exclusiva de QA: encerra sem finally após cada fronteira."""

import json
import os
from pathlib import Path
import sqlite3
import sys

from vigilia.save.database import Database

path, trace_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
stop = int(sys.argv[3])
stages = []


def checkpoint(name):
    stages.append(name)
    trace_path.write_text(json.dumps(stages), encoding="utf-8")
    if len(stages) - 1 == stop:
        os._exit(71)


original_connect = sqlite3.connect


class Connection(sqlite3.Connection):
    migrating = False
    main = False

    def execute(self, sql, *args, **kwargs):
        result = super().execute(sql, *args, **kwargs)
        normalized = " ".join(sql.upper().split())
        if self.main and normalized == "BEGIN IMMEDIATE":
            self.migrating = True
            checkpoint("begin")
        elif self.main and self.migrating and (normalized.split()[0] in ("ALTER", "CREATE", "INSERT", "DROP", "UPDATE")
                or normalized.startswith("PRAGMA USER_VERSION=")):
            checkpoint(sql)
        return result

    def backup(self, destination, *args, **kwargs):
        kwargs.update(pages=1, progress=lambda *unused: checkpoint("backup.page"))
        return super().backup(destination, *args, **kwargs)

    def __exit__(self, *args):
        if self.main and self.migrating:
            checkpoint("before_commit")
        result = super().__exit__(*args)
        if self.main and self.migrating:
            checkpoint("after_commit")
        return result


def connect(database, *args, **kwargs):
    connection = original_connect(database, *args, factory=Connection, **kwargs)
    connection.main = Path(database).resolve() == path
    return connection


sqlite3.connect = connect
backup = Database._backup


def observed_backup(self):
    checkpoint("before_backup")
    backup(self)
    checkpoint("after_backup")


Database._backup = observed_backup
Database(path)
