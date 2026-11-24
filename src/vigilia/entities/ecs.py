"""Registro ECS com índices por combinação de tipos de componente."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Entity:
    """Identificador local ao mundo, estável até a remoção."""

    id: int


class System(Protocol):
    def tick(self, world: World, dt: float) -> None: ...


class World:
    """Armazena tipos exatos e indexa entidades com a mesma assinatura."""

    def __init__(self) -> None:
        self._next = 0
        self._rows: dict[Entity, dict[type, object]] = {}
        self._archetypes: dict[frozenset[type], dict[Entity, None]] = {}

    def spawn(self, *components: object) -> Entity:
        """Cria uma entidade com os componentes informados."""
        entity = Entity(self._next)
        self._next += 1
        row = {type(component): component for component in components}
        self._rows[entity] = row
        self._index(entity, frozenset(row))
        return entity

    def _index(self, entity: Entity, signature: frozenset[type]) -> None:
        self._archetypes.setdefault(signature, {})[entity] = None

    def _unindex(self, entity: Entity, signature: frozenset[type]) -> None:
        bucket = self._archetypes[signature]
        del bucket[entity]
        if not bucket:
            del self._archetypes[signature]

    def add(self, entity: Entity, *components: object) -> None:
        """Insere ou atualiza componentes de uma entidade ativa."""
        row = self._rows[entity]
        before = frozenset(row)
        row.update((type(component), component) for component in components)
        self._reindex(entity, before, frozenset(row))

    def remove(self, entity: Entity, *types: type) -> None:
        """Remove os componentes informados."""
        row = self._rows[entity]
        before = frozenset(row)
        for kind in types:
            row.pop(kind, None)
        self._reindex(entity, before, frozenset(row))

    def _reindex(self, entity: Entity, before: frozenset[type], after: frozenset[type]) -> None:
        if before != after:
            self._unindex(entity, before)
            self._index(entity, after)

    def get(self, entity: Entity, kind: type[T]) -> T | None:
        """Lê um componente sem alterar o registro."""
        return cast(T | None, self._rows.get(entity, {}).get(kind))

    def query(self, *types: type) -> Iterator[tuple[Entity, tuple]]:
        """Percorre os arquétipos compatíveis em ordem de inserção."""
        wanted = frozenset(types)
        for signature, entities in self._archetypes.items():
            if wanted <= signature:
                for entity in entities:
                    row = self._rows[entity]
                    yield entity, tuple(row[kind] for kind in types)

    def destroy(self, entity: Entity) -> None:
        """Remove a entidade e seus componentes."""
        row = self._rows.pop(entity, None)
        if row is not None:
            self._unindex(entity, frozenset(row))
