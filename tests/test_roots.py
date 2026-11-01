"""The layers root is configurable: --root, PSIQUE_ROOT, or the folder that holds the checkout. No ~/Codes."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layers  # noqa: E402
import roots  # noqa: E402


def make_root(base: Path, rel_paths: bool) -> Path:
    """<base>/psique/manifest.json + <base>/superego/layer.json, outside any ~/Codes."""
    (base / "psique").mkdir(parents=True)
    (base / "superego").mkdir()
    (base / "superego" / "layer.json").write_text(json.dumps({"level": "superego"}), encoding="utf-8")
    path = "superego" if rel_paths else str(base / "superego")
    (base / "psique" / "manifest.json").write_text(
        json.dumps({"default_level": "id", "layers": [{"level": "superego", "path": path, "repo": "x/y"}]}), encoding="utf-8")
    return base


class RootsTest(unittest.TestCase):
    def test_precedence_flag_env_checkout(self) -> None:
        self.assertEqual(roots.layers_root("/a/flag", {"PSIQUE_ROOT": "/b/env"}), os.path.normpath("/a/flag"))
        self.assertEqual(roots.layers_root(None, {"PSIQUE_ROOT": "/b/env"}), os.path.normpath("/b/env"))
        self.assertEqual(roots.layers_root(None, {}), str(ROOT.parent))

    def test_default_manifest_hangs_off_the_root(self) -> None:
        self.assertEqual(roots.default_manifest("/r", {}), os.path.normpath("/r/psique/manifest.json"))

    def test_relative_layer_path_resolves_against_root(self) -> None:
        self.assertEqual(roots.resolve_layer_path("superego", "/r"), os.path.normpath("/r/superego"))
        absolute = os.path.abspath(os.sep + "abs" + os.sep + "x")
        self.assertEqual(roots.resolve_layer_path(absolute, "/r"), os.path.normpath(absolute))
        self.assertEqual(roots.resolve_layer_path("~/Codes/superego", "/r"), os.path.normpath(os.path.expanduser("~/Codes/superego")))

    def test_old_manifest_with_absolute_paths_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = make_root(Path(tmp) / "any folder" / "work", rel_paths=False)
            man = layers.load_manifest(str(base / "psique" / "manifest.json"))
            self.assertEqual(man["layers"][0]["path"], os.path.normpath(str(base / "superego")))

    def test_relative_manifest_loads_from_a_root_outside_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = make_root(Path(tmp) / "elsewhere", rel_paths=True)
            man = layers.load_manifest(str(base / "psique" / "manifest.json"))
            self.assertEqual(man["layers"][0]["path"], os.path.normpath(str(base / "superego")))
            self.assertEqual(man["layers"][0]["config"], {"level": "superego"})

    def _plan(self, *extra: str, env: dict | None = None) -> subprocess.CompletedProcess:
        e = {k: v for k, v in os.environ.items() if k != "PSIQUE_ROOT"}
        e.update(env or {})
        return subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "layers.py"), "plan", *extra],
                              capture_output=True, text=True, encoding="utf-8", env=e, cwd=tempfile.gettempdir())

    def test_cli_root_flag_and_env_find_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = make_root(Path(tmp) / "no-codes-here", rel_paths=True)
            claude = Path(tmp) / "claude"
            claude.mkdir()
            by_flag = self._plan("--root", str(base), "--claude-home", str(claude))
            by_env = self._plan("--claude-home", str(claude), env={"PSIQUE_ROOT": str(base)})
            for res in (by_flag, by_env):
                self.assertEqual(res.returncode, 0, res.stderr[-400:])
            missing = self._plan("--root", str(Path(tmp) / "empty"), "--claude-home", str(claude))
            self.assertNotEqual(missing.returncode, 0, "a root without psique/manifest.json must fail")

    def test_roots_cli_prints_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "roots.py"), "--root", tmp],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(out.stdout.strip(), os.path.normpath(tmp))


class NoHardcodedRootTest(unittest.TestCase):
    def test_tools_do_not_default_to_a_fixed_codes_folder(self) -> None:
        for name in ("layers", "compose", "context_budget", "render_harness", "bootstrap"):
            src = (ROOT / "tools" / f"{name}.py").read_text(encoding="utf-8")
            self.assertNotIn('"~/Codes', src, name)
            self.assertNotIn('home / "Codes"', src, name)


if __name__ == "__main__":
    unittest.main()
