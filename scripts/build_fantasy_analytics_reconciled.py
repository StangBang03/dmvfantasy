import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
ANALYTICS = ROOT / "data" / "analytics"
ALIASES = ROOT / "data" / "identity_aliases.json"

START_YEAR = 2011
END_YEAR = 2026


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    # ESPN returned a one-item list wrapper in many older seasons.
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]
    return data if isinstance(data, dict) else {}


def raw_view(year, view):
    return unwrap(load_json(RAW / str(year) / f"{view}.json"))


def team_id_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def build_person_map():
    """
    Returns:
      - ESPN owner ID -> internal person_id
      - internal person_id -> canonical person record

    Confirmed manual aliases take precedence. Other ESPN identities are
    initially treated as distinct people, but their display names are
    populated from ESPN's member data for usability.
    """
    aliases = load_json(ALIASES) if ALIASES.exists() else {"people": {}}

    espn_to_person = {}
    people = {}

    for person_id, person in aliases.get("people", {}).items():
        people[person_id] = {
            "person_id": person_id,
            "name": person.get("name"),
            "espn_ids": list(person.get("espn_ids", [])),
            "notes": person.get("notes"),
        }
        for espn_id in person.get("espn_ids", []):
            espn_to_person[espn_id] = person_id

    return espn_to_person, people


def season_teams(year, espn_to_person, people):
    data = raw_view(year, "mTeam")
    teams = data.get("teams", [])
    members = data.get("members", [])

    member_by_id = {
        m.get("id"): m
        for m in members
        if m.get("id")
    }

    result = []

    for t in teams:
        team_id = team_id_int(t.get("id"))
        owners = t.get("owners") or []
        owner_id = owners[0] if owners else None

        person_id = None

        if owner_id:
            person_id = espn_to_person.get(owner_id)

            if not person_id:
                # No manual alias exists: preserve this ESPN identity as its
                # own person until the league owner explicitly confirms a merge.
                person_id = (
                    "espn_" + owner_id.strip("{}").replace("-", "").lower()
                )
                espn_to_person[owner_id] = person_id

                member = member_by_id.get(owner_id, {})
                first = (member.get("firstName") or "").strip()
                last = (member.get("lastName") or "").strip()
                display = " ".join(x for x in [first, last] if x).strip() or None
                if not display:
                    display = member.get("displayName") or member.get("username")

                people[person_id] = {
                    "person_id": person_id,
                    "name": display,
                    "espn_ids": [owner_id],
                    "notes": (
                        "Generated from ESPN owner ID; no manual alias merge."
                    ),
                }
            else:
                # Make sure the manually confirmed alias has every ESPN ID
                # encountered in the raw data, without changing its identity.
                if owner_id not in people[person_id]["espn_ids"]:
                    people[person_id]["espn_ids"].append(owner_id)

        result.append(
            {
                "season": year,
                "team_id": team_id,
                "team_name": t.get("name"),
                "abbrev": t.get("abbrev"),
                "espn_owner_id": owner_id,
                "person_id": person_id,
                "division_id": t.get("divisionId"),
                "draft_day": t.get("draftDay"),
                "draft_slot": (
                    t.get("draftDay", {}).get("draftOrder")
                    if isinstance(t.get("draftDay"), dict)
                    else None
                ),
                "playoff_seed": t.get("playoffSeed"),
                "rank": t.get("rank"),
            }
        )

    return result



