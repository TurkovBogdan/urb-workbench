"""Files on the agent surface — the places a ``FILE@`` is held and the holders it is attached to.

``places.py`` reads where a file is bound and which of those bindings the active workspace sees;
``holders.py`` maps a holder's code prefix to the binding table it writes. The tools are in
``tools/file.py``, the ``FILE@`` handler of the shared methods in ``entities/file.py``.
"""
