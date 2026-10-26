"""File codes: generation and the normal form of an incoming code.

The module has its own code standard and its own copy of the technique: the stored code is a
bare hex hash of ``CODE_LEN`` in upper case. The module takes and returns codes without a
prefix — a presentation prefix belongs to whoever shows the code outside.
"""

from __future__ import annotations

import string

from src.core.utils.hashing import random_hash
from src.modules.core_storage.constants import CODE_LEN
from src.modules.core_storage.errors import FileNotFound

_HEX = frozenset(string.hexdigits.upper())


def new_code() -> str:
    """A new file code — a bare ``CODE_LEN``-hex ``random_hash``, upper case."""
    return random_hash(CODE_LEN).upper()


def parse_code(value: str) -> str | None:
    """An incoming code in its stored form — trimmed, upper case — or ``None`` if malformed."""
    code = value.strip().upper() if isinstance(value, str) else ""
    if len(code) != CODE_LEN or not set(code) <= _HEX:
        return None
    return code


def normalize_code(value: str) -> str:
    """An incoming code in its stored form.

    A malformed code is ``FileNotFound``, the same refusal as a well-formed code nobody
    registered: a typo is the commonest way to miss a file, and the caller handles one miss,
    not two kinds of it.
    """
    code = parse_code(value)
    if code is None:
        raise FileNotFound(str(value))
    return code


__all__ = ["new_code", "normalize_code", "parse_code"]
