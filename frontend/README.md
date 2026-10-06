# FFL League History — Frontend v0.1

A zero-dependency static frontend built against the normalized FFL history datasets.

## Included

- Dashboard
- 2026 current standings
- Championship leaderboard
- Career owner leaderboard
- Owner profiles
- Season archive + season detail
- League records
- Draft history
- Matchup browser

## Data used

The frontend consumes these normalized JSON files:

- advanced_stats.json
- teams.json
- people.json
- matchups.json
- draft_picks.json
- standings.json
- seasons.json

The raw ESPN data is intentionally not included.

## Run locally

From this directory:

```powershell
python -m http.server 8000
```

Then browse to:

http://localhost:8000

## GitHub Pages

This version can be hosted directly as a static site. No npm install or build step is required.

## Next iteration

1. Wire the existing analytics JSON outputs directly into dedicated record/H2H views.
2. Add richer player metadata and player pages.
3. Add draft/player value analysis.
4. Add historical playoff brackets.
5. Add charts and interactive season comparisons.
6. Add the league's branding/logo and final visual system.
7. Eventually move to React/Vite if the app complexity warrants it.
