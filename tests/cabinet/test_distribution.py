"""Structural contract tests for the Cabinet plugin's distribution metadata.

Repository-only checks (see AGENTS.md: the `scripts/` and `tests/` trees are
not shipped to users). Python 3 standard library only, plain `unittest`.

Run:
    python3 -m unittest discover -s tests/cabinet -p test_distribution.py -v
"""

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ManifestContract(unittest.TestCase):
    """The advertised version must be the version that is actually shipped."""

    def test_cabinet_table_matches_manifest(self):
        manifest = json.loads(
            (ROOT / "plugins/cabinet/.claude-plugin/plugin.json").read_text()
        )
        row = next(
            line
            for line in (ROOT / "README.md").read_text().splitlines()
            if line.startswith("| [cabinet]")
        )
        version = row.split("|")[2].strip()
        self.assertEqual(version, manifest["version"])

    def test_cabinet_manifests_agree(self):
        claude = json.loads(
            (ROOT / "plugins/cabinet/.claude-plugin/plugin.json").read_text()
        )
        codex = json.loads(
            (ROOT / "plugins/cabinet/.codex-plugin/plugin.json").read_text()
        )
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(claude["description"], codex["description"])


if __name__ == "__main__":
    unittest.main()
