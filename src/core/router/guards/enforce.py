"""Attaching guards to routes and enforcing them — three stages of one layer.

- **Declaration** — ``@guard("kind", *args)`` puts an opaque rule ``(kind, *args)`` on the
  endpoint function (data only, the core does not parse it);
  ``guard_rules``/``is_allow_all``/``is_deny_all`` read these marks back.
- **Execution** — ``make_zone_guard`` builds ``zone_guard`` (a zone dependency): on
  every request it handles ``allow_all``/``deny_all`` itself and resolves the other kinds through
  the registry (zone default + mark kinds, in order; the first ``raise`` stops it).
- **Validation** — ``validate_guard_rules`` checks at build time that every referenced
  kind is registered (the decorator cannot — it runs at import, before the registry exists).
"""

from __future__ import annotations

from starlette.requests import HTTPConnection

from src.core.router.guards.registry import GuardFn, GuardRegistry


def guard(kind: str, *args: str):
    """Attach a ``(kind, *args)`` rule to the endpoint. The core does not interpret it."""

    def deco(fn):
        fn.__guards__ = (*getattr(fn, "__guards__", ()), (kind, *args))
        return fn

    return deco


def guard_rules(endpoint) -> tuple:
    """All of the route's rules: a tuple of ``(kind, *args)``."""
    return getattr(endpoint, "__guards__", ())


def is_allow_all(endpoint) -> bool:
    return ("allow_all",) in guard_rules(endpoint)


def is_deny_all(endpoint) -> bool:
    return ("deny_all",) in guard_rules(endpoint)


def make_zone_guard(registry: GuardRegistry, default: list[str]) -> GuardFn:
    """A zone dependency: ``default`` is the zone's default kinds (default-on).

    ``allow_all``/``deny_all`` execute at once; otherwise run the zone default +
    the mark kinds in order, each through the registry. Empty ⇒ ``deny_all`` (fallback).
    """

    async def zone_guard(connection: HTTPConnection) -> None:
        endpoint = connection.scope["endpoint"]
        if is_allow_all(endpoint):
            return await registry.resolve("allow_all")(connection)
        if is_deny_all(endpoint):
            return await registry.resolve("deny_all")(connection)
        kinds = (*default, *(rule[0] for rule in guard_rules(endpoint)))
        for kind in kinds or ("deny_all",):
            await registry.resolve(kind)(connection)

    return zone_guard


def validate_guard_rules(app, registry: GuardRegistry, *, defaults=()) -> None:
    """Check at build time that every guard kind is registered.

    Scans the kinds in ``@guard(...)`` on every route of ``app`` and the zone's default
    kinds (``defaults``). An unregistered kind ⇒ ``RuntimeError`` at
    startup ("a guard must be registered before use"). The decorator
    runs at import, so the check lives here, after the registry is assembled.
    """
    unknown: list[str] = []
    for kind in defaults:
        if not registry.has(kind):
            unknown.append(f'default "{kind}"')
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        for rule in guard_rules(endpoint):
            if not registry.has(rule[0]):
                path = getattr(route, "path", "?")
                unknown.append(f'@guard("{rule[0]}") @ {path}')
    if unknown:
        raise RuntimeError(
            "guard kinds not registered in the registry: " + ", ".join(unknown)
        )


__all__ = [
    "guard",
    "guard_rules",
    "is_allow_all",
    "is_deny_all",
    "make_zone_guard",
    "validate_guard_rules",
]
