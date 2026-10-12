"""Offline integration tests against real Git checkouts and the SSH collector."""

from contextlib import redirect_stdout
import hashlib
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
        self.archive_content = b"#!/bin/sh\necho historical private script\n"
        manifest = {
            "schema_version": 1,
            "runtime_copies": [
                {"source": "scripts/start.sh", "target": "bin/start.sh"},
                {"source": "docs/worker.py", "target": "worker.py"},
            ],
            "local_copies": [{"source": "scripts/start.sh", "target": ".agents/snapshot/start.sh"}],
            "excluded_remote_files": [{"path": "external-history.sh", "reason": "external standalone script"}],
            "archived_remote_files": [{
                "original_path": "legacy.sh", "archive_path": ".archives/legacy.sh",
                "sha256": hashlib.sha256(self.archive_content).hexdigest(),
                "reason": "retired historical tool",
            }],
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
        self.archive = self.home / ".archives/legacy.sh"
        self.archive.parent.mkdir()
        self.archive.write_bytes(self.archive_content)
        self.archive.chmod(0o644)
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

    def version_archive_source(self):
        source = "archive/deployment-tools/20261012/legacy.sh.disabled"
        source_path = self.local / source
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(self.archive_content)
        source_path.chmod(0o644)
        manifest_path = self.local / "scripts/deployment_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["archived_remote_files"][0]["source"] = source
        manifest_path.write_text(json.dumps(manifest))
        self.git(self.local, "add", source, "scripts/deployment_manifest.json")
        self.git(self.local, "commit", "-m", "version historical source")
        self.git(self.local, "push", "origin", "main")
        self.git(self.remote, "pull", "--ff-only")
        return source

    @staticmethod
    def failures(report, category):
        return [entry for entry in report["checks"] if entry["category"] == category
                and entry["status"] not in {"ok", "skipped", "excluded"}]

    def test_identical_checkouts_runtime_and_local_copies_pass_with_one_ssh(self):
        report = self.audit()
        self.assertTrue(report["ok"], report)
        self.assertEqual(len(self.ssh_calls), 1)
        self.assertEqual(report["counts"]["excluded"], 1)
        self.assertEqual(report["archival_summary"], {"total": 1, "ok": 1, "failed": 0, "counts": {"ok": 1}})
        self.assertNotIn(self.archive_content.decode(), json.dumps(report))
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

    def test_missing_archive_is_a_failure(self):
        self.archive.unlink()
        report = self.audit()
        self.assertFalse(report["ok"])
        failure = self.failures(report, "remote_archive")[0]
        self.assertEqual(failure["status"], "missing")
        self.assertEqual(failure["actual"]["original"]["status"], "missing")
        self.assertEqual(report["archival_summary"]["failed"], 1)

    def test_archive_content_drift_is_a_failure_without_exposing_contents(self):
        self.archive.write_bytes(b"modified archive content\n")
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertEqual(self.failures(report, "remote_archive")[0]["detail"], "archive different sha256")
        self.assertNotIn("modified archive content", json.dumps(report))

    def test_archive_any_execute_bit_is_a_failure(self):
        for mode in (0o744, 0o654, 0o645):
            with self.subTest(mode=oct(mode)):
                self.archive.chmod(mode)
                report = self.audit()
                self.assertFalse(report["ok"])
                self.assertEqual(self.failures(report, "remote_archive")[0]["detail"],
                                 "archive different executable")

    def test_reappeared_original_file_or_dangling_symlink_is_a_failure(self):
        original = self.home / "legacy.sh"
        for kind in ("file", "dangling_symlink", "directory"):
            with self.subTest(kind=kind):
                if kind == "file":
                    original.write_bytes(self.archive_content)
                elif kind == "dangling_symlink":
                    original.symlink_to("absent-target.sh")
                    self.assertFalse(original.exists())
                else:
                    original.mkdir()
                report = self.audit()
                self.assertFalse(report["ok"])
                failure = self.failures(report, "remote_archive")[0]
                self.assertEqual(failure["status"], "mismatch")
                self.assertEqual(failure["detail"], "original path still exists")
                self.assertEqual(failure["actual"]["original"]["status"], "present")
                if kind == "directory":
                    original.rmdir()
                else:
                    original.unlink()

    def test_archive_symlink_is_not_an_inert_regular_file(self):
        content_file = self.home / "retained-contents.txt"
        self.archive.rename(content_file)
        self.archive.symlink_to(content_file)
        report = self.audit()
        self.assertFalse(report["ok"])
        failure = self.failures(report, "remote_archive")[0]
        self.assertEqual(failure["actual"]["archive"]["kind"], "symlink")
        self.assertIn("kind", failure["detail"])
        self.assertIn("executable", failure["detail"])

    def test_archive_manifest_validation_rejects_invalid_paths_hashes_and_overlaps(self):
        manifest_path = self.local / "scripts/deployment_manifest.json"
        original = json.loads(manifest_path.read_text())
        cases = (
            ("source", "../outside.disabled", "stay inside"),
            ("source", "/absolute/outside.disabled", "stay inside"),
            ("original_path", "../legacy.sh", "stay inside"),
            ("archive_path", "/absolute/legacy.sh", "stay inside"),
            ("sha256", "abcdef", "64 hexadecimal"),
            ("sha256", "g" * 64, "64 hexadecimal"),
            ("reason", " ", "needs a reason"),
            ("archive_path", "legacy.sh", "must not overlap"),
            ("original_path", "bin/start.sh", "must not overlap"),
            ("archive_path", "bin/start.sh", "must not overlap"),
        )
        for field, value, error in cases:
            with self.subTest(field=field, value=value):
                payload = json.loads(json.dumps(original))
                payload["archived_remote_files"][0][field] = value
                manifest_path.write_text(json.dumps(payload))
                with self.assertRaisesRegex(ValueError, error):
                    self.audit()
        self.assertEqual(self.ssh_calls, [])

    def test_archive_manifest_rejects_duplicate_paths(self):
        manifest_path = self.local / "scripts/deployment_manifest.json"
        payload = json.loads(manifest_path.read_text())
        payload["archived_remote_files"].append(dict(payload["archived_remote_files"][0]))
        manifest_path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "must be unique"):
            self.audit()
        self.assertEqual(self.ssh_calls, [])

    def test_archive_manifest_group_is_optional(self):
        payload = json.loads((self.local / "scripts/deployment_manifest.json").read_text())
        del payload["archived_remote_files"]
        external_manifest = Path(self.temp.name) / "without-archives.json"
        external_manifest.write_text(json.dumps(payload))
        self.args.manifest = str(external_manifest)
        report = self.audit()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["archival_summary"], {"total": 0, "ok": 0, "failed": 0, "counts": {}})

    def test_versioned_archive_source_is_checked_in_all_three_repositories(self):
        source = self.version_archive_source()
        report = self.audit()
        self.assertTrue(report["ok"], report)
        self.assertTrue(any(entry["source"] == f"origin/main:{source}"
                            for entry in report["checks"] if entry["category"] == "repo_origin"))
        self.assertTrue(any(entry["source"] == str(self.local / source)
                            for entry in report["checks"] if entry["category"] == "repo_remote"))
        archive = next(entry for entry in report["checks"] if entry["category"] == "remote_archive")
        self.assertEqual(archive["archive_source"], str(self.local / source))
        self.assertEqual(archive["actual"]["local_source"]["sha256"],
                         hashlib.sha256(self.archive_content).hexdigest())

    def test_versioned_archive_source_content_mode_and_missing_are_failures(self):
        source = self.version_archive_source()
        source_path = self.local / source
        for change, expected in (("content", "different sha256"), ("mode", "different executable"),
                                 ("missing", "is missing")):
            with self.subTest(change=change):
                source_path.write_bytes(self.archive_content)
                source_path.chmod(0o644)
                if change == "content":
                    source_path.write_bytes(b"unapproved historical contents\n")
                elif change == "mode":
                    source_path.chmod(0o645)
                else:
                    source_path.unlink()
                report = self.audit()
                self.assertFalse(report["ok"])
                self.assertIn(expected, self.failures(report, "remote_archive")[0]["detail"])
                self.assertEqual(report["archival_summary"]["failed"], 1)
                self.assertTrue(self.failures(report, "repo_origin"))

    def test_remote_versioned_archive_source_drift_is_detected(self):
        source = self.version_archive_source()
        (self.remote / source).write_bytes(b"remote historical drift\n")
        report = self.audit()
        self.assertFalse(report["ok"])
        self.assertIn(source, report["remote_dirty_paths"])
        self.assertTrue(any(entry["source"] == str(self.local / source)
                            for entry in self.failures(report, "repo_remote")))

    def test_main_exits_nonzero_for_archive_drift_and_prints_archive_summary(self):
        self.archive.chmod(0o755)
        arguments = [
            "--repo", str(self.local), "--host", "fixture@offline.invalid",
            "--remote-repo", str(self.remote), "--remote-home", str(self.home),
            "--skip-origin-network",
        ]
        with patch.object(CHECKER.subprocess, "run", side_effect=self.run_with_local_ssh):
            with redirect_stdout(io.StringIO()) as printed:
                result = CHECKER.main(arguments)
        self.assertEqual(result, 1)
        self.assertIn("Archived remote files: total=1, ok=0, failed=1", printed.getvalue())
        self.assertNotIn(self.archive_content.decode(), printed.getvalue())


if __name__ == "__main__":
    unittest.main()
