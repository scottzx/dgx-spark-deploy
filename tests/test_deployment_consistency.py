"""Offline integration tests against real Git checkouts and the SSH collector."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


CHECKER_PATH = Path(__file__).resolve().parents[1] / "scripts/05_ops/check_deployment_consistency.py"
SPEC = importlib.util.spec_from_file_location("deployment_consistency", CHECKER_PATH)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
REAL_RUN = subprocess.run


class DeploymentConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.local = root / "local checkout"
        self.remote = root / "remote checkout' $ literal"
        self.home = root / "remote home' $ literal"
        self.origin = root / "origin.git"
        self.local.mkdir()
        self.home.mkdir()
        self.git(self.local, "init", "-b", "main")
        self.git(self.local, "config", "user.email", "fixture@example.invalid")
        self.git(self.local, "config", "user.name", "Fixture")
        self.git(self.local, "config", "core.filemode", "true")
        self.write("scripts/start.sh", "#!/bin/sh\necho ready\n", executable=True)
        self.write("scripts/runtime/config.json", '{"slots": 2}\n')
        self.write(".agents/skills/cache/SKILL.md", "Cache documentation\n")
        self.write(".agents/snapshot/start.sh", "#!/bin/sh\necho ready\n")
        self.write("docs/worker.py", "print('worker')\n")
        manifest = {
            "schema_version": 1,
            "runtime_copies": [
                {"source": "scripts/start.sh", "target": "bin/start.sh"},
                {"source": "docs/worker.py", "target": "worker.py"},
            ],
            "local_copies": [{"source": "scripts/start.sh", "target": ".agents/snapshot/start.sh"}],
            "excluded_remote_files": [{"path": "legacy.sh", "reason": "historical standalone script"}],
        }
        self.write("scripts/deployment_manifest.json", json.dumps(manifest))
        self.git(self.local, "add", ".")
        self.git(self.local, "commit", "-m", "fixture")
        REAL_RUN(["git", "init", "--bare", "--initial-branch=main", str(self.origin)],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.git(self.local, "remote", "add", "origin", str(self.origin))
        self.git(self.local, "push", "-u", "origin", "main")
        REAL_RUN(["git", "clone", str(self.origin), str(self.remote)],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.git(self.remote, "config", "user.email", "fixture@example.invalid")
        self.git(self.remote, "config", "user.name", "Fixture")
        self.git(self.remote, "config", "core.filemode", "true")
        (self.home / "bin").mkdir()
        shutil.copy2(self.local / "scripts/start.sh", self.home / "bin/start.sh")
        shutil.copy2(self.local / "docs/worker.py", self.home / "worker.py")
        self.args = CHECKER.parser().parse_args([
            "--repo", str(self.local), "--host", "fixture@offline.invalid",
            "--remote-repo", str(self.remote), "--remote-home", str(self.home),
            "--skip-origin-network",
        ])
        self.ssh_calls = []

    @staticmethod
    def git(repo, *arguments):
        return REAL_RUN(["git", "-C", str(repo), *arguments], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=True).stdout

    def write(self, relative, content, *, executable=False):
        path = self.local / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755 if executable else 0o644)

    def run_with_local_ssh(self, command, **kwargs):
        if command[0] == "ssh":
            self.ssh_calls.append(command)
            # Execute exactly the supplied read-only remote program, using paths
            # with shell metacharacters to exercise JSON payload construction.
            return REAL_RUN([sys.executable, "-"], **kwargs)
        return REAL_RUN(command, **kwargs)

    def audit(self):
        with patch.object(CHECKER.subprocess, "run", side_effect=self.run_with_local_ssh):
            return CHECKER.check_deployment(self.args)

    @staticmethod
    def failures(report, category):
        return [entry for entry in report["checks"] if entry["category"] == category
                and entry["status"] not in {"ok", "skipped", "excluded"}]

    def test_identical_checkouts_runtime_and_local_copies_pass_with_one_ssh(self):
        report = self.audit()
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(self.ssh_calls), 1)
        self.assertEqual(report["counts"]["excluded"], 1)
        for entry in report["checks"]:
            self.assertTrue({"source", "target", "status"}.issubset(entry))
        # A local documentation copy may intentionally omit executable mode.
        self.assertFalse((self.local / ".agents/snapshot/start.sh").stat().st_mode & 0o111)

    def test_non_script_extension_remote_drift_and_dirty_path_are_reported(self):
        (self.remote / "scripts/runtime/config.json").write_text('{"slots": 8}\n')
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(report["remote_dirty_paths"], ["scripts/runtime/config.json"])
        failures = self.failures(report, "repo_remote")
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["detail"], "different sha256")

    def test_untracked_files_are_reported_but_gitignored_cache_is_omitted(self):
        (self.local / "scripts/new.conf").write_text("new script configuration\n")
        (self.remote / "scripts/new.sh").write_text("#!/bin/sh\n")
        (self.remote / ".git/info/exclude").write_text("__pycache__/\n")
        cache = self.remote / "scripts/__pycache__"
        cache.mkdir()
        (cache / "temporary.pyc").write_bytes(b"cache")
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(report["local_dirty_paths"], ["scripts/new.conf"])
        self.assertEqual(report["remote_dirty_paths"], ["scripts/new.sh"])

    def test_local_and_runtime_executable_drift_is_reported(self):
        (self.home / "bin/start.sh").chmod(0o644)
        (self.local / "scripts/runtime/config.json").chmod(0o755)
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(self.failures(report, "runtime_copy")[0]["detail"], "different executable")
        self.assertEqual(self.failures(report, "repo_origin")[0]["detail"], "different executable")

    def test_missing_runtime_and_tracked_files_are_reported(self):
        (self.home / "worker.py").unlink()
        (self.remote / ".agents/skills/cache/SKILL.md").unlink()
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(self.failures(report, "runtime_copy")[0]["status"], "missing")
        self.assertEqual(self.failures(report, "repo_remote")[0]["status"], "missing")

    def test_manifest_source_outside_default_scopes_is_checked_against_origin_and_remote(self):
        (self.local / "docs/worker.py").write_text("print('local drift')\n")
        report = self.audit()
        self.assertTrue(any(entry["source"] == "origin/main:docs/worker.py"
                            for entry in self.failures(report, "repo_origin")))
        self.assertTrue(any(entry["source"] == str(self.local / "docs/worker.py")
                            for entry in self.failures(report, "repo_remote")))
        self.assertIn("docs/worker.py", report["local_dirty_paths"])

    def test_remote_head_mismatch_fails_even_without_script_changes(self):
        self.git(self.remote, "commit", "--allow-empty", "-m", "different remote HEAD")
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(len(self.failures(report, "git_ref")), 1)
        self.assertNotEqual(report["refs"]["local_head"], report["refs"]["remote_head"])

    def test_local_origin_tracking_head_mismatch_fails(self):
        self.git(self.local, "commit", "--allow-empty", "-m", "different local HEAD")
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(len(self.failures(report, "git_ref")), 2)

    def test_live_origin_is_checked_without_fetching_tracking_ref(self):
        self.git(self.remote, "commit", "--allow-empty", "-m", "origin advanced")
        self.git(self.remote, "push", "origin", "main")
        self.args.skip_origin_network = False
        before = self.git(self.local, "rev-parse", "origin/main").decode().strip()
        report = self.audit()
        after = self.git(self.local, "rev-parse", "origin/main").decode().strip()
        self.assertEqual(before, after)
        self.assertNotEqual(report["refs"]["origin_actual_head"], before)
        self.assertTrue(any(entry["target"] == "origin:refs/heads/main"
                            for entry in self.failures(report, "git_ref")))

    def test_staged_deletion_with_untracked_replacement_cannot_hide_missing_index_entry(self):
        content = (self.local / "scripts/runtime/config.json").read_text()
        self.git(self.local, "rm", "scripts/runtime/config.json")
        self.write("scripts/runtime/config.json", content)
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(self.failures(report, "repo_origin")[0]["status"], "missing")

    def test_main_writes_json_and_exits_nonzero_on_runtime_drift(self):
        (self.home / "worker.py").write_text("print('outdated runtime')\n")
        output = Path(self.temp.name) / "audit/report.json"
        arguments = [
            "--repo", str(self.local), "--host", "fixture@offline.invalid",
            "--remote-repo", str(self.remote), "--remote-home", str(self.home),
            "--skip-origin-network", "--output", str(output),
        ]
        with patch.object(CHECKER.subprocess, "run", side_effect=self.run_with_local_ssh):
            with redirect_stdout(io.StringIO()) as printed:
                result = CHECKER.main(arguments)
        self.assertEqual(result, 1)
        self.assertIn("FAIL", printed.getvalue())
        self.assertIn("different sha256", printed.getvalue())
        self.assertFalse(json.loads(output.read_text())["ok"])

    def test_manifest_paths_cannot_escape_roots(self):
        manifest = self.local / "scripts/deployment_manifest.json"
        payload = json.loads(manifest.read_text())
        payload["runtime_copies"][0]["target"] = "../outside.sh"
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "stay inside"):
            self.audit()
        self.assertEqual(self.ssh_calls, [])

    def test_network_timeout_becomes_a_reported_failure(self):
        def timeout_ssh(command, **kwargs):
            if command[0] == "ssh":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            return REAL_RUN(command, **kwargs)

        with patch.object(CHECKER.subprocess, "run", side_effect=timeout_ssh):
            report = CHECKER.check_deployment(self.args)
        self.assertFalse(report["ok"])
        self.assertIn("timed out after 60 seconds", self.failures(report, "remote_access")[0]["detail"])


if __name__ == "__main__":
    unittest.main()
