"""Content editing over MCP — ``content_*`` tools and the per-field handlers behind them.

``base.py`` holds the handler every field inherits: the four actions and the string work.
``task.py`` / ``stage.py`` / ``note.py`` hold one handler class per content field, ``registry.py``
maps "code prefix + field" to its handler, ``tools.py`` registers the tools.
"""

from src.modules.tasks.mcp.content.tools import register

__all__ = ["register"]
