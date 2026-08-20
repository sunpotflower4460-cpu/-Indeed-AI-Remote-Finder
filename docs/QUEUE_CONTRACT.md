# Candidate queue contract

This document fixes the intended candidate-stock behavior as a product invariant.

## Capacity layers

- Server rolling pool hard limit: **150 candidates**.
- User-facing unapplied stock target: **100 candidates**.
- Initial recommendation window: **30 candidates**.
- Additional browsing expands in **30-candidate batches** only when the user explicitly asks to see more.

The 150-row layer is not permission to weaken quality. Every row in the server pool must have survived the current remote, autonomy, presence, AI-use-policy, deterministic-quality, freshness and applicable LLM gates.

## Automatic replacement after a user action

The recommendation queue filters user actions before taking the visible 30-row window.

Example with 100 eligible candidates:

1. Candidate IDs 1-30 are visible.
2. The user marks candidate 1 as applied.
3. Candidate 1 is excluded from recommendations but remains in the user's applied history.
4. The recommendation queue is rebuilt from the remaining eligible rows.
5. Candidate 31 moves into the visible window, so the main list still contains 30 candidates.

The same rule applies to **応募しない**. Favorites do not remove a candidate from recommendations. Applied and declined state is persisted separately from candidate stock.

## Refill behavior

A click on **応募済み** or **応募しない** does not spend a SerpApi request. Replacement first comes from the already-held 100-150 candidate stock. Scheduled acquisition replenishes the rolling pool separately.

When fewer than 30 eligible candidates exist, the UI shows all available candidates rather than inserting weaker candidates. When fewer than 100 eligible candidates exist, the feed remains in replenishment mode; quality thresholds are not relaxed to fill the target.

## Freshness and safety

- Unrediscovered reserve rows are limited to 14 days.
- Explicit AI-tool bans are rejected.
- Old client cache rows cannot bypass current server quality/presence/AI-policy stamps.
- Server and device stock are both bounded to 150 rows.

## Regression protection

`tests/test_postprocess.py` verifies the server pool caps at 150 even when more rows are supplied.

`tests/test_queue_contract.py` locks the client/server 150 -> 100 -> 30 contract and verifies that applied/declined filtering occurs before the visible-window slice, which is the property that makes the next queued candidate automatically move into the 30-row recommendation window.
