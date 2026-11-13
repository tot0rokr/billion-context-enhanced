#!/usr/bin/env python3
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
