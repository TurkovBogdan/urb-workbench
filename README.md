# urb-workbench

> A workbench for a developer and the agent that does the work. The person sets a task, the agent carries it through MCP, and everything it does shows up for the person right away as a page in the browser.

The application has two halves. The first is the **`workbench` MCP server**: twenty-two tools the agent uses to create tasks, write a plan, close stages and keep a journal. The second is the **web interface**: the same data, open to the person for reading and editing. The work does not dissolve with the agent's session — it stays in the database and outlives it.

## How work is organized

A **workspace** is the isolation boundary. Nothing is read across workspaces: that is how work is kept apart from personal matters, and one client from another. The agent picks a workspace once per connection, and after that no tool accepts it as an argument — addressing the wrong workspace in a single call is physically impossible.

Inside a workspace there are **groups** — standing topics — and **tasks** — the work itself. A task can be carried at three depths, and each one adds one way of working:

| Type | What it adds |
|---|---|
| `simple` | a title and a goal; often a task for the person rather than the agent |
| `standard` | plus a brief (context, constraints, acceptance criteria), a plan in prose and a journal of decisions, findings and facts |
| `extended` | plus **stages**: the plan broken into steps, each with its own state and its own evidence |

The agent may extend and refine the brief of any task, including one the person created — and it records an edit to someone else's brief as a journal entry. The one thing it does not do is accept the work. It hands finished work over in the `in_review` status — from there the person has the final word.

Every entity has its own prefixed code — `WORKSPACE@`, `TASKGROUP@`, `TASK@`, `STAGE@`, `JOURNAL@`. The code is both the page address and the argument to any tool.

## What the agent can do

Twenty-two tools in five groups.

- **Workspace.** List workspaces, pick the active one, list groups.
- **Work.** List and read tasks, create, edit, change status.
- **Plan.** Add a stage, edit it, close it. A stage cannot be closed without evidence: the argument is mandatory, and it expects a pointer — a command with its outcome, the path to a changed file, a diff summary.
- **Journal.** Add an entry, close it with a resolution, list entries. Entries are append-only: history cannot be rewritten.
- **Long text.** A task's plan, a stage's description and an entry's subject are edited in place: replace everything, replace a line, replace a section by its heading, append. The reply is not the document but the **edit seam** — a slice of text on each side of the insertion. That is where you can see whether something got glued together wrong.

On top of these five groups there are four standalone tools: `delete(code)` (one door for every type), `interface_open(code)` puts an entity on the person's screen, and `skills_list` / `skill_get` serve the server's own handbooks: how it expects a brief, a plan and a journal, and what its interface renders. The agent reads them before the work, not after a failure.

## Web interface

- **Workspaces** — a list with group and task counters; create, edit, delete.
- **Tasks** and **Groups** — a task tree with priorities and due dates, a task card with the brief, plan, stages and journal; editing in place.
- **Interface** — theme, fonts, styling of text, code blocks and diagrams.
- **Job monitoring** — not the same as tasks: the scheduler's background jobs, their runs and logs. Read-only.
- **Server** — edit `.env` right from the interface, with a process restart.
- **MCP servers** — what is exposed as an MCP server, its instructions, its tool list and a ready-made connection config.
- **Version and update** — the installed version, how far it lags behind the branch, and an update button.

## Requirements

You need **git** and **uv**; the application brings Python, its dependencies and its database by itself.

Install git with your system package manager — `apt`, `dnf`, `brew`. You don't have to think about uv: `./install.sh` offers to install it with Astral's official installer, which also downloads the right Python (3.12, pinned in `.python-version`).

There is no database to install: **SQLite** is the default — a single file, no server. PostgreSQL is an option for production scale (it needs a 14+ server with the database and user already created).

## Installation

```bash
git clone https://github.com/TurkovBogdan/urb-workbench.git && cd urb-workbench
./install.sh
```

The script checks the tools, installs the dependencies and starts the application — all that is left is to open the interface. Running it again is safe: it syncs the dependencies and brings the application up again.

