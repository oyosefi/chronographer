#!/usr/bin/env python3
"""Agentskills-compatible handler for the Chronographer skill.

This script implements a minimal CLI-style handler that accepts an action as the
first argument and a JSON payload on stdin (or empty). It delegates to the
ChronoClient in the same package.

Usage examples:
  echo '{"start":"2026-07-12T00:00:00-07:00","end":"2026-07-12T23:59:59-07:00"}' | \
    python handler.py list_upcoming

  echo '{"task_id":"<id>","completed_at":"2026-07-12T18:00:00-07:00"}' | \
    python handler.py complete_task

The agentskills runner can invoke the handler.py module with the same contract.
"""

import sys
import json
import os

from client import ChronoClient


def _read_payload():
    try:
        raw = sys.stdin.read()
        if not raw or raw.strip() == "":
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _output(obj):
    print(json.dumps(obj, default=str))


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing action argument"}))
        sys.exit(2)
    action = sys.argv[1]
    payload = _read_payload()

    try:
        client = ChronoClient()
    except Exception as e:
        _output({"error": f"failed to initialize ChronoClient: {e}"})
        sys.exit(1)

    try:
        if action == 'list_upcoming':
            start = payload.get('start')
            end = payload.get('end')
            display_tz = payload.get('display_tz')
            result = client.list_upcoming(start, end, display_tz)
            _output(result)
            return

        if action == 'get_next':
            task_id = payload.get('task_id')
            result = client.get_next(task_id)
            _output(result)
            return

        if action == 'get_last':
            task_id = payload.get('task_id')
            result = client.get_last_completion(task_id)
            _output(result)
            return

        if action == 'create_task':
            task = payload.get('task')
            result = client.create_task(task)
            _output(result)
            return

        if action == 'complete_task':
            task_id = payload.get('task_id')
            completed_at = payload.get('completed_at')
            notes = payload.get('notes')
            metadata = payload.get('metadata')
            idempotency_key = payload.get('idempotency_key')
            result = client.complete_task(task_id, completed_at, notes, metadata, idempotency_key)
            _output(result)
            return

        _output({"error": f"unknown action: {action}"})
        sys.exit(2)
    except Exception as e:
        _output({"error": str(e)})
        sys.exit(1)


if __name__ == '__main__':
    main()
