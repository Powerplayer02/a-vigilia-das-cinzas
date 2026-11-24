"""Persistência do jogador e mundo na mesma transação."""

from vigilia.model.areas import area_at
from vigilia.model.snapshots import SaveSnapshot
from vigilia.save.database import Database
from vigilia.save.serializers import decode, encode
from vigilia.core.views import SlotView
from datetime import datetime, timezone
from vigilia.save.locks import SlotChangedError


class SlotRepository:
    """Snapshot e cabeçalho gravados na mesma transação."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, slot: int, snapshot: SaveSnapshot, *, require_empty: bool = False) -> None:
        self._validate_slot(slot)
        player, world = encode(snapshot)
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if require_empty and connection.execute("SELECT 1 FROM slots WHERE id=?", (slot,)).fetchone():
                raise ValueError("slots.occupied")
            connection.execute(
                "INSERT INTO slots VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "version=excluded.version, timing_version=excluded.timing_version",
                (slot, snapshot.version, snapshot.timing_version))
            for table, payload in (("player", player), ("world", world)):
                connection.execute(
                    f"INSERT INTO {table} VALUES (?,?) ON CONFLICT(slot) DO UPDATE SET payload=excluded.payload",
                    (slot, payload))
            player = snapshot.player
            area = area_at(player.motion.position)
            timestamp = datetime.now(timezone.utc).isoformat()
            connection.execute("INSERT INTO slot_metadata (slot,name,level,playtime_sec,area_id,saved_at,class_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(slot) DO UPDATE SET "
                "name=excluded.name,level=excluded.level,playtime_sec=excluded.playtime_sec,"
                "area_id=excluded.area_id,saved_at=excluded.saved_at,class_id=excluded.class_id", (
                slot, player.character_name, player.level, player.playtime_sec, area, timestamp,
                player.character_class, timestamp))

    def create(self, slot: int, snapshot: SaveSnapshot) -> None:
        self.save(slot, snapshot, require_empty=True)

    def delete(self, slot: int, *, expected_updated_at: str | None = None) -> bool:
        """Remove apenas o slot indicado; qualquer falha desfaz as quatro tabelas."""
        self._validate_slot(slot)
        with self.database.connect(timeout=.025) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute("SELECT 1 FROM slots WHERE id=?", (slot,)).fetchone():
                return False
            if expected_updated_at is not None:
                row = connection.execute("SELECT saved_at FROM slot_metadata WHERE slot=?", (slot,)).fetchone()
                if row is None or row[0] != expected_updated_at:
                    raise SlotChangedError()
            for table in ("world", "player", "slot_metadata"):
                connection.execute(f"DELETE FROM {table} WHERE slot=?", (slot,))
            connection.execute("DELETE FROM slots WHERE id=?", (slot,))
        return True

    def load(self, slot: int) -> SaveSnapshot | None:
        self._validate_slot(slot)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT slots.version, slots.timing_version, player.payload, world.payload FROM slots "
                "LEFT JOIN player ON player.slot=slots.id LEFT JOIN world ON world.slot=slots.id WHERE slots.id=?",
                (slot,)).fetchone()
        return None if row is None else decode(*row)

    @staticmethod
    def _validate_slot(slot):
        if type(slot) is not int or slot not in (1, 2, 3):
            raise ValueError("Slot precisa ser 1, 2 ou 3.")

    def list(self) -> list[SlotView]:
        """Lê somente o cabeçalho, sem desserializar snapshots."""
        with self.database.connect() as connection:
            rows = connection.execute("SELECT slot,name,level,playtime_sec,area_id,saved_at,class_id,created_at FROM slot_metadata ORDER BY slot").fetchall()
        return [SlotView(*row[:6], occupied=True, class_id=row[6], created_at=row[7]) for row in rows]
