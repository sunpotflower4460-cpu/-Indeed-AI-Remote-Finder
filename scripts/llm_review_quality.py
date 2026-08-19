#!/usr/bin/env python3
"""Spend only unused per-run LLM budget on quality-gated REVIEW candidates.

The primary llm_review.py remains responsible for deterministic HIGH rows. This
second pass never increases the configured eight-attempt run budget: it computes
how many attempts the primary pass already spent compared with the previous
feed and uses only the remainder. If the primary pass reported any provider
failure or uncertain attempt accounting, the spare pass is skipped entirely so
we do not keep calling a degraded provider.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import llm_review

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
QUALITY_POLICY_VERSION = 2
QUALITY_GATE = "async-ai-remote-v2"
RUN_ATTEMPT_CAP = 8
REVIEW_AUTOMATION_MIN = 64
REVIEW_HUMAN_RISK_MAX = 18


def eligible(row: dict) -> bool:
    return bool(
        isinstance(row, dict)
        and row.get("id")
        and row.get("tier") == "review"
        and int(row.get("quality_policy_version") or 0) == QUALITY_POLICY_VERSION
        and row.get("quality_gate") == QUALITY_GATE
        and row.get("autonomy_attention_risk") == "low"
        and row.get("remote_search_only") is not True
        and int(row.get("automation_confidence") or 0) >= REVIEW_AUTOMATION_MIN
        and int(row.get("human_dependency_risk") or 0) <= REVIEW_HUMAN_RISK_MAX
        and not isinstance(row.get("llm_review"), dict)
    )


def sort_key(row: dict) -> tuple[int, int, int, int]:
    return (
        1 if not row.get("carryover") else 0,
        int(row.get("automation_confidence") or 0),
        int(row.get("freshness_confidence") or 0),
        int(row.get("score") or 0),
    )


def enrich_review_tier(
    payload: dict,
    previous: dict,
    *,
    api_key: str,
    model: str,
    run_attempt_cap: int = RUN_ATTEMPT_CAP,
    max_paid_attempts_per_month: int = llm_review.DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH,
) -> dict:
    jobs = payload.get("jobs") or []
    month = llm_review.month_key()
    previous_attempts = llm_review.prior_month_attempts({}, previous, month)
    try:
        current_attempts = max(previous_attempts, int(payload.get("llm_paid_attempts_month") or 0))
    except Exception:
        current_attempts = previous_attempts
    spent_this_run = max(0, current_attempts - previous_attempts)
    remaining_run = max(0, int(run_attempt_cap) - spent_this_run)
    monthly_cap = max(0, int(max_paid_attempts_per_month))
    remaining_month = max(0, monthly_cap - current_attempts)
    allowed = min(remaining_run, remaining_month)

    failures = int(payload.get("llm_review_failures") or 0)
    errors = list(payload.get("llm_errors") or [])
    fatal_error = payload.get("llm_fatal_error")
    primary_degraded = bool(
        failures > 0 or fatal_error or payload.get("llm_attempts_uncertain") is True
    )
    new_review_tier = 0
    attempts = 0

    if api_key and allowed > 0 and not primary_degraded:
        candidates = sorted(
            [row for row in jobs if eligible(row)], key=sort_key, reverse=True
        )
        for row in candidates[:allowed]:
            current_attempts += 1
            attempts += 1
            try:
                review = llm_review.call_openai(row, api_key, model)
                row["llm_review"] = review
                row["llm_input_hash"] = llm_review.input_hash(row)
                row["llm_model"] = model
                row["llm_reviewed_at"] = datetime.now(timezone.utc).isoformat()
                row["llm_strict_pass"] = bool(review.get("strict_pass"))
                new_review_tier += 1
            except llm_review.OpenAIRequestError as exc:
                failures += 1
                errors.append(f"{row.get('id')}: {exc}")
                print(f"WARN review-tier LLM failed [{row.get('id')}]: {exc}", file=sys.stderr)
                if 400 <= exc.status < 500:
                    fatal_error = str(exc)
                break
            except Exception as exc:
                failures += 1
                errors.append(f"{row.get('id')}: {exc}")
                print(f"WARN review-tier LLM failed [{row.get('id')}]: {exc}", file=sys.stderr)
                break

    reviewed = sum(
        1 for row in jobs if isinstance(row, dict) and isinstance(row.get("llm_review"), dict)
    )
    strict = sum(
        1 for row in jobs if isinstance(row, dict) and row.get("llm_strict_pass") is True
    )
    payload["llm_reviewed_jobs"] = reviewed
    payload["llm_strict_jobs"] = strict
    payload["llm_new_reviews"] = int(payload.get("llm_new_reviews") or 0) + new_review_tier
    payload["llm_review_tier_new_reviews"] = new_review_tier
    payload["llm_review_tier_attempts"] = attempts
    payload["llm_review_tier_skipped_after_primary_failure"] = primary_degraded
    payload["llm_run_attempt_cap"] = int(run_attempt_cap)
    payload["llm_review_failures"] = failures
    payload["llm_errors"] = errors[:8]
    payload["llm_fatal_error"] = fatal_error
    payload["llm_budget_month"] = month
    payload["llm_paid_attempts_month"] = current_attempts
    payload["llm_max_paid_attempts_per_month"] = monthly_cap
    payload["llm_monthly_budget_exhausted"] = bool(
        api_key and current_attempts >= monthly_cap
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--run-attempt-cap", type=int, default=RUN_ATTEMPT_CAP)
    parser.add_argument(
        "--max-paid-attempts-per-month",
        type=int,
        default=llm_review.DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH,
    )
    args = parser.parse_args()

    payload = llm_review.load_json(args.feed)
    previous = llm_review.load_json(args.previous) if args.previous else {}
    if not isinstance(payload.get("jobs"), list):
        raise SystemExit("feed does not contain jobs[]")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", llm_review.DEFAULT_MODEL).strip() or llm_review.DEFAULT_MODEL
    result = enrich_review_tier(
        payload,
        previous,
        api_key=api_key,
        model=model,
        run_attempt_cap=max(0, args.run_attempt_cap),
        max_paid_attempts_per_month=max(0, args.max_paid_attempts_per_month),
    )
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "review-tier LLM audit: "
        f"new={result.get('llm_review_tier_new_reviews', 0)} "
        f"attempts={result.get('llm_review_tier_attempts', 0)} "
        f"total_month={result.get('llm_paid_attempts_month', 0)}/"
        f"{result.get('llm_max_paid_attempts_per_month', 0)} "
        f"skip-after-primary-failure={result.get('llm_review_tier_skipped_after_primary_failure', False)}"
    )
    if result.get("llm_fatal_error"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
