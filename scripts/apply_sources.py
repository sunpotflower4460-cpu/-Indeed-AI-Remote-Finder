#!/usr/bin/env python3
"""Conservative application-target selection for candidate rows.

Indeed remains the preferred destination. When a result has no Indeed apply
option, allow a small audited set of established Japanese job boards, major ATS
hosts, and selected official AI-work provider career/project hosts instead of
discarding an otherwise high-quality remote/AI-automatable listing before the
strict quality gates can evaluate it.

This module does not grant publication eligibility by URL alone. The listing
must still pass the production remote, autonomy, presence, AI-use-policy,
deterministic-quality, freshness and applicable LLM gates.
"""
from __future__ import annotations

import hashlib
import re
import sys
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplyTarget:
    url: str
    job_id: str
    source: str
    kind: str


# Ordered after Indeed. Keep these lists intentionally bounded and recognizable.
TRUSTED_JOB_BOARD_HOSTS: tuple[tuple[str, str], ...] = (
    ("next.rikunabi.com", "リクナビNEXT"),
    ("townwork.net", "タウンワーク"),
    ("froma.com", "フロム・エー ナビ"),
    ("hatalike.jp", "はたらいく"),
    ("toranet.jp", "とらばーゆ"),
)

TRUSTED_ATS_HOSTS: tuple[tuple[str, str], ...] = (
    ("jobs.lever.co", "Lever"),
    ("boards.greenhouse.io", "Greenhouse"),
    ("job-boards.greenhouse.io", "Greenhouse"),
    ("job-boards.eu.greenhouse.io", "Greenhouse"),
    ("jobs.ashbyhq.com", "Ashby"),
    ("myworkdayjobs.com", "Workday"),
    ("jobs.smartrecruiters.com", "SmartRecruiters"),
    ("apply.workable.com", "Workable"),
)

# Direct career/project hosts are deliberately limited to providers whose
# current remote AI-training/rating/annotation work has been independently
# verified. These hosts are only trusted destinations; they never bypass the
# content quality gates.
TRUSTED_PROVIDER_HOSTS: tuple[tuple[str, str], ...] = (
    ("outlier.ai", "Outlier"),
    ("alignerr.com", "Alignerr"),
    ("oneforma.com", "OneForma"),
    ("dataannotation.tech", "DataAnnotation"),
    ("jobs.telusdigital.com", "TELUS Digital"),
)

# The product is Indeed-first. Other trusted sources are a separately presented
# fallback pool and must never make the Indeed inventory look healthy.
INDEED_PRIMARY_STOCK_TARGET = 30


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _safe_https_url(link: str) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlparse(link)
    except Exception:
        return None
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").lower().strip(".")
    if not host or len(link) > 2048:
        return None
    # Root/homepage links are not useful application targets.
    if not parsed.path or parsed.path == "/":
        return None
    normalized = urllib.parse.urlunparse(
        ("https", parsed.netloc, parsed.path, parsed.params, parsed.query, "")
    )
    return normalized, host


def _stable_target(link: str, source: str, kind: str) -> ApplyTarget:
    digest = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
    return ApplyTarget(
        url=link,
        job_id=f"apply-{digest}",
        source=source,
        kind=kind,
    )


def _indeed_target(link: str) -> ApplyTarget | None:
    safe = _safe_https_url(link)
    if not safe:
        return None
    normalized, host = safe
    if not _host_matches(host, "indeed.com"):
        return None
    parsed = urllib.parse.urlparse(normalized)
    if "/viewjob" not in parsed.path.lower():
        return None
    params = urllib.parse.parse_qs(parsed.query)
    job_id = _clean((params.get("jk") or [""])[0])
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", job_id):
        return None
    encoded = urllib.parse.quote(job_id, safe="")
    return ApplyTarget(
        url=f"https://jp.indeed.com/viewjob?jk={encoded}",
        job_id=job_id,
        source="Indeed",
        kind="indeed",
    )


def _match_allowlist(
    link: str,
    rules: tuple[tuple[str, str], ...],
    kind: str,
) -> ApplyTarget | None:
    safe = _safe_https_url(link)
    if not safe:
        return None
    normalized, host = safe
    for suffix, label in rules:
        if _host_matches(host, suffix):
            return _stable_target(normalized, label, kind)
    return None


def _trusted_board_target(link: str) -> ApplyTarget | None:
    return _match_allowlist(link, TRUSTED_JOB_BOARD_HOSTS, "trusted-job-board")


def _trusted_ats_target(link: str) -> ApplyTarget | None:
    return _match_allowlist(link, TRUSTED_ATS_HOSTS, "trusted-ats")


def _trusted_provider_target(link: str) -> ApplyTarget | None:
    return _match_allowlist(link, TRUSTED_PROVIDER_HOSTS, "trusted-provider")


def find_trusted_apply(job: dict) -> ApplyTarget | None:
    """Return Indeed first, then audited board/ATS/provider application URLs."""
    if not isinstance(job, dict):
        return None
    options = job.get("apply_options") or []
    if not isinstance(options, list):
        return None

    links: list[str] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        link = _clean(option.get("link"))
        if link:
            links.append(link)

    # Preserve the product's original Indeed preference whenever available.
    for link in links:
        target = _indeed_target(link)
        if target:
            return target
    for resolver in (
        _trusted_board_target,
        _trusted_ats_target,
        _trusted_provider_target,
    ):
        for link in links:
            target = resolver(link)
            if target:
                return target
    return None


def target_tuple(job: dict) -> tuple[str, str] | None:
    target = find_trusted_apply(job)
    if not target:
        return None
    return target.url, target.job_id


def _row_has_verified_indeed(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("apply_source_kind") or "").strip().lower() == "indeed":
        return True
    return _indeed_target(_clean(row.get("url"))) is not None


def _indeed_stock(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    jobs = payload.get("jobs") or []
    if isinstance(jobs, list):
        return sum(1 for row in jobs if _row_has_verified_indeed(row))
    try:
        return max(0, int(payload.get("candidate_final_indeed_apply_jobs") or 0))
    except (TypeError, ValueError):
        return 0


def _install_production_indeed_priority() -> None:
    """Make SerpApi search budget follow Indeed stock, not total mixed-source stock.

    This is intentionally installed only when the production acquisition entrypoint
    is executed. Unit tests and supplemental-source scripts keep their isolated
    module behavior.
    """
    if not str(sys.argv[0] or "").replace("\\", "/").endswith("/acquisition_precision.py"):
        return

    import acquisition_supply_yield as supply

    if getattr(supply, "_indeed_primary_priority_installed", False):
        return
    supply._indeed_primary_priority_installed = True
    original_select = supply.select_query_profiles

    def indeed_first_select(previous_payload: dict | None) -> list[tuple[str, str]]:
        stock = _indeed_stock(previous_payload)
        if stock < INDEED_PRIMARY_STOCK_TARGET:
            # All paced SerpApi requests are directed at the existing proven
            # Indeed-biased recovery query set until the Indeed pool is healthy.
            supply._ACTIVE_SOURCE_RECOVERY = True
            supply._SOURCE_RECOVERY_TRIGGER_RATIO = 1.0
            supply._SOURCE_RECOVERY_COOLDOWN_REMAINING = 0
            supply._SOURCE_RECOVERY_TRIGGER_REASON = (
                f"indeed-primary-stock-low:{stock}/{INDEED_PRIMARY_STOCK_TARGET}"
            )
            return list(supply.SOURCE_RECOVERY_QUERY_PROFILES)
        return original_select(previous_payload)

    supply.select_query_profiles = indeed_first_select


_install_production_indeed_priority()