def extract_standings(year, team_lookup):
    """
    Normalize season standings by combining ESPN's two relevant views.

    mTeam contains the team's overall record and points totals.
    mStandings contains standings/playoff metadata such as playoffSeed
    and rankCalculatedFinal/rankFinal.

    This is intentional: ESPN does not expose all of these fields on the
    same object in the historical mStandings responses.
    """
    team_view = raw_view(year, "mTeam")
    standings_view = raw_view(year, "mStandings")

    raw_teams = team_view.get("teams") or []
    standing_teams = standings_view.get("teams") or []

    standing_by_id = {
        team_id_int(t.get("id")): t
        for t in standing_teams
        if t.get("id") is not None
    }

    out = []

    for raw_team in raw_teams:
        team_id = team_id_int(raw_team.get("id"))
        team = team_lookup.get(team_id, {})
        standing = standing_by_id.get(team_id, {})

        record = raw_team.get("record") or {}
        overall = record.get("overall") or {}

        # ESPN's final-rank fields vary by season/state. Preserve both
        # calculated and final values rather than silently choosing one.
        rank = standing.get("rank")
        if rank is None:
            rank = raw_team.get("rank")

        final_standing = standing.get("rankCalculatedFinal")
        if final_standing is None:
            final_standing = standing.get("rankFinal")

        out.append(
            {
                "season": year,
                "team_id": team_id,
                "person_id": team.get("person_id"),
                "wins": overall.get("wins"),
                "losses": overall.get("losses"),
                "ties": overall.get("ties"),
                "points_for": overall.get("pointsFor"),
                "points_against": overall.get("pointsAgainst"),
                "rank": rank,
                "playoff_seed": standing.get("playoffSeed"),
                "final_standing": final_standing,
            }
        )

    return out


def validate_standings(standings, teams):
    """Validate standings coverage and team/person relationships."""
    teams_by_year = {}
    for t in teams:
        teams_by_year.setdefault(t["season"], set()).add(t["team_id"])

    standings_by_year = {}
    errors = []

    for s in standings:
        standings_by_year.setdefault(s["season"], []).append(s)

    for year, expected_team_ids in sorted(teams_by_year.items()):
        rows = standings_by_year.get(year, [])
        actual_team_ids = [r["team_id"] for r in rows]

        if len(rows) != len(expected_team_ids):
            errors.append(
                f"{year}: expected {len(expected_team_ids)} standings rows, "
                f"found {len(rows)}"
            )

        if len(actual_team_ids) != len(set(actual_team_ids)):
            errors.append(f"{year}: duplicate team_id values in standings")

        missing = expected_team_ids - set(actual_team_ids)
        if missing:
            errors.append(
                f"{year}: missing standings for team_id(s): "
                + ", ".join(str(x) for x in sorted(missing))
            )

        unknown = set(actual_team_ids) - expected_team_ids
        if unknown:
            errors.append(
                f"{year}: standings contain unknown team_id(s): "
                + ", ".join(str(x) for x in sorted(unknown))
            )

        unresolved = [r for r in rows if r["person_id"] is None]
        if unresolved:
            errors.append(
                f"{year}: {len(unresolved)} standings rows have no person_id"
            )

    return errors


def extract_draft_picks(year, team_lookup):
    """
    Normalize ESPN draft picks.

    IMPORTANT:
      - teamId is authoritative for which fantasy team received the pick.
      - memberId is preserved only as raw ESPN traceability.
      - Do not infer ownership from memberId; older ESPN seasons contain
        generic/shared member IDs that do not correspond to team owners.
    """
    data = raw_view(year, "mDraftDetail")
    draft_detail = data.get("draftDetail") or {}
    picks = draft_detail.get("picks") or []

    out = []

    for p in picks:
        team_id = team_id_int(p.get("teamId")) if p.get("teamId") is not None else None
        team = team_lookup.get(team_id, {})

        out.append(
            {
                "season": year,
                "team_id": team_id,
                "person_id": team.get("person_id"),
                "player_id": p.get("playerId"),
                "overall_pick": p.get("overallPickNumber"),
                "round": p.get("roundId"),
                "round_pick": p.get("roundPickNumber"),
                "keeper": bool(p.get("keeper", False)),
                "owning_team_ids": p.get("owningTeamIds") or [],
                "member_id": p.get("memberId"),
            }
        )

    return out


