"""Non-destructive import of legacy Markdown company documents.

The legacy company directory keeps `company.md`, `decisions.md`, `money.md`,
`proposals.md` and one Markdown notebook per role. This module copies each file
into a snapshot directory, records its sha256, and stores its text as a
source-tagged document revision. Originals are never written to.

Only the `documents` table is populated. Nothing here creates a batch, grant,
action or assignment: notebook text is evidence, not an instruction to run.
"""

import hashlib
import re
import shutil
from pathlib import Path

from .errors import CabinetError

SNAPSHOT_DIRECTORY = "legacy-snapshot"

LEGACY_CORE_DOCUMENTS = ("company.md", "decisions.md", "money.md", "proposals.md")

REPO_IN_URL = re.compile(r"github\.com[:/]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)"
                         r"(?:\.git)?(?=[\s/)\]]|$)")
REPO_IN_FIELD = re.compile(
    r"^\s*(?:Repository|Repo)\s*[:=]\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)\s*$",
    re.MULTILINE)
DECISION_HEADING = re.compile(r"^#{1,6}\s*(D\d+)\b", re.MULTILINE)


def repositories_named_in(text):
    """Return every `owner/name` the legacy charter text points at."""

    found = []
    for owner, name in REPO_IN_URL.findall(text):
        found.append("%s/%s" % (owner, name))
    found.extend(REPO_IN_FIELD.findall(text))
    ordered = []
    for item in found:
        if item not in ordered:
            ordered.append(item)
    return ordered


def decision_ids_in(text):
    """Return the decision numbers a legacy decisions file already uses."""

    ordered = []
    for found in DECISION_HEADING.findall(text):
        if found not in ordered:
            ordered.append(found)
    return ordered


def _legacy_files(source):
    files = []
    for path in sorted(source.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        if path.resolve().parent != source:
            raise CabinetError("UNSAFE_PATH",
                               "%s resolves outside %s" % (path, source))
        files.append(path)
    return files


def migrate_documents(store, source=None):
    """Import legacy Markdown into the store. Re-running changes nothing."""

    source = Path(source or store.root).resolve()
    if not source.is_dir():
        raise CabinetError("UNSAFE_PATH", "%s is not a directory" % source)
    files = _legacy_files(source)

    charter = source / "company.md"
    if charter in files:
        _verify_identity(store, charter.read_text(encoding="utf-8"))

    snapshot = store.runtime_dir / "backups" / SNAPSHOT_DIRECTORY
    snapshot.mkdir(mode=0o700, parents=True, exist_ok=True)

    before = store.max_event_seq()
    imported = []
    unchanged = []
    for path in files:
        content = path.read_text(encoding="utf-8")
        raw = path.read_bytes()
        file_digest = hashlib.sha256(raw).hexdigest()
        record = {"kind": "legacy_markdown", "path": path.name,
                  "sha256": file_digest, "bytes": len(raw),
                  "imported": store.now()}
        if path.name == "decisions.md":
            record["decision_ids"] = decision_ids_in(content)
        stored = store.put_document(path.name, content, record)
        if stored["created"]:
            imported.append(path.name)
            shutil.copy2(str(path), str(snapshot / path.name))
        else:
            unchanged.append(path.name)
            copy = snapshot / path.name
            if not copy.exists():
                shutil.copy2(str(path), str(copy))

    return {"source": str(source), "snapshot": str(snapshot),
            "imported": imported, "unchanged": unchanged,
            "documents": len(files),
            "events": store.max_event_seq() - before}


def _verify_identity(store, charter_text):
    named = repositories_named_in(charter_text)
    identity = store.identity
    if identity is None:
        if len(named) > 1:
            raise CabinetError(
                "IDENTITY_CONFLICT",
                "the legacy charter names %d repositories (%s); bind the "
                "company to one before importing" % (len(named), ", ".join(named)))
        if len(named) == 1:
            store.bind_identity(named[0])
        return
    for candidate in named:
        if candidate != identity["repo"]:
            raise CabinetError(
                "IDENTITY_CONFLICT",
                "the legacy charter names %s but this company is bound to %s"
                % (candidate, identity["repo"]))
