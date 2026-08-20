# Candidate queue contract

This document fixes the intended candidate-stock behavior as a product invariant.

## Capacity layers

- Server rolling pool hard limit: **150 candidates**.
- Pre-final official-source acquisition buffer: **120 candidates**.
- User-facing strict unapplied stock target after final quality vetoes: **100 candidates**.
- Initial recommendation window: **30 candidates**.
- Additional browsing expands in **30-candidate batches** only when the user explicitly asks to see more.

The 120-row acquisition buffer is deliberately deeper than the 100-row user target because LLM, continuous-presence and AI-use-policy vetoes run after acquisition. It is headroom for quality removal, not permission to publish weaker work.

The 150-row layer is also not permission to weaken quality. Every published row in the server pool must have survived the current remote, autonomy, presence, AI-use-policy, deterministic-quality, freshness and applicable LLM gates.

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

A click on **応募済み** or **応募しない** never spends a SerpApi request. Replacement first comes from already-held server/device stock. After the action, if the device has fewer than **60** unprocessed candidates, the PWA checks the latest published `jobs.json` with a no-store request. It does not dispatch GitHub Actions and does not hold any API key or GitHub credential.

The server separately refreshes audited free official sources every six hours. Those sources include documented employer ATS feeds and a small allowlisted set of live official AI-work provider pages. The free refill path uses **zero SerpApi requests**, reruns the final quality gates and validators, and aims for the 120-row pre-final buffer so that roughly 100 strict rows can remain after downstream vetoes.

The normal scheduled acquisition remains available for discovery outside those official sources and is independently governed by the monthly SerpApi pacing guard.

## Floor semantics

**30 is the operational visible floor, not a license to fabricate supply.** If at least 30 strict, live, unprocessed candidates exist in the server/device stock, the main recommendation view should display 30. User actions are removed before slicing, so queued rows replace them immediately.

If the real market plus current official sources contain fewer than 30 candidates that satisfy all strict gates, the UI must show the smaller truthful number rather than weakening the remote/automation/human-presence/AI-policy requirements. Such a state is considered a supply-health failure to be replenished, not a successful full queue.

When fewer than 100 strict candidates exist, the feed remains in replenishment mode. When fewer than 60 remain on the device, the client begins checking for a newer published feed early enough to preserve one full 30-row reserve batch behind the visible window.

## Freshness and safety

- Unrediscovered reserve rows are limited to 14 days.
- Recently reverified official ATS listings may use their live ATS verification timestamp for freshness.
- Direct official-provider pages are rechecked by the scheduled zero-SerpApi refill; a provider page that is closed, redirects away from the audited host, or explicitly requires the worker's voice/likeness/live participation is not admitted by that source path.
- Explicit AI-tool bans are rejected.
- Old client cache rows cannot bypass current server quality/presence/AI-policy stamps.
- Server and device stock are both bounded to 150 rows.

## Regression protection

`tests/test_postprocess.py` verifies the server pool caps at 150 even when more rows are supplied.

`tests/test_queue_contract.py` locks the client/server 150 -> 100 -> 30 contract and verifies that applied/declined filtering occurs before the visible-window slice, which makes the next queued candidate automatically move into the 30-row recommendation window.

`tests/test_action_refill_contract.py` locks the 60-row low-stock recheck behavior and verifies that the browser never calls authenticated/search endpoints.

`tests/test_pre_final_supply_buffer.py` locks the distinct 120 pre-final -> 100 post-final -> 30 visible stock layers.

`tests/test_official_ai_provider_supply.py` verifies that direct official-provider pages still enter through the normal production quality builder and rejects closed or physical/media-participation listings.
