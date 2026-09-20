"""Редактор тела — правки markdown-текста сущности по префиксу её кода.

Тело есть у трёх сущностей модуля, и у всех оно называется одинаково — колонкой ``body``:
у задачи это план, у этапа описание работы, у записи журнала её предмет. Одно имя на весь
модуль и означает один набор инструментов правки; постановка задачи (``context`` и соседи)
телом не считается и правится карточкой.

Трансформы — чистые функции над строкой; ошибка ввода (не найдено, неоднозначно) →
``ValueError``. Наружу едет не тело, а **шов**: окно по обе стороны от правки, где сам
вставленный текст заменён заглушкой. Текст прислал агент; назад ему нужно ровно то, чего он не
знает, — как вставка легла.

Два правила здесь свои, у соседнего сервера их нет.

**Лимит отказывает, а не усекает,** и отказ называет длину РЕЗУЛЬТАТА. Агент дописал две строки
в почти полное тело и упёрся не в них: скажи ему длину присланного куска — и он будет резать не
то место.

**Тело начатого этапа не правится.** Впереди план живой, позади застывший: иначе формулировку
подгонят под результат, и расхождение «обещали одно, сделали другое» исчезнет вместе с
единственным сигналом, ради которого план ведут. На план задачи и на предмет записи запрет не
распространяется — первый живёт, пока живёт задача, во втором агент ещё разбирается.

Заголовок ищется только вне ограждённого кода: строка ``# comment`` внутри ```` ``` ````-блока
не заголовок, иначе раздел с примером кода обрывался бы на середине фенса.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import NamedTuple, TypeVar

from src.core.database import write_scope
from src.modules.tasks.codes import code_prefix, strip_prefix
from src.modules.tasks.constants import (
    BODY_MAX,
    NOTE_BODY_MAX,
    NOTE_CODE_PREFIX,
    STAGE_CODE_PREFIX,
    TASK_CODE_PREFIX,
    TASK_STATUSES_TERMINAL,
    STATUS_PLANNED,
)
from src.modules.tasks.models.note import TasksNote
from src.modules.tasks.models.stage import TasksStage
from src.modules.tasks.models.task import TasksTask


class _Holder(NamedTuple):
    """Что известно про тело этого типа: модель, потолок и как назвать его агенту."""

    model: type
    limit: int
    what: str


_HOLDERS = {
    TASK_CODE_PREFIX: _Holder(TasksTask, BODY_MAX, "the task plan"),
    STAGE_CODE_PREFIX: _Holder(TasksStage, BODY_MAX, "the stage body"),
    NOTE_CODE_PREFIX: _Holder(TasksNote, NOTE_BODY_MAX, "the journal entry body"),
}

PREVIEW_WINDOW_CHARS = 128
SEAM_TEXT_PLACEHOLDER = "<text>"
SEAM_TRUNCATION_MARK = "…"
PREVIEW_ELISION_MARK = " … "
HEADING_PATH_SEPARATOR = " > "


def _holder_for(code: str) -> _Holder:
    holder = _HOLDERS.get(code_prefix(code))
    if holder is None:
        raise ValueError(
            f"{code!r} has no body to edit — pass a "
            f"{' / '.join(f'{p}@' for p in _HOLDERS)} code. The brief of a task "
            "(goal, context, constraints, criteria) is not a body: it is edited with "
            "task_update."
        )
    return holder


def _seam(before: str, after: str) -> str:
    """Шов правки: по ``PREVIEW_WINDOW_CHARS`` символов по обе стороны, текст — заглушкой.

    ``…`` ставится только там, где окно обрезано серединой тела: край и так виден по тому, что
    окно кончилось, а неразличимые эти два случая заставляли бы гадать.
    """
    head, tail = before[-PREVIEW_WINDOW_CHARS:], after[:PREVIEW_WINDOW_CHARS]
    opening = SEAM_TRUNCATION_MARK if len(before) > PREVIEW_WINDOW_CHARS else ""
    closing = SEAM_TRUNCATION_MARK if len(after) > PREVIEW_WINDOW_CHARS else ""
    return f"{opening}{head}{SEAM_TEXT_PLACEHOLDER}{tail}{closing}"


def _elided(text: str) -> str:
    """Предпросмотр фрагмента: начало и конец через маркер пропуска; короткий — целиком."""
    if len(text) <= PREVIEW_WINDOW_CHARS * 2:
        return text
    return f"{text[:PREVIEW_WINDOW_CHARS]}{PREVIEW_ELISION_MARK}{text[-PREVIEW_WINDOW_CHARS:]}"


# ── чистые трансформы ─────────────────────────────────────────────────────────
def op_set(body: str, *, text: str) -> str:
    return text


def op_append(body: str, *, text: str, position: str) -> tuple[str, str]:
    if position == "start":
        return text + body, _seam("", body)
    if position == "end":
        return body + text, _seam(body, "")
    raise ValueError("position must be 'start' or 'end'.")


def op_insert(body: str, *, text: str, anchor: str, position: str) -> tuple[str, str]:
    count = body.count(_searchable(anchor))
    if count == 0:
        raise ValueError(f"Anchor {anchor!r} not found in the body.")
    if count > 1:
        raise ValueError(f"Anchor {anchor!r} occurs {count} times — it must be unique.")
    at = body.index(anchor)
    cut = at if position == "before" else at + len(anchor)
    if position not in ("before", "after"):
        raise ValueError("position must be 'before' or 'after'.")
    return body[:cut] + text + body[cut:], _seam(body[:cut], body[cut:])


def _searchable(find: str) -> str:
    """Пустая строка встречается везде и нигде не кончается: обход вхождений не завершился бы."""
    if not find:
        raise ValueError("The text to look for must not be empty.")
    return find


def _replacement_seams(body: str, *, find: str) -> list[str]:
    """Швы всех вхождений в порядке документа, каждый — окном по ИСХОДНОМУ телу."""
    seams, at = [], body.find(find)
    while at != -1:
        seams.append(_seam(body[:at], body[at + len(find):]))
        at = body.find(find, at + len(find))
    return seams


def op_replace(body: str, *, find: str, text: str) -> tuple[str, list[str]]:
    count = body.count(_searchable(find))
    if count == 0:
        raise ValueError(f"{find!r} is not in the body.")
    if count > 1:
        raise ValueError(
            f"{find!r} occurs {count} times — it must be unique to replace one. Pass a longer "
            "fragment, or mode='all' to replace every one."
        )
    return body.replace(find, text, 1), _replacement_seams(body, find=find)


def op_replace_all(body: str, *, find: str, text: str) -> tuple[str, list[str]]:
    seams = _replacement_seams(body, find=_searchable(find))
    if not seams:
        raise ValueError(f"{find!r} is not in the body.")
    return body.replace(find, text), seams


# ── разбор заголовков ─────────────────────────────────────────────────────────
_FENCE_LINE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


def _heading_level(line: str) -> int:
    """Уровень markdown-заголовка (число ведущих ``#``), или 0 если строка не заголовок."""
    stripped = line.lstrip()
    hashes = len(stripped) - len(stripped.lstrip("#"))
    if hashes == 0:
        return 0
    return hashes if len(stripped) == hashes or stripped[hashes] == " " else 0


def _heading_levels(lines: Sequence[str]) -> list[int]:
    """Уровень для каждой строки; 0 — не заголовок, в том числе внутри ограждённого кода."""
    levels, opened = [], ""
    for line in lines:
        fence = _FENCE_LINE.match(line)
        if opened:
            if fence and fence["marker"][0] == opened[0] and len(fence["marker"]) >= len(
                opened
            ) and not fence["info"].strip():
                opened = ""
            levels.append(0)
        elif fence:
            opened = fence["marker"]
            levels.append(0)
        else:
            levels.append(_heading_level(line))
    return levels


class _Scope(NamedTuple):
    start: int
    limit: int


def _block_end(levels: Sequence[int], start: int, limit: int) -> int:
    """Где обрывается блок заголовка: следующий заголовок того же или старшего уровня."""
    level = levels[start]
    for index in range(start + 1, limit):
        if levels[index] and levels[index] <= level:
            return index
    return limit


def _matches(lines, levels, segment: str, scope: _Scope) -> list[int]:
    return [
        index
        for index in range(scope.start, scope.limit)
        if levels[index] and lines[index].strip() == segment
    ]


def _segment_index(lines, levels, segment: str, scope: _Scope, resolved: Sequence[str]) -> int:
    """Единственная строка сегмента внутри области; ноль и два совпадения — отказ.

    Неоднозначность именно отказ, а не первое совпадение: молча взятый первый раздел переписал
    бы не тот, о котором агент думал, и узнать об этом было бы неоткуда.
    """
    if _heading_level(segment) == 0:
        raise ValueError(
            f"{segment!r} is not a markdown heading — every segment carries its own '#', "
            f"e.g. '## Section{HEADING_PATH_SEPARATOR}### Subsection'."
        )
    found = _matches(lines, levels, segment, scope)
    where = f"inside {resolved[-1]!r}" if resolved else "in the body"
    if not found:
        raise ValueError(f"Heading {segment!r} is not {where}.")
    if len(found) > 1:
        raise ValueError(
            f"Heading {segment!r} occurs {len(found)} times {where} — it must name exactly one "
            f"section. Say which with a path, segments separated by {HEADING_PATH_SEPARATOR!r}: "
            f"'## Section{HEADING_PATH_SEPARATOR}### Subsection'."
        )
    return found[0]


def _heading_index(lines, levels, heading: str) -> int:
    """Строка заголовка, названного голым заголовком или путём ``A > B``."""
    segments = [segment.strip() for segment in heading.split(HEADING_PATH_SEPARATOR)]
    scope = _Scope(0, len(lines))
    index = _segment_index(lines, levels, segments[0], scope, resolved=[])
    for depth, segment in enumerate(segments[1:], start=1):
        scope = _Scope(index + 1, _block_end(levels, index, scope.limit))
        index = _segment_index(lines, levels, segment, scope, resolved=segments[:depth])
    return index


class SectionCut(NamedTuple):
    """Что вырезала правка раздела: предпросмотр блока, его длина и оборвавший его заголовок.

    Границу считает сервер по уровню заголовка, так что непредсказуем для агента именно размах
    выреза: шов вокруг нового текста выглядел бы одинаково аккуратно и при вырезе вдвое шире
    нужного.
    """

    removed: str
    removed_length: int
    stopped_at: str | None


def op_set_section(body: str, *, heading: str, text: str) -> tuple[str, SectionCut]:
    """Заменить раздел (от заголовка до следующего равного или старшего уровня) на ``text``."""
    lines = body.split("\n")
    levels = _heading_levels(lines)
    start = _heading_index(lines, levels, heading)
    end = _block_end(levels, start, len(lines))
    removed = "\n".join(lines[start:end])
    cut = SectionCut(
        removed=_elided(removed),
        removed_length=len(removed),
        stopped_at=lines[end].strip() if end < len(lines) else None,
    )
    return "\n".join(lines[:start] + text.split("\n") + lines[end:]), cut


# ── применение ────────────────────────────────────────────────────────────────
Report = TypeVar("Report")


def _fits(text: str, holder: _Holder, code: str) -> str:
    """Результат целиком или отказ, называющий ЕГО длину, а не длину присланного куска."""
    if len(text) > holder.limit:
        raise ValueError(
            f"This would make {holder.what} of {code} {len(text)} characters long, and the "
            f"limit is {holder.limit} — {len(text) - holder.limit} too many. The limit refuses "
            "instead of trimming because the end of a plan is where the files are listed. "
            "Shorten what is already there, or move the detail into a stage."
        )
    return text


def _editable(row, code: str) -> None:
    """Начатый этап тело не меняет — «позади застывший» как шлюз, а не как просьба."""
    if isinstance(row, TasksStage) and row.status != STATUS_PLANNED:
        gone = "finished" if row.status in TASK_STATUSES_TERMINAL else "running"
        raise ValueError(
            f"Stage {code} is already {gone}, and the plan behind you does not get rewritten — "
            "otherwise nobody can tell what was promised from what was done. Record the change "
            "with note_add(type='decision') and add the stage that follows it."
        )


async def apply_edit(
    code: str, edit: Callable[[str], tuple[str, Report]]
) -> tuple[object, Report]:
    """Применить ``edit(body) -> (новое тело, отчёт)`` к телу сущности ``code`` (с префиксом)."""
    holder = _holder_for(code)
    bare = strip_prefix(code)
    async with write_scope() as s:
        row = await s.get(holder.model, bare)
        if row is None:
            raise ValueError(f"{code} does not exist.")
        _editable(row, code)
        text, report = edit(row.body or "")
        row.body = _fits(text, holder, code)
        await s.flush()
        await s.refresh(row)
    return row, report


async def apply(code: str, mutate: Callable[[str], str]) -> object:
    """``apply_edit`` для правки, которой нечего сообщить о себе сверх нового тела."""
    row, _ = await apply_edit(code, lambda body: (mutate(body), None))
    return row


__all__ = [
    "HEADING_PATH_SEPARATOR",
    "PREVIEW_ELISION_MARK",
    "PREVIEW_WINDOW_CHARS",
    "SEAM_TEXT_PLACEHOLDER",
    "SEAM_TRUNCATION_MARK",
    "SectionCut",
    "apply",
    "apply_edit",
    "op_append",
    "op_insert",
    "op_replace",
    "op_replace_all",
    "op_set",
    "op_set_section",
]
