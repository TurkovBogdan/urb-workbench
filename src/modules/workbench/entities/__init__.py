"""The entity types the agent surface reaches by code — one module per domain module below, and
``file.py`` for a stored file, held by the tasks and the codexes at once.

Each holds the handlers of its types for the shared methods (``contracts.py``): the fence, and
where the type has them, deletion and a page. The registries that dispatch to them live with the
tools (``scope.py``, ``tools/delete.py``, ``tools/interface.py``, ``content/registry.py``).
"""
