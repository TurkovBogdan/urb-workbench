"""workbench — the agent surface: the ``workbench`` MCP server, its tools, skills and refusals.

**Level 3**, above every domain module: it implements each tool by calling the services and CRUD
of the modules below (``workspace``, ``notes``, ``tasks``), and none of them imports it back. The
person reaches the same data through each domain module's own HTTP API; the agent reaches it
here.
"""

from src.modules.workbench.module import WorkbenchModule

__all__ = ["WorkbenchModule"]
