"""Catálogos TOML com fallback explícito e interpolação de dados."""

from pathlib import Path
import tomllib

LANGUAGES = ("pt_BR", "en_US")


class Localizer:
    def __init__(self, directory: Path, language="pt_BR"):
        self.directory = directory
        with (directory / "pt_BR.toml").open("rb") as file:
            self.fallback = tomllib.load(file)
        self.set_language(language)

    def set_language(self, language: str):
        if language not in LANGUAGES:
            raise ValueError("options.invalid_language")
        with (self.directory / f"{language}.toml").open("rb") as file:
            catalog = tomllib.load(file)
        if not all(isinstance(value, str) for value in catalog.values()):
            raise ValueError("Catálogo de idioma inválido.")
        self.catalog, self.language = catalog, language

    def t(self, message_id: str, **values) -> str:
        return self.catalog.get(message_id, self.fallback.get(message_id, message_id)).format(**values)
