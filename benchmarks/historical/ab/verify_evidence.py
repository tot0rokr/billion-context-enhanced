import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "dataset-v2"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_arm(label):
    run = ROOT / "runs" / label
    phases = [json.loads(path.read_text()) for path in sorted((run / "audit").glob("phase-*.json"))]
    phase_five = next((phase for phase in phases if phase["phase"] == 5), None)
    files_after_code = [] if phase_five is None else [str(path.relative_to(run / "candidate")) for path in (run / "candidate").rglob("*.py") if path.stat().st_mtime > phase_five["finished"]]
    malformed = []
    for path in (run / "audit").glob("*.jsonl"):
        for index, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            try:
                json.loads(line)
            except json.JSONDecodeError:
                malformed.append({"file": path.name, "line": index})
    return {
        "phase_prompt_hashes_match": all(digest(FIXTURE / "prompts" / f'{phase["phase"]:02d}.txt') == phase["prompt_sha256"] for phase in phases),
        "visible_input_unchanged": digest(FIXTURE / "visible/data/visible.jsonl") == digest(run / "candidate/data/visible.jsonl"),
        "python_files_modified_after_phase5": files_after_code,
        "malformed_jsonl_records": malformed,
    }


def verify_compressed_originals():
    run = ROOT / "runs/B"
    db = run / "home/.local/share/billion-context/sessions/index.db"
    session = json.loads((run / "audit/phase-01.json").read_text())["thread_id"]
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.row_factory = sqlite3.Row
    originals = []
    texts = []
    for row in connection.execute("SELECT m.ref,m.seq,m.role,c.bytes FROM messages m JOIN content c ON c.hash=m.content_hash WHERE m.session_id=?", (session,)):
        value = json.loads(row["bytes"])
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            texts.append((row["ref"], row["seq"], row["role"], value["text"]))
    for phase in (2, 3, 4):
        expected = (FIXTURE / "prompts" / f"{phase:02d}.txt").read_text()
        matches = [{"ref": ref, "seq": seq, "role": role} for ref, seq, role, text in texts if text == expected]
        originals.append({"phase": phase, "characters": len(expected), "sha256": hashlib.sha256(expected.encode()).hexdigest(), "exact_text_matches": matches})
    blocks = [dict(row) for row in connection.execute("SELECT block_id,start_ref,end_ref,tier,active,created_at,payload_json FROM blocks WHERE session_id=? ORDER BY ord", (session,))]
    for block in blocks:
        payload = json.loads(block.pop("payload_json"))
        block["summary"] = payload.get("summary")
    connection.close()
    return {"original_evidence": originals, "blocks": blocks}


if __name__ == "__main__":
    output = {"A": verify_arm("A"), "B": verify_arm("B"), "storage": verify_compressed_originals()}
    (ROOT / "evidence-verification.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    concise = {"A": output["A"], "B": output["B"], "stored_original_prompts": [bool(row["exact_text_matches"]) for row in output["storage"]["original_evidence"]], "blocks": len(output["storage"]["blocks"])}
    print(json.dumps(concise, indent=2))