def validate_draft_picks(draft_picks, teams):
    """Validate expected draft counts and basic pick integrity by season."""
    expected = {10: 160, 8: 128, 12: 192}

    teams_by_year = {}
    for t in teams:
        teams_by_year.setdefault(t["season"], []).append(t)

    picks_by_year = {}
    for p in draft_picks:
        picks_by_year.setdefault(p["season"], []).append(p)

    errors = []

    for year in sorted(teams_by_year):
        team_count = len(teams_by_year[year])
        picks = picks_by_year.get(year, [])
        expected_count = expected.get(team_count)

        if expected_count is not None and len(picks) != expected_count:
            errors.append(
                f"{year}: expected {expected_count} draft picks for "
                f"{team_count} teams, found {len(picks)}"
            )

        overall = [p["overall_pick"] for p in picks if p["overall_pick"] is not None]
        if len(overall) != len(set(overall)):
            errors.append(f"{year}: duplicate overall_pick values")

        missing_team = [
            p for p in picks
            if p["team_id"] is None or p["team_id"] not in {
                t["team_id"] for t in teams_by_year[year]
            }
        ]
        if missing_team:
            errors.append(
                f"{year}: {len(missing_team)} draft picks reference an unknown team_id"
            )

        missing_person = [p for p in picks if p["person_id"] is None]
        if missing_person:
            errors.append(
                f"{year}: {len(missing_person)} draft picks could not resolve to a person_id"
            )

    return errors

def extract_matchups(year, team_lookup):
    """
    Normalize matchup records directly from raw ESPN mMatchupScore.
    teamId is authoritative for ownership.
    """
    data = raw_view(year, "mMatchupScore")
    schedule = data.get("schedule", [])

    out = []

    for m in schedule:
        home = m.get("home") or {}
        away = m.get("away") or {}

        home_team = team_id_int(home.get("teamId")) if home.get("teamId") is not None else None
        away_team = team_id_int(away.get("teamId")) if away.get("teamId") is not None else None

        def score(side):
            if not side:
                return None
            if side.get("totalPoints") is not None:
                return side.get("totalPoints")
            pts = side.get("pointsByScoringPeriod") or {}
            if not pts:
                return None
            try:
                return sum(float(v) for v in pts.values() if v is not None)
            except (TypeError, ValueError):
                return None

        winner = m.get("winner")
        if winner == "HOME":
            winner_team_id = home_team
        elif winner == "AWAY":
            winner_team_id = away_team
        else:
            winner_team_id = None

        out.append(
            {
                "season": year,
                "matchup_id": m.get("id"),
                "matchup_period_id": m.get("matchupPeriodId"),
                "scoring_period_id": m.get("scoringPeriodId"),
                "playoff_tier_type": m.get("playoffTierType"),
                "winner": winner,
                "winner_team_id": winner_team_id,
                "home_team_id": home_team,
                "away_team_id": away_team,
                "home_person_id": team_lookup.get(home_team, {}).get("person_id"),
                "away_person_id": team_lookup.get(away_team, {}).get("person_id"),
                "home_score": score(home),
                "away_score": score(away),
            }
        )

    return out


def build_championships(all_matchups):
    championships = []

    by_year = {}
    for m in all_matchups:
        by_year.setdefault(m["season"], []).append(m)

    for year in sorted(by_year):
        winners = [
            m for m in by_year[year]
            if m.get("playoff_tier_type") == "WINNERS_BRACKET"
        ]

        if not winners:
            championships.append({
                "season": year,
                "status": "NO_WINNERS_BRACKET",
                "championship_matchup_id": None,
                "champion_team_id": None,
                "champion_person_id": None,
            })
            continue

        final_period = max(
            m["matchup_period_id"]
            for m in winners
            if m.get("matchup_period_id") is not None
        )

        finals = [
            m for m in winners
            if m.get("matchup_period_id") == final_period
        ]

        # Normally there is exactly one final. If ESPN gives multiple
        # winners-bracket records at the final period, don't guess.
        if len(finals) != 1:
            championships.append({
                "season": year,
                "status": "AMBIGUOUS_FINAL",
                "championship_matchup_id": None,
                "champion_team_id": None,
                "champion_person_id": None,
                "final_period": final_period,
                "candidate_matchup_ids": [m["matchup_id"] for m in finals],
            })
            continue

        final = finals[0]

        if final.get("winner_team_id") is None:
            championships.append({
                "season": year,
                "status": "INCOMPLETE",
                "championship_matchup_id": final["matchup_id"],
                "champion_team_id": None,
                "champion_person_id": None,
                "final_period": final_period,
            })
            continue

        championships.append({
            "season": year,
            "status": "COMPLETE",
            "championship_matchup_id": final["matchup_id"],
            "champion_team_id": final["winner_team_id"],
            "champion_person_id": (
                final.get("home_person_id")
                if final["winner"] == "HOME"
                else final.get("away_person_id")
            ),
            "runner_up_team_id": (
                final.get("away_team_id")
                if final["winner"] == "HOME"
                else final.get("home_team_id")
            ),
            "runner_up_person_id": (
                final.get("away_person_id")
                if final["winner"] == "HOME"
                else final.get("home_person_id")
            ),
            "final_period": final_period,
            "champion_score": (
                final.get("home_score")
                if final["winner"] == "HOME"
                else final.get("away_score")
            ),
            "runner_up_score": (
                final.get("away_score")
                if final["winner"] == "HOME"
                else final.get("home_score")
            ),
        })

    return championships


