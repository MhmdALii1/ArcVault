#!/usr/bin/env python3
"""Posts test messages to the live n8n webhook, saves the records, and scores them.

Usage:
  python scripts/run_cases.py --url <WEBHOOK_URL> --cases data/samples.json --out output/results.json
  python scripts/run_cases.py --url <WEBHOOK_URL> --cases data/edge_cases.json --out output/edge_cases.json
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def post(url, payload):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "arcvault-test-runner/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def check(case, status, record):
    """Returns a list of differences between the expected and actual result."""
    expect = case["expect"]
    if status != expect.get("status", 200):
        return [f"HTTP status {status}, expected {expect.get('status', 200)}"]
    if status != 200:
        return []

    routing, classification = record["routing"], record["classification"]
    problems = []
    if "category" in expect and classification["category"] != expect["category"]:
        problems.append(f"category {classification['category']!r}, expected {expect['category']!r}")
    if "priority" in expect and classification["priority"] not in expect["priority"]:
        problems.append(f"priority {classification['priority']!r}, expected one of {expect['priority']}")
    if "final_queue" in expect and routing["final_queue"] != expect["final_queue"]:
        problems.append(f"queue {routing['final_queue']!r}, expected {expect['final_queue']!r}")
    if "escalated" in expect and routing["escalated"] != expect["escalated"]:
        problems.append(f"escalated {routing['escalated']}, expected {expect['escalated']}")
    for reason in expect.get("reasons", []):
        if reason not in routing["escalation_reasons"]:
            problems.append(f"missing reason {reason!r}, got {routing['escalation_reasons']}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pause", type=float, default=8.0, help="seconds between messages, for free-tier limits")
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    records, failures = [], 0
    for index, case in enumerate(cases):
        if index:
            time.sleep(args.pause)
        status, body = post(args.url, case["input"])
        record = None
        if status == 200:
            try:
                record = json.loads(body)
            except json.JSONDecodeError:
                status = -1
        problems = check(case, status, record)
        failures += bool(problems)
        print(f"[{'PASS' if not problems else 'FAIL'}] {case['input'].get('id')}: {case['note']}")
        if record:
            c, r = record["classification"], record["routing"]
            print(f"       {c['category']} | {c['priority']} | {c['confidence']} | "
                  f"{r['final_queue']} | {r['escalation_reasons']}")
        for problem in problems:
            print(f"       -> {problem}")
        if record:
            records.append(record)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"record_count": len(records), "records": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(cases) - failures}/{len(cases)} passed. Saved {len(records)} records to {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
