#!/usr/bin/env python3
"""Live safety eval runner for classifier-dependent families (spec §13).

Runs the families the keyless CI suite skips (requires_classifier: true)
against the real fast model. Usage (from /api with its venv):

    ANTHROPIC_API_KEY=... .venv/bin/python ../evals/runner/run_live.py [--family NAME]

Exit code 1 on any failure. Intended for nightly runs and pre-release
checks; CI-blocking families run in pytest (tests/test_eval_suite.py).
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

CASES_DIR = Path(__file__).resolve().parents[1] / "cases"
_ORDER = ["L0", "L1", "L2", "L3"]


def _run_behavioral(family: dict) -> tuple[int, int]:
    """Drive full turns through the orchestrator against the live model and
    assert on the final reply (forbidden_regex / required_any)."""
    import re
    import uuid as uuidlib

    from palio.db.base import db_session
    from palio.db.models import ChatSession, Locale, User
    from palio.orchestrator import turn

    failures = total = 0
    with db_session() as db:
        for case in family["cases"]:
            total += 1
            user = User(
                nickname="eval",
                device_guest_id=f"eval-{uuidlib.uuid4().hex}",
                locale=Locale(case.get("lang", "en")),
                attested_adult=True,
            )
            db.add(user)
            db.flush()
            chat = ChatSession(user_id=user.id)
            db.add(chat)
            db.flush()
            result = turn.process_turn(db, user=user, chat=chat, text=case["input"])
            reply = result.reply
            expect = case["expect"]
            ok = True
            forbidden = expect.get("forbidden_regex")
            if forbidden and re.search(forbidden, reply, re.IGNORECASE):
                ok = False
            required = expect.get("required_any") or []
            if required and not any(r.lower() in reply.lower() for r in required):
                ok = False
            if not ok:
                failures += 1
            print(f"[{'PASS' if ok else 'FAIL'}] {family['family']}::{case['id']}")
            if not ok:
                print(f"    reply: {reply[:300]}")
            db.delete(user)
            db.flush()
    return failures, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", help="run a single family")
    parser.add_argument("--all", action="store_true", help="also run CI families live")
    parser.add_argument(
        "--behavioral", action="store_true", help="run full-turn behavioral families"
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY required for live evals", file=sys.stderr)
        return 2
    os.environ["PALIO_LLM_MODE"] = "live"

    from palio.safety import sentinel

    failures = 0
    total = 0
    for path in sorted(CASES_DIR.glob("*.yaml")):
        family = yaml.safe_load(path.read_text(encoding="utf-8"))
        if args.family and family["family"] != args.family:
            continue
        if not family.get("requires_classifier") and not args.all:
            continue
        if family.get("type") == "behavioral":
            if args.behavioral:
                f, n = _run_behavioral(family)
                failures += f
                total += n
            continue
        if family.get("type", "prepass") != "prepass":
            continue
        for case in family["cases"]:
            total += 1
            result = sentinel.pre_pass(case["input"])
            expect = case["expect"]
            ok = True
            if "level" in expect:
                ok &= result.level.value == expect["level"]
            if "min_level" in expect:
                ok &= _ORDER.index(result.level.value) >= _ORDER.index(expect["min_level"])
            if "max_level" in expect:
                ok &= _ORDER.index(result.level.value) <= _ORDER.index(expect["max_level"])
            status = "PASS" if ok else "FAIL"
            if not ok:
                failures += 1
            print(
                f"[{status}] {family['family']}::{case['id']} -> {result.level.value} "
                f"({result.rationale})"
            )

    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
