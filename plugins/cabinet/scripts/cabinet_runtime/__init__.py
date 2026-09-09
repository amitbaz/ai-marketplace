"""Cabinet runtime package.

Standard-library-only modules backing the Cabinet MCP service. Installing the
plugin copies these files; there is no build step and no third-party import.

Modules:
    errors      CabinetError and the stable error-code table.
    contracts   canonical JSON digest, field validation, state machines.
    store       transactional SQLite store for events and projections.
    migration   non-destructive import of legacy Markdown documents.
    exports     atomic human-readable views written from stored state.
    processes   bounded subprocess adapter with an allowlisted environment.
    profiles    restricted launch profiles for the chief, staff and workers.
"""

__all__ = ["contracts", "errors", "exports", "migration", "processes",
           "profiles", "store"]