def build_playoff_appearances(all_matchups):
    """
    A team has a playoff appearance when it participates in a
    WINNERS_BRACKET matchup. This deliberately excludes consolation-only teams.
    """
    rows = []
    by_year = {}

    for m in all_matchups:
        if m.get("playoff_tier_type") != "WINNERS_BRACKET":
            continue
        by_year.setdefault(m["season"], set()).update(
            x for x in (m.get("home_team_id"), m.get("away_team_id"))
            if x is not None
        )

    for season, team_ids in sorted(by_year.items()):
        for team_id in sorted(team_ids, key=str):
            rows.append({"season": season, "team_id": team_id})

    return rows


def build_season_results(championships, teams):
    team_by_year_id = {(t["season"], t["team_id"]): t for t in teams}
    results = []

    for c in championships:
        team = team_by_year_id.get((c["season"], c.get("champion_team_id")))
        results.append(
            {
                "season": c["season"],
                "status": c["status"],
                "champion_team_id": c.get("champion_team_id"),
                "champion_person_id": c.get("champion_person_id"),
                "champion_team_name": team.get("team_name") if team else None,
                "runner_up_team_id": c.get("runner_up_team_id"),
                "runner_up_person_id": c.get("runner_up_person_id"),
                "runner_up_team_name": (
                    team_by_year_id.get(
                        (c["season"], c.get("runner_up_team_id")), {}
                    ).get("team_name")
                ),
                "championship_matchup_id": c.get("championship_matchup_id"),
            }
        )

    return results


def build_owner_records(teams, championships, playoff_appearances):
    """
    Owner-level championship/playoff totals based on canonical person_id.
    No ranking or 'best owner' conclusions are generated here.
    """
    stats = {}

    def ensure(pid):
        if pid:
            stats.setdefault(
                pid,
                {
                    "person_id": pid,
                    "seasons": 0,
                    "championships": 0,
                    "playoff_appearances": 0,
                },
            )

    for t in teams:
        pid = t.get("person_id")
        ensure(pid)
        if pid:
            stats[pid]["seasons"] += 1

    for c in championships:
        ensure(c.get("champion_person_id"))
        if c.get("champion_person_id"):
            stats[c["champion_person_id"]]["championships"] += 1

    for p in playoff_appearances:
        t = next(
            (
                x for x in teams
                if x["season"] == p["season"] and x["team_id"] == p["team_id"]
            ),
            None,
        )
        if t and t.get("person_id"):
            stats[t["person_id"]]["playoff_appearances"] += 1

    return sorted(stats.values(), key=lambda x: x["person_id"])



