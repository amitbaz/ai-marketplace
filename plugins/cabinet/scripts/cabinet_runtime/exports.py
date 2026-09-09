"""Atomic human-readable views written from stored company state.

Each view is written to a temporary file in the views directory and moved into
place with `os.replace`, so a reader never sees a half-written file.

Views carry selected company content only. Lease session identifiers, process
markers, approval responses, launch profiles and storage locations are not
copied into them.
"""

import os
import tempfile
from pathlib import Path

VIEW_NAMES = ("company-context.md", "current-batch.md", "handoffs.md",
              "latest-brief.md", "departments.md")

CONTEXT_DOCUMENTS = ("company.md", "decisions.md")
NOTEBOOK_EXCLUSIONS = ("company.md", "decisions.md", "money.md", "proposals.md")

VIEW_FILE_MODE = 0o600
VIEW_DIR_MODE = 0o700


def export_company(store):
    """Write every view and return the paths written."""

    from .errors import CabinetError

    views = store.views_dir
    if views.is_symlink():
        raise CabinetError("UNSAFE_PATH", "views directory must not be a symlink")
    views.mkdir(mode=VIEW_DIR_MODE, parents=True, exist_ok=True)

    generated = store.now()
    documents = {row["name"]: row for row in store.get_documents()}
    batches = store.get_batches()
    latest = batches[-1] if batches else None

    pages = {
        "company-context.md": _company_context(store, documents, generated),
        "current-batch.md": _current_batch(latest, generated),
        "handoffs.md": _handoffs(store, generated),
        "latest-brief.md": _latest_brief(latest, generated),
        "departments.md": _departments(store, documents, generated),
    }

    written = []
    for name in VIEW_NAMES:
        written.append(str(_atomic_write(views / name, pages[name])))
    return {"generated": generated, "views": written}


def _atomic_write(path, text):
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".view-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(temporary, VIEW_FILE_MODE)
        os.replace(temporary, str(path))
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return Path(path)


def _header(title, repo, generated):
    return ("# %s\n\nRepository: %s\nGenerated: %s\n"
            "Generated from stored company state; edits here are not read back.\n"
            % (title, repo, generated))


def _repo_of(store):
    identity = store.identity
    return identity["repo"] if identity else "unbound"


def _company_context(store, documents, generated):
    lines = [_header("Company context", _repo_of(store), generated)]
    present = [name for name in CONTEXT_DOCUMENTS if name in documents]
    if not present:
        lines.append("\nNo charter document has been imported yet.\n")
        return "".join(lines)
    for name in present:
        row = documents[name]
        lines.append("\n## %s (revision %d, sha256 %s)\n\n"
                     % (name, row["revision"], row["digest"][:16]))
        lines.append(row["content"].rstrip("\n") + "\n")
    return "".join(lines)


def _current_batch(latest, generated):
    if latest is None:
        return ("# Current batch\n\nGenerated: %s\n\nNo batch has been proposed.\n"
                % generated)
    body = latest["body"]
    lines = [_header("Current batch", body["repo"], generated)]
    lines.append("\n## %s revision %d — %s\n\n"
                 % (latest["batch_id"], latest["revision"], latest["state"]))
    lines.append("Digest: %s\n" % latest["digest"])
    lines.append("Base revision: %s\n" % body["base_sha"])
    lines.append("\nGoal: %s\n" % body["goal"])
    lines.append("Outcome: %s\n" % body["outcome"])
    lines.append("\n### In scope\n\n")
    lines.extend("- %s\n" % item for item in body["in_scope"])
    lines.append("\n### Out of scope\n\n")
    lines.extend("- %s\n" % item for item in body["out_of_scope"])
    lines.append("\n### Acceptance\n\n")
    lines.extend("- %s: %s\n" % (item["id"], item["behavior"])
                 for item in body["acceptance"])
    lines.append("\n### Owned paths\n\n")
    lines.extend("- %s\n" % item for item in body["owned_paths"])
    if body["issues"]:
        lines.append("\n### Issues\n\n")
        lines.extend("- #%d\n" % number for number in body["issues"])
    return "".join(lines)


def _handoffs(store, generated):
    rows = store.get_handoffs()
    lines = [_header("Open questions and corrections", _repo_of(store), generated)]
    if not rows:
        lines.append("\nNothing is outstanding between roles.\n")
        return "".join(lines)
    lines.append("\n| Handoff | Batch | From | To | State |\n")
    lines.append("| --- | --- | --- | --- | --- |\n")
    for row in rows:
        lines.append("| %s | %s r%d | %s | %s | %s |\n"
                     % (row["handoff_id"], row["batch_id"], row["revision"],
                        row["from_role"], row["to_role"], row["state"]))
    return "".join(lines)


def _latest_brief(latest, generated):
    lines = ["# Latest brief\n\nGenerated: %s\n" % generated]
    if latest is None:
        lines.append("\nNo brief has been recorded.\n")
        return "".join(lines)
    lines.append("\nThe current batch is %s revision %d, state %s.\n"
                 % (latest["batch_id"], latest["revision"], latest["state"]))
    lines.append("Goal: %s\n" % latest["body"]["goal"])
    lines.append("Outcome: %s\n" % latest["body"]["outcome"])
    return "".join(lines)


def _departments(store, documents, generated):
    lines = [_header("Departments", _repo_of(store), generated)]
    notebooks = [name for name in sorted(documents)
                 if name not in NOTEBOOK_EXCLUSIONS]
    lines.append("\n## Role notebooks\n\n")
    if notebooks:
        for name in notebooks:
            lines.append("- %s (revision %d)\n" % (name, documents[name]["revision"]))
    else:
        lines.append("- none imported\n")
    assignments = store.get_assignments()
    lines.append("\n## Work assignments\n\n")
    if not assignments:
        lines.append("- none reserved\n")
        return "".join(lines)
    for row in assignments:
        lines.append("- %s: %s on %s (%s)\n"
                     % (row["assignment_id"], row["role"], row["work_key"],
                        row["state"]))
    return "".join(lines)
