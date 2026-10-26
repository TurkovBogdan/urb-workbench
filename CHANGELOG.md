# Changelog

English · [Русский](docs/changelog/ru.md)

## [0.10.15] — 2026-10-26

### Added

#### Moving tasks and knowledge bases

- A task can be exported to `.utsk` from its row menu (right click or "⋯") and from the "⋯" menu of its page. The archive holds the task, its subtasks, stages, journal, notes and files. The group and deleted items stay behind.
- A knowledge base can be exported whole to `.ucdx`: rules, every record including the bin, files. "Export" is in the row menu of "Available" and in the materials tree.
- Import is in the new "⋯" menu at the top of each section: drop the file into the window or pick it with a click. A task goes into the group you choose; a knowledge base can be mounted into the workspace at once.
- Codes are kept. For each taken code you choose "Update" or "Replace". A replacement comes in as a copy with a new code, and references in texts follow it. Both sides' change dates are shown alongside.
- A task of another workspace, a note of another task, a record of another knowledge base and a file with other content can only be replaced. "Update" never deletes what exists only here.
- A file with the same content is not a conflict: the one here is used.
- A taken knowledge base path gets a suffix: `-2`, `-3`…
- A damaged archive is refused before anything is written.

#### Storage

- An imported file keeps its `FILE@` code.
- The new `core_transfer` module holds what both transfers share.

## [0.10.13] — 2026-10-26

### Added

#### Files

- Files can now be attached to a task, a stage, a task note and a knowledge base note: screenshots, exports, diagrams, documents.
- A task's page and a knowledge base note have a new "Files" section. It shows everything attached — by people and by the agent alike.
- Files are uploaded with the "Upload files" button — several at once — or dragged from a folder on your computer straight onto the section.
- Uploads go in a queue: files are sent one at a time, each with a card showing its progress. If the server refuses one, the reason stays on its card until you dismiss it.
- A folder, or a file over the storage limit, is never sent: the app says why at once.
- You set the order of the files: drag a card by its handle. A file the agent attaches goes to the end of the list.
- A card's menu has "Open in a new tab", "Download" and "Delete". Deleting takes the file out of this place only: if the same file is attached elsewhere, it stays there.
- A task also shows the files of its notes and stages — the "Notes (N)" and "Stages (N)" switches bring them in. The task's own files are always shown.
- A file can be pasted or dropped straight into a text field. It is attached to the field's owner, and its code goes into the text: `IMAGE@` for a picture, `FILE@` for anything else.
- The same without dragging: "Picture or file…" in the "/" menu.
- Where a file from a field goes: from the task's fields and a journal entry — to the task, from a stage's field — to the stage, from a note's field — to the note.

#### Editor

- An `IMAGE@` code in a text shows as the picture itself — both when reading and when editing.
- Auto galleries: pictures written one after another in a paragraph form a gallery. Rows line up to one height and fill the width, and every picture keeps its proportions. On a narrow screen the gallery steps down to two and then one picture per row.
- A gallery ends at a blank line: put a paragraph break between pictures and a new one begins.
- A picture can be dragged to another place in its gallery, into another gallery or into a line of text. Alt+←/→ moves the selected picture along its gallery.
- A right click on a picture opens its menu: copy the code, copy the picture itself, open, download, remove from the text or delete the file.
- The button in a picture's corner copies its code in one click.
- A `FILE@` code shows as a link pill: a click opens the file in a new tab.
- The card that pops up over a file's pill has "Open" and "Download".
- A picture opens full screen, and the gallery pages: with the arrows, with ←/→ and A/D, and with a swipe on a phone.
- Under the picture in the viewer are its title and description. On the page of the file's owner they can be edited right there.
- A diagram has a right-click menu: "Edit" and "Delete".

#### Agent (MCP)

- The `attach_file` tool attaches a file to a task, a stage, a task note or a knowledge base note and returns the code to put into a text.
- The agent names the file by a path on the server or by the code of a file already stored. When the server cannot see the file, the agent gets a one-time address and uploads the file with `curl`.
- The `file_get` tool tells what a file is and where to get it. The `workbench://file/{code}` resource shows the file to the model itself.
- `task_get` and `codex_get` return the owner's files.
- `delete` and `interface_open` take a `FILE@` code.

#### Storage

- Files are kept by three new modules: `core_storage`, `core_storage_upload` and `core_storage_view`.
- The same content is stored once, however many times it is attached.
- A file attached nowhere any more is removed from disk after 48 hours.
- A file can be uploaded only from the app's own page or to a one-time address.
- SVG and HTML open in a sandbox: a script inside such a file gets none of the app's rights.

### Interface

- "Settings → Modules" is back in the menu. The modules' names and descriptions there are translated.
- It holds the storage and upload settings: how many hours before a file is removed, the size limit (128 MB by default), how long a one-time upload address stays open, and whether files are read by a path on the server.
- The ENV page has a new "File storage folder" field.
- While you drag files over the window, the places that take them get a dashed outline. The place under the pointer lights up and shows the size limit.
- A new file lights up in the list for 700 ms — wherever it came from: the section, a text or the agent.
- File cards are coloured by format: spreadsheet and CSV — green, document — blue, PDF — red, slides — orange, archive — yellow, picture — sky blue, video — violet, audio — rose, calendar — teal. Text, code and unknown formats are grey.
- A picture's card shows its thumbnail, any other card the glyph of its type.
- A file's pill in a text is green, to stand apart from the pills of tasks and notes. Its glyph shows the type: PDF, document, spreadsheet, slides, archive, audio, video, code.
- The code card no longer repeats the code as a line: the pill under it shows it.
- The code card has a copy button that names the type: "Task code", "Stage code", "File code".
- The code card's "Open in new tab" button is shorter now — "New tab".
- Diagram: a softer background, a fainter hint under it in the editor, a new icon on the zoom reset button.
- There is no longer an empty line under the last block that could not be deleted.
- To keep writing after the last block, press Enter, the down arrow or Ctrl+Enter — or click below the text. The design system stand "Document edges: empty lines" shows how this works for each block.
- On a phone the picture viewer takes the whole screen, and the arrows move to the bottom corners, clear of the picture.

### Changed

- The app starts the background worker by default (`MCP_STDIO_START_WORKER=true`).
- When a task, a stage, a note or a workspace is deleted for good, its files are released. After a soft delete the files stay for the restore.
- A task opened by a link from another workspace reads its codes in its own workspace. Before, every pill in it showed as foreign.

### Fixed

- Tooltips, dialogs, menus and editor toolbars close with their page and no longer stay on top of the next one.
- The arrow keys in a table no longer put the caret between cells.
- Pasting after a code at the end of a paragraph: text that starts with a blank line goes into a new paragraph. Before, it stuck to the code — `TASK@1a2b3c4d5eText`.
- A code followed directly by a letter or a digit gets a space on save. Glued, it stopped reading as a code.
- Bold and italic around a code stay one run. Before, every save split `**bold CODE text**` into `**bold** CODE **text**`.
- A file dropped outside an upload place no longer makes the browser open it instead of the app.
- A `file:///…` path from a drag is no longer typed into the text.