def validate_standings_against_matchups(standings, matchups):
    """
    Reconcile official ESPN standings against completed regular-season
    matchup results and scores.

    Important historical behavior:
      - PF/PA comes from matchup scores.
      - W/L/T comes from ESPN's matchup winner field when ESPN recorded one.
      - Equal scores are NOT automatically treated as ties. In 2014 the
        league had a regular-season tiebreaker (bench points), so ESPN can
        record HOME/AWAY for an equal-score game.
      - Equal non-zero scores with no winner are treated as genuine ties.
      - Unplayed/future matchups (0-0 with no winner) are ignored. This is
        needed for the incomplete 2026 season.
    """
    calculated = {}
    warnings = []

    for m in matchups:
        if m.get("playoff_tier_type") != "NONE":
            continue

        season = m.get("season")
        home_id = m.get("home_team_id")
        away_id = m.get("away_team_id")
        home_score = m.get("home_score")
        away_score = m.get("away_score")
        winner = m.get("winner")

        if home_id is None or away_id is None:
            continue
        if home_score is None or away_score is None:
            continue

        try:
            hs = float(home_score)
            aws = float(away_score)
        except (TypeError, ValueError):
            continue

        # ESPN uses UNDECIDED for both genuine ties and unplayed games.
        # A 0-0/UNDECIDED matchup is therefore treated as unplayed. The
        # league's historical ties all have actual fantasy points.
        if winner in (None, "UNDECIDED") and hs == 0 and aws == 0:
            continue

        season_data = calculated.setdefault(season, {})

        for team_id in (home_id, away_id):
            season_data.setdefault(
                team_id,
                {
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "points_for": 0.0,
                    "points_against": 0.0,
                    "games": 0,
                },
            )

        h = season_data[home_id]
        a = season_data[away_id]

        h["games"] += 1
        a["games"] += 1
        h["points_for"] += hs
        h["points_against"] += aws
        a["points_for"] += aws
        a["points_against"] += hs

        if winner == "HOME":
            h["wins"] += 1
            a["losses"] += 1
        elif winner == "AWAY":
            a["wins"] += 1
            h["losses"] += 1
        else:
            # Any completed equal-score regular-season matchup that did not
            # record HOME/AWAY as the winner is treated as a genuine tie.
            # ESPN has used different non-winner values across historical
            # seasons (for example UNDECIDED/TIE), so do not depend on one
            # literal string here.
            if abs(hs - aws) <= 0.01:
                h["ties"] += 1
                a["ties"] += 1
            else:
                warnings.append(
                    f"{season} matchup {m.get('matchup_id')}: scores differ "
                    f"({hs:g}-{aws:g}) but ESPN winner is {winner!r}"
                )

    standings_by_key = {
        (s["season"], s["team_id"]): s
        for s in standings
    }

    errors = []

    for season, season_data in sorted(calculated.items()):
        for team_id, expected in sorted(season_data.items()):
            key = (season, team_id)
            actual = standings_by_key.get(key)

            if actual is None:
                errors.append(
                    f"{season} team {team_id}: missing standings row"
                )
                continue

            for field in ("wins", "losses", "ties"):
                actual_value = actual.get(field)
                expected_value = expected[field]

                if actual_value is None:
                    warnings.append(
                        f"{season} team {team_id}: standings {field} is missing"
                    )
                elif int(actual_value) != expected_value:
                    errors.append(
                        f"{season} team {team_id}: {field} mismatch "
                        f"(standings={actual_value}, matchup_results={expected_value})"
                    )

            for field in ("points_for", "points_against"):
                actual_value = actual.get(field)
                expected_value = expected[field]

                if actual_value is None:
                    warnings.append(
                        f"{season} team {team_id}: standings {field} is missing"
                    )
                elif abs(float(actual_value) - expected_value) > 0.01:
                    errors.append(
                        f"{season} team {team_id}: {field} mismatch "
                        f"(standings={actual_value}, matchup_scores={expected_value:.2f})"
                    )

            # A completed regular-season team should have the same number of
            # games implied by its official record. This catches accidental
            # inclusion/exclusion of schedule rows without treating the
            # incomplete 2026 future schedule as played games.
            actual_games = sum(
                int(actual.get(x) or 0) for x in ("wins", "losses", "ties")
            )
            if actual_games != expected["games"]:
                errors.append(
                    f"{season} team {team_id}: games mismatch "
                    f"(standings={actual_games}, matchup_results={expected['games']})"
                )

    return errors, warnings

