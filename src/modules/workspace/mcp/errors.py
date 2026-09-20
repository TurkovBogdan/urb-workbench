"""Отказы правил MCP-поверхности, у которых есть имя.

Тот же приём, что в ``tasks/errors.py``: код правила отделён от текста, потому что читателей
двое. Агент читает английскую фразу и по ней чинит вызов; интерфейс (и будущие тесты) смотрят на
код, которому переименование фразы не страшно.

Оба отказа здесь — про **контур**, а не про данные, и оба существуют затем, чтобы работа не в том
пространстве была громкой. Тихо взять список чужих задач хуже, чем отказать: ошибка контура не
выглядит ошибкой, она выглядит пустым списком или чужой работой.
"""

from __future__ import annotations

NO_ACTIVE_WORKSPACE = "no_active_workspace"
"""Сессия не привязана к пространству, а инструмент без него бессмыслен."""

WORKSPACE_MISMATCH = "workspace_mismatch"
"""Код сущности указывает в пространство, отличное от активного в этой сессии."""


class WorkspaceScopeError(ValueError):
    """Отказ контура с машинным именем.

    Наследник ``ValueError`` намеренно: ``fastmcp`` превращает его в ошибку исполнения
    (``isError``), а она по спецификации и возвращается модели — чтобы та поправилась и
    повторила вызов. Это единственный канал, которым инструмент может чему-то научить.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def no_active_workspace() -> WorkspaceScopeError:
    """Отказ «пространство не выбрано» — с обоими инструментами, которыми это чинится.

    Текст называет путь целиком, а не констатирует нехватку: агент, которому сказали «нет
    активного пространства», без второй половины фразы начнёт искать аргумент у инструмента,
    которого там нет.
    """
    return WorkspaceScopeError(
        NO_ACTIVE_WORKSPACE,
        "This session is not bound to a workspace yet, and this tool works inside one. "
        "Call workspaces_list() to see what exists, then workspace_use(workspace_code) to "
        "pick one — after that no tool needs a workspace argument.",
    )


def workspace_mismatch(
    *, code: str, owner_code: str, owner_title: str, active_code: str, active_title: str
) -> WorkspaceScopeError:
    """Отказ «код из чужого пространства» — с названиями обоих, а не только кодами.

    Названия в тексте не украшение: коды случайны и на глаз неразличимы, а «Личное против
    Работы» агент понимает сразу и чинит правильным способом — сменой пространства или сменой
    кода, а не повтором того же вызова.
    """
    return WorkspaceScopeError(
        WORKSPACE_MISMATCH,
        f"{code} belongs to workspace {owner_code} ({owner_title!r}), but this session works "
        f"in {active_code} ({active_title!r}). A workspace is a hard boundary here: either "
        f"pass a code from {active_title!r}, or switch with workspace_use({owner_code}).",
    )


__all__ = [
    "NO_ACTIVE_WORKSPACE",
    "WORKSPACE_MISMATCH",
    "WorkspaceScopeError",
    "no_active_workspace",
    "workspace_mismatch",
]
