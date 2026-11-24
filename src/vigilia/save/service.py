"""Serviço síncrono de snapshots pequenos com commit atômico."""

from __future__ import annotations

from pathlib import Path

from vigilia.model.snapshots import SaveSnapshot
from vigilia.save.database import Database
from vigilia.save.repositories import SlotRepository
from vigilia.core.views import SlotView
from vigilia.save.locks import SlotLease, SlotInUseError
from contextlib import contextmanager
import sqlite3


class SaveService:
    def __init__(self, path: Path) -> None:
        self.repository = SlotRepository(Database(path))
        self._leases = {}

    def save(self, slot: int, snapshot: SaveSnapshot, *, require_empty: bool = False) -> None:
        """Valida e persiste jogador e mundo juntos."""
        with self._write_slot(slot):
            self.repository.save(slot, snapshot, require_empty=require_empty)

    def load(self, slot: int = 1) -> SaveSnapshot | None:
        """Lê o snapshot completo em uma única consulta."""
        return self.repository.load(slot)

    def list(self):
        return self.repository.list()

    def list_slots(self) -> list[SlotView]:
        """Três destinos ordenados, incluindo os vazios, sem ler payloads."""
        occupied = {row.slot: row for row in self.repository.list()}
        return [occupied.get(slot, SlotView(slot)) for slot in (1, 2, 3)]

    def create(self, slot: int, snapshot: SaveSnapshot) -> None:
        """Uma criação exige um personagem validado e não sobrescreve progresso."""
        with self._write_slot(slot):
            self.repository.create(slot, snapshot)

    def delete(self, slot: int, *, expected_updated_at: str | None = None) -> bool:
        self.repository._validate_slot(slot)
        if slot in self._leases:
            raise SlotInUseError()
        lease = SlotLease(self.repository.database.path, slot)
        if not lease.acquire():
            raise SlotInUseError()
        try:
            return self.repository.delete(slot, expected_updated_at=expected_updated_at)
        except sqlite3.OperationalError as error:
            if getattr(error, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                raise ValueError("slots.busy") from error
            raise
        finally:
            lease.close()

    def acquire(self, slot: int):
        self.repository._validate_slot(slot)
        if slot not in self._leases:
            lease = SlotLease(self.repository.database.path, slot)
            if not lease.acquire():
                raise SlotInUseError()
            self._leases[slot] = lease
            return True
        return False

    def release(self, slot: int):
        if lease := self._leases.pop(slot, None):
            lease.close()

    def in_use(self, slot: int) -> bool:
        self.repository._validate_slot(slot)
        if slot in self._leases:
            return True
        lease = SlotLease(self.repository.database.path, slot)
        acquired = lease.acquire()
        lease.close()
        return not acquired

    @contextmanager
    def _write_slot(self, slot):
        self.repository._validate_slot(slot)
        if slot in self._leases:
            yield
            return
        lease = SlotLease(self.repository.database.path, slot)
        if not lease.acquire(timeout=5):
            raise SlotInUseError()
        try:
            yield
        finally:
            lease.close()

    def close(self):
        for slot in tuple(self._leases):
            self.release(slot)
