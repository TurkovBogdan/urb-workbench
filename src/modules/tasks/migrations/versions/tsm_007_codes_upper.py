"""tasks + workspace: every entity code to upper case

Codes are generated, stored and returned upper case from this revision on, and every incoming
code is folded to upper case (``codes.py`` in both modules). This revision converts the rows
written before: each primary key and each column that refers to one.

**It touches the ``workspaces`` table, which belongs to the module one level down.** The parent
and its children must change together: on PostgreSQL a foreign key is checked at once, so
``workspaces.code`` cannot change before the ``workspace_code`` columns pointing at it, nor
after — and the level-1 module may not depend on a level-2 revision. This module is allowed to
know about ``workspace`` (the reverse is forbidden), so the whole conversion lives here.

- **SQLite:** the runner turns foreign keys off around the migration and checks for violations
  after it (``core/database/sqlite.py::foreign_keys_disabled``), so plain ``UPDATE``s suffice.
- **PostgreSQL:** the eight foreign keys are dropped, the columns updated, and the keys
  re-created under the same names and actions as the models declare them.

Codes quoted inside text (task bodies, briefs, journal entries) are left as written: the entity
pill and the API fold case on the way in, so a lower-case reference still resolves. ``upper``
is ASCII-only on SQLite, which is all a hex code needs.

No ``depends_on``: ``workspaces`` already exists by ``tsm_001_group``'s dependency on
``wkm_001_workspaces``, and pointing at the workspace branch's head is the trap described in
``wkm_002``.

Revision ID: tsm_007_codes_upper
Revises: tsm_006_group_description_len
Create Date: 2026-10-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "tsm_007_codes_upper"
down_revision: Union[str, None] = "tsm_006_group_description_len"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODE_COLUMNS: dict[str, tuple[str, ...]] = {
    "workspaces": ("code",),
    "tasks_group": ("code", "workspace_code"),
    "tasks": ("code", "workspace_code", "group_code"),
    "tasks_link": ("task_code", "parent_code"),
    "tasks_stage": ("code", "task_code"),
    "tasks_note": ("code", "task_code", "stage_code"),
}

# (name, source table, source column, target table, ondelete) — as the models declare them.
_FOREIGN_KEYS: tuple[tuple[str, str, str, str, str], ...] = (
    ("fk_tasks_group_workspace_code", "tasks_group", "workspace_code", "workspaces", "CASCADE"),
    ("fk_tasks_workspace_code", "tasks", "workspace_code", "workspaces", "CASCADE"),
    ("fk_tasks_group_code", "tasks", "group_code", "tasks_group", "SET NULL"),
    ("fk_tasks_link_task_code", "tasks_link", "task_code", "tasks", "CASCADE"),
    ("fk_tasks_link_parent_code", "tasks_link", "parent_code", "tasks", "CASCADE"),
    ("fk_tasks_stage_task_code", "tasks_stage", "task_code", "tasks", "CASCADE"),
    ("fk_tasks_note_task_code", "tasks_note", "task_code", "tasks", "CASCADE"),
    ("fk_tasks_note_stage_code", "tasks_note", "stage_code", "tasks_stage", "CASCADE"),
)


def _convert(function: str) -> None:
    on_postgres = op.get_bind().dialect.name == "postgresql"
    if on_postgres:
        for name, source, _column, _target, _ondelete in _FOREIGN_KEYS:
            op.drop_constraint(name, source, type_="foreignkey")
    for table, columns in _CODE_COLUMNS.items():
        for column in columns:
            op.execute(
                f"UPDATE {table} SET {column} = {function}({column}) "
                f"WHERE {column} IS NOT NULL AND {column} <> {function}({column})"
            )
    if on_postgres:
        for name, source, column, target, ondelete in _FOREIGN_KEYS:
            op.create_foreign_key(name, source, target, [column], ["code"], ondelete=ondelete)


def upgrade() -> None:
    _convert("upper")


def downgrade() -> None:
    _convert("lower")
