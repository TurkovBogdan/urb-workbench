"""Moving a codex between installations: the ``.ucdx`` archive, its export and its import.

The export is whole — the codex, every record of every level with its code, segment and place,
the bin included, and the files with their bytes. The mounts stay: they are one installation's
layout, and the import asks where to mount instead. What every transfer shares is
``core_transfer``; what a codex is — one code space for two tables, segments, four levels — is
this package's.
"""
