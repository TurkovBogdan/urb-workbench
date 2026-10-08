"""tasks: the journal table tasks_note renamed to tasks_journal, with its constraints and indexes

The work journal is named after itself in every layer: the word "note" is freed for documents.
Only names change — the columns, their types and the rows stay as they are.

- **PostgreSQL** renames in place: the table, the primary key, the check, both foreign keys and
  both indexes. Nothing is rebuilt or rescanned.
- **SQLite** cannot rename a constraint or an index: the table is renamed, then rebuilt in batch
  mode with the constraints re-declared under the new names, and the indexes re-created. The
  journal is a leaf — nothing references it — so the rebuild fires no cascade; its own foreign
  keys are re-declared with the same ``ON DELETE CASCADE``, or deleting a task would stop
  clearing its journal.

Revision ID: tsm_010_journal
Revises: tsm_009_task_work_fields
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "tsm_010_journal"
down_revision: Union[str, None] = "tsm_009_task_work_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TYPES_CHECK = "type IN ('decision', 'remark', 'finding', 'fact')"

# (suffix of the foreign key name, column, target table) — as the model declares them.
_FOREIGN_KEYS = (("task_code", "task_code", "tasks"), ("stage_code", "stage_code", "tasks_stage"))
# (suffix of the index name, columns)
_INDEXES = (("task_created", ["task_code", "created_at"]), ("stage", ["stage_code"]))


def _rename_on_postgres(old: str, new: str) -> None:
    op.rename_table(old, new)
    op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT {old}_pkey TO {new}_pkey")
    op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT ck_{old}_type TO ck_{new}_type")
    for suffix, _column, _target in _FOREIGN_KEYS:
        op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT fk_{old}_{suffix} TO fk_{new}_{suffix}")
    for suffix, _columns in _INDEXES:
        op.execute(f"ALTER INDEX ix_{old}_{suffix} RENAME TO ix_{new}_{suffix}")


def _rename_on_sqlite(old: str, new: str) -> None:
    for suffix, _columns in _INDEXES:
        op.drop_index(f"ix_{old}_{suffix}", table_name=old)
    op.rename_table(old, new)
    with op.batch_alter_table(new, recreate="always") as batch_op:
        batch_op.drop_constraint(f"ck_{old}_type", type_="check")
        batch_op.create_check_constraint(f"ck_{new}_type", _TYPES_CHECK)
        for suffix, column, target in _FOREIGN_KEYS:
            batch_op.drop_constraint(f"fk_{old}_{suffix}", type_="foreignkey")
            batch_op.create_foreign_key(
                f"fk_{new}_{suffix}", target, [column], ["code"], ondelete="CASCADE"
            )
    for suffix, columns in _INDEXES:
        op.create_index(f"ix_{new}_{suffix}", new, columns)


def _rename(old: str, new: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        _rename_on_postgres(old, new)
    else:
        _rename_on_sqlite(old, new)


def upgrade() -> None:
    _rename("tasks_note", "tasks_journal")


def downgrade() -> None:
    _rename("tasks_journal", "tasks_note")
