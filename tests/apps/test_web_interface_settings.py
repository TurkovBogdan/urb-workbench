"""The interface settings registry and the frontend talk about the same thing.

Defaults and sets of allowed values are declared on the backend (``core_interface/registry.py``),
but the frontend draws the choice for the person from its own lists — with labels and notes the
schema does not and will not carry. So the lists stay in ``web/src/constants``, and the only risk
here is divergence: a set that has drifted from the registry means an option that can be picked
on screen and is rejected by the server with 422.

The test catches the divergence on a run rather than on a live click. Like the neighbouring
frontend checks, it reads sources as text — no build, no browser, hence ``pure``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.modules.core_interface.registry import SETTINGS

pytestmark = pytest.mark.pure

WEB_SRC = Path(__file__).resolve().parents[2] / "web" / "src"
CONSTANTS = WEB_SRC / "constants"

INTERFACE_PAGE = WEB_SRC / "features" / "settings" / "views" / "InterfaceView.vue"
DOCUMENT_COLUMN = WEB_SRC / "layout" / "components" / "DocumentAppearance.vue"

# The settings-page groups that the detail column repeats. The fourth, "Interface", is absent
# there: theme, interface font and list layout have nothing to do with the document on display.
DOCUMENT_COLUMN_GROUPS = ("document", "code", "diagram")

# A group starts with its label and the fields follow it — both on the page (`<SettingsGroup
# :title>`) and in the column (a header strip). So both surfaces are read by one parse. For a field
# not only the binding is read but also the control: a list with left-right stepping and a plain
# list are different controls, and the choice between them belongs to the setting, not to where it
# is shown.
_GROUP_OR_FIELD = re.compile(
    r"settings\.interface\.group\.(\w+)\.title"
    r"|<(\w+)[^>]*?v-model=\"settings\.([\w.]+)\""
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _numbers(source: str, name: str) -> list[int]:
    body = re.search(rf"{name} = \[([^\]]*)\]", source).group(1)
    return [int(value) for value in re.findall(r"-?\d+", body)]


def _number(source: str, name: str) -> int:
    return int(re.search(rf"{name} = (-?\d+)", source).group(1))


def _string(source: str, name: str) -> str:
    return re.search(rf"{name}(?:: \w+)? = '([^']*)'", source).group(1)


def _codes(source: str, name: str) -> list[str]:
    body = re.search(rf"{name}(?:: [\w\[\]]+)? = \[(.*?)\n\]", source, re.S).group(1)
    return re.findall(r"code: '([^']*)'", body)


def _font_code(source: str, name: str) -> str:
    """``DEFAULT_MONO_FONT = JETBRAINS_MONO.code`` — resolve the reference down to the code itself."""
    option = re.search(rf"{name} = (\w+)\.code", source).group(1)
    return re.search(rf"const {option}: FontOption = \{{\s*code: '([^']*)'", source).group(1)


def _fields_by_group(path: Path) -> dict[str, list[tuple[str, str]]]:
    """"Control + store binding" fields, sorted into groups in order of appearance."""
    groups: dict[str, list[tuple[str, str]]] = {}
    current: list[tuple[str, str]] = []
    for match in _GROUP_OR_FIELD.finditer(_source(path)):
        group, control, binding = match.groups()
        if group is not None:
            current = groups.setdefault(group, [])
        else:
            current.append((control, binding))
    return groups


def _options(key: str) -> list:
    return list(SETTINGS[key].options or ())


def _default(key: str):
    return SETTINGS[key].default


def test_store_syncs_exactly_the_keys_the_registry_declares():
    store = _source(WEB_SRC / "stores" / "settings.ts")

    assert set(re.findall(r"synced(?:<[^>]+>)?\('([^']+)'", store)) == set(SETTINGS)


def test_switch_defaults_in_the_store_match_the_registry():
    """For toggles the default is written as a literal in the store itself — they have no constant.

    A divergence here is quiet and nasty: a value that matches the wrong default goes to the server
    as a reset instead of a write, and the setting snaps back on the next hydration.
    """
    store = _source(WEB_SRC / "stores" / "settings.ts")
    declared = {
        key: literal == "true"
        for key, literal in re.findall(r"synced\('(\w+)', (true|false), boolCodec\)", store)
    }

    assert declared == {
        key: setting.default
        for key, setting in SETTINGS.items()
        if isinstance(setting.default, bool)
    }


def test_document_column_repeats_the_page_groups_field_for_field():
    """The detail column and the settings page show the same fields with the same controls.

    A setting here is one for two places (a shared store), so diverging sets mean either a field
    editable only on the settings page or — worse — a field filed under the wrong group in the
    column: that is how the code font once ended up as "document appearance". Both the order is
    checked (in the same column of fields the eye looks for a familiar spot rather than reading
    labels) and the control: a left-right stepping list swapped for a plain list takes away
    stepping through neighbouring options — the very move the setting is opened next to the text
    for.
    """
    page = _fields_by_group(INTERFACE_PAGE)

    assert _fields_by_group(DOCUMENT_COLUMN) == {
        group: page[group] for group in DOCUMENT_COLUMN_GROUPS
    }


def test_language_matches_the_registry():
    language = _source(CONSTANTS / "language.ts")

    assert _codes(language, "LANGUAGE_OPTIONS") == _options("interface_language")
    assert _string(language, "DEFAULT_LANGUAGE") == _default("interface_language")


def test_theme_matches_the_registry():
    theme = _source(CONSTANTS / "theme.ts")

    assert _codes(theme, "THEME_OPTIONS") == _options("interface_theme")
    assert _string(theme, "DEFAULT_THEME") == _default("interface_theme")


def test_reading_zone_matches_the_registry():
    fonts = _source(CONSTANTS / "fonts.ts")

    assert _numbers(fonts, "READING_SIZES") == _options("interface_font_reading_size")
    assert _numbers(fonts, "READING_MEASURES") == _options("interface_font_reading_measure")
    assert _number(fonts, "DEFAULT_READING_SIZE") == _default("interface_font_reading_size")
    assert _number(fonts, "DEFAULT_READING_MEASURE") == _default("interface_font_reading_measure")


def test_font_defaults_match_the_registry():
    fonts = _source(CONSTANTS / "fonts.ts")

    assert _font_code(fonts, "DEFAULT_INTERFACE_FONT") == _default("interface_font")
    assert _font_code(fonts, "DEFAULT_READING_FONT") == _default("interface_font_reading")
    assert _font_code(fonts, "DEFAULT_MONO_FONT") == _default("interface_font_mono")
    assert _font_code(fonts, "DEFAULT_DIAGRAM_FONT") == _default("interface_font_diagram")


def test_diagram_layout_matches_the_registry():
    diagrams = _source(CONSTANTS / "diagrams.ts")

    assert _codes(diagrams, "DIAGRAM_ALIGNS") == _options("interface_diagram_align")
    assert _numbers(diagrams, "DIAGRAM_HEIGHTS") == _options("interface_diagram_max_height")
    assert _string(diagrams, "DEFAULT_DIAGRAM_ALIGN") == _default("interface_diagram_align")
    assert _number(diagrams, "DEFAULT_DIAGRAM_HEIGHT") == _default("interface_diagram_max_height")


# The research list layout was checked here too while it was an interface setting. The key
# `interface_list_research_view` was removed along with the section (2026-09-20): the value set
# remains only in the frontend (`constants/lists.ts`), and there is nothing to check it against.


# Option labels live in the dictionary by code (`composables/useAppearanceOptions.ts`), and the
# constants keep only codes and proper names. A miss here is quiet: `vue-i18n` renders the key path,
# and the option shows in the list as `settings.interface.option.font.lora.note`.
_OPTION_SOURCES = {
    "theme": ("theme.ts", "THEME_OPTIONS"),
    "code_variant": ("code.ts", "CODE_VARIANTS"),
    "diagram_align": ("diagrams.ts", "DIAGRAM_ALIGNS"),
    "diagram_theme": ("diagrams.ts", "DIAGRAM_THEMES"),
}
_OPTION = re.compile(r"\{\s*code: ('[^']*'|\w+)(,\s*label: '[^']*')?")


def _option_strings() -> dict:
    strings = json.loads((WEB_SRC / "features" / "settings" / "locales" / "ru.json").read_text(encoding="utf-8"))
    return strings["interface"]["option"]


def _declared_options(kind: str) -> dict[str, bool]:
    """Option code → whether it has its own label in the constants."""
    if kind == "font":
        source = _source(CONSTANTS / "fonts.ts")
        return {
            code: bool(label)
            for code, label in re.findall(r": FontOption = \{\s*code: '([^']+)',(\s*label: '[^']*')?", source)
        }
    path, name = _OPTION_SOURCES[kind]
    source = _source(CONSTANTS / path)
    body = re.search(rf"{name}(?:: [\w\[\]]+)? = \[(.*?)\n\]", source, re.S).group(1)
    return {
        code.strip("'") if code.startswith("'") else _string(source, code): bool(label)
        for code, label in _OPTION.findall(body)
    }


@pytest.mark.parametrize("kind", [*_OPTION_SOURCES, "font"])
def test_every_option_has_its_words_in_the_dictionary(kind: str):
    strings = _option_strings()[kind]
    declared = _declared_options(kind)

    assert declared
    assert {code for code in declared if "note" not in strings.get(code, {})} == set()
    assert {code for code, own in declared.items() if not own and "label" not in strings.get(code, {})} == set()
