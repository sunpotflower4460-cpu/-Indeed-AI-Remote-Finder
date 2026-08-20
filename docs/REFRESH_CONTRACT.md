# Production refresh contract

The production feed is intentionally separated from pull-request validation.

## Triggers

`update-jobs.yml` can start from:

- the daily scheduled run;
- an explicit `workflow_dispatch`;
- a trusted `main` push touching production scripts or `update-jobs.yml`.

A merged pull request that changes candidate-pipeline scripts creates a normal
`main` push, so that push is the **single automatic post-merge refresh path**.
There is intentionally no second merged-PR dispatcher: running both paths was
proven in production to consume SerpApi requests twice for the same merge even
though the stale-feed commit guard correctly prevented the second run from
publishing over newer data.

Runs remain serialized by the `update-job-candidates` concurrency group. If main
moves while a refresh is generating data, that run must skip its stale feed
commit rather than rebase old-policy output onto newer code.

## Candidate quantity

- User-facing unapplied stock target: **100**.
- Server-side quality reserve target: **150**.
- The acquisition loop remains in top-up mode through 149 candidates and only enters low-cost steady mode at 150+.
- Applying to or declining a job removes it from the normal recommendation queue without deleting the user's action history.

Quantity is a supply objective, not a reason to weaken quality gates.

## Publication quality

A normal recommended candidate must still pass the production rules, including:

- explicit unconditional full-remote evidence in the listing itself;
- strict AI-automation and human-dependency thresholds;
- exclusion of hybrid/partial-office work;
- exclusion of direct synchronous human work such as calls, customer support, meetings and negotiation;
- full-listing screening for requirements that need the human applicant to remain physically present at the computer;
- final LLM vetoes where an audited listing shows too much human dependency or too little end-to-end automation.

Generic always-on software operation or automated real-time monitoring is not rejected merely because it runs continuously.

## Indeed supply measurement

The measured acquisition wrapper keeps the existing search budget while comparing ordinary anchor searches with a small set of Indeed-biased anchor variants. The public feed may contain aggregate counts for:

- jobs seen;
- jobs with apply options;
- jobs with a canonical Indeed application path;
- candidates surviving the deterministic publication gates;
- bounded apply/via source counts.

Telemetry never persists the SerpApi key, OpenAI key, raw account response, or apply-option URLs.

## Request-budget behavior

The hard monthly SerpApi cap remains authoritative. In addition, acquisition
paces the remaining allowance across the remaining UTC calendar days when extra
manual or code-change refreshes have pushed usage ahead of the normal once-daily
cadence. Pacing can only lower a run's request count; it never relaxes candidate
quality or increase the hard monthly cap.

## Failure behavior

A provider/acquisition failure must not erase a last-known-good feed or pretend old data is newly generated.

The refresh pipeline records a safe coarse acquisition outcome and SerpApi guard status. If acquisition fails, the previous valid jobs remain available and the feed records that the previous data was preserved. Detailed provider errors and secrets are not published.
