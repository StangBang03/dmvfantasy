import json
from pathlib import Path
from collections import defaultdict, Counter

RAW = Path("data/raw")

def unwrap(data):
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return data if isinstance(data, dict) else {}

print("=" * 80)
print("ESPN DRAFT MEMBER ID DIAGNOSTIC")
print("=" * 80)

for year_dir in sorted(RAW.iterdir()):
    if not year_dir.is_dir() or not year_dir.name.isdigit():
        continue

    year = int(year_dir.name)
    draft_file = year_dir / "mDraftDetail.json"
    team_file = year_dir / "mTeam.json"

    if not draft_file.exists() or not team_file.exists():
        continue

    draft = unwrap(json.loads(draft_file.read_text(encoding="utf-8-sig")))
    teams = unwrap(json.loads(team_file.read_text(encoding="utf-8-sig")))

    picks = draft.get("draftDetail", {}).get("picks", [])
    team_rows = teams.get("teams", [])
    members = teams.get("members", [])

    owner_by_team = {}
    for team in team_rows:
        owners = team.get("owners") or []
        owner_by_team[team.get("id")] = owners[0] if owners else None

    member_ids = {m.get("id") for m in members if m.get("id")}

    # For each draft memberId, collect the team IDs it appears on.
    member_to_teams = defaultdict(set)
    member_to_pick_count = Counter()

    # Also check whether memberId is constant for the entire draft.
    for pick in picks:
        mid = pick.get("memberId")
        tid = pick.get("teamId")
        if mid:
            member_to_teams[mid].add(tid)
            member_to_pick_count[mid] += 1

    print(f"\nYEAR {year}")
    print(f"  Teams: {len(team_rows)} | Members: {len(members)} | Picks: {len(picks)}")
    print(f"  Unique draft memberIds: {len(member_to_teams)}")

    for mid, count in sorted(member_to_pick_count.items(), key=lambda x: (-x[1], str(x[0]))):
        teams_used = sorted(t for t in member_to_teams[mid] if t is not None)
        matches_owner = sum(
            1 for tid in teams_used
            if owner_by_team.get(tid) == mid
        )
        in_current_members = mid in member_ids

        print(
            f"    memberId={mid!r} | picks={count:3} | "
            f"teamIds={teams_used} | owner_matches={matches_owner}/{len(teams_used)} | "
            f"in_mTeam_members={in_current_members}"
        )

    # More useful diagnostic: for every team, what memberId appears on its picks?
    print("  Team -> draft memberId(s):")
    team_members = defaultdict(set)
    for pick in picks:
        if pick.get("teamId") is not None and pick.get("memberId"):
            team_members[pick["teamId"]].add(pick["memberId"])

    for tid in sorted(team_members):
        mids = sorted(team_members[tid])
        owner = owner_by_team.get(tid)
        print(f"    Team {tid}: owner={owner!r} | draft_memberIds={mids}")

print("\n" + "=" * 80)
print("Interpretation guide")
print("=" * 80)
print("1. If each draft has ONE memberId across all picks, memberId is not the picker/owner.")
print("2. If memberId changes with teamId, it may identify the drafter.")
print("3. If memberId matches team owners only in newer seasons, ESPN changed the field semantics.")
print("4. We will NOT normalize memberId to person_id until this diagnostic proves what it represents.")
