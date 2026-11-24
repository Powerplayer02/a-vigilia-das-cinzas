"""Migrações com backup consistente e exclusão mútua por transação SQLite."""

import sqlite3
import time
from contextlib import contextmanager, closing
from pathlib import Path
from collections.abc import Iterator
from uuid import uuid4
from vigilia.save.migrations import v2_multi_slot, v3_slot_headers

SCHEMA_VERSION = 3


class Database:
    def __init__(self, path: Path) -> None:
        self.path, self.backup_path = Path(path), None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            self._check_version(connection)
            self._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            # Releitura sob lock: outra instância pode ter migrado enquanto aguardávamos.
            version = self._check_version(connection)
            if version == SCHEMA_VERSION:
                return
            if version == 0 and connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                raise ValueError("Banco não versionado com tabelas desconhecidas.")
            if version in (1, 2):
                self._backup()
            if version == 0:
                v2_multi_slot.create_schema(connection)
            if version == 1:
                v2_multi_slot.migrate(connection)
            v3_slot_headers.migrate(connection)
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("Referências inválidas após migração.")
            connection.execute("INSERT INTO metadata VALUES ('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (SCHEMA_VERSION,))
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @staticmethod
    def _enable_wal(connection):
        deadline = time.monotonic() + 5
        while True:
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as error:
                if getattr(error, "sqlite_errorcode", None) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)

    @staticmethod
    def _check_version(connection):
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ValueError("O banco foi criado por uma versão mais recente do jogo.")
        return version

    def _backup(self):
        target = self.path.with_name(self.path.name + f".before-v{SCHEMA_VERSION}.sqlite3")
        if target.exists():
            target = self.path.with_name(self.path.name + f".before-v{SCHEMA_VERSION}-{uuid4().hex[:8]}.sqlite3")
        # O escritor mantém BEGIN IMMEDIATE; um leitor separado copia o estado
        # confirmado, inclusive WAL, sem tentar fazer backup da própria transação.
        temporary = target.with_name(target.name + ".tmp")
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as source, closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination, pages=64)
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()
        self.backup_path = target

    @contextmanager
    def connect(self, *, timeout=5) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=timeout)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=NORMAL")
            with connection:
                yield connection
        finally:
            connection.close()
