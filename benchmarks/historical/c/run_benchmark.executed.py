import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = Path("/tmp/billion-context-c-exec-20261113")
VENDOR = Path("/home/junho.lee/.local/share/fnm/aliases/default/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl")
AUTH = Path("/home/junho.lee/.codex/auth.json")
IMAGE = "node@sha256:18a6d90fd60542269850c80ca03b29b1d9b14d6b221ac7ee8e35b0d33ef904bd"
MODEL = "gpt-6-astra"
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


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare(label, fixture):
    run = ROOT / "runs" / label
    if run.exists():
        raise RuntimeError(f"Refusing to overwrite existing run {run}")
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(fixture / "visible", run / "candidate")
    home = run / "home"
    codex = home / ".codex"
    codex.mkdir(parents=True)
    shutil.copy2(AUTH, codex / "auth.json")
    (codex / "auth.json").chmod(0o600)
    (codex / "config.toml").write_text(CONFIG)
    audit = run / "audit"
    audit.mkdir()
    bili_config = home / ".config" / "billion-context"
    bili_config.mkdir(parents=True)
    settings = {
        "host": "127.0.0.1", "autoUpdate": False, "advisoryCheck": False,
        "releaseNotesCheck": False, "remoteAnnouncementsUrl": "http://127.0.0.1:9/disabled",
        "autoModeForge": {"enabled": False},
        "compress": {"modelContextLimit": 1000000},
    }
    if "smoke" in label:
        settings["dumpSse"] = "/audit/raw-sse"
    write_json(bili_config / "billion-context.json", settings)
    write_json(run / "manifest.json", {
        "arm": label, "model": MODEL, "reasoning_effort": "xhigh", "context_window": 1000000,
        "auto_compact_limit": 900000, "bili_commit": "be611a8566c22ee0a65fb5765365671d47e810d5",
        "codex_version": "0.163.0", "image": IMAGE, "mode": "controlled-long-context",
        "fixture": str(fixture), "config_sha256": hashlib.sha256(CONFIG.encode()).hexdigest(),
        "instrumentation": "Same response-byte-preserving observer as B; Codex OTLP and rollouts",
        "source_sha256": {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in ["src/loop/core.ts", "kernel/src/report.ts", "src/fetch-util.ts", "src/audit-usage.ts", "dist/index.js"]},
        "kernel_version": json.loads((SOURCE / "kernel/package.json").read_text())["version"],
        "historical_comparison": "A and B were executed on 2026-11-06; C is a later single run",
    })
    return run


def start_container(label, run):
    name = f"bili-bench-{label.lower()}-20261113"
    args = ["docker", "run", "--detach", "--rm", "--name", name,
            "--user", f"{os.getuid()}:{os.getgid()}", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "8g", "--cpus", "4",
            "--pids-limit", "768", "--oom-score-adj", "500",
            "--env", "HOME=/home/bench", "--env", "CODEX_HOME=/home/bench/.codex",
            "--env", "PATH=/opt/codex/bin:/usr/local/bin:/usr/bin:/bin",
            "--env", "BILI_SQLITE_AUTO_DOWNLOAD=0",
            "--env", "AUDIT_USAGE_LOG=/audit/provider-usage.jsonl",
            "--volume", f"{run / 'candidate'}:/task",
            "--volume", f"{run / 'home'}:/home/bench",
            "--volume", f"{run / 'audit'}:/audit",
            "--volume", f"{VENDOR}:/opt/codex:ro",
            "--volume", f"{SOURCE}:/bili:ro",
            "--volume", f"{ROOT / 'collector.py'}:/control/collector.py:ro",
            "--workdir", "/task", IMAGE, "sleep", "infinity"]
    command(args, stdout=subprocess.DEVNULL)
    command(["docker", "exec", "--detach", name, "python3", "/control/collector.py"])
    return name


def run_phase(name, label, run, number, prompt, thread_id, timeout):
    final_path = f"/audit/final-{number:02d}.txt"
    client = ["/opt/codex/bin/codex", "--no-daemon"]
    if label.startswith("C"):
        client = ["node", "/bili/dist/index.js", "codex", "--no-daemon"]
    args = ["docker", "exec", "--interactive", "--workdir", "/task", name, *client,
            "exec", "--json", "--skip-git-repo-check", "--color", "never",
            "--output-last-message", final_path]
    if thread_id:
        args.extend(["resume", thread_id])
    args.append("-")
    started = time.time()
    output = run / "audit" / f"events-{number:02d}.jsonl"
    error = run / "audit" / f"stderr-{number:02d}.log"
    with output.open("wb") as stdout, error.open("wb") as stderr:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        try:
            process.communicate(prompt.encode(), timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            timed_out = True
    events = []
    for line in output.read_text(errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    for event in events:
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id", thread_id)
    result = {
        "phase": number, "started": started, "finished": time.time(),
        "elapsed_s": time.time() - started, "exit_code": process.returncode,
        "timed_out": timed_out, "thread_id": thread_id,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt_chars": len(prompt),
        "turn_completions": [event for event in events if event.get("type") == "turn.completed"],
        "errors": [event for event in events if event.get("type") in ("error", "turn.failed")],
    }
    write_json(run / "audit" / f"phase-{number:02d}.json", result)
    print(json.dumps({"arm": label, **result}, ensure_ascii=False), flush=True)
    return result


def run_arm(label, fixture, minutes, smoke=False):
    run = prepare(label, fixture)
    name = start_container(label, run)
    started = time.time()
    results = []
    thread_id = None
    try:
        prompts = [(0, "Reply exactly READY. Do not use any tools.")] if smoke else [
            (int(path.stem), path.read_text()) for path in sorted((fixture / "prompts").glob("[0-9][0-9].txt"))
        ]
        for number, prompt in prompts:
            remaining = minutes * 60 - (time.time() - started)
            if remaining <= 0:
                break
            if number == 8:
                evidence = run / "candidate" / "evidence"
                evidence.mkdir(exist_ok=True)
                for phase in (2, 3, 4):
                    shutil.copy2(fixture / "prompts" / f"{phase:02d}.txt", evidence / f"{phase:02d}.txt")
            result = run_phase(name, label, run, number, prompt, thread_id, remaining)
            results.append(result)
            thread_id = result["thread_id"]
            if result["timed_out"] or result["exit_code"] != 0 or not thread_id:
                break
        wall = time.time() - started
        state = {"arm": label, "started": started, "finished": time.time(), "wall_s": wall,
                 "budget_minutes": minutes, "phases": results, "completed": len(results) == len(prompts) and all(r["exit_code"] == 0 for r in results)}
        write_json(run / "result.json", state)
    finally:
        command(["docker", "stop", "--time", "10", name], stdout=subprocess.DEVNULL)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["run"])
    parser.add_argument("--fixture", type=Path, default=Path("/tmp/billion-context-benchmark-20261106/dataset-v2"))
    parser.add_argument("--order", choices=["C"], default="C")
    parser.add_argument("--minutes", type=int, default=60)
    options = parser.parse_args()
    for arm in options.order.split(","):
        label = arm + "-smoke" if options.mode == "smoke" else arm
        print(json.dumps({"starting": label, "at": time.time()}), flush=True)
        result = run_arm(label, options.fixture, 5 if options.mode == "smoke" else options.minutes, options.mode == "smoke")
        print(json.dumps({"finished": label, "wall_s": result["wall_s"], "completed": result["completed"]}), flush=True)
        if options.mode == "smoke" and not result["completed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
