"""The tools of the ``workbench`` server, one file per area; each exposes ``register(mcp)``.

No file imports ``fastmcp`` at the top level (``FastMCP`` only under ``TYPE_CHECKING``): the
package is pulled in by ``build_modules()``, and the worker must stay free of the fork.
"""
