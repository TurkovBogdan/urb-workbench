"""References ``TYPE@CODE`` in texts: collected, and rewritten by an import's map of codes.

The texts of an archive refer to its entities by code, and when an import gives one a new code,
the references must move with it. The rewrite is **one pass of one pattern** over a dictionary:
rewriting pair by pair chains into itself (a code that has just become ``B`` moves on to ``C``
with the second pair) and spoils the texts silently.

A key of the map is a pair «canonical type + code», not a bare code: one hash may be a note's
code in the archive and a stage's code here, and their rewrites differ. An alias reads as its
canonical type — ``IMAGE@X`` is the file ``FILE@X`` shown as a picture — and keeps the word it was
written with.

The match ignores case, as the interface's ``REF_CODE`` does (bodies written before codes were
upper case quote them in lower case); a rewritten code is written in upper case, the stored form.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

CODE_LEN = 10

RefMap = Mapping[tuple[str, str], str]


class ReferenceScheme:
    """The reference words one consumer reads, and the aliases among them."""

    def __init__(self, prefixes: Iterable[str], *, aliases: Mapping[str, str] | None = None) -> None:
        self.aliases = {word.upper(): target.upper() for word, target in (aliases or {}).items()}
        words = sorted({word.upper() for word in prefixes} | set(self.aliases), key=len, reverse=True)
        # The look-ahead cuts a longer hash off: without it the first ten characters of a retired
        # 22-character code would be taken for a reference and moved to nowhere.
        self.pattern = re.compile(
            rf"\b({'|'.join(map(re.escape, words))})@([0-9a-f]{{{CODE_LEN}}})(?![0-9a-f])",
            re.IGNORECASE,
        )

    def canonical(self, word: str) -> str:
        word = word.upper()
        return self.aliases.get(word, word)

    def collect(self, text: str | None) -> set[tuple[str, str]]:
        """``(canonical type, code)`` pairs a text refers to."""
        if not text:
            return set()
        return {
            (self.canonical(match.group(1)), match.group(2).upper())
            for match in self.pattern.finditer(text)
        }

    def rewrite(self, text: str | None, mapping: RefMap) -> tuple[str | None, int]:
        """Rewrite by ``(canonical type, old code) → new code``; return the text and the count.

        Each occurrence is resolved exactly once — the result of a replacement is not looked at
        again, so no chain of rewrites can form. A reference absent from the map stays as it is:
        a code that did not change, or a reference out of the archive.
        """
        if not text:
            return text, 0

        rewritten = 0

        def substitute(match: re.Match[str]) -> str:
            nonlocal rewritten
            word, code = match.group(1), match.group(2).upper()
            replacement = mapping.get((self.canonical(word), code))
            if replacement is None or replacement == code:
                return match.group(0)
            rewritten += 1
            return f"{word}@{replacement}"

        return self.pattern.sub(substitute, text), rewritten


__all__ = ["CODE_LEN", "RefMap", "ReferenceScheme"]
