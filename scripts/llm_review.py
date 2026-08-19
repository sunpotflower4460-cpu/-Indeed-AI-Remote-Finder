#!/usr/bin/env python3
"""Optional LLM second-opinion audit for already-filtered job candidates.

The deterministic scorer remains authoritative. This enrichment layer adds a
structured second opinion, an estimated automatable fraction, likely blockers,
and an implementation sketch. It never calls Indeed directly and never embeds
an API key in the client.

Required for new LLM reviews:
    OPENAI_API_KEY
Optional:
    OPENAI_MODEL (default: gpt-5.6-luna)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_MAX_NEW_REVIEWS = 8
DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH = 700
REASONING_EFFORT = "none"

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["strong", "uncertain", "reject"]},
        "automatable_fraction": {"type": "integer"},
        "confidence": {"type": "integer"},
        "human_dependency": {"type": "string", "enum": ["low", "medium", "high"]},
        "physical_presence_required": {"type": "boolean"},
        "synchronous_human_interaction": {
            "type": "string",
            "enum": ["none", "occasional", "frequent"],
        },
        "data_sensitivity_risk": {
            "type": "string",
            "enum": ["low", "unknown", "elevated"],
        },
        "automation_summary": {"type": "string"},
        "automation_plan": {"type": "array", "items": {"type": "string"}},
        "blockers": {"type": "array", "items": {"type": "string"}},
        "questions_to_confirm": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict",
        "automatable_fraction",
        "confidence",
        "human_dependency",
        "physical_presence_required",
        "synchronous_human_interaction",
        "data_sensitivity_risk",
        "automation_summary",
        "automation_plan",
        "blockers",
        "questions_to_confirm",
    ],
    "additionalProperties": False,
}

INSTRUCTIONS = """You are the second-pass auditor for a job-finding app that is intentionally conservative.
Use ONLY the supplied job text. Never assume facts that are not present.
Judge technical task automability, not whether automation is contractually allowed.

