"""Отказы правил модуля, у которых есть имя.

Обычный ``ValueError`` из CRUD едет наружу текстом — этого хватает, пока текст читает агент: он
написан по-английски, называет причину и сам чинит вызов. Но два отказа читает ЧЕЛОВЕК в
интерфейсе, и английская фраза из недр слоя данных там неуместна.

Поэтому у них есть код: CRUD поднимает ``TaskRuleError`` с именем правила, API кладёт это имя в
поле ``code`` ответа, а интерфейс показывает свою формулировку на своём языке. Текст исключения
при этом остаётся прежним — он нужен в логах и в ответах агенту, который кода не читает.

Новый код заводится вместе с правилом, которое он называет, и попадает в словарь интерфейса
(``tasks.error.*``). Код без перевода не ломает показ: интерфейс падает обратно на текст ответа.
"""

from __future__ import annotations

STAGE_EVIDENCE_REQUIRED = "stage_evidence_required"
"""Закрыть этап нельзя: доказательство выполнения пустое."""

NOTE_ALREADY_RESOLVED = "note_already_resolved"
"""Запись журнала уже закрыта: переписать разрешение нельзя, журнал дописываемый."""

# Отказы HTTP-слоя: их тоже читает человек. Код ``tasks.<сущность>.<причина>`` интерфейс ищет в
# ``tasks.error.<сущность>.<причина>``; текст ответа — английский запасной.
GROUP_NOT_FOUND = "tasks.group.not_found"
GROUP_DELETED = "tasks.group.deleted"
GROUP_NOT_DELETED = "tasks.group.not_deleted"
TASK_NOT_FOUND = "tasks.task.not_found"
TASK_DELETED = "tasks.task.deleted"
TASK_NOT_DELETED = "tasks.task.not_deleted"
STAGE_NOT_FOUND = "tasks.stage.not_found"
NOTE_NOT_FOUND = "tasks.note.not_found"


class TaskRuleError(ValueError):
    """Отказ правила модуля с машинным именем.

    Наследник ``ValueError`` намеренно: весь CRUD уже отвечает им, и обработчики в API ловят
    его одним ``except`` — добавление кода не должно требовать второй ветки в каждой ручке.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


__all__ = [
    "GROUP_DELETED",
    "GROUP_NOT_DELETED",
    "GROUP_NOT_FOUND",
    "NOTE_ALREADY_RESOLVED",
    "NOTE_NOT_FOUND",
    "STAGE_EVIDENCE_REQUIRED",
    "STAGE_NOT_FOUND",
    "TASK_DELETED",
    "TASK_NOT_DELETED",
    "TASK_NOT_FOUND",
    "TaskRuleError",
]
