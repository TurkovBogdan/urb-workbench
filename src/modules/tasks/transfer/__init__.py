"""Moving a task between installations: the ``.utsk`` archive, its export and its import.

The archive carries the task with its subtasks, stages, journal, notes and files — the bytes too —
and leaves out the group and the workspace: the import asks for them. What every transfer shares
is ``core_transfer``; what a task is, and what may happen to one here, is this package's.
"""
