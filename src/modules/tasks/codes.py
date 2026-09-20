"""Коды сущностей ``tasks``: генерация, презентационный префикс и его снятие.

Хранимый код (PK и все FK модуля) — **голый hex-хеш** длиной ``CODE_LEN``, как его отдаёт
``random_hash``. Тип-префикс (``WORKSPACE@`` / ``GROUP@`` / ``TASK@``) — **презентация**: он
позволяет человеку и агенту отличить одну сущность от другой с одного взгляда и превращает
свободно летающий код в типизированную ссылку. Форма на проводе — ``type@hash``: ``@`` читается
как «ссылка в пространстве имён» и в hex-алфавите не встречается никогда.

Префикс живёт ТОЛЬКО на границе, в базу не попадает:

- **наружу** (DTO → агент / API): поле, аннотированное ``prefixed(PREFIX)``, сериализуется с
  префиксом, причём только в JSON — внутренний ``model_dump()`` остаётся голым;
- **внутрь** (агент / API → CRUD): ``bare_code`` снимает префикс до того, как значение
  доедет до SQL.

Так как алфавит хеша — ``[0-9a-f]`` (символа ``@`` там нет), ``strip_prefix`` идемпотентен на
уже голом коде: применять его к внутренним значениям безопасно.

``bare_code`` дополнительно проверяет, что префикс — **тот самый**. Код чужого типа (``GROUP@``
там, где ждут задачу) — это не «не найдено», а перепутанный аргумент; отказ называет оба типа,
и агент чинит вызов с первого раза, вместо того чтобы решать, что запись удалили.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import PlainSerializer

from src.core.utils.hashing import random_hash
from src.modules.tasks.constants import CODE_LEN


def new_code() -> str:
    """Новый код сущности — голый ``CODE_LEN``-hex ``random_hash``.

    Генератор один на модуль: естественного ключа дедупа нет ни у одной таблицы, а длина кода —
    свойство модуля, не сущности. Коллизия роняет вставку, а не сливает две строки в одну.
    """
    return random_hash(CODE_LEN)


def code_prefix(value: str) -> str:
    """Тип-слово входного кода (``TASK`` из ``TASK@<hash>``); ``""`` — код голый."""
    return value.split("@", 1)[0] if "@" in value else ""


def strip_prefix(value: str | None) -> str | None:
    """Граница → хранилище: снять презентационный префикс, оставив голый хеш.

    Идемпотентно на голом коде (в hex-хеше нет ``@`` → значение возвращается как есть).
    """
    return value.rpartition("@")[2] if value else value


def bare_code(value: str | None, prefix: str) -> str | None:
    """Голый код сущности типа ``prefix``; чужой префикс — отказ с названием обоих типов.

    Голый код проходит без вопросов: это внутренняя форма, и требовать префикс от неё значило
    бы запретить передавать наружу то, что модуль вернул сам.
    """
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
    """Хранилище → граница: презентационная форма голого кода (``TASK@<hash>``); ``None`` → ``None``."""
    return value if value is None else f"{prefix}@{value}"


def prefixed(prefix: str):
    """Тип ``str``, чья JSON-форма несёт ``prefix@`` (на вход по-прежнему принимается голый хеш).

    ``prefix`` — голое тип-слово (``TASK``/``GROUP``/…); разделитель ``@`` дописывается здесь,
    чтобы константа не смешивала имя типа с синтаксисом ссылки. Для будущих DTO модуля.
    """
    return Annotated[
        str,
        PlainSerializer(
            lambda value: tagged(prefix, value), return_type=str, when_used="json"
        ),
    ]


__all__ = [
    "CODE_LEN",
    "bare_code",
    "code_prefix",
    "new_code",
    "prefixed",
    "strip_prefix",
    "tagged",
]