def main():
    PROCESSED.mkdir(parents=True, exist_ok=True)
    ANALYTICS.mkdir(parents=True, exist_ok=True)

    espn_to_person, people = build_person_map()

    teams = []
    all_matchups = []
    all_draft_picks = []
    all_standings = []

    for year in range(START_YEAR, END_YEAR + 1):
        year_teams = season_teams(year, espn_to_person, people)
        teams.extend(year_teams)

        lookup = {t["team_id"]: t for t in year_teams}
        all_matchups.extend(extract_matchups(year, lookup))
        all_draft_picks.extend(extract_draft_picks(year, lookup))
        all_standings.extend(extract_standings(year, lookup))

    championships = build_championships(all_matchups)
    playoff_appearances = build_playoff_appearances(all_matchups)
    season_results = build_season_results(championships, teams)
    owner_records = build_owner_records(
        teams, championships, playoff_appearances
    )
    draft_errors = validate_draft_picks(all_draft_picks, teams)
    standings_errors = validate_standings(all_standings, teams)
    standings_matchup_errors, standings_matchup_warnings = (
        validate_standings_against_matchups(all_standings, all_matchups)
    )

    def write(name, obj):
        with name.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")

    write(PROCESSED / "people.json", list(people.values()))
    write(PROCESSED / "teams.json", teams)
    write(PROCESSED / "matchups.json", all_matchups)
    write(PROCESSED / "draft_picks.json", all_draft_picks)
    write(PROCESSED / "standings.json", all_standings)

    write(ANALYTICS / "championships.json", championships)
    write(ANALYTICS / "playoff_appearances.json", playoff_appearances)
    write(ANALYTICS / "season_results.json", season_results)
    write(ANALYTICS / "owner_records.json", owner_records)

    print("\n=== CHAMPIONSHIP BUILD ===")
    for c in championships:
        print(
            c["season"],
            c["status"],
            "team=", c.get("champion_team_id"),
            "person=", c.get("champion_person_id"),
            "matchup=", c.get("championship_matchup_id"),
        )

    print("\n=== DRAFT VALIDATION ===")
    if draft_errors:
        for error in draft_errors:
            print("ERROR:", error)
        raise SystemExit("Draft validation failed.")
    else:
        by_year = {}
        for p in all_draft_picks:
            by_year.setdefault(p["season"], 0)
            by_year[p["season"]] += 1
        for year in sorted(by_year):
            print(year, "OK", by_year[year], "picks")

    print("\n=== STANDINGS VALIDATION ===")
    if standings_errors:
        for error in standings_errors:
            print("ERROR:", error)
        raise SystemExit("Standings validation failed.")
    else:
        by_year = {}
        for s in all_standings:
            by_year.setdefault(s["season"], 0)
            by_year[s["season"]] += 1
        for year in sorted(by_year):
            print(year, "OK", by_year[year], "standings rows")

    print("\n=== STANDINGS / MATCHUP RECONCILIATION ===")
    if standings_matchup_errors:
        for error in standings_matchup_errors:
            print("ERROR:", error)
        raise SystemExit("Standings/matchup reconciliation failed.")

    if standings_matchup_warnings:
        for warning in standings_matchup_warnings:
            print("WARNING:", warning)

    print(
        "PASS:",
        "all regular-season W/L/T and points-for/against values reconcile"
        if not standings_matchup_warnings
        else "matchup reconciliation passed with warnings"
    )

    print("\nWrote:")
    for p in [
        PROCESSED / "people.json",
        PROCESSED / "teams.json",
        PROCESSED / "matchups.json",
        PROCESSED / "draft_picks.json",
        PROCESSED / "standings.json",
        ANALYTICS / "championships.json",
        ANALYTICS / "playoff_appearances.json",
        ANALYTICS / "season_results.json",
        ANALYTICS / "owner_records.json",
    ]:
        print(" ", p)


if __name__ == "__main__":
    main()
