# DMV Fantasy Football — League History & Analytics

> A historical archive, analytics pipeline, and static website for the DMV Fantasy Football league.

This repository collects, normalizes, validates, analyzes, and publishes league history from ESPN Fantasy Football. It combines season-level league records, matchups, standings, draft history, transactions, player performance, owner identity history, and derived league analytics in one version-controlled project.

The project is designed to do two things well:

1. **Preserve the league's history.** Historical seasons should remain available even as the current season changes.
2. **Turn that history into useful league context.** The website presents the underlying records as dashboards, owner profiles, career summaries, league records, draft analysis, matchups, and rivalries.

The production site is a static frontend hosted with GitHub Pages. Python scripts collect and process data; GitHub Actions runs scheduled and manually dispatched jobs; the resulting JSON files are published alongside the frontend.

---

## Contents

- [Project at a glance](#project-at-a-glance)
- [What the site provides](#what-the-site-provides)
- [System architecture](#system-architecture)
- [Data lifecycle](#data-lifecycle)
- [Repository layout](#repository-layout)
- [Data sources and coverage](#data-sources-and-coverage)
- [Data model and important identifiers](#data-model-and-important-identifiers)
- [Processed data reference](#processed-data-reference)
- [Analytics data reference](#analytics-data-reference)
- [Collection and processing scripts](#collection-and-processing-scripts)
- [GitHub Actions workflows](#github-actions-workflows)
- [Scheduled current-season refresh](#scheduled-current-season-refresh)
- [Historical data workflows](#historical-data-workflows)
- [Owner identity and privacy](#owner-identity-and-privacy)
- [Analytics methodology and business rules](#analytics-methodology-and-business-rules)
- [Local development](#local-development)
- [Running the data pipeline manually](#running-the-data-pipeline-manually)
- [Validation and testing](#validation-and-testing)
- [Deployment](#deployment)
- [Secrets and configuration](#secrets-and-configuration)
- [Troubleshooting](#troubleshooting)
- [Operational guidance](#operational-guidance)
- [Known limitations and interpretation notes](#known-limitations-and-interpretation-notes)
- [Change management](#change-management)
- [Future work](#future-work)

---

## Project at a glance

| Area | Implementation |
|---|---|
| League platform | ESPN Fantasy Football |
| ESPN league ID | \`112536\` |
| Historical seasons | 2011–2025 |
| Current season | 2026 |
| Backend / data engineering | Python 3.12 |
| API client | \`requests\` |
| Local environment loading | \`python-dotenv\` |
| Published data format | JSON |
| Frontend | HTML, CSS, vanilla JavaScript |
| Frontend dependencies | None; no npm build is required |
| Automation | GitHub Actions |
| Hosting | GitHub Pages |
| Primary branch | \`main\` |

The repository is public. The published JSON is intended to contain league information and opaque canonical owner IDs, not ESPN authentication cookies or ESPN member identifiers.

## What the site provides

The frontend currently exposes these sections:

| Section | Purpose |
|---|---|
| Dashboard | High-level league overview and current-season context |
| Seasons | Browse the league by season |
| Owners | Browse owner profiles and season participation |
| Career | Compare career-level owner performance |
| Records | Explore league and owner records |
| Analytics | View derived league statistics |
| Draft | Explore draft history and draft analytics |
| Matchups | Browse historical matchups |
| Rivalries | Compare owners head-to-head |

The interface is a static single-page application. Navigation is handled in the browser, and the page loads its data from JSON files served from the same site.

The frontend currently reads these principal datasets:

- \`data/analytics/advanced_stats.json\`
- \`data/analytics/draft_analytics.json\`
- \`data/analytics/owner_records.json\`
- \`data/analytics/championships.json\`
- \`data/processed/teams.json\`
- \`data/processed/people.json\`
- \`data/processed/matchups.json\`
- \`data/processed/draft_picks.json\`
- \`data/processed/standings.json\`
- \`data/processed/seasons.json\`
- \`data/processed/transaction_events.json\`
- \`data/processed/historical_waiver_adds.json\`

The application has fallback paths for some earlier flat JSON layouts. The production deployment uses the \`data/processed/\` and \`data/analytics/\` directories.

## System architecture

At a high level, the project follows a data pipeline:

\`\`\`text
                   ESPN Fantasy Football
                 authenticated league API
                            |
                            v
                 Python collection scripts
                            |
                            v
                   Raw API responses
                  data/raw/ (local/CI)
                            |
                            v
                Normalization and builders
                            |
                            v
                  data/processed/*.json
                            |
                            v
                  Analytics / record engines
                            |
                            v
                  data/analytics/*.json
                            |
                            v
                 Static frontend (frontend/)
                            |
                            v
                 GitHub Pages deployment
\`\`\`

### Responsibilities by layer

**1. ESPN collection**

Collection scripts call ESPN's fantasy football league endpoints. Authenticated requests use the \`ESPN_S2\` and \`ESPN_SWID\` cookies. The collectors save responses locally under \`data/raw/\` so that the response can be inspected and processed without repeatedly calling ESPN.

**2. Normalization**

Normalization converts ESPN's response structures into stable project-owned records. The normalized model separates people, teams, seasons, matchups, standings, and draft picks. ESPN's older league-history endpoint can return a one-element list containing the league object, while newer endpoints return an object directly; collectors account for that response difference.

**3. Processing and reconciliation**

Specialized builders convert raw transaction and player data into event records, ownership histories, and player-performance datasets. Audit scripts inspect source coverage and flag anomalies.

**4. Analytics**

Analytics builders read the normalized data and write derived JSON files. The record engine is responsible for head-to-head records, streaks, league records, the current-season summary, and related record catalogs. Separate builders calculate advanced matchup statistics and draft analytics.

**5. Frontend**

The browser loads the generated JSON and renders the league-history experience. It does not call ESPN directly and does not need ESPN credentials.

**6. Deployment**

GitHub Actions assembles a deployable directory by copying the frontend files to the site root and copying the processed and analytics JSON into a \`data/\` directory. GitHub Pages hosts that assembled directory.

### Important design principle

The frontend is a presentation layer, not the source of truth. Data collection, identity reconciliation, and statistical calculations belong in the Python pipeline. The browser should consume prepared JSON rather than reconstructing historical league facts from ESPN.

## Data lifecycle

The normal current-season lifecycle is:

1. GitHub Actions checks out \`main\`.
2. Python 3.12 is installed.
3. The workflow installs \`requests\`.
4. \`scripts/refresh_current_season.py\` requests the current ESPN season.
5. The script validates the private ESPN-to-canonical-owner mapping before updating owner-linked records.
6. Current-season rows replace only rows for the configured current season in the normalized files. Earlier seasons are retained.
7. \`scripts/validate_owner_identity.py\` checks the public datasets.
8. Analytics are rebuilt.
9. Changed JSON files are committed to \`main\`.
10. The workflow assembles the static site, uploads a Pages artifact, and deploys it.

The refresh is intentionally designed to preserve historical seasons. It is not a full historical re-import.

### Data directories

- \`data/raw/\`: raw ESPN responses and local research data. This directory is ignored by Git and should not be committed.
- \`data/processed/\`: normalized league records and processed source data. These files are version-controlled and published.
- \`data/analytics/\`: derived analytics JSON. These files are version-controlled and published.
- \`artifacts/\`: temporary diagnostic output used by some scripts and workflows. It is not part of the public website unless explicitly copied by a deployment step.

Raw responses are valuable for auditability and reproducibility. Keep them private and local or in short-retention workflow artifacts; do not add raw ESPN responses to the public repository.

## Repository layout

The main branch is organized as follows:

\`\`\`text
dmvfantasy/
├── .github/
│   └── workflows/                 # GitHub Actions automation
├── data/
│   ├── analytics/                 # Published derived analytics JSON
│   └── processed/                 # Published normalized league JSON
├── docs/
│   └── owner-identity-migration.md # Owner identity privacy migration notes
├── frontend/
│   ├── app.js                     # Client-side application and rendering
│   ├── index.html                 # Application shell and navigation
│   ├── styles.css                 # Visual styling
│   └── README.md                  # Frontend-specific notes
├── scripts/
│   ├── refresh_current_season.py  # Current-season collection and normalization
│   ├── collect_*.py               # ESPN data collectors
│   ├── build_*.py                 # Processed data and analytics builders
│   ├── audit_*.py                 # Data quality and coverage audits
│   ├── validate_*.py              # Validation and privacy checks
│   ├── probe_*.py                 # ESPN endpoint research/probes
│   └── inspect_*.py               # Local inspection utilities
├── tests/
│   └── test_owner_identity.py     # Unit tests for identity mapping
├── .gitignore
└── README.md
\`\`\`

The exact script inventory changes as research and maintenance work evolves. The active production pipeline is identified separately below; the presence of a script in \`scripts/\` does not automatically mean that it is part of the scheduled refresh.

## Data sources and coverage

### ESPN Fantasy Football API

The primary source is ESPN's fantasy football league API:

\`\`\`text
https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl
\`\`\`

The project uses league ID \`112536\`.

The collectors use different endpoint forms depending on the age of the season:

- 2018 and later: \`/seasons/{year}/segments/0/leagues/{league_id}\`
- 2011–2017: \`/leagueHistory/{league_id}?seasonId={year}\`

The exact views vary by collection task. The current-season refresh requests \`mSettings\`, \`mTeam\`, \`mStandings\`, \`mMatchupScore\`, and \`mDraftDetail\`. Historical collectors also use views such as \`mRoster\` and \`mTransactions2\`; player-performance collection uses \`mBoxscore\`.

These are ESPN endpoints used by the project, not a stable public API contract. ESPN can change response shapes, authentication requirements, fields, or historical availability. A successful HTTP response does not by itself guarantee that the response contains complete or correctly interpreted data.

### Coverage matrix

| Data area | Current documented coverage | Source / method |
|---|---:|---|
| League seasons, teams, standings, matchups, draft | 2011–2026 | ESPN league views, normalized into processed JSON |
| Current season | 2026 | Weekly authenticated refresh |
| Transactions | 2011–2025 | ESPN \`mTransactions2\` by scoring period |
| Historical weekly player points | 2011–2017 | ESPN \`mBoxscore\` historical collection |
| Player roster/stat metadata | 2011–2026 | ESPN \`mRoster\` collection |
| Historical waiver-add totals | 2011–2017 | Final standings MOVES values supplied from owner screenshots |
| Derived analytics | Based on available processed data | Python analytics builders |

Coverage is not identical for every statistic. A dataset may contain a season while a particular player-level or transaction-level measure is unavailable for that season. Refer to the notes attached to the individual dataset before comparing values across eras.

## Data model and important identifiers

### Canonical people

A person is represented by an opaque canonical ID:

\`\`\`json
{
  "person_id": "person_001",
  "name": "Display Name"
}
\`\`\`

Canonical IDs are stable project identifiers. They are not ESPN member IDs, SWIDs, usernames, or authentication values.

The same person may have had multiple ESPN member identities over the history of the league. Those ESPN identities are reconciled privately and mapped to one canonical \`person_id\`. This allows career statistics to follow a person across team renames, account changes, and ESPN identity changes.

### Season-scoped teams

A team record is keyed by the combination of \`season\` and \`team_id\`. ESPN team IDs are reused across seasons, so \`team_id\` alone is not a globally unique identifier.

Common fields include:

- \`season\`
- \`team_id\`
- \`team_name\`
- \`abbrev\`
- \`person_id\`
- \`division_id\`
- \`draft_day\`
- \`draft_slot\`
- \`playoff_seed\`
- \`rank\`

A team name can change from one season to another. The canonical person ID is the key used to connect an owner's career across those seasons.

### Matchups

Matchup records contain season, matchup/scoring period identifiers, home and away team IDs, home and away canonical person IDs, scores, winner, and playoff tier metadata.

The combination of season and matchup identifiers provides context. Do not assume that a matchup-period ID or team ID is globally unique across all seasons.

### Draft picks

Draft-pick records include season, team, canonical owner, player ID, overall pick, round, pick within round, keeper status, and ESPN owning-team information where available.

### Dates and time periods

ESPN uses several related concepts: scoring period, matchup period, and transaction timestamps. They are not interchangeable. Scripts should preserve the original identifiers and use the season-specific schedule to interpret them.

## Processed data reference

Files in \`data/processed/\` are normalized or source-derived datasets. They are published with the website.

| File | Purpose |
|---|---|
| \`people.json\` | Canonical people directory. Uses opaque \`person_NNN\` identifiers. |
| \`seasons.json\` | Season inventory, league ID, season name, and source views collected. |
| \`teams.json\` | Season-scoped team history, owner references, names, seeds, and records. |
| \`matchups.json\` | Normalized matchup schedule and scoring results. |
| \`standings.json\` | Season standings and team-level results. |
| \`draft_picks.json\` | Normalized draft picks and keeper information. |
| \`transaction_events.json\` | Transaction items normalized into player/team ownership events. |
| \`supplemental_trade_events.json\` | Supplemental trade events recovered or verified through additional trade analysis. |
| \`ownership_ledger.json\` | Player ownership timeline built from draft ownership and transaction events. |
| \`ownership_ledger_issues.json\` | Issues identified while building the ownership ledger. |
| \`player_performance.json\` | Player-level season and weekly performance data. |
| \`player_performance_audit.json\` | Audit information associated with player-performance extraction. |
| \`player_performance_weekly_audit.json\` | Weekly player-performance coverage audit. |
| \`historical_waiver_adds.json\` | Historical aggregate waiver-add totals for 2011–2017, with source and classification metadata. |
| \`trade_audit.json\` | Trade reconciliation and audit output. |
| \`normalization_audit.json\` | Normalization audit output. |

Some datasets are consumed directly by the frontend; others support analysis, validation, or future features. A file being present in \`data/processed/\` does not necessarily mean the frontend currently displays every field in it.

## Analytics data reference

Files in \`data/analytics/\` are generated by analytics builders and are also published.

| File | Purpose |
|---|---|
| \`advanced_stats.json\` | Historical advanced matchup and owner statistics. |
| \`current_advanced_stats.json\` | Advanced statistics scoped to the current season. |
| \`current_season.json\` | Current-season standings and summary. |
| \`head_to_head.json\` | Career head-to-head owner comparisons. |
| \`streaks.json\` | Owner and league streak records. |
| \`league_records.json\` | Career and season record summaries. |
| \`league_record_catalog.json\` | Catalog of record categories and record entries. |
| \`owner_records.json\` | Owner-focused record summaries. |
| \`championships.json\` | Championship and podium history. |
| \`playoff_appearances.json\` | Owner playoff appearance summaries. |
| \`season_results.json\` | Season-level results and finishes. |
| \`career_stats.json\` | Career-level statistics. |
| \`season_stats.json\` | Season-level statistical summaries. |
| \`draft_analytics.json\` | Draft trends and owner draft profiles. |
| \`analytics_audit.json\` | Analytics validation/audit summary. |
| \`boxscore_reconciliation.json\` | Boxscore reconciliation and comparison output. |

The builders are the authority for the meaning and calculation of each field. When changing a formula, update the relevant builder and this documentation together.

## Collection and processing scripts

The scripts are grouped by responsibility. Some are active production components; others are one-off research, diagnostics, or earlier iterations retained to preserve useful work.

### Active production and primary data builders

| Script | Responsibility |
|---|---|
| \`refresh_current_season.py\` | Fetches the configured current season from ESPN, maps owners to canonical people, and replaces only that season's rows in normalized teams, matchups, standings, drafts, and season metadata. |
| \`collect_transactions.py\` | Collects historical transaction responses for 2011–2025 by scoring period. |
| \`build_transaction_events.py\` | Converts raw transaction responses into normalized transaction events and supplemental trade events. |
| \`collect_rosters.py\` | Collects ESPN roster views across 2011–2026 for player-performance processing. |
| \`collect_historical_weekly_stats.py\` | Collects historical weekly boxscore data for 2011–2017. |
| \`build_player_performance.py\` | Builds normalized player season/weekly performance records and audit output from collected roster data. |
| \`build_advanced_analytics.py\` | Builds historical and current-season advanced analytics from normalized matchups and teams. |
| \`build_records_engine_v3.py\` | Builds head-to-head, streak, league record, record catalog, and current-season analytics outputs. |
| \`build_draft_analytics.py\` | Builds draft analytics from normalized draft picks, people, and seasons. |
| \`build_ownership_ledger.py\` | Reconstructs player ownership over time using draft picks and transaction events. |

### Identity, validation, and audit scripts

| Script | Responsibility |
|---|---|
| \`owner_identity.py\` | Loads and validates the private ESPN identity-to-canonical-person mapping. |
| \`export_owner_map.py\` | Exports the private owner map from the preserved pre-migration source commit. The output must remain private. |
| \`validate_owner_identity.py\` | Scans published processed and analytics JSON for exposed ESPN identifiers, forbidden fields, duplicate canonical IDs, and unresolved person references. |
| \`validate_owner_map_secret.py\` | Validates the protected owner-map secret without contacting ESPN or writing data. |
| \`reconcile_identities.py\` | Analyzes historical ESPN owner identities and team associations to support manual identity reconciliation. |
| \`audit_owner_identity.py\` | Audits owner/member identity history from raw ESPN responses. |
| \`audit_espn.py\` | General ESPN data audit utility. |
| \`audit_weekly_performance.py\` | Audits weekly player-performance coverage. |
| \`audit_all_trades.py\` | Audits trade activity and attempts to reconcile trade history. |
| \`validate_boxscore_reconciliation.py\` | Validates boxscore reconciliation results. |

### Additional collectors and research utilities

| Script | Responsibility |
|---|---|
| \`collect_boxscores.py\` | Collects historical matchup boxscores; supports the older and newer ESPN endpoint patterns. |
| \`collect_historical_lineups_v2.py\` | Experimental historical lineup/boxscore collection. |
| \`analyze_transactions.py\` | Summarizes raw transaction types, statuses, and transaction items. |
| \`inspect_data.py\` | Builds an inventory of raw ESPN data and its contents. |
| \`inspect_missing_trades.py\` | Investigates missing or incomplete trade records. |
| \`inspect_playoff_metadata.py\` | Inspects playoff-related metadata. |
| \`inspect_playoffs.py\` | Prints season playoff structures and matchup details. |
| \`inspect_structure.py\` | Inspects ESPN response structure. |
| \`inspect_transaction_types.py\` | Inspects transaction type and item semantics. |
| \`diagnose_boxscore_parameters.py\` | Tests boxscore request parameters. |
| \`diagnose_draft_member_ids.py\` | Investigates owner/member identifiers in draft responses. |
| \`diagnose_historical_weekly_semantics.py\` | Investigates the meaning and structure of historical weekly scoring data. |
| \`diagnose_mroster_vs_boxscore.py\` | Compares roster and boxscore data sources. |
| \`probe_boxscore_structure.py\` | Probes boxscore response structure. |
| \`probe_boxscore_teams.py\` | Probes team information in boxscore responses. |
| \`probe_historical_player_stats.py\` | Tests historical player-stat availability. |
| \`probe_historical_weekly_views.py\` | Tests historical weekly endpoint views. |
| \`probe_mroster.py\` | Probes ESPN roster response behavior. |
| \`probe_player_stats_endpoint.py\` | Tests player-stat endpoint behavior. |
| \`probe_transactions.py\` | Tests transaction endpoint behavior. |
| \`check_boxscore_parent_total.py\` | Checks parent-level boxscore totals. |
| \`test_mboxscore_2018.py\` | Focused test of the 2018 mBoxscore endpoint. |
| \`test_mboxscore_years.py\` | Tests mBoxscore endpoint behavior across years. |

### Legacy analytics iterations

The repository also contains earlier analytics implementations:

- \`build_analytics.py\`
- \`build_fantasy_analytics.py\`
- \`build_fantasy_analytics_reconciled.py\`
- \`build_fantasy_analytics_standings_fixed2.py\`
- \`build_fantasy_analytics_validated.py\`
- \`build_fantasy_analytics_with_drafts.py\`
- \`build_fantasy_analytics_with_standings.py\`
- \`build_records_engine.py\`
- \`build_records_engine_v2.py\`

These files are retained for historical context and comparison. The current scheduled refresh explicitly invokes \`build_advanced_analytics.py\`, \`build_records_engine_v3.py\`, and \`build_draft_analytics.py\`. Do not substitute an older builder into production merely because its name looks similar. Before using or removing an older script, compare its inputs, output schema, and behavior with the active builder.

## GitHub Actions workflows

Workflow files live in \`.github/workflows/\`. Open the repository's **Actions** tab to view runs, logs, artifacts, and manual dispatch controls.

### Production and data workflows

| Workflow file | Trigger | Purpose |
|---|---|---|
| \`refresh-current-season.yml\` | Every Tuesday; manual dispatch | Refreshes the current season, validates owner identity, rebuilds analytics, commits changed data, and deploys Pages. |
| \`deploy.yml\` | Push to \`main\`; manual dispatch | Validates frontend JavaScript, assembles the site, and deploys Pages. |
| \`collect-historical-transactions.yml\` | Manual dispatch; selected script/workflow changes on \`main\` | Collects 2011–2025 transactions, builds normalized events, commits changed outputs, and deploys Pages. |
| \`collect-historical-weekly-stats.yml\` | Manual dispatch; selected collector/builder/workflow changes on \`main\` | Collects rosters and 2011–2017 weekly player stats, rebuilds player performance and analytics, commits changed data, and deploys Pages. |
| \`validate-owner-identity.yml\` | Pull requests; selected pushes to the identity migration branch; manual dispatch | Compiles the identity-related modules, runs unit tests, and validates public owner data. |
| \`validate-owner-map-secret.yml\` | Manual dispatch | Checks that the private owner map secret is valid. It does not contact ESPN or change data. |

### Audit and diagnostic workflows

| Workflow file | Trigger | Purpose |
|---|---|---|
| \`audit-current-player-performance.yml\` | Manual dispatch; selected changes on \`main\` | Audits weekly player-performance coverage and uploads an audit artifact. |
| \`diagnose-historical-weekly-semantics.yml\` | Manual dispatch; selected changes on \`main\` | Investigates historical weekly scoring semantics and uploads diagnostic output. |
| \`probe-historical-player-stats.yml\` | Manual dispatch; selected changes on \`main\` | Runs a historical player-stat audit and uploads results. |
| \`probe-historical-weekly-views.yml\` | Manual dispatch; selected changes on \`main\` | Probes historical weekly-stat views and uploads results. |
| \`probe-legacy-trades.yml\` | Manual dispatch; selected changes on \`main\` | Runs the trade-history audit/probe. |
| \`probe-player-stats-endpoint.yml\` | Manual dispatch; selected changes on \`main\` | Probes player weekly-stat endpoints and uploads results. |

### Workflow concurrency

The current-season refresh, Pages deployment, and historical data workflows share the concurrency group:

\`\`\`text
dmvfantasy-data-and-pages
\`\`\`

They use \`cancel-in-progress: false\` so a second run does not cancel an in-progress data/deployment operation. This serializes the main data-and-Pages workflows and reduces the risk of two jobs committing or deploying overlapping data at the same time.

Diagnostic workflows generally use their own concurrency groups and read-only repository permissions.

## Scheduled current-season refresh

The current-season workflow is \`.github/workflows/refresh-current-season.yml\`.

### Schedule

\`\`\`yaml
schedule:
  - cron: "30 12 * * 2"
\`\`\`

This is every Tuesday at 12:30 UTC:

- 7:30 AM Eastern during standard time.
- 8:30 AM Eastern during daylight time.

GitHub Actions cron schedules are defined in UTC. The local Eastern time therefore changes when daylight saving time begins or ends.

The workflow can also be run manually from:

**GitHub → Actions → Refresh Current FFL Season → Run workflow**

### Season selection

The workflow currently sets:

\`\`\`text
FFL_SEASON=2026
\`\`\`

The Python script defaults to 2026 if the environment variable is absent. When the league moves to a new season, update the workflow's environment value and review any season-specific assumptions in the collectors and analytics builders.

### What the refresh changes

The script fetches the current season's settings, teams, standings, matchups, and draft details. It then replaces rows for the configured year in:

- \`data/processed/seasons.json\`
- \`data/processed/teams.json\`
- \`data/processed/matchups.json\`
- \`data/processed/standings.json\`
- \`data/processed/draft_picks.json\`

It preserves records for all other seasons. The people directory is read to validate canonical owners; it is not regenerated from ESPN member IDs.

The script refuses to proceed if it cannot map every ESPN league member to a canonical person, if no teams are returned, or if matchup/standings data is missing. These checks are intended to prevent a partial or malformed ESPN response from replacing good production data.

### Analytics rebuilt after refresh

The workflow runs:

\`\`\`bash
python scripts/build_advanced_analytics.py
python scripts/build_records_engine_v3.py
python scripts/build_draft_analytics.py
\`\`\`

It then commits changes under \`data/processed/\` and \`data/analytics/\` if there are any.

The workflow performs its own Pages deployment. This is intentional: commits made using the repository's \`GITHUB_TOKEN\` do not automatically trigger a second \`push\` workflow. Deploying in the same workflow ensures the newly refreshed data is published.

A short wait step currently follows the Pages artifact upload to avoid a metadata-visibility race before deployment.

## Historical data workflows

### Transaction history

\`collect-historical-transactions.yml\` runs:

\`\`\`bash
python scripts/collect_transactions.py
python scripts/build_transaction_events.py
\`\`\`

The collector requests transaction data by scoring period for seasons 2011–2025. The builder normalizes transaction items and writes:

- \`data/processed/transaction_events.json\`
- \`data/processed/supplemental_trade_events.json\`

The workflow commits changed outputs, preserves raw transaction responses as a 90-day workflow artifact when available, assembles the site, and deploys it.

### Historical weekly player performance

\`collect-historical-weekly-stats.yml\` runs:

\`\`\`bash
python scripts/collect_rosters.py
python scripts/collect_historical_weekly_stats.py
python scripts/build_player_performance.py
python scripts/build_advanced_analytics.py
python scripts/build_records_engine_v3.py
python scripts/build_draft_analytics.py
\`\`\`

The weekly historical boxscore collector currently targets seasons 2011–2017 and scoring periods 1–17. The roster collector targets 2011–2026. The workflow rebuilds the player-performance data and the analytics outputs, commits changes, and deploys the site.

This workflow is broader than a simple current-season refresh. Run it when intentionally updating historical player-performance coverage, not as a routine substitute for the Tuesday refresh.

## Owner identity and privacy

Owner identity is one of the most important data-integrity and privacy decisions in this project.

### Why canonical IDs exist

ESPN member IDs can change when a person changes accounts or when ESPN identity metadata changes. If career statistics were keyed directly to ESPN identifiers, a single person could appear as multiple owners.

The public data therefore uses stable opaque identifiers such as:

- \`person_001\`
- \`person_002\`
- \`person_003\`

The human-readable name is stored separately in \`people.json\`.

### Private owner mapping

The mapping from ESPN member IDs/SWIDs to canonical person IDs is held in the protected GitHub Actions environment secret:

\`\`\`text
ESPN_OWNER_MAP_JSON
\`\`\`

The current-season refresh requires this mapping. It fails closed if the secret is absent, invalid, or does not map the current ESPN league members to known canonical people.

The mapping must never be committed to Git, placed in a public issue or pull request, or pasted into a public chat or log.

### Required GitHub environment secrets

The \`github-pages\` environment is expected to contain:

| Secret | Purpose |
|---|---|
| \`ESPN_S2\` | ESPN authenticated session cookie |
| \`ESPN_SWID\` | ESPN authenticated user/session identifier cookie |
| \`ESPN_OWNER_MAP_JSON\` | Private JSON map from ESPN identity aliases to canonical \`person_NNN\` IDs |

The first two secrets authenticate ESPN API requests. The third maps ESPN identities to the project's public owner model. They are separate concerns.

### Validating the mapping

The mapping can be validated without contacting ESPN:

\`\`\`bash
python scripts/validate_owner_map_secret.py
\`\`\`

In GitHub Actions, use **Validate Private Owner Map → Run workflow**. This workflow reads the protected secret and the public people directory. It does not write data or deploy the site.

### Validating public data

Run:

\`\`\`bash
python scripts/validate_owner_identity.py
\`\`\`

This checks the JSON files under \`data/processed/\` and \`data/analytics/\` for:

- Duplicate canonical person IDs.
- IDs that do not match the \`person_NNN\` format.
- Forbidden ESPN identity fields.
- ESPN-derived identifiers in public data.
- References to canonical people that do not exist in \`people.json\`.

The privacy migration details and one-time owner-map setup are documented in [docs/owner-identity-migration.md](docs/owner-identity-migration.md).

### Retired normalizer

\`scripts/normalize_espn.py\` is intentionally disabled. Its legacy output schema does not match the production datasets and could reintroduce ESPN identifiers into public JSON. Do not remove the safety guard or use that script to regenerate production data.

## Analytics methodology and business rules

Analytics are only useful when the underlying rules are explicit and consistent. The following rules are important when interpreting or changing the data.

### Canonical owner attribution

Career-level statistics are grouped by canonical \`person_id\`, not by team name or ESPN member ID. Team IDs are interpreted within a season because ESPN can reuse team IDs between seasons.

### Completed matchups

The advanced analytics and records engines exclude matchups without both teams and usable scores. Future or unplayed rows represented as 0–0 with no decided winner are not treated as completed games. Historical playoff bye rows without two teams are also excluded from played-game calculations.

### Winner and tie handling

Where ESPN supplies a winner, the normalized winner is treated as authoritative. When ESPN does not supply a winner and the scores are equal, the game is treated as a tie. The records engine includes a defensive score comparison when the winner is absent and the scores are not tied.

Do not casually replace this logic with a simple greater-than comparison; historical tiebreaker behavior and ESPN winner fields matter.

### Transaction events

A transaction response can contain multiple items. The normalized event builder preserves transaction-level and item-level ordering, transaction type/status, player, source team, destination team, and available timestamps.

For event chronology, the builder prefers ESPN's \`processDate\`; when that is absent it can use \`proposedDate\`. The event records retain which timestamp source was used. ESPN values \`-1\` and \`0\` for team IDs can represent no actual fantasy team (for example, free agent/no destination) and are normalized to null team references in the ownership-event model.

Trade workflows can involve related transaction records. Supplemental trade events exist to capture trade legs that are not represented cleanly in a single transaction response. Do not count every trade workflow row as a separate completed trade without checking status and related transaction information.

### Ownership ledger

The ownership ledger starts with draft ownership and then applies transaction events in chronological order. The builder uses season, scoring period, effective date, transaction index, and item index to establish a stable sequence. The resulting ledger is an analytical reconstruction, not an independent ESPN source of truth; inspect \`ownership_ledger_issues.json\` when investigating anomalies.

### Historical waiver adds: 2011–2017

The historical waiver-add dataset for 2011–2017 is based on the ESPN Final Standings **MOVES** column captured in owner-provided screenshots. Per the league's chosen interpretation, MOVES is treated as waiver adds for those seasons.

Important qualifications:

- These are season-level aggregate totals.
- They are not transaction-by-transaction counts reconstructed from the ESPN transaction endpoint.
- Each row records source and classification metadata.
- The classification is explicitly marked \`waiver_adds_assumed_from_moves\`.

Do not describe these values as verified transaction-level waiver claims. The methodology is an agreed historical interpretation of the standings MOVES figure.

### Historical weekly player performance

The historical weekly player-performance collector currently targets 2011–2017 and uses ESPN's historical \`mBoxscore\` endpoint. The player-performance builder also uses roster data and ESPN stat metadata to distinguish actual season totals from weekly scoring-period records.

Coverage and meaning can vary by season and endpoint response. Use the audit files and diagnostic workflows when a player or week appears to be missing. Do not assume a missing record means the player scored zero.

### Draft analytics

Draft analytics use completed historical seasons (seasons before the current season listed in \`seasons.json\`). The current season is excluded from historical career draft profiles until it is no longer the active season.

## Local development

### Prerequisites

- Git
- Python 3.12
- Internet access for ESPN collection tasks
- ESPN session credentials for authenticated collection
- A modern browser for frontend testing

The frontend itself is plain HTML, CSS, and JavaScript. It does not require Node.js or an npm package installation. Node.js is used in CI for the JavaScript syntax check.

### Clone the repository

\`\`\`bash
git clone https://github.com/StangBang03/dmvfantasy.git
cd dmvfantasy
\`\`\`

### Create a virtual environment

Windows PowerShell:

\`\`\`powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests python-dotenv
\`\`\`

macOS / Linux:

\`\`\`bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests python-dotenv
\`\`\`

### Configure local credentials

Create a local \`.env\` file in the repository root for scripts that use \`python-dotenv\`:

\`\`\`dotenv
ESPN_S2=your_private_espn_s2_cookie
ESPN_SWID=your_private_espn_swid_cookie
\`\`\`

Do not commit this file. It is excluded by \`.gitignore\`.

The private owner map is needed by the current-season refresh. For local execution, provide \`ESPN_OWNER_MAP_JSON\` as an environment variable containing the private JSON mapping. Do not put the map in a tracked file.

PowerShell example (set the value in the current session from a secure local source):

\`\`\`powershell
$env:ESPN_OWNER_MAP_JSON = Get-Content -Raw .\\espn-owner-map.json
\`\`\`

Keep \`espn-owner-map.json\` outside version control and remove the local copy securely after use if it is no longer needed.

### Preview the website locally

The deployment assembles the site root by combining the contents of \`frontend/\` with the \`data/\` directories. To reproduce that layout locally, create a temporary preview directory.

PowerShell:

\`\`\`powershell
$site = Join-Path $PWD "_site"
New-Item -ItemType Directory -Force "$site\\data\\analytics" | Out-Null
New-Item -ItemType Directory -Force "$site\\data\\processed" | Out-Null
Copy-Item "frontend\\*" $site -Recurse -Force
Copy-Item "data\\analytics\\*" "$site\\data\\analytics" -Recurse -Force
Copy-Item "data\\processed\\*" "$site\\data\\processed" -Recurse -Force
python -m http.server 8000 --directory $site
\`\`\`

Then open:

\`\`\`text
http://localhost:8000
\`\`\`

Serving the assembled directory is important because the frontend fetches JSON from relative \`data/...\` paths. Serving \`frontend/\` by itself will not include the sibling data directories in the expected location.

To stop the local server, press Ctrl+C in the terminal.

## Running the data pipeline manually

Run collection and processing steps intentionally. Some scripts overwrite generated JSON files.

### Refresh the current season locally

After configuring \`ESPN_S2\`, \`ESPN_SWID\`, and \`ESPN_OWNER_MAP_JSON\`:

\`\`\`bash
python scripts/refresh_current_season.py
python scripts/validate_owner_identity.py
python scripts/build_advanced_analytics.py
python scripts/build_records_engine_v3.py
python scripts/build_draft_analytics.py
\`\`\`

The current-season script uses \`FFL_SEASON\` if supplied; otherwise it defaults to 2026. It updates only the selected season's rows in the normalized season, team, matchup, standings, and draft files. Review the resulting Git diff before committing.

### Rebuild analytics from existing processed data

If the processed data is already correct and only analytics need to be regenerated:

\`\`\`bash
python scripts/build_advanced_analytics.py
python scripts/build_records_engine_v3.py
python scripts/build_draft_analytics.py
\`\`\`

These builders write to \`data/analytics/\`. Review the generated JSON and Git diff before publishing.

### Collect and rebuild transaction history

\`\`\`bash
python scripts/collect_transactions.py
python scripts/build_transaction_events.py
\`\`\`

The collector requires ESPN credentials and writes raw responses under the ignored \`data/raw/transactions/\` directory. The builder reads those raw files and writes processed event datasets.

### Collect historical weekly player performance

\`\`\`bash
python scripts/collect_rosters.py
python scripts/collect_historical_weekly_stats.py
python scripts/build_player_performance.py
\`\`\`

This is a historical collection task and can take substantially longer than a current-season refresh. The collector makes repeated requests across seasons and scoring periods. Review its reported failures and the audit outputs before treating the resulting dataset as complete.

### Build the ownership ledger

\`\`\`bash
python scripts/build_ownership_ledger.py
\`\`\`

This requires \`data/processed/draft_picks.json\` and \`data/processed/transaction_events.json\`. Inspect both the ledger and \`ownership_ledger_issues.json\` after running it.

## Validation and testing

Run these checks before merging changes that affect data or identity:

### Owner identity unit tests

\`\`\`bash
python -m unittest discover -s tests -v
\`\`\`

### Public identity and reference validation

\`\`\`bash
python scripts/validate_owner_identity.py
\`\`\`

### Private owner-map validation

\`\`\`bash
python scripts/validate_owner_map_secret.py
\`\`\`

This requires \`ESPN_OWNER_MAP_JSON\` in the environment.

### Frontend JavaScript syntax

If Node.js is installed:

\`\`\`bash
node --check frontend/app.js
\`\`\`

### Review generated data

Before committing regenerated data:

1. Check that the expected files changed.
2. Confirm that historical seasons remain present.
3. Confirm that the current season has the expected number of teams and schedule rows.
4. Check that owner references resolve to canonical people.
5. Review audit files and diagnostic output.
6. Search the diff for private ESPN identifiers or raw API response fragments.
7. Confirm the frontend still loads the expected JSON paths.

A successful script exit is necessary but not sufficient. It confirms that the code completed, not that every source response was complete or that a historical interpretation is correct.

## Deployment

### Standard deployment

The \`deploy.yml\` workflow runs on pushes to \`main\` and can be manually dispatched. It:

1. Checks out the repository.
2. Runs \`node --check frontend/app.js\`.
3. Configures GitHub Pages.
4. Creates \`_site/\`.
5. Copies \`frontend/.\` into the site root.
6. Copies \`data/analytics/.\` and \`data/processed/.\` into \`_site/data/\`.
7. Uploads the Pages artifact.
8. Deploys the artifact to GitHub Pages.

The deployment does not run Python analytics builders. It publishes the data files that are already committed.

### Deployment after a scheduled refresh

The current-season workflow performs its own deployment after rebuilding and committing data. This avoids relying on a second push-triggered workflow after a commit made by the GitHub Actions token.

### Verify a deployment

After a workflow completes:

- Confirm the job reached the Deploy step successfully.
- Open the Pages URL shown in the workflow environment/deployment output.
- Hard-refresh the site if the browser appears to show cached assets.
- Check the current-season standings and at least one historical page.
- If data appears stale, inspect the commit created by the workflow and confirm that the expected JSON files were included.

## Secrets and configuration

### GitHub Actions environment

The production data workflows use the \`github-pages\` environment. Configure the following environment secrets there:

- \`ESPN_S2\`
- \`ESPN_SWID\`
- \`ESPN_OWNER_MAP_JSON\`

Do not use plaintext values in workflow YAML. Reference secrets through GitHub's \`secrets\` context.

### Local environment

Local scripts that call \`load_dotenv()\` read values from a root-level \`.env\` file. The current-season refresh reads environment variables directly; a local shell can export them before running the script.

### Files that must remain private

Never commit:

- \`.env\` or \`.env.*\` files containing credentials.
- ESPN \`espn_s2\` or \`SWID\` cookie values.
- The private ESPN owner map.
- Raw ESPN responses that contain member IDs, SWIDs, or other private identity data.
- Identity audit/reconciliation files containing raw ESPN identifiers.

The \`.gitignore\` includes protections for common local secret and raw-data paths. A Git ignore rule is not a substitute for checking the staged diff before committing.

If a credential is accidentally committed, removing it in a later commit is not sufficient. Revoke or rotate the exposed credential and follow the repository's incident/remediation process.

## Troubleshooting

### The current-season workflow fails before collection

Check that the \`github-pages\` environment contains \`ESPN_S2\`, \`ESPN_SWID\`, and \`ESPN_OWNER_MAP_JSON\`. Verify that the secret values are current and that the owner map contains every active ESPN member identity.

### ESPN returns an authentication error

The ESPN session cookies may have expired or been rotated. Refresh the credentials using the account's normal secure process and update the GitHub environment secrets. Never paste cookie values into workflow logs, issues, or chat.

### The workflow says an owner is missing from the private map

The ESPN member identity is not mapped to a known canonical \`person_id\`. Review the private identity reconciliation process, update \`ESPN_OWNER_MAP_JSON\`, run **Validate Private Owner Map**, and then retry the current-season refresh.

Do not solve this by generating a new public person ID automatically. A new canonical identity should only be added after confirming that the ESPN identity represents a distinct person.

### The site loads but shows a loading screen or missing data

- Confirm the deployment completed.
- Confirm the deployed site contains \`data/processed/\` and \`data/analytics/\`.
- Check browser developer tools for failed JSON requests.
- Confirm JSON files parse correctly.
- Check that the frontend fetch paths match the deployed directory layout.
- Hard-refresh to bypass cached JavaScript or CSS.

### The Pages deployment reports that no artifact named \`github-pages\` exists

The data-refresh workflow uploads a Pages artifact and then deploys it in the same job. A short wait is present between artifact upload and deployment to reduce the chance of the deployment API checking for the artifact before its metadata is visible. If the issue recurs, inspect the upload step and artifact metadata in the same run before changing the workflow.

### Historical data is missing for a player or week

Do not assume that missing data means zero points. Check:

- Whether the season is in the collector's configured range.
- Whether the scoring period was requested.
- Whether ESPN returned a usable \`mBoxscore\` response.
- Whether the roster data contains the player.
- Whether the player-performance audit reports a coverage gap.
- Whether the endpoint's response shape changed for that season.

Use the historical weekly probe and diagnostic workflows to investigate source behavior.

### A trade or ownership history looks wrong

Review the raw transaction response locally, then inspect:

- Transaction status and type.
- Transaction item list.
- \`processDate\` and \`proposedDate\`.
- Related transaction IDs for multi-step trade workflows.
- Source and destination team IDs.
- \`transaction_events.json\`.
- \`supplemental_trade_events.json\`.
- \`ownership_ledger_issues.json\`.

Avoid manually editing a derived ledger row without fixing the source or builder logic. Otherwise, the next rebuild can overwrite the manual correction.

### A historical owner appears as two people

Check \`people.json\`, the private owner map, and the identity reconciliation audit. Confirm whether the ESPN identities belong to the same human before changing the mapping. Because career records use canonical IDs, a mapping correction can change many downstream analytics.

## Operational guidance

### Before changing a collector

- Identify which raw ESPN view it requests.
- Check whether the endpoint uses the legacy or modern season URL.
- Preserve raw responses locally for comparison.
- Check how the script handles list-wrapped legacy responses.
- Confirm request timeouts, retries, and pacing.
- Confirm that private identifiers do not flow into public outputs.

### Before changing a builder

- Identify its input files and output files.
- Determine whether it is part of an active workflow.
- Review the existing output schema before changing field names.
- Preserve season scoping for team IDs.
- Keep canonical person references intact.
- Add or update validation when a new reference field is introduced.
- Run the builder and inspect the full Git diff.

### Before changing frontend code

- Keep the frontend independent of ESPN credentials.
- Use the published JSON files as its data source.
- Test using the assembled \`_site/\` layout.
- Run \`node --check frontend/app.js\`.
- Confirm that all routes still render when optional analytics data is unavailable.
- Test at desktop and mobile widths.

### Before changing a workflow

- Check its trigger paths. A push to \`main\` that changes a watched collector or workflow can start a historical collection job.
- Check its permissions. Use read-only permissions for audits and diagnostics where possible.
- Preserve the shared concurrency group for data/deployment workflows unless there is a deliberate reason to change it.
- Avoid overlapping jobs that commit to the same JSON files.
- Confirm whether the workflow commits data and whether it deploys Pages itself.

### Data changes should be reproducible

Whenever possible, change the collector or builder that produces a dataset rather than hand-editing generated JSON. If a manual historical correction is necessary, document its source and rationale in the dataset or a dedicated methodology note so the correction is not lost or misunderstood later.

## Known limitations and interpretation notes

1. **ESPN API stability:** The project uses ESPN endpoints that may change without notice. Response shape and historical availability can vary by season.
2. **Historical weekly player stats:** The current dedicated weekly collection targets 2011–2017. Do not assume identical coverage across all seasons.
3. **Historical waiver adds:** The 2011–2017 totals are interpreted from the Final Standings MOVES column and owner-provided screenshots. They are aggregate totals, not transaction-level event counts.
4. **Transaction history:** The current historical transaction collector covers 2011–2025. The current season is handled separately and transaction collection should not be assumed to include 2026 unless the collector range is intentionally updated.
5. **Owner mapping:** The current-season refresh depends on a correctly maintained private identity map. This is deliberate; the pipeline should stop rather than guess owner identity.
6. **Derived data:** Analytics and ownership ledgers are calculated outputs. They should be rebuilt from source/processed data after logic changes.
7. **Historical scripts:** The repository contains exploratory scripts and earlier builder versions. Only the workflows listed as production workflows should be treated as the current automated path.
8. **Frontend data scope:** Some processed datasets exist for analysis or future development and may not yet be displayed in the website.
9. **Local preview:** The frontend must be served with the processed and analytics data in the expected relative paths. Opening \`index.html\` directly or serving only the \`frontend/\` folder will not reproduce the deployed layout.

## Change management

The primary production branch is \`main\`.

Recommended change process:

1. Create a focused feature branch.
2. Make the smallest logical change.
3. Update this README or a relevant document when behavior, data schemas, or operational steps change.
4. Run the relevant unit tests and validation scripts.
5. Run affected builders against known inputs.
6. Review generated JSON changes and confirm no private data is staged.
7. Open a pull request and inspect workflow results.
8. Merge only after validating the output and the deployment.

### What should be documented when adding a dataset

For each new dataset, record:

- Its source endpoint or manual source.
- Its season coverage.
- Whether it is raw, normalized, derived, or manually curated.
- Its schema and primary keys.
- The script that creates it.
- The workflow that runs that script, if any.
- Whether it is published to the website.
- Known gaps, assumptions, and validation checks.

### What should be documented when changing a statistic

Record:

- The exact calculation.
- The included and excluded records.
- Tie, bye, playoff, and incomplete-game behavior.
- The source fields used.
- The seasons for which the calculation is valid.
- Any known historical exceptions.

## Future work

Potential future improvements include:

- Continue auditing historical player-performance completeness.
- Expand player-level views and player value analysis.
- Improve historical playoff bracket presentation.
- Add richer season comparisons and visual analytics.
- Further document and test trade reconstruction edge cases.
- Consolidate or clearly archive superseded analytics builders after their behavior has been reviewed.
- Add automated schema checks for all published JSON datasets.
- Add broader regression tests for analytics calculations and historical edge cases.
- Add a documented release/checklist process for the transition to each new fantasy season.

These are improvement areas, not claims that the features are already implemented.

---

## Quick reference

| Task | Command / location |
|---|---|
| Run owner identity tests | \`python -m unittest discover -s tests -v\` |
| Validate published owner data | \`python scripts/validate_owner_identity.py\` |
| Validate private owner map | \`python scripts/validate_owner_map_secret.py\` |
| Check frontend JavaScript | \`node --check frontend/app.js\` |
| Refresh current season | \`python scripts/refresh_current_season.py\` |
| Rebuild advanced analytics | \`python scripts/build_advanced_analytics.py\` |
| Rebuild league records | \`python scripts/build_records_engine_v3.py\` |
| Rebuild draft analytics | \`python scripts/build_draft_analytics.py\` |
| Collect transactions | \`python scripts/collect_transactions.py\` |
| Build transaction events | \`python scripts/build_transaction_events.py\` |
| Build ownership ledger | \`python scripts/build_ownership_ledger.py\` |
| Run production refresh | GitHub → Actions → Refresh Current FFL Season |
| Deploy site | GitHub → Actions → Deploy FFL Site |

---

*This README describes the repository's current implementation and operational behavior. Update it whenever the data model, active builders, workflow triggers, secrets, or deployment process changes.*