> Packages are installed as prebuilt binaries — no compiler or system dev libraries are needed. The same by hand: `uv sync --all-groups`, then `./run.sh`.

**You don't need to write a `.env` file.** It does not exist until the first run: the application creates it with default values (`prod` mode, SQLite at `runtime/prod/app.sqlite3`) and issues itself two secrets — the MCP server token and the encryption master key. After that the file is edited on the "Server" page or by hand; annotated samples are `.env.example.prod` and `.env.example.dev`.

The database schema is deployed automatically **only on the first run, against an empty database**. After that, migrations are applied by the update (`./update.sh`), not by starting the application: a database that has fallen behind the code is met with a stub page listing the unapplied revisions.

## Running

```bash
./run.sh
```

The script starts the backend together with the background worker in one process and opens the browser as soon as the application responds. `./install.sh` ends the same way. The address comes from `.env` (`SERVER_HOST` / `SERVER_PORT`, default `http://127.0.0.1:13410`).

Other commands:

```bash
./run.sh stop        # stop this installation (only its own processes, neighbours are left alone)
./run.sh test        # run the tests; arguments pass through: ./run.sh test --core
./run.sh help        # help
```

The same without the wrapper: `uv run python src/app.py --backend --worker`. The `--backend` (HTTP server) and `--worker` (background jobs) flags can be split across separate processes; a single process takes both.

## Connecting an agent

There is no need to keep the server running by hand. The MCP client connects through a **stdio shim**: the client itself spawns the process when a session opens, the shim brings up the backend, opens the browser on the home page and forwards tool calls to it. The backend outlives the session: the next one connects to the already running instance.

A ready-made config is on the **"MCP servers"** page: it already contains this installation's absolute paths and the token. Copy it into your client's settings (Claude Desktop, Claude Code). It looks like this:

```json
{
  "mcpServers": {
    "workbench": {
      "command": "/path/to/uv",
      "args": [
        "run", "--directory", "/path/to/urb-workbench",
        "python", "src/app.py", "--mcp-stdio=workbench"
      ],
      "env": { "MCP_TOKEN": "<token from .env>" }
    }
  }
}
```

> The paths to `uv` and to the project (`--directory`) are **absolute**. Many MCP clients start from their own directory with a trimmed PATH, and without `--directory` uv won't find the project: "Connection Failed".

The agent picks the workspace itself (`workspaces_list` → `workspace_use`). To make a connection always open in the same one, add `--mcp-workspace=WORKSPACE@…` to the arguments: the session starts already bound.

## Updating

```bash
./update.sh            # update
./update.sh --dry-run  # show what would be done without touching anything
```

The command stops running MCP server instances, blocks new ones from starting while it works, and updates the installation. The "Update" button on the "Version and update" page does the same: it also shows how many commits behind the installation is.

## Structure

```
├── src/       # code: app.py (entry point), core/ (platform), modules/ (domains)
├── web/       # Vue 3 interface; web/dist/ is the built SPA, kept in the repository
├── runtime/   # data of the running application: database, cache, logs, backups
├── tests/     # tests
└── tools/     # utility scripts (demo data seeding)
```

There are eight modules. Three are application modules: `workspace` (workspaces — the shared isolation level), `notes` (markdown documents with no owner, which the modules above link to) and `tasks` (groups, the task tree, plan, journal and the `workbench` MCP server). The other five are infrastructure: `core_setup` (editing `.env`), `core_interface` (appearance settings), `core_monitoring` (background jobs), `core_mcp` (MCP server introspection), `core_changes` (the change feed behind live updates).

## For developers

```bash
./run.sh dev         # Vite with HMR + backend with hot reload (needs Node.js 20+ and pnpm)
./run.sh build-prod  # rebuild the frontend into web/dist
./run.sh test --core # core tests; full run: ./run.sh test --all
```

How the tests are organized and which flags they understand: [`tests/README.md`](tests/README.md).
