"""Счётчики содержимого пространства — точка, которой модули поверх дополняют его карточку.

Пространство само не знает, что в нём лежит: зоны и задачи — дело модуля ``tasks``, документы
будут делом другого модуля, и список «сколько внутри» не может быть зашит здесь, иначе
зависимость шла бы сверху вниз — от уровня 1 к уровню 2.

Поэтому счётчик **регистрируют**: модуль поверх в своём ``configure()`` объявляет ключ, ключ
подписи для интерфейса и функцию, считающую свои строки разом по списку кодов пространств.
Карточка пространства показывает то, что зарегистрировано, и ничего не знает о самих сущностях.

Считаем пачкой (``codes -> {code: count}``), а не по строке: список пространств помещается на
экран целиком, и запрос на карточку дал бы N+1 там, где хватает одной группировки.

Подпись счётчика не приезжает строкой: бэкенд отдаёт КЛЮЧ сообщения (``label_key``), а текст
берёт интерфейс. Иначе русский текст поселился бы в модуле, который про язык ничего не знает, а
владел бы им не тот, кто владеет самой сущностью.

Реестр — process-global, как и реестр задач планировщика: ``configure()`` зовётся один раз на
сборку приложения, а повторная сборка (тесты поднимают приложение много раз) перезаписывает
запись по ключу, а не плодит дубли.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

CountByCodes = Callable[[list[str]], Awaitable[dict[str, int]]]


@dataclass(frozen=True)
class WorkspaceCounter:
    """Объявление счётчика: чем считать, как назвать и в каком порядке показывать."""

    key: str
    """Ключ счётчика в ответе API (``groups``/``tasks``); уникален в пределах приложения."""

    label_key: str
    """Ключ сообщения интерфейса для подписи — принадлежит модулю, который счётчик завёл."""

    count_by_codes: CountByCodes = field(compare=False)
    """``[код пространства, …] -> {код: сколько}``. Пространства без строк можно не возвращать."""

    sort: int = 500
    """Больший идёт раньше — порядок в карточке задаёт тот, кто счётчик регистрирует."""


_REGISTRY: dict[str, WorkspaceCounter] = {}


def register_counter(counter: WorkspaceCounter) -> None:
    """Объявить счётчик содержимого пространства (повторная регистрация ключа — замена)."""
    _REGISTRY[counter.key] = counter


def registered_counters() -> list[WorkspaceCounter]:
    """Объявленные счётчики: больший ``sort`` раньше, дальше по ключу — порядок стабилен."""
    return sorted(_REGISTRY.values(), key=lambda counter: (-counter.sort, counter.key))


async def counts_for(codes: list[str]) -> dict[str, dict[str, int]]:
    """``код пространства -> {ключ счётчика: сколько}`` для всех объявленных счётчиков.

    Ноль подставляется здесь, а не в считающей функции: «не вернули» и «ничего не нашли» — это
    один и тот же ответ для карточки, и требовать от каждого модуля заполнять нули значило бы
    повторять одну и ту же сборку в каждом из них.
    """
    if not codes:
        return {}
    counters = registered_counters()
    counted = {counter.key: await counter.count_by_codes(codes) for counter in counters}
    return {
        code: {counter.key: counted[counter.key].get(code, 0) for counter in counters}
        for code in codes
    }


def reset_counters() -> None:
    """Очистить реестр — для тестов, которым нужна карточка без чужих счётчиков."""
    _REGISTRY.clear()


__all__ = [
    "WorkspaceCounter",
    "counts_for",
    "register_counter",
    "registered_counters",
    "reset_counters",
]
