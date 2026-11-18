# Owner identity privacy migration

## What changed

Public owner identifiers are now opaque canonical IDs (`person_001` through
`person_027`). ESPN SWIDs/member IDs are no longer included in the published
people, teams, draft-pick, standings, matchup, or owner analytics JSON.

The current-season refresh now requires a private `ESPN_OWNER_MAP_JSON`
GitHub Actions secret. It fails closed if the secret is absent, invalid, or
does not map every ESPN league member to a known canonical person. It no
longer invents person IDs from ESPN identifiers.

The old `scripts/normalize_espn.py` normalizer is intentionally disabled:
its output schema does not match the production datasets and it would
reintroduce public identifiers.

## One-time setup before merging

1. Update your local checkout to include this branch.
2. Generate the private mapping file locally:

   ```bash
   python scripts/export_owner_map.py --output espn-owner-map.json
   ```

3. Add it as an Actions environment secret for the `github-pages` environment:

   ```bash
   gh secret set ESPN_OWNER_MAP_JSON --env github-pages < espn-owner-map.json
   ```

4. Verify the secret exists in GitHub Settings → Environments → `github-pages`
   → Environment secrets. Do not reveal or paste the secret value anywhere.
5. Securely delete the local `espn-owner-map.json` file after the secret is set.
6. After this PR is merged, run **Actions → Validate Private Owner Map → Run workflow**.
   This is a non-mutating check: it reads the protected secret and public people
   file, does not contact ESPN, and does not write or deploy any data. Wait for
   its success before allowing the scheduled refresh to run.

The generated file is ignored by Git. Never commit it. The existing
`ESPN_S2` and `ESPN_SWID` secrets remain required for authenticated ESPN API
requests; this change does not rotate or replace them.

## Validation

The pull-request workflow compiles all Python scripts and runs
`scripts/validate_owner_identity.py`, which checks for exposed ESPN-derived
IDs, forbidden identity fields, and unresolved canonical owner references.

Do not merge until that check passes and the `ESPN_OWNER_MAP_JSON` environment
secret has been configured. The scheduled refresh will fail safely until the
secret is present.
