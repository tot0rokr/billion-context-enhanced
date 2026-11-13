#!/usr/bin/env python3
"""Generate deterministic, staged rollout-reconciliation benchmark fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path


FINAL_RULES = """Final contract R3
Normalize schema 1 and 2 before reasoning. Schema 1 keys: event_id, board,
epoch, sequence, action, tx, slot (0=A, 1=B), digest, success, time.
Schema 2 keys: id, device, boot, seq, kind (lowercase action), transaction,
slot (A or B), sha256, ok, timestamp. Ignore time/timestamp for semantics.
Missing tx, slot, digest normalize to null. success/ok is always boolean.

Group by event ID globally. Identical normalized payloads are replays: keep
one and count the extra rows in duplicate_replays. If one ID has multiple
different normalized payloads, exclude ALL rows for that ID, count one
conflicted_id, and emit one duplicate_conflict incident using the minimum
(board, epoch, sequence, event_id) location among those payloads. Do not
count rows of a conflicted ID as duplicate_replays. Ignored timestamp and
schema spelling differences do not make normalized payloads different.

Process retained events sorted by (board, epoch, sequence, event_id).
Each board has one successful BASELINE before its other events: set active
slot/digest and add that exact image to verified image history. Initial
epoch is the baseline epoch. Advancing epoch clears all pending tx state
but retains active image and verified image history. A successful RESET
also clears pending state without changing the active image. A failed
RESET emits reset_failed and does not clear pending state.

STAGE failure emits stage_failed and leaves pending state unchanged.
STAGE success replaces that tx's pending slot/digest and clears its verified
flag. VERIFY without a pending tx emits verify_without_stage. VERIFY with
a pending tx and success=false emits verify_failed AND clears its verified
flag. Successful VERIFY for a different slot or digest emits
verify_mismatch AND clears its verified flag. Matching successful VERIFY
sets verified=true and adds the exact (slot,digest) to verified history.

Failed COMMIT always emits commit_failed. Successful COMMIT without a
pending tx emits commit_without_stage. Successful COMMIT whose slot/digest
does not match pending emits commit_mismatch. A matching COMMIT without
the verified flag emits commit_unverified. Otherwise change active image,
increment applied_commits, and remove the pending tx. Thus a second commit
needs a new stage/verification. Incidents do not otherwise mutate state.

Failed ROLLBACK emits rollback_failed. Successful ROLLBACK is accepted only
when the exact (slot,digest) occurs in that board's verified history; then
change active image, increment accepted_rollbacks, and clear pending tx.
Otherwise emit rollback_unverified and leave state unchanged. Verification
history survives epoch changes, but a verification for slot A never
authorizes a rollback to slot B with the same digest.

