import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import reproduce


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bili-reproduce-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        fixture = self.root / "fixture"
        (fixture / "visible").mkdir(parents=True)
        (fixture / "visible/reconcile.py").write_text("pass\n")
        (fixture / "prompts").mkdir()
        hashes = {}
        for phase in range(1, 9):
            name = f"prompts/{phase:02d}.txt"
            (fixture / name).write_text(f"phase {phase}\n")
            hashes[name] = reproduce.digest(fixture / name)
        (fixture / "manifest.json").write_text(json.dumps({"hashes": hashes}))
        vendor = self.root / "vendor"
        (vendor / "bin").mkdir(parents=True)
        binary = vendor / "bin/codex"
        binary.write_bytes(b"\x7fELFfixture")
        binary.chmod(0o700)
        auth = self.root / "auth.json"
        auth.write_text(json.dumps({"tokens": {"access_token": "test-only-credential"}}))
        collector = self.root / "collector.py"
        collector.write_text("pass\n")
        self.options = argparse.Namespace(output=self.root / "new-run", fixture=fixture,
                                          collector=collector, codex_vendor=vendor,
                                          codex_binary=None, auth_file=auth,
                                          baseline_source=None, enhanced_source=None,
                                          order="A", minutes=60, model="gpt-6-astra",
                                          expected_codex_version="0.163.0", image=reproduce.IMAGE)

    def test_default_config_matches_historical_record(self):
        self.assertEqual(hashlib.sha256(reproduce.config_text("gpt-6-astra").encode()).hexdigest(),
                         "1f7fd3126f9a562b13504df74215a4a13f3850f74b0d41252d94c830fed9058a")

    def test_preflight_uses_no_network_and_no_authentication_mount(self):
        def run(command, **kwargs):
            version = "codex-cli 0.163.0\n" if command[-1] == "--version" and "codex" in command[-2] else "ok\n"
            return subprocess.CompletedProcess(command, 0, version, "")
        with patch("subprocess.run", side_effect=run) as mocked:
            result = reproduce.preflight(self.options)
        self.assertEqual(result["model_requests"], 0)
        for call in mocked.call_args_list:
            command = call.args[0]
            self.assertNotIn(str(self.options.auth_file), command)
            if command[1] == "run":
                self.assertIn("none", command)
                self.assertIn("--network", command)
        self.assertFalse(self.options.output.exists())

    def test_wrong_codex_version_is_rejected_without_substitution(self):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "codex-cli 99.0.0\n", "")):
            with self.assertRaisesRegex(ValueError, "Expected codex-cli"):
                reproduce.preflight(self.options)

    def test_existing_output_is_never_overwritten(self):
        self.options.output.mkdir()
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            reproduce.validate(self.options)

    def test_fixture_changes_are_rejected_before_running(self):
        (self.options.fixture / "prompts/02.txt").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "Fixture hash mismatch"):
            reproduce.validate(self.options)

    def test_budget_cannot_exceed_sixty_minutes(self):
        self.options.minutes = 61
        with self.assertRaisesRegex(ValueError, "at most 60"):
            reproduce.validate(self.options)

    def test_different_instrumentation_is_rejected(self):
        self.options.order = "B,C"
        for arm, attribute in (("B", "baseline_source"), ("C", "enhanced_source")):
            source = self.root / arm
            (source / "src").mkdir(parents=True)
            (source / "src/loop").mkdir()
            (source / "kernel/src").mkdir(parents=True)
            (source / "dist").mkdir()
            (source / "dist/index.js").write_text("AUDIT_USAGE_LOG")
            (source / "src/fetch-util.ts").write_text("auditResponseBody")
            (source / "src/audit-usage.ts").write_text(arm)
            (source / "src/loop/core.ts").write_text(arm)
            (source / "kernel/src/report.ts").write_text(arm)
            setattr(self.options, attribute, source)
        with self.assertRaisesRegex(ValueError, "instrumentation differs"):
            reproduce.validate(self.options)

    def test_run_mounts_only_visible_workspace_and_private_home(self):
        run = self.root / "output/A"
        home = self.root / "private-home"
        command = reproduce.container_command(self.options, "A", run, home, None)
        self.assertIn(f"{run / 'candidate'}:/task", command)
        self.assertIn(f"{home}:/home/bench", command)
        self.assertNotIn(str(self.options.fixture), command)
        self.assertFalse(any("oracle" in item for item in command))
        self.assertIn("no-new-privileges", command)
        self.assertIn("8g", command)

    def test_deadline_kills_the_container_when_wait_times_out(self):
        deadline = reproduce.ContainerDeadline("a" * 64, 1)
        def run(command, **kwargs):
            if command[1] == "wait":
                raise subprocess.TimeoutExpired(command, 1)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("subprocess.run", side_effect=run) as mocked:
            deadline.run()
        self.assertTrue(deadline.state["triggered"])
        self.assertEqual(mocked.call_args_list[-1].args[0],
                         ["docker", "kill", "--signal", "KILL", "a" * 64])

    def test_phase_timeout_kills_container_before_exec_process(self):
        run = self.root / "phase"
        (run / "audit").mkdir(parents=True)
        process = Mock(returncode=-9)
        process.communicate.side_effect = subprocess.TimeoutExpired("docker exec", 1)
        actions = []
        process.kill.side_effect = lambda: actions.append("exec-killed")
        def control(command, **kwargs):
            actions.append("container-killed")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("subprocess.Popen", return_value=process), patch("subprocess.run", side_effect=control):
            result = reproduce.run_phase("a" * 64, "A", run, 1, "prompt", None, 1)
        self.assertEqual(actions, ["container-killed", "exec-killed"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["exit_code"], -9)

    def test_collector_failure_stops_container_and_keeps_credentials_private(self):
        self.options.output.mkdir()
        commands = []
        private_home = None
        def run(command, **kwargs):
            nonlocal private_home
            commands.append(command)
            if command[1] == "run":
                private_home = Path(next(item for item in command if item.endswith(":/home/bench")).rsplit(":", 1)[0])
                self.assertTrue((private_home / ".codex/auth.json").exists())
                return subprocess.CompletedProcess(command, 0, "a" * 64 + "\n", "")
            if command[1] == "exec":
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch("subprocess.run", side_effect=run):
            result = reproduce.run_arm(self.options, "A", None)
        self.assertFalse(result["completed"])
        self.assertEqual(result["failure"]["type"], "CalledProcessError")
        self.assertTrue(any(command[1] == "stop" for command in commands))
        self.assertFalse(private_home.exists())
        self.assertFalse(list(self.options.output.rglob("auth.json")))
        self.assertNotIn("test-only-credential", (self.options.output / "A/result.json").read_text())

    def test_export_excludes_auth_and_ca_keys(self):
        home = self.root / "private"
        home.mkdir()
        reproduce.prepare_home(home, self.options.auth_file, self.options.model)
        (home / ".codex/sessions").mkdir()
        (home / ".codex/sessions/rollout.jsonl").write_text("{}\n")
        (home / ".local/share/billion-context/ca").mkdir(parents=True)
        (home / ".local/share/billion-context/ca/key.pem").write_text("test-key")
        output = self.root / "export"
        reproduce.export_runtime(home, output)
        self.assertTrue((output / "home/.codex/sessions/rollout.jsonl").is_file())
        self.assertFalse(list(output.rglob("auth.json")))
        self.assertFalse(list(output.rglob("*.pem")))

    def test_eight_phases_resume_one_thread_and_release_originals_only_in_phase_eight(self):
        self.options.output.mkdir()
        seen = []
        def control(command, **kwargs):
            output = "a" * 64 + "\n" if command[1] == "run" else ""
            return subprocess.CompletedProcess(command, 0, output, "")
        def popen(command, **kwargs):
            number = len(seen) + 1
            seen.append(command)
            evidence = self.options.output / "A/candidate/evidence"
            self.assertEqual(evidence.exists(), number == 8)
            if number == 8:
                self.assertEqual(sorted(path.name for path in evidence.iterdir()), ["02.txt", "03.txt", "04.txt"])
                self.assertEqual((evidence / "02.txt").read_text(), "phase 2\n")
            self.assertEqual("resume" in command, number > 1)
            if number > 1:
                self.assertEqual(command[command.index("resume") + 1], "same-thread")
            process = Mock(returncode=0)
            def communicate(prompt, **arguments):
                self.assertEqual(prompt, f"phase {number}\n".encode())
                kwargs["stdout"].write((json.dumps({"type": "thread.started", "thread_id": "same-thread"}) + "\n").encode())
                kwargs["stdout"].write(b'{"type":"turn.completed"}\n')
                return None, None
            process.communicate.side_effect = communicate
            return process
        with patch("subprocess.run", side_effect=control), patch("subprocess.Popen", side_effect=popen):
            result = reproduce.run_arm(self.options, "A", None)
        self.assertTrue(result["completed"])
        self.assertEqual(len(result["phases"]), 8)
        self.assertEqual(len(seen), 8)
        self.assertFalse(list(self.options.output.rglob("auth.json")))

    def test_telemetry_redaction_preserves_measurements(self):
        path = self.root / "otel.jsonl"
        path.write_text(json.dumps({"payload": {"resourceMetrics": [{"attributes": [
            {"key": "user.email", "value": {"stringValue": "private@example.test"}},
            {"key": "user.account_id", "value": {"stringValue": "private-id"}},
            {"key": "input_token_count", "value": {"intValue": "123"}},
        ]}]}}) + "\n")
        reproduce.sanitize_telemetry(path)
        text = path.read_text()
        self.assertNotIn("private", text)
        self.assertEqual(json.loads(text)["payload"]["resourceMetrics"][0]["attributes"],
                         [{"key": "input_token_count", "value": {"intValue": "123"}}])

    def test_interrupted_telemetry_records_omitted_lines(self):
        path = self.root / "otel.jsonl"
        path.write_text('{}\n{"incomplete":')
        reproduce.sanitize_telemetry(path)
        self.assertEqual(path.read_text(), '{}\n')
        redaction = json.loads((self.root / "telemetry-redaction.json").read_text())
        self.assertEqual(redaction["discarded_malformed_lines"], [2])


if __name__ == "__main__":
    unittest.main()
