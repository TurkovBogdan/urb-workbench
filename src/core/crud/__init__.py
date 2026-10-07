"""Core CRUD functions. Every update is a targeted UPDATE by id/key."""

from src.core.crud import lock, tasks, tasks_logs

__all__ = ["lock", "tasks", "tasks_logs"]
