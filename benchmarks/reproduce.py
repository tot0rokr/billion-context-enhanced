#!/usr/bin/env python3
"""Run the published eight-phase workload with private runtime credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parent
IMAGE = "node@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd"
MAX_MINUTES = 60
CONTROL_TIMEOUT = 15
CONFIG = '''model = "gpt-6-astra"
model_reasoning_effort = "xhigh"
model_context_window = 1000000
model_auto_compact_token_limit = 900000
approval_policy = "never"
sandbox_mode = "danger-full-access"
cli_auth_credentials_store = "file"
check_for_update_on_startup = false
web_search = "disabled"

[features]
multi_agent = true
apps = false
plugins = false
hooks = false
shell_snapshot = false

[agents]
max_threads = 4
max_depth = 1

[analytics]
enabled = false

[otel]
environment = "billion-context-controlled-benchmark"
log_user_prompt = false
log_agent_responses = false
exporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/logs", protocol = "json" } }
metrics_exporter = { otlp-http = { endpoint = "http://127.0.0.1:4318/v1/metrics", protocol = "json" } }
tool_result = { max_bytes = 0 }
'''
RUNTIME_EXPORTS = (
    ".codex/sessions",
    ".local/share/billion-context/sessions",
    ".local/state/billion-context/bili.log",
)
PRIVATE_ATTRIBUTES = {"user.account_id", "user.email"}


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_text(model: str) -> str:
    return CONFIG.replace('model = "gpt-6-astra"', "model = " + json.dumps(model), 1)


def docker_control(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *arguments], capture_output=True, text=True,
                          timeout=CONTROL_TIMEOUT, check=True)


def validate(options: argparse.Namespace) -> dict[str, Path]:
    if options.output.exists():
        raise ValueError(f"Refusing to overwrite existing output: {options.output}")
    if not 0 < options.minutes <= MAX_MINUTES:
        raise ValueError(f"--minutes must be greater than zero and at most {MAX_MINUTES}")
    arms = options.order.split(",")
    if len(set(arms)) != len(arms) or any(arm not in ("A", "B", "C") for arm in arms):
        raise ValueError("--order must contain distinct arms from A,B,C")
    if not options.model.strip():
        raise ValueError("--model must not be empty")
    manifest = json.loads((options.fixture / "manifest.json").read_text())
    for name, expected in manifest["hashes"].items():
        if digest(options.fixture / name) != expected:
            raise ValueError(f"Fixture hash mismatch: {name}")
    prompts = sorted((options.fixture / "prompts").glob("[0-9][0-9].txt"))
    if [path.stem for path in prompts] != [f"{phase:02d}" for phase in range(1, 9)]:
        raise ValueError("The fixture must contain exactly prompts 01 through 08")
    auth = json.loads(options.auth_file.read_text())
    if not isinstance(auth, dict) or not auth:
        raise ValueError("Authentication file must contain a nonempty JSON object")
    if not options.collector.is_file():
        raise ValueError(f"Missing telemetry collector: {options.collector}")
    binary = options.codex_binary or options.codex_vendor / "bin/codex"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError(f"Codex executable is unavailable: {binary}")
    with binary.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ValueError("Use a native Linux Codex executable, not the npm JavaScript launcher")
    sources = {}
    for arm, source in (("B", options.baseline_source), ("C", options.enhanced_source)):
        if arm not in arms:
            continue
        if source is None:
            raise ValueError(f"Arm {arm} requires its prebuilt instrumented source directory")
        for name in ("dist/index.js", "src/audit-usage.ts", "src/fetch-util.ts",
                     "src/loop/core.ts", "kernel/src/report.ts"):
            if not (source / name).is_file():
                raise ValueError(f"Missing arm {arm} file: {source / name}")
        if "AUDIT_USAGE_LOG" not in (source / "dist/index.js").read_text():
            raise ValueError(f"Arm {arm} dist does not contain the benchmark observer; rebuild it")
        if "auditResponseBody" not in (source / "src/fetch-util.ts").read_text():
            raise ValueError(f"Arm {arm} does not connect the benchmark observer")
        sources[arm] = source
    if set(sources) == {"B", "C"}:
        for name in ("src/audit-usage.ts", "src/fetch-util.ts"):
            if digest(sources["B"] / name) != digest(sources["C"] / name):
                raise ValueError(f"B/C instrumentation differs: {name}")
    return sources


def codex_mount(options: argparse.Namespace) -> str:
    if options.codex_vendor:
        return f"{options.codex_vendor}:/opt/codex:ro"
    return f"{options.codex_binary}:/opt/codex/bin/codex:ro"


def preflight(options: argparse.Namespace) -> dict:
    sources = validate(options)
    docker_control("version", "--format", "{{.Server.Version}}")
    docker_control("image", "inspect", options.image)
    version = docker_control("run", "--rm", "--network", "none", "--volume",
                             codex_mount(options), options.image,
                             "/opt/codex/bin/codex", "--version").stdout.strip()
    if version != f"codex-cli {options.expected_codex_version}":
        raise ValueError(f"Expected codex-cli {options.expected_codex_version}, got {version!r}")
    docker_control("run", "--rm", "--network", "none", options.image,
                   "python3", "--version")
    return {"mode": "preflight", "model_requests": 0, "codex_version": version,
            "image": options.image, "model": options.model, "order": options.order,
            "instrumented_arms": sorted(sources), "output": str(options.output)}


def container_command(options: argparse.Namespace, arm: str, run: Path,
                      private_home: Path, source: Path | None) -> list[str]:
    command = ["docker", "run", "--detach", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--memory", "8g", "--cpus", "4", "--pids-limit", "768",
               "--oom-score-adj", "500", "--env", "HOME=/home/bench",
               "--env", "CODEX_HOME=/home/bench/.codex",
               "--env", "PATH=/opt/codex/bin:/usr/local/bin:/usr/bin:/bin",
               "--env", "BILI_SQLITE_AUTO_DOWNLOAD=0",
               "--env", "AUDIT_USAGE_LOG=/audit/provider-usage.jsonl",
               "--volume", f"{run / 'candidate'}:/task",
               "--volume", f"{private_home}:/home/bench",
               "--volume", f"{run / 'audit'}:/audit",
               "--volume", codex_mount(options),
               "--volume", f"{options.collector}:/control/collector.py:ro"]
    if source is not None:
        command.extend(["--volume", f"{source}:/bili:ro"])
    command.extend(["--workdir", "/task", options.image, "sleep", "infinity"])
    return command


class ContainerDeadline(threading.Thread):
    def __init__(self, container_id: str, timeout: float):
        super().__init__(daemon=True)
        self.container_id = container_id
        self.timeout = timeout
        self.state = {"container_id": container_id, "armed_at": time.time(),
                      "budget_seconds": timeout, "triggered": False}

    def run(self) -> None:
        try:
            subprocess.run(["docker", "wait", self.container_id], capture_output=True,
                           timeout=self.timeout, check=True)
            self.state["result"] = "container exited before deadline"
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            self.state.update(triggered=True, reason=type(error).__name__)
            try:
                docker_control("kill", "--signal", "KILL", self.container_id)
                self.state["result"] = "container killed"
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as kill_error:
                self.state["kill_error"] = type(kill_error).__name__
        finally:
            self.state["finished_at"] = time.time()


def run_phase(container_id: str, arm: str, run: Path, number: int, prompt: str,
              thread_id: str | None, timeout: float) -> dict:
    client = ["/opt/codex/bin/codex", "--no-daemon"] if arm == "A" else [
        "node", "/bili/dist/index.js", "codex", "--no-daemon"]
    command = ["docker", "exec", "--interactive", "--workdir", "/task", container_id,
               *client, "exec", "--json", "--skip-git-repo-check", "--color", "never",
               "--output-last-message", f"/audit/final-{number:02d}.txt"]
    if thread_id:
        command.extend(["resume", thread_id])
    command.append("-")
    started = time.time()
    monotonic_start = time.monotonic()
    output = run / "audit" / f"events-{number:02d}.jsonl"
    with output.open("wb") as stdout, (run / "audit" / f"stderr-{number:02d}.log").open("wb") as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        try:
            process.communicate(prompt.encode(), timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            try:
                docker_control("kill", "--signal", "KILL", container_id)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            finally:
                process.kill()
                process.wait(timeout=CONTROL_TIMEOUT)
            timed_out = True
    events = []
    malformed = []
    for index, line in enumerate(output.read_text(errors="replace").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            malformed.append(index)
    for event in events:
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id", thread_id)
    result = {"phase": number, "started": started, "finished": time.time(),
              "elapsed_s": time.monotonic() - monotonic_start, "exit_code": process.returncode,
              "timed_out": timed_out, "thread_id": thread_id,
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt),
              "turn_completions": [event for event in events if event.get("type") == "turn.completed"],
              "errors": [event for event in events if event.get("type") in ("error", "turn.failed")],
              "malformed_event_lines": malformed}
    write_json(run / "audit" / f"phase-{number:02d}.json", result)
    return result


def prepare_home(home: Path, auth_file: Path, model: str) -> None:
    codex = home / ".codex"
    codex.mkdir()
    shutil.copyfile(auth_file, codex / "auth.json")
    (codex / "auth.json").chmod(0o600)
    (codex / "config.toml").write_text(config_text(model))
    bili = home / ".config/billion-context"
    bili.mkdir(parents=True)
    write_json(bili / "billion-context.json", {
        "host": "127.0.0.1", "autoUpdate": False, "advisoryCheck": False,
        "releaseNotesCheck": False, "remoteAnnouncementsUrl": "http://127.0.0.1:9/disabled",
        "autoModeForge": {"enabled": False}, "compress": {"modelContextLimit": 1000000},
    })


def export_runtime(home: Path, run: Path) -> None:
    for relative in RUNTIME_EXPORTS:
        source = home / relative
        if not source.exists():
            continue
        target = run / "home" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)


def sanitize_telemetry(path: Path) -> None:
    if not path.exists():
        return
    def sanitize(value: object) -> object:
        if isinstance(value, dict):
            return {key: sanitize([item for item in child if item.get("key") not in PRIVATE_ATTRIBUTES]
                                  if key == "attributes" and isinstance(child, list) else child)
                    for key, child in value.items()}
        if isinstance(value, list):
            return [sanitize(child) for child in value]
        return value

    source_hash = digest(path)
    records = []
    malformed = []
    for index, line in enumerate(path.read_text().splitlines(), 1):
        try:
            records.append(json.dumps(sanitize(json.loads(line))))
        except json.JSONDecodeError:
            malformed.append(index)
    path.write_text("\n".join(records) + ("\n" if records else ""))
    write_json(path.with_name("telemetry-redaction.json"), {
        "source_sha256": source_hash, "removed_attributes": sorted(PRIVATE_ATTRIBUTES),
        "discarded_malformed_lines": malformed,
    })


def run_arm(options: argparse.Namespace, arm: str, source: Path | None) -> dict:
    run = options.output / arm
    run.mkdir(mode=0o700)
    shutil.copytree(options.fixture / "visible", run / "candidate")
    (run / "audit").mkdir()
    config = config_text(options.model)
    manifest = {"arm": arm, "model": options.model, "reasoning_effort": "xhigh",
                "context_window": 1000000, "auto_compact_limit": 900000,
                "codex_version": options.expected_codex_version, "image": options.image,
                "fixture_sha256": digest(options.fixture / "manifest.json"),
                "config_sha256": hashlib.sha256(config.encode()).hexdigest(),
                "runner_sha256": digest(Path(__file__)), "collector_sha256": digest(options.collector),
                "budget_minutes": options.minutes,
                "mode": "portable reproduction; not the historical runner",
                "telemetry_redactions": sorted(PRIVATE_ATTRIBUTES),
                "runtime_export_allowlist": list(RUNTIME_EXPORTS)}
    if source:
        manifest["source_sha256"] = {name: digest(source / name) for name in (
            "dist/index.js", "src/audit-usage.ts", "src/fetch-util.ts", "src/loop/core.ts",
            "kernel/src/report.ts")}
    write_json(run / "manifest.json", manifest)
    results = []
    container_id = None
    watchdog = None
    started = time.time()
    monotonic_start = time.monotonic()
    failure = None
    with tempfile.TemporaryDirectory(prefix="bili-benchmark-private-") as directory:
        home = Path(directory)
        prepare_home(home, options.auth_file, options.model)
        try:
            created = subprocess.run(container_command(options, arm, run, home, source),
                                     check=True, capture_output=True, text=True, timeout=CONTROL_TIMEOUT)
            container_id = created.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
                raise RuntimeError("Docker did not return a container ID")
            docker_control("exec", "--detach", container_id, "python3", "/control/collector.py")
            started = time.time()
            monotonic_start = time.monotonic()
            deadline = monotonic_start + options.minutes * 60
            watchdog = ContainerDeadline(container_id, options.minutes * 60)
            watchdog.start()
            thread_id = None
            for number in range(1, 9):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or watchdog.state["triggered"]:
                    break
                if number == 8:
                    evidence = run / "candidate/evidence"
                    evidence.mkdir(exist_ok=True)
                    for phase in (2, 3, 4):
                        shutil.copyfile(options.fixture / "prompts" / f"{phase:02d}.txt",
                                        evidence / f"{phase:02d}.txt")
                prompt = (options.fixture / "prompts" / f"{number:02d}.txt").read_text()
                result = run_phase(container_id, arm, run, number, prompt, thread_id, remaining)
                results.append(result)
                print(json.dumps({"arm": arm, "phase": number, "exit_code": result["exit_code"],
                                  "elapsed_s": result["elapsed_s"]}), flush=True)
                thread_id = result["thread_id"]
                if (result["timed_out"] or result["exit_code"] != 0 or not thread_id
                        or result["malformed_event_lines"] or result["errors"] or not result["turn_completions"]):
                    break
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            finished = time.time()
            wall = time.monotonic() - monotonic_start
            if container_id:
                try:
                    docker_control("stop", "--time", "5", container_id)
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    if watchdog is None or not watchdog.state["triggered"]:
                        failure = failure or {"type": "cleanup_error", "message": type(error).__name__}
            if watchdog:
                watchdog.join(timeout=CONTROL_TIMEOUT)
                write_json(run / "watchdog.json", watchdog.state)
            export_runtime(home, run)
            sanitize_telemetry(run / "audit/otel.jsonl")
            state = {"arm": arm, "started": started, "finished": finished, "wall_s": wall,
                     "budget_minutes": options.minutes, "phases": results,
                     "completed": len(results) == 8 and failure is None
                                  and not (watchdog and watchdog.state["triggered"])
                                  and all(result["exit_code"] == 0 and not result["timed_out"]
                                          and result["turn_completions"] and not result["errors"]
                                          and not result["malformed_event_lines"] for result in results),
                     "failure": failure}
            write_json(run / "result.json", state)
    return state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("plan", "preflight", "run"), help="Only run sends model requests")
    result.add_argument("--output", type=Path, required=True, help="New directory; existing paths are refused")
    result.add_argument("--fixture", type=Path, default=ROOT / "dataset-v2")
    result.add_argument("--collector", type=Path, default=ROOT / "collector.py")
    binary = result.add_mutually_exclusive_group(required=True)
    binary.add_argument("--codex-vendor", type=Path, help="Linux vendor directory containing bin/codex")
    binary.add_argument("--codex-binary", type=Path, help="Native Linux ELF executable; vendor is preferred")
    result.add_argument("--auth-file", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json")
    result.add_argument("--baseline-source", type=Path)
    result.add_argument("--enhanced-source", type=Path)
    result.add_argument("--order", default="A,B,C")
    result.add_argument("--minutes", type=float, default=60)
    result.add_argument("--model", default="gpt-6-astra")
    result.add_argument("--expected-codex-version", default="0.163.0")
    result.add_argument("--image", default=IMAGE)
    return result


def main() -> None:
    options = parser().parse_args()
    for name in ("output", "fixture", "collector", "codex_vendor", "codex_binary", "auth_file", "baseline_source", "enhanced_source"):
        value = getattr(options, name)
        if value is not None:
            setattr(options, name, value.expanduser().resolve())
    if options.mode == "plan":
        sources = validate(options)
        print(json.dumps({"mode": "plan", "model_requests": 0, "order": options.order,
                          "model": options.model, "image": options.image,
                          "budget_minutes_per_arm": options.minutes, "output": str(options.output),
                          "instrumented_arms": sorted(sources)}, indent=2))
        return
    print(json.dumps(preflight(options), indent=2))
    if options.mode == "preflight":
        return
    sources = validate(options)
    options.output.mkdir(mode=0o700, parents=True)
    for arm in options.order.split(","):
        result = run_arm(options, arm, sources.get(arm))
        print(json.dumps({key: result[key] for key in ("arm", "completed", "wall_s", "failure")}), flush=True)
        if not result["completed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