Rules:
- strong: the work appears almost entirely digital, repeatable, and technically delegable to AI/RPA; physical presence is not inherent; frequent synchronous human interaction is not inherent; estimated automatable_fraction should normally be >= 90.
- uncertain: evidence is incomplete, mixed, or hidden workflow details could materially change the answer.
- reject: physical work, real-time persuasion/support, relationship work, management, frequent meetings/calls, or other inherently human activity is central.
- If employer permission for AI, confidentiality rules, personal data handling, or external-AI usage is not explicit, put that in questions_to_confirm rather than inventing an answer.
- blockers are actual technical/task blockers visible in the text, not generic legal cautions.
- automation_plan should be concise and concrete, at most 5 steps.
- questions_to_confirm should be concise, at most 5 items.
Return only the schema-defined result.
"""


class OpenAIRequestError(RuntimeError):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"OpenAI HTTP {status}: {detail}")


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def job_input(row: dict) -> dict:
    return {
        "title": row.get("title"),
        "company": row.get("company"),
        "location": row.get("location"),
        "summary": row.get("snippet"),
        "tags": row.get("tags") or [],
        "automation_reasons": row.get("automation_reasons") or [],
        "risk_reasons": row.get("risk_reasons") or [],
        "deterministic": {
            "tier": row.get("tier"),
            "automation_confidence": row.get("automation_confidence"),
            "remote_confidence": row.get("remote_confidence"),
            "freshness_confidence": row.get("freshness_confidence"),
            "human_dependency_risk": row.get("human_dependency_risk"),
        },
    }


def input_hash(row: dict) -> str:
    raw = json.dumps(job_input(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_output_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"].strip()
            if content.get("type") == "refusal":
                raise RuntimeError(f"model refusal: {content.get('refusal') or 'unknown'}")
    raise RuntimeError("OpenAI response did not contain output_text")


def clamp_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not a score")
    try:
        n = int(value)
    except Exception as exc:
        raise ValueError(f"invalid integer: {value!r}") from exc
    return max(0, min(100, n))


def clean_list(value: object, *, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text[:240])
        if len(out) >= limit:
            break
    return out


def normalize_review(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("review must be an object")
    verdict = str(raw.get("verdict") or "")
    human = str(raw.get("human_dependency") or "")
    sync = str(raw.get("synchronous_human_interaction") or "")
    sensitivity = str(raw.get("data_sensitivity_risk") or "")
    if verdict not in {"strong", "uncertain", "reject"}:
        raise ValueError(f"invalid verdict: {verdict!r}")
    if human not in {"low", "medium", "high"}:
        raise ValueError(f"invalid human_dependency: {human!r}")
    if sync not in {"none", "occasional", "frequent"}:
        raise ValueError(f"invalid synchronous_human_interaction: {sync!r}")
    if sensitivity not in {"low", "unknown", "elevated"}:
        raise ValueError(f"invalid data_sensitivity_risk: {sensitivity!r}")
    physical = raw.get("physical_presence_required")
    if not isinstance(physical, bool):
        raise ValueError("physical_presence_required must be boolean")

    review = {
        "verdict": verdict,
        "automatable_fraction": clamp_int(raw.get("automatable_fraction")),
        "confidence": clamp_int(raw.get("confidence")),
        "human_dependency": human,
        "physical_presence_required": physical,
        "synchronous_human_interaction": sync,
        "data_sensitivity_risk": sensitivity,
        "automation_summary": str(raw.get("automation_summary") or "").strip()[:600],
        "automation_plan": clean_list(raw.get("automation_plan")),
        "blockers": clean_list(raw.get("blockers")),
        "questions_to_confirm": clean_list(raw.get("questions_to_confirm")),
    }
    review["strict_pass"] = bool(
        review["verdict"] == "strong"
        and review["automatable_fraction"] >= 90
        and review["confidence"] >= 80
        and review["human_dependency"] == "low"
        and review["physical_presence_required"] is False
        and review["synchronous_human_interaction"] == "none"
        and not review["blockers"]
    )
    return review


def request_body(row: dict, model: str) -> dict:
    return {
        "model": model,
        "store": False,
        "reasoning": {"effort": REASONING_EFFORT},
        "instructions": INSTRUCTIONS,
        "input": json.dumps(job_input(row), ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "job_automation_audit",
                "strict": True,
                "schema": SCHEMA,
            }
        },
        "max_output_tokens": 900,
    }


def call_openai(row: dict, api_key: str, model: str) -> dict:
    body = request_body(row, model)
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "AI-Remote-Finder/5.2",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise OpenAIRequestError(exc.code, detail) from exc
    return normalize_review(json.loads(extract_output_text(payload)))


def reusable_review(
    row: dict,
    expected_hash: str,
    expected_model: str | None = None,
) -> tuple[dict, str] | None:
    review = row.get("llm_review")
    old_hash = str(row.get("llm_input_hash") or "")
    model = str(row.get("llm_model") or "")
    if old_hash != expected_hash or not isinstance(review, dict) or not model:
        return None
    if expected_model and model != expected_model:
        return None
    try:
        normalized = normalize_review(review)
    except Exception:
        return None
    return normalized, model


def month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y-%m")


def prior_month_attempts(current: dict, previous: dict, month: str) -> int:
    values: list[int] = []
    for source in (current, previous):
        if str(source.get("llm_budget_month") or "") != month:
            continue
        try:
            values.append(max(0, int(source.get("llm_paid_attempts_month") or 0)))
        except Exception:
            continue
    return max(values, default=0)


def enrich(
    payload: dict,
    previous: dict,
    *,
    api_key: str,
    model: str,
    max_new_reviews: int = DEFAULT_MAX_NEW_REVIEWS,
    max_paid_attempts_per_month: int = DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH,
) -> dict:
    jobs = payload.get("jobs") or []
    prev_by_id = {
        str(row.get("id")): row
        for row in (previous.get("jobs") or [])
        if isinstance(row, dict) and row.get("id")
    }
    new_reviews = reused = failures = skipped_non_high = 0
    errors: list[str] = []
    fatal_error: str | None = None
    stop_after_transient_error = False
    month = month_key()
    monthly_cap = max(0, int(max_paid_attempts_per_month))
    paid_attempts_month = prior_month_attempts(payload, previous, month)
    required_model = model if api_key else None

    for row in jobs:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        digest = input_hash(row)
        candidates = [row, prev_by_id.get(str(row["id"])) or {}]
        reused_value = None
        for candidate in candidates:
            reused_value = reusable_review(candidate, digest, required_model)
            if reused_value:
                break
        if reused_value:
            review, used_model = reused_value
            row["llm_review"] = review
            row["llm_input_hash"] = digest
            row["llm_model"] = used_model
            row["llm_strict_pass"] = bool(review.get("strict_pass"))
            reused += 1
            continue

        for key in ("llm_review", "llm_input_hash", "llm_model", "llm_reviewed_at", "llm_strict_pass"):
            row.pop(key, None)

        # Cost guard: only deterministic high-confidence candidates receive a new
        # paid LLM review. Review-tier rows remain visible through the free rules.
        if row.get("tier") != "high":
            skipped_non_high += 1
            continue
        if not api_key or new_reviews >= max_new_reviews:
            continue
        if fatal_error or stop_after_transient_error:
            continue
        if paid_attempts_month >= monthly_cap:
            continue

        paid_attempts_month += 1
        try:
            review = call_openai(row, api_key, model)
            row["llm_review"] = review
            row["llm_input_hash"] = digest
            row["llm_model"] = model
            row["llm_reviewed_at"] = datetime.now(timezone.utc).isoformat()
            row["llm_strict_pass"] = bool(review.get("strict_pass"))
            new_reviews += 1
        except OpenAIRequestError as exc:
            failures += 1
            errors.append(f"{row.get('id')}: {exc}")
            print(f"WARN LLM review failed [{row.get('id')}]: {exc}", file=sys.stderr)
            if 400 <= exc.status < 500:
                fatal_error = str(exc)
            else:
                stop_after_transient_error = True
        except Exception as exc:
            failures += 1
            errors.append(f"{row.get('id')}: {exc}")
            print(f"WARN LLM review failed [{row.get('id')}]: {exc}", file=sys.stderr)
            stop_after_transient_error = True

    reviewed = sum(1 for row in jobs if isinstance(row, dict) and isinstance(row.get("llm_review"), dict))
    strict = sum(1 for row in jobs if isinstance(row, dict) and row.get("llm_strict_pass") is True)
    payload["llm_provider_configured"] = bool(api_key)
    payload["llm_model"] = model if api_key or reviewed else None
    payload["llm_reasoning_effort"] = REASONING_EFFORT
    payload["llm_reviewed_jobs"] = reviewed
    payload["llm_strict_jobs"] = strict
    payload["llm_new_reviews"] = new_reviews
    payload["llm_reused_reviews"] = reused
    payload["llm_review_failures"] = failures
    payload["llm_skipped_non_high"] = skipped_non_high
    payload["llm_max_new_reviews_per_run"] = max_new_reviews
    payload["llm_budget_month"] = month
    payload["llm_paid_attempts_month"] = paid_attempts_month
    payload["llm_max_paid_attempts_per_month"] = monthly_cap
    payload["llm_monthly_budget_exhausted"] = bool(api_key and paid_attempts_month >= monthly_cap)
    payload["llm_fatal_error"] = fatal_error
    payload["llm_errors"] = errors[:8]
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--max-new-reviews", type=int, default=DEFAULT_MAX_NEW_REVIEWS)
    parser.add_argument(
        "--max-paid-attempts-per-month",
        type=int,
        default=DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH,
    )
    args = parser.parse_args()

    payload = load_json(args.feed)
    if not isinstance(payload.get("jobs"), list):
        print("ERROR: feed does not contain jobs[]", file=sys.stderr)
        raise SystemExit(1)
    previous = load_json(args.previous) if args.previous else {}
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    enrich(
        payload,
        previous,
        api_key=api_key,
        model=model,
        max_new_reviews=max(0, args.max_new_reviews),
        max_paid_attempts_per_month=max(0, args.max_paid_attempts_per_month),
    )
    args.feed.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if api_key:
        print(
            f"LLM audit: reviewed={payload['llm_reviewed_jobs']} strict={payload['llm_strict_jobs']} "
            f"new={payload['llm_new_reviews']} reused={payload['llm_reused_reviews']} "
            f"attempts_month={payload['llm_paid_attempts_month']}/{payload['llm_max_paid_attempts_per_month']} "
            f"skipped_non_high={payload['llm_skipped_non_high']} failures={payload['llm_review_failures']}"
        )
    else:
        print(
            f"OPENAI_API_KEY not configured; preserved {payload['llm_reviewed_jobs']} reusable LLM reviews."
        )
    if payload.get("llm_fatal_error"):
        print(f"ERROR: {payload['llm_fatal_error']}", file=sys.stderr)
        raise SystemExit(3)


if __name__ == "__main__":
    main()