Output exactly these keys: boards, incidents, totals. boards is sorted by
board and contains objects {board, epoch, active_slot, active_digest}.
incidents is sorted by (board, epoch, sequence, event_id, reason) and contains
objects {board, epoch, sequence, event_id, reason}. totals contains
board_count, applied_commits, accepted_rollbacks, duplicate_replays,
conflicted_ids, rejected_events; rejected_events equals len(incidents).
No timestamps, paths or runtime-dependent fields belong in the output.
"""


def normalized(row: dict) -> dict:
    if row["schema"] == 1:
        slot = {0: "A", 1: "B", None: None}[row.get("slot")]
        return dict(event_id=row["event_id"], board=row["board"],
                    epoch=row["epoch"], sequence=row["sequence"],
                    action=row["action"], tx=row.get("tx"), slot=slot,
                    digest=row.get("digest"), success=row["success"])
    return dict(event_id=row["id"], board=row["device"], epoch=row["boot"],
                sequence=row["seq"], action=row["kind"].upper(),
                tx=row.get("transaction"), slot=row.get("slot"),
                digest=row.get("sha256"), success=row["ok"])


def locate(row: dict) -> tuple:
    return row["board"], row["epoch"], row["sequence"], row["event_id"]


def reference(rows: list[dict]) -> dict:
    grouped = defaultdict(list)
    for raw in rows:
        row = normalized(raw)
        grouped[row["event_id"]].append(row)
    incidents = []
    retained = []
    duplicates = conflicts = commits = rollbacks = 0

    def reject(row: dict, reason: str) -> None:
        incidents.append({k: row[k] for k in ("board", "epoch", "sequence", "event_id")} | {"reason": reason})

    for members in grouped.values():
        variants = {json.dumps(row, sort_keys=True): row for row in members}
        if len(variants) != 1:
            conflicts += 1
            reject(min(members, key=locate), "duplicate_conflict")
        else:
            duplicates += len(members) - 1
            retained.append(members[0])
    boards = {}
    for row in sorted(retained, key=locate):
        board = row["board"]
        if board not in boards:
            boards[board] = {"epoch": row["epoch"], "active": (None, None), "history": set(), "pending": {}}
        state = boards[board]
        if row["epoch"] != state["epoch"]:
            state["epoch"] = row["epoch"]
            state["pending"].clear()
        image = row["slot"], row["digest"]
        action = row["action"]
        tx = row["tx"]
        ok = row["success"]
        pending = state["pending"]
        if action == "BASELINE":
            state["active"] = image
            state["history"].add(image)
        elif action == "RESET":
            if ok:
                pending.clear()
            else:
                reject(row, "reset_failed")
        elif action == "STAGE":
            if ok:
                pending[tx] = {"image": image, "verified": False}
            else:
                reject(row, "stage_failed")
        elif action == "VERIFY":
            if tx not in pending:
                reject(row, "verify_without_stage")
            elif not ok:
                pending[tx]["verified"] = False
                reject(row, "verify_failed")
            elif pending[tx]["image"] != image:
                pending[tx]["verified"] = False
                reject(row, "verify_mismatch")
            else:
                pending[tx]["verified"] = True
                state["history"].add(image)
        elif action == "COMMIT":
            if not ok:
                reject(row, "commit_failed")
            elif tx not in pending:
                reject(row, "commit_without_stage")
            elif pending[tx]["image"] != image:
                reject(row, "commit_mismatch")
            elif not pending[tx]["verified"]:
                reject(row, "commit_unverified")
            else:
                commits += 1
                state["active"] = image
                del pending[tx]
        elif action == "ROLLBACK":
            if not ok:
                reject(row, "rollback_failed")
            elif image not in state["history"]:
                reject(row, "rollback_unverified")
            else:
                rollbacks += 1
                state["active"] = image
                pending.clear()
        else:
            raise ValueError(action)
    board_rows = [dict(board=board, epoch=state["epoch"], active_slot=state["active"][0], active_digest=state["active"][1])
                  for board, state in sorted(boards.items())]
    incidents.sort(key=lambda row: (*locate(row), row["reason"]))
    return {"boards": board_rows, "incidents": incidents, "totals": dict(
        board_count=len(board_rows), applied_commits=commits,
        accepted_rollbacks=rollbacks, duplicate_replays=duplicates,
        conflicted_ids=conflicts, rejected_events=len(incidents))}


def digest(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()


def wire(row: dict, schema: int, clock: int) -> dict:
    if schema == 1:
        return dict(schema=1, event_id=row["event_id"], board=row["board"],
                    epoch=row["epoch"], sequence=row["sequence"], action=row["action"],
                    tx=row["tx"], slot={"A": 0, "B": 1, None: None}[row["slot"]],
                    digest=row["digest"], success=row["success"], time=clock)
    return dict(schema=2, id=row["event_id"], device=row["board"], boot=row["epoch"],
                seq=row["sequence"], kind=row["action"].lower(), transaction=row["tx"],
                slot=row["slot"], sha256=row["digest"], ok=row["success"], timestamp=clock)


def case(seed: int, number: int, pattern: int | None = None) -> list[dict]:
    rng = random.Random(seed * 100003 + number)
    board = f"board-{number:05d}"
    initial, first, second = [digest(seed, f"{board}:{value}") for value in ("initial", "first", "second")]
    tx = f"tx-{number % 13:02d}"
    logical = []

    def add(action, epoch=0, slot="B", value=first, success=True, transaction=tx):
        logical.append(dict(event_id=f"{board}-e{len(logical):03d}", board=board,
                            epoch=epoch, sequence=len(logical) * 7, action=action,
                            tx=transaction, slot=slot, digest=value, success=success))

    add("BASELINE", slot="A", value=initial, transaction=None)
    add("STAGE")
    add("VERIFY")
    mode = number % 12 if pattern is None else pattern
    if mode == 0:
        add("COMMIT")
        add("COMMIT")
    elif mode == 1:
        add("VERIFY", success=False)
        add("COMMIT")
    elif mode == 2:
        add("COMMIT", epoch=1)
    elif mode == 3:
        add("COMMIT", value=second)
        add("COMMIT")
    elif mode == 4:
        add("RESET", slot=None, value=None, transaction=None)
        add("COMMIT")
    elif mode == 5:
        add("RESET", slot=None, value=None, transaction=None, success=False)
        add("COMMIT")
    elif mode == 6:
        add("VERIFY", slot="A")
        add("COMMIT")
    elif mode == 7:
        add("COMMIT", success=False)
        add("COMMIT")
    elif mode == 8:
        add("COMMIT")
        add("ROLLBACK", slot="B", value=initial)
    elif mode == 9:
        add("COMMIT")
        add("ROLLBACK", slot="A", value=initial)
    elif mode == 10:
        add("STAGE", value=second, success=False)
        add("COMMIT")
    else:
        add("COMMIT")
        add("ROLLBACK", slot="A", value=initial, success=False)
    last_epoch = max(row["epoch"] for row in logical)
    add("STAGE", epoch=last_epoch + 1, value=second)
    add("VERIFY", epoch=last_epoch + 1, value=second, success=number % 4 != 1)
    if number % 4 == 2:
        add("RESET", epoch=last_epoch + 1, slot=None, value=None, transaction=None)
    add("COMMIT", epoch=last_epoch + 1, value=initial if number % 4 == 3 else second)
    if number % 5 == 0:
        conflict = copy.deepcopy(logical[1])
        conflict["digest"] = second
        logical.append(conflict)
    rows = [wire(row, 1 + (index + number) % 2, 1700000000 + rng.randrange(1000000))
            for index, row in enumerate(logical)]
    duplicate = copy.deepcopy(rows[-2])
    rows.extend([duplicate, wire(normalized(duplicate), 3 - duplicate["schema"], 1900000000)])
    rng.shuffle(rows)
    return rows


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows))


STUB = '''#!/usr/bin/env python3
import argparse
import json


def reconcile(events):
    raise NotImplementedError("Implement the rollout reconciliation contract")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with open(args.input) as source:
        events = [json.loads(line) for line in source if line.strip()]
    with open(args.output, "w") as target:
        json.dump(reconcile(events), target, sort_keys=True, indent=2)


if __name__ == "__main__":
    main()
'''


PUBLIC_TEST = '''import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class PublicContract(unittest.TestCase):
    def test_successful_commit_and_replay(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            subprocess.run([sys.executable, str(root / "reconcile.py"),
                            "--input", str(root / "data/public.jsonl"),
                            "--output", str(output)], check=True)
            expected = json.loads((root / "data/public-expected.json").read_text())
            self.assertEqual(json.loads(output.read_text()), expected)


if __name__ == "__main__":
    unittest.main()
'''


def fact(seed: int, index: int) -> dict:
    labels = ["change ticket", "approved rollback digest", "settle window in milliseconds",
              "forbidden operator action", "escalation scope", "accepted boot status",
              "audit correlation nonce", "evidence retention in days"]
    kind = (index - 1) % len(labels)
    values = [f"CHG-{seed % 10000:04d}-{index:03d}", digest(seed, f"fact:{index}"),
              str(17000 + index * 137), "erase-active-slot" if index % 2 else "reuse-old-epoch-verification",
              ["single-board", "rack", "deployment-batch"][index % 3],
              f"ready-epoch-{index + 7}", digest(seed, f"nonce:{index}")[:20], str(30 + index)]
    incident = f"OPS-{index:03d}"
    return {"id": f"F{index:02d}", "incident": incident, "label": labels[kind],
            "answer": values[kind], "question": f"For {incident}, what is the FINAL {labels[kind]}? Return its exact value as a string."}


def generate(root: Path, seed: int, target_chars: int) -> None:
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty output directory: {root}")
    visible, prompts, oracle = [root / name for name in ("visible", "prompts", "oracle")]
    for directory in (visible, prompts, oracle):
        directory.mkdir(parents=True, exist_ok=True)
    initial_rules = FINAL_RULES.replace("Final contract R3", "Provisional contract R1")
    initial_rules = initial_rules.replace("Ignore time/timestamp for semantics.", "R1 provisional ordering uses time/timestamp; sequence is diagnostic until review.")
    initial_rules = initial_rules.replace("Process retained events sorted by (board, epoch, sequence, event_id).", "R1 provisional rule: order each board and epoch by its reported timestamp.")
    initial_rules = initial_rules.replace("Advancing epoch clears all pending tx state", "R1 provisional rule: advancing epoch preserves pending tx state")
    initial_rules = initial_rules.replace("VERIFY with\na pending tx and success=false emits verify_failed AND clears its verified\nflag.", "R1 provisional rule: a failed VERIFY emits verify_failed but preserves an earlier verified flag.")
    (visible / "README.md").write_text("# Rollout incident reconstruction\n\nUse Python standard library only. Implement the CLI in reconcile.py.\nLater user messages may revise this provisional contract. Latest explicit\nrevision wins; record the revised decisions while working.\n\n" + initial_rules)
    (visible / "reconcile.py").write_text(STUB)
    (visible / "tests").mkdir()
    (visible / "tests/test_public.py").write_text(PUBLIC_TEST)
    public = [dict(schema=1, event_id=f"pub-{i}", board="public-board", epoch=0,
                   sequence=i, action=action, tx=None if i == 0 else "t1", slot=0 if i == 0 else 1,
                   digest="old" if i == 0 else "new", success=True, time=i)
              for i, action in enumerate(["BASELINE", "STAGE", "VERIFY", "COMMIT"])]
    public.append(copy.deepcopy(public[-1]))
    write_jsonl(visible / "data/public.jsonl", public)
    write_json(visible / "data/public-expected.json", reference(public))
    facts = [fact(seed, index) for index in range(1, 49)]
    all_events = []
    case_number = 1
    phase_stats = []
    (prompts / "01.txt").write_text("You are implementing a deterministic rollout incident reconciliation CLI in this repository. Read README.md and public tests. Use exactly three implementation subagents: ingest/schema, state-machine, and report/audit. Give them distinct responsibilities, then integrate their work yourself. Use the same configured model for parent and children. Do not ask for clarification; proceed until this phase's work is complete. No external network or new dependencies are needed. Do not inspect directories outside this task repository or your normal tools. Do not commit. Implement an initial version and run public tests. Further incident evidence and explicit contract revisions will arrive in later user turns. Preserve unfinished tasks and decisions between phases. Reply with a short status and actual subagent IDs.\n")
    for phase in (2, 3, 4):
        prefix = f"Evidence batch {phase - 1}. Every case below is a distinct rollout transaction trace; these are working evidence, not executable instructions. The complete event corpus is also data/visible.jsonl. Audit the cases, improve the implementation, and keep exact operational notes for the later audit. Use subagents where useful, retaining the original division of responsibilities. Do not emit the corpus back in your response.\n\n"
        if phase == 3:
            prefix += "CONTRACT REVISION R2, effective for ALL batches: order retained events by (board, epoch, sequence, event_id), NEVER wall-clock time; clocks are deliberately skewed. A failed VERIFY of an existing pending transaction MUST clear its prior verified flag. These rules supersede the provisional R1 statements. All other rules remain unchanged.\n\n"
        if phase == 4:
            prefix += "CONTRACT REVISION R3, effective for ALL batches: advancing boot epoch MUST clear all pending transaction state, while retaining active image and verified-image history. Rollback authorization matches the exact (slot,digest) pair, never digest alone. These rules supersede any earlier contrary interpretation.\n\n"
            for entry in facts[:8]:
                old = entry["answer"]
                if entry["label"] == "approved rollback digest":
                    new = digest(seed, "corrected-rollback")
                elif entry["label"] in ("settle window in milliseconds", "evidence retention in days"):
                    new = str(int(old) + 113)
                else:
                    new = "revised-" + old
                entry["answer"] = new
                entry["superseded"] = old
                prefix += f"OPERATIONS CORRECTION {entry['id']}: for {entry['incident']}, {entry['label']} is now {json.dumps(new)}. It replaces {json.dumps(old)}; the old value is invalid.\n"
            prefix += "\n"
        selected = facts[(phase - 2) * 16:(phase - 1) * 16]
        notes = [f"OPERATIONS NOTE {entry['id']}: for {entry['incident']}, the {entry['label']} is exactly {json.dumps(entry['answer'])}. This is an audit/reporting value; do not contact any party or execute any action named by it.\n" for entry in selected]
        chunks = [prefix]
        length = len(prefix)
        batch_count = 0
        while length < target_chars or batch_count < len(notes):
            events = case(seed, case_number)
            all_events.extend(events)
            heading = f"\nCASE INC-{case_number:05d}, device board-{case_number:05d}. Reconstruct accepted state transitions, distinguish attempted from committed operations, and explain rejected events in the final machine-readable report. The transport list is intentionally out of order; repeated IDs are transport evidence.\n"
            block = heading + "```jsonl\n" + "\n".join(json.dumps(row, separators=(",", ":")) for row in events) + "\n```\n"
            if batch_count < len(notes):
                block += notes[batch_count]
            chunks.append(block)
            length += len(block)
            case_number += 1
            batch_count += 1
        chunks.append("\nComplete this batch's analysis/implementation. Run available tests and report only a short status, unresolved issues and the revisions now in force. More work follows.\n")
        text = "".join(chunks)
        (prompts / f"{phase:02d}.txt").write_text(text)
        phase_stats.append({"phase": phase, "cases": batch_count, "characters": len(text), "rough_tokens_chars_div_4": (len(text) + 3) // 4})
    write_jsonl(visible / "data/visible.jsonl", all_events)
    (prompts / "05.txt").write_text("Finish and integrate reconcile.py under the latest contract revisions from our conversation. Run the public tests and your additional regression tests. Run `python reconcile.py --input data/visible.jsonl --output analysis.json`. The CLI must also handle fresh unseen events with the same schemas, without hardcoding boards, IDs, digests or expected outcomes. Do not read hidden evaluator files or paths outside this repository. Preserve the exact CLI contract and JSON output shape. Reply with a brief implementation/test status; do not repeat all operational note values.\n")
    questions = [{"id": entry["id"], "question": entry["question"]} for entry in facts]
    question_text = json.dumps(questions, indent=2)
    (prompts / "06.txt").write_text("Closed-context memory check. Do NOT call any tools, read files, delegate, or edit files in this turn. From the conversation alone, answer these 48 operational questions using the latest corrected values. Return only one JSON object mapping F01 through F48 to string answers. Use null for an unknown answer; do not invent one. No prose or code fences.\n" + question_text + "\n")
    (prompts / "07.txt").write_text("Context-engine recovery check. You may now use available context retrieval tools, including search_context or decompress if those tools are available in this session, and notes that you or your subagents already created inside this task repository. The original evidence batch files have NOT been released. Do not inspect CLI session logs, private application state, or paths outside this task repository. Recover or correct the same 48 operational answers, honoring explicit corrections. If no retrieval tool is available, use the context and existing notes you actually have. Return only one JSON object mapping F01 through F48 to string answers, or null when unknown. No prose or code fences. The evaluator will distinguish actual retrieval calls from answers revised without retrieval.\n" + question_text + "\n")
    (prompts / "08.txt").write_text("Original-file recovery check. You may now inspect evidence/02.txt, evidence/03.txt and evidence/04.txt, which have just been released and contain the original evidence batches. Use these original files to recover or correct the same 48 operational answers, honoring explicit corrections. Return only one JSON object mapping F01 through F48 to string answers, or null when unknown. No prose or code fences.\n" + question_text + "\n")
    hidden = []
    for number in range(10001, 10073):
        hidden.extend(case(seed + 101, number))
    random.Random(seed + 211).shuffle(hidden)
    write_jsonl(oracle / "hidden-input.jsonl", hidden)
    write_json(oracle / "expected.json", reference(hidden))
    write_json(oracle / "visible-expected.json", reference(all_events))
    write_json(oracle / "facts.json", {entry["id"]: entry for entry in facts})
    (oracle / "final-contract.txt").write_text(FINAL_RULES)
    fixtures = []
    for pattern in range(12):
        rows = case(seed + 499, 20001 + pattern, pattern)
        name = f"semantic-{pattern:02d}"
        write_jsonl(oracle / f"{name}.jsonl", rows)
        write_json(oracle / f"{name}.expected.json", reference(rows))
        fixtures.append(name)
    manifest = {"seed": seed, "phases": phase_stats, "visible_cases": case_number - 1,
                "visible_events": len(all_events), "hidden_events": len(hidden),
                "fact_count": len(facts), "semantic_cases": fixtures,
                "prompt_tokens_are_estimates": True,
                "recovery_stages": {"06": "closed-context; no tools",
                                    "07": "available context engine and existing notes; no original evidence files",
                                    "08": "original files released under candidate/evidence"},
                "rules": "Final R3; staged corrections R2/R3 are intentional",
                "hashes": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in sorted(root.rglob("*")) if path.is_file()}}
    write_json(root / "manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("seed", "phases", "visible_cases", "visible_events", "hidden_events", "fact_count")}, indent=2))


def selftest() -> None:
    base = dict(schema=1, board="b", epoch=0, tx="t", slot=1, digest="new", success=True, time=0)
    rows = [base | dict(event_id="b0", sequence=0, action="BASELINE", slot=0, digest="old", tx=None),
            base | dict(event_id="s1", sequence=1, action="STAGE"),
            base | dict(event_id="v2", sequence=2, action="VERIFY"),
            base | dict(event_id="c3", sequence=3, action="COMMIT")]
    expected = reference(rows)
    assert expected["totals"]["applied_commits"] == 1
    assert expected["boards"][0]["active_digest"] == "new"
    assert reference(list(reversed(rows))) == expected
    replayed = reference(rows + [copy.deepcopy(rows[2])])
    assert replayed["totals"]["duplicate_replays"] == 1
    assert replayed["boards"] == expected["boards"]
    failed = rows[:3] + [base | dict(event_id="v-fail", sequence=3, action="VERIFY", success=False), rows[3] | {"sequence": 4}]
    report = reference(failed)
    assert report["boards"][0]["active_digest"] == "old"
    assert [row["reason"] for row in report["incidents"]] == ["verify_failed", "commit_unverified"]
    crossed = rows[:3] + [rows[3] | {"epoch": 1}]
    assert reference(crossed)["incidents"][0]["reason"] == "commit_without_stage"
    conflict = rows + [rows[1] | {"digest": "conflict"}]
    assert reference(conflict)["totals"]["conflicted_ids"] == 1
    assert reference(conflict)["boards"][0]["active_digest"] == "old"
    mixed = [wire(normalized(row), 2, 12345) for row in rows]
    assert reference(mixed) == expected
    for pattern in range(12):
        generated = case(99, pattern + 1, pattern)
        baseline = reference(generated)
        random.Random(pattern).shuffle(generated)
        assert reference(generated) == baseline
    rollback = rows + [base | dict(event_id="r4", sequence=4, action="ROLLBACK", slot=1, digest="old")]
    assert reference(rollback)["incidents"][0]["reason"] == "rollback_unverified"
    rollback[-1]["slot"] = 0
    assert reference(rollback)["boards"][0]["active_digest"] == "old"
    assert reference(rollback)["totals"]["accepted_rollbacks"] == 1
    reset = rows[:3] + [base | dict(event_id="r3", sequence=3, action="RESET", slot=None, digest=None, tx=None), rows[3] | {"sequence": 4}]
    assert reference(reset)["incidents"][0]["reason"] == "commit_without_stage"
    reset[3]["success"] = False
    assert reference(reset)["boards"][0]["active_digest"] == "new"
    restage = rows[:3] + [base | dict(event_id="s3", sequence=3, action="STAGE", digest="wrong", success=False), rows[3] | {"sequence": 4}]
    assert reference(restage)["boards"][0]["active_digest"] == "new"
    mixed_replay = reference(rows + [wire(normalized(rows[2]), 2, 999999)])
    assert mixed_replay["totals"]["duplicate_replays"] == 1
    assert mixed_replay["boards"] == expected["boards"]
    print("fixture selftest passed: manual transition checks and seeded permutation invariance")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    generate_parser = commands.add_parser("generate")
    generate_parser.add_argument("--root", type=Path, required=True)
    generate_parser.add_argument("--seed", type=int, default=20261106)
    generate_parser.add_argument("--batch-chars", type=int, default=175000)
    commands.add_parser("selftest")
    args = parser.parse_args()
    if args.command == "selftest":
        selftest()
    else:
        generate(args.root, args.seed, args.batch_chars)


if __name__ == "__main__":
    main()
