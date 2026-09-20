"""Коды пространств: генерация, презентационный префикс и его снятие.

Тот же приём, что у ``tasks.codes`` и ``research.codes``: хранимый код — **голый hex-хеш** длиной
``CODE_LEN``, а тип-слово (``WORKSPACE@``) надевается на границе и снимается на входе. Копия
машинерии здесь, а не общий модуль в ядре, по той же причине, по какой она есть у соседей: длина
кода и набор префиксов — свойство модуля, и общий на всех генератор связал бы их вместе на
первом же расхождении.

Наружу код уезжает с префиксом только в JSON (``prefixed``), внутренний ``model_dump()``
остаётся голым. Внутрь ``bare_code`` проверяет, что префикс тот самый: код чужого типа
(``GROUP@`` там, где ждут пространство) — это перепутанный аргумент, а не пропавшая строка, и
отказ называет оба типа.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import PlainSerializer

from src.core.utils.hashing import random_hash
from src.modules.workspace.constants import CODE_LEN


def new_code() -> str:
    """Новый код пространства — голый ``CODE_LEN``-hex ``random_hash``."""
    return random_hash(CODE_LEN)


def code_prefix(value: str) -> str:
    """Тип-слово входного кода (``WORKSPACE`` из ``WORKSPACE@<hash>``); ``""`` — код голый."""
    return value.split("@", 1)[0] if "@" in value else ""


def strip_prefix(value: str | None) -> str | None:
    """Граница → хранилище: снять презентационный префикс, оставив голый хеш.

    Идемпотентно на голом коде (в hex-хеше нет ``@`` → значение возвращается как есть).
    """
    return value.rpartition("@")[2] if value else value


def bare_code(value: str | None, prefix: str) -> str | None:
    """Голый код сущности типа ``prefix``; чужой префикс — отказ с названием обоих типов."""
    if not value:
        return value
    actual = code_prefix(value)
    if actual and actual != prefix:
        raise ValueError(
            f"Code {value!r} is a {actual}@ reference, but a {prefix}@ code is expected here. "
            f"This is a wrong argument, not a missing row — pass the {prefix}@ code of the "
            "entity you mean (or its bare form)."
        )
    return strip_prefix(value)


def tagged(prefix: str, value: str | None) -> str | None:
    """Хранилище → граница: презентационная форма голого кода; ``None`` → ``None``."""
    return value if value is None else f"{prefix}@{value}"


def prefixed(prefix: str):
    """Тип ``str``, чья JSON-форма несёт ``prefix@`` (на вход принимается и голый хеш)."""
    return Annotated[
        str,
        PlainSerializer(
            lambda value: tagged(prefix, value), return_type=str, when_used="json"
        ),
    ]


__all__ = [
    "bare_code",
    "code_prefix",
    "new_code",
    "prefixed",
    "strip_prefix",
    "tagged",
]
