"""Esquema 2 → 3: classe e criação no cabeçalho, sem alterar estado pesado."""

import json
import sqlite3


def migrate(connection):
    roots = {row[0] for row in connection.execute("SELECT id FROM slots")}
    if not roots <= {1, 2, 3}:
        raise sqlite3.IntegrityError("Identificador de slot fora do intervalo.")
    for table in ("player", "world", "slot_metadata"):
        if {row[0] for row in connection.execute(f"SELECT slot FROM {table}")} != roots:
            raise sqlite3.IntegrityError("Slot incompleto: jogador, mundo e cabeçalho precisam coexistir.")
    connection.execute("ALTER TABLE slot_metadata ADD COLUMN class_id TEXT NOT NULL DEFAULT 'warrior'")
    connection.execute("ALTER TABLE slot_metadata ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
    for slot, payload, saved_at in connection.execute(
            "SELECT m.slot,p.payload,m.saved_at FROM slot_metadata m JOIN player p ON p.slot=m.slot"):
        player = json.loads(payload)
        identity = player.get("character_class", "warrior")
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("Classe inválida no save anterior.")
        # v2 não registrava criação. O último save é o primeiro timestamp conhecido.
        connection.execute("UPDATE slot_metadata SET class_id=?,created_at=? WHERE slot=?", (identity, saved_at, slot))
