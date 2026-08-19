# AI Remote Finder quality contract

Production recommendations are not a generic remote-job list. A published candidate must be suitable for an asynchronous AI-substitution workflow.

## Required

- Indeed individual application URL verified from structured Google Jobs data.
- The listing text itself provides explicit full-remote evidence (for example 完全在宅 / フルリモート / 完全リモート / 100%リモート).
- No explicit partial/hybrid arrangement such as 在宅週1〜2日, 一部在宅, 出社併用, or 慣れたら在宅.
- No core requirement for synchronous human attention such as calls, live customer support, meetings, real-time monitoring, negotiation, ongoing coordination, progress management, or similar human-presence work.
- REVIEW candidates must have automation_confidence >= 55 and human_dependency_risk <= 25.

## Quantity policy

The server target remains 100 candidates, but quantity never overrides the quality gates above. Discovery breadth is increased through rotating task-specific searches and rolling retention of already quality-gated candidates rather than by weakening the publication threshold.

## Safety boundary

Technical AI substitutability does not imply that an employer permits generative AI use or that confidential/personal information may be sent to external AI services. Those employment and data-handling rules still require confirmation before automation is used in real work.
