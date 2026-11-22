"""End-to-end tests of apply.py and measure.py, run as the skill and the hook run them.

Standard library only: python -m unittest discover tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "context-profile"
SCRIPTS = PLUGIN / "skills" / "context-profile" / "scripts"

CONFIG = {
    "profiles": {
        "basic": {"plugins": []},
        "Web": {"plugins": ["frontend-design@market"]},
        "docs": {"tools": ["Artifact"]},
    }
}


class ScriptTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / "home"
        self.home.mkdir()
        (self.home / "context-profiles.json").write_text(json.dumps(CONFIG), encoding="utf-8")
        # An accented folder name: the hook must read its UTF-8 input on every platform.
        self.project = Path(tmp.name) / "proj-é"
        (self.project / ".claude").mkdir(parents=True)
        self.local = self.project / ".claude" / "settings.local.json"
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.home))

    def run_script(self, script, *args, stdin=b""):
        p = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args],
                           input=stdin, capture_output=True, env=self.env)
        return p.returncode, p.stdout.decode("utf-8")

    def apply(self, *args):
        return self.run_script("apply.py", *args, "--project", str(self.project))

    def hook(self):
        payload = json.dumps({"cwd": str(self.project)}, ensure_ascii=False).encode("utf-8")
        code, out = self.run_script("apply.py", "--hook", stdin=payload)
        self.assertEqual(code, 0)
        return json.loads(out)  # the hook output must always be valid JSON

    def test_apply_writes_managed_entries_and_keeps_the_rest(self):
        self.local.write_text('{"permissions": {"allow": ["Bash(ls)"]}}', encoding="utf-8")
        code, out = self.apply("WEB")  # profile names are case-insensitive
        self.assertEqual(code, 0, out)
        settings = json.loads(self.local.read_text(encoding="utf-8"))
        self.assertEqual(settings["enabledPlugins"], {"frontend-design@market": True})
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ls)"], "deny": ["Artifact"]})

    def test_dry_run_writes_nothing(self):
        code, _ = self.apply("docs", "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(self.local.exists())

    def test_global_except(self):
        self.apply("global", "except", "docs")
        settings = json.loads(self.local.read_text(encoding="utf-8"))
        self.assertTrue(settings["enabledPlugins"]["frontend-design@market"])
        self.assertEqual(settings["permissions"]["deny"], ["Artifact"])

    def test_reset_deletes_a_file_left_empty(self):
        self.apply("web")
        code, _ = self.apply("reset,")
        self.assertEqual(code, 0)
        self.assertFalse(self.local.exists())

    def test_unknown_profile_exits_3(self):
        code, out = self.apply("nope")
        self.assertEqual(code, 3)
        self.assertIn("Unknown profile: nope", out)

    def test_invalid_settings_exits_2_untouched(self):
        self.local.write_text("{bad", encoding="utf-8")
        code, out = self.apply("web")
        self.assertEqual(code, 2)
        self.assertIn("Invalid JSON", out)
        self.assertEqual(self.local.read_text(encoding="utf-8"), "{bad")

    def test_hook_reads_an_accented_folder(self):
        self.apply("web")
        msg = self.hook()["systemMessage"]
        self.assertTrue(msg.startswith("Context profile: basic + web"), msg)

    def test_hook_reports_invalid_settings_as_json(self):
        (self.project / ".claude" / "settings.json").write_text("{bad", encoding="utf-8")
        self.assertIn("Invalid JSON", self.hook()["systemMessage"])

    def test_measure_runs(self):
        code, out = self.run_script("measure.py", "--project", str(self.project))
        self.assertEqual(code, 0, out)
        self.assertIn("Enabled:", out)

    def test_json_files_parse(self):
        for path in [ROOT / ".claude-plugin" / "marketplace.json",
                     PLUGIN / ".claude-plugin" / "plugin.json",
                     PLUGIN / "hooks" / "hooks.json",
                     SCRIPTS.parent / "profiles.example.json"]:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
