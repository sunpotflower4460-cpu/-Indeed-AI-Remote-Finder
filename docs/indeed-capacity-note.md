# Indeed discovery capacity

The public-index discovery keeps truth labels and promotion rules unchanged while increasing storage/search-page capacity:

- 100 Google results requested per discovery query
- up to 300 deduplicated Indeed job-key seeds retained
- seeds retained for up to 45 days so the rotating search-profile set can complete a cycle
- results remain sorted by latest `last_seen`, so fresher leads appear first
- no backend request is made directly to Indeed job pages
