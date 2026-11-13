import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROGRESS = Path("/tmp/billion-context-c-evidence-20261113/progress.jsonl")
NAME = "bili-bench-c-20261113"
record = json.loads(PROGRESS.read_text().splitlines()[0])
deadline = record["at"] + 3600
info = json.loads(subprocess.check_output(["docker", "inspect", NAME]))[0]
expected = str(ROOT / "runs/C/candidate")
assert any(mount.get("Source") == expected and mount.get("Destination") == "/task" for mount in info["Mounts"])
container_id = info["Id"]
state = {"container_id": container_id, "deadline": deadline, "started_at": record["at"], "armed_at": time.time(), "triggered": False}
output = ROOT / "runs/C/watchdog.json"
output.write_text(json.dumps(state, indent=2) + "\n")
waiter = subprocess.Popen(["docker", "wait", container_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    waiter.wait(timeout=max(0, deadline - time.time()))
    state["result"] = "container exited before deadline"
except subprocess.TimeoutExpired:
    stopped = subprocess.run(["docker", "kill", "--signal", "KILL", container_id], capture_output=True, text=True, timeout=10)
    state.update(triggered=True, kill_returncode=stopped.returncode, killed_at=time.time())
    waiter.wait(timeout=10)
finally:
    state["finished_at"] = time.time()
    output.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state), flush=True)
