"""Строки с числом склоняются правилом своего языка.

Правила лежат в `web/src/plugins/plural.ts` и подключены к `vue-i18n` (`pluralRules`). Без них
библиотека выбирает форму по индексу `min(n, 2)`, и русское «5 коммитов» выходит «5 коммита».
Промах не роняет страницу — он просто читается неграмотно, поэтому ловится здесь.

Правило исполняется настоящим файлом под Node (`--experimental-strip-types`), а не копией на
Python: копия разошлась бы с оригиналом молча. Без Node тест пропускается.

Заодно ловится буквальная `|` в тексте: для `vue-i18n` это разделитель форм, и строка без числа
рисуется одним своим куском. Пишется она как `{'|'}`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
RULES = WEB_SRC / "plugins" / "plural.ts"

# Сколько форм пишется в строке с числом: с отдельной формой нуля и без неё.
FORM_COUNTS = {"en": {2, 3}, "ru": {3, 4}}

_ESCAPED_PIPE = "{'|'}"


def _dictionaries(locale: str) -> list[Path]:
    return sorted(
        path
        for path in WEB_SRC.rglob(f"{locale}.json")
        if path.parent.name == "locales" or path.parent.parent.name == "locales"
        if "research" not in path.parts and "web_search" not in path.parts
    )


def _leaves(node, prefix: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _leaves(value, f"{prefix}[{index}]")
    elif isinstance(node, str):
        yield prefix, node


def _plural_messages(locale: str) -> dict[str, list[str]]:
    found = {}
    for path in _dictionaries(locale):
        strings = json.loads(path.read_text(encoding="utf-8"))
        for key, value in _leaves(strings):
            if "|" in value.replace(_ESCAPED_PIPE, ""):
                found[f"{path.relative_to(WEB_SRC).as_posix()}:{key}"] = [
                    form.strip() for form in value.split("|")
                ]
    return found


def _forms_chosen(locale: str, numbers: list[int], forms: int) -> list[int]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node не найден — правило склонения нечем исполнить")
    script = (
        f"import {{ PLURAL_RULES }} from '{RULES.as_uri()}';"
        f"console.log(JSON.stringify({json.dumps(numbers)}.map((n) => PLURAL_RULES.{locale}(n, {forms}))))"
    )
    result = subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _render(message: str, locale: str, n: int) -> str:
    forms = [form.strip() for form in message.split("|")]
    [index] = _forms_chosen(locale, [n], len(forms))
    return forms[index].replace("{n}", str(n))


def _message(feature: str, locale: str, key: str) -> str:
    node = json.loads((WEB_SRC / "features" / feature / "locales" / f"{locale}.json").read_text(encoding="utf-8"))
    for step in key.split("."):
        node = node[step]
    return node


@pytest.mark.parametrize("locale", sorted(FORM_COUNTS))
def test_every_plural_message_has_the_forms_its_language_needs(locale: str):
    wrong = {
        key: len(forms)
        for key, forms in _plural_messages(locale).items()
        if len(forms) not in FORM_COUNTS[locale]
    }

    assert not wrong, wrong


def test_russian_takes_one_few_many():
    message = _message("about", "ru", "upstream.behind")

    assert [_render(message, "ru", n) for n in (0, 1, 2, 5, 11, 12, 14, 21, 22, 25, 101, 111)] == [
        "0 коммитов",
        "1 коммит",
        "2 коммита",
        "5 коммитов",
        "11 коммитов",
        "12 коммитов",
        "14 коммитов",
        "21 коммит",
        "22 коммита",
        "25 коммитов",
        "101 коммит",
        "111 коммитов",
    ]


def test_english_takes_one_other():
    message = _message("about", "en", "upstream.behind")

    assert [_render(message, "en", n) for n in (0, 1, 2, 21)] == [
        "0 commits",
        "1 commit",
        "2 commits",
        "21 commits",
    ]


def test_a_zero_form_is_picked_only_when_written():
    assert _forms_chosen("ru", [0, 1, 2, 5], 4) == [0, 1, 2, 3]
    assert _forms_chosen("en", [0, 1, 2], 3) == [0, 1, 2]


def test_rules_file_is_what_the_i18n_plugin_registers():
    plugin = (WEB_SRC / "plugins" / "i18n.ts").read_text(encoding="utf-8")

    assert re.search(r"pluralRules:\s*PLURAL_RULES", plugin)
