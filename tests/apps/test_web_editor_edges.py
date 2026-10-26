"""The editor keeps no line markdown does not store: the document's edges.

``StarterKit`` of Tiptap 3 brings ``TrailingNode``: an empty paragraph after a closing list, table,
code block or diagram that no key could delete — the same transaction put it back — and that never
reached the stored markdown. The editor turns it off, and a person writes past the last block by the
blocks' own exits, the gap cursor, or a press below the text (``behavior/continueBelow.ts``).

The gap cursor itself must not stand between table cells: drawn inside ``<tr>`` it took a cell's
place, and a key typed there added a cell. ``TableRow`` refuses it.

The behaviour needs a browser — the stand is the "Document edges" section of
``/design-system/markdown-editor``. This file only keeps the two settings from coming back by
accident. Sources are read as text: ``pure``. TASK@A6235116E9.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

EDITOR = Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "markdown" / "editor"


def test_the_editor_turns_trailing_node_off() -> None:
    text = (EDITOR / "MarkdownEditor.vue").read_text(encoding="utf-8")
    assert re.search(r"StarterKit\.configure\(\{.*?\btrailingNode: false,", text, re.S)


def test_a_table_row_takes_no_gap_cursor() -> None:
    text = (EDITOR / "blocks" / "table.ts").read_text(encoding="utf-8")
    row = re.search(r"export const TableRow = Node\.create\(\{(.*?)\n\}\)", text, re.S)
    assert row, "TableRow not found — the check reads a renamed node"
    assert "allowGapCursor: false" in row.group(1)


def test_a_press_below_the_text_continues_it() -> None:
    text = (EDITOR / "MarkdownEditor.vue").read_text(encoding="utf-8")
    assert '@mousedown="onBodyPress"' in text
    assert "continueBelow(" in text
