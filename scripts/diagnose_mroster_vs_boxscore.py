import json
import os
import requests
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# Targeted historical cases.
# 2011 SP10 Team 5 = known 99 vs 105 mismatch
# 2011 SP11 Team 6 = known 80 vs 97 mismatch
# 2017 SP10 = known clean/reconciling season
# 2019 SP10 = known clean/reconciling season
TESTS = [
    {"year": 2011, "scoring_period": 10, "team_id": 5},
    {"year": 2011, "scoring_period": 11, "team_id": 6},
    {"year": 2017, "scoring_period": 10, "team_id": 15},
    {"year": 2019, "scoring_period": 10, "team_id": 8},
]

load_dotenv()

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("ESPN_S2 / ESPN_SWID missing from .env")

session = requests.Session()

session.cookies.update({
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
})

session.headers.update({
    "User-Agent": "FantasyLeagueHistory/1.0",
    "Accept": "application/json",
})


def unwrap(data):
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        return data[0]

    if isinstance(data, dict):
        return data

    return {}


def league_url(year):
    if year >= 2018:
        return (
            f"{BASE}/seasons/{year}/segments/0/"
            f"leagues/{LEAGUE_ID}"
        )

    return (
        f"{BASE}/leagueHistory/"
        f"{LEAGUE_ID}?seasonId={year}"
    )


def get_side_from_boxscore(data, team_id):
    for matchup in data.get("schedule", []):

        for side_name in ("home", "away"):

            side = matchup.get(side_name) or {}

            if side.get("teamId") == team_id:
                return matchup, side_name, side

    return None, None, None


def roster_players(roster):
    result = {}

    for entry in roster.get("entries", []) or []:

        player_id = entry.get("playerId")

        if player_id is None:
            continue

        pool = entry.get("playerPoolEntry") or {}
        player = pool.get("player") or {}

        result[str(player_id)] = {
            "player_id": player_id,
            "name": player.get("fullName"),
            "lineup_slot_id": entry.get("lineupSlotId"),
            "applied_stat_total": pool.get("appliedStatTotal"),
            "acquisition_type": entry.get("acquisitionType"),
            "keeper": entry.get("keeper"),
        }

    return result


def fetch_mroster(year, scoring_period):

    params = [
        ("view", "mRoster"),
        ("scoringPeriodId", str(scoring_period)),
    ]

    response = session.get(
        league_url(year),
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    return unwrap(response.json()), response.url


def fetch_mboxscore(year, scoring_period):

    params = [
        ("view", "mBoxscore"),
        ("view", "mMatchupScore"),
        ("matchupPeriodId", str(scoring_period)),
        ("scoringPeriodId", str(scoring_period)),
    ]

    response = session.get(
        league_url(year),
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    return unwrap(response.json()), response.url


def main():

    all_results = []

    for test in TESTS:

        year = test["year"]
        sp = test["scoring_period"]
        team_id = test["team_id"]

        print("=" * 78)
        print(
            f"{year} | scoring period {sp} | team {team_id}"
        )
        print("=" * 78)

        # ------------------------------------------------------------
        # Get mRoster
        # ------------------------------------------------------------

        roster_data, roster_url = fetch_mroster(
            year,
            sp
        )

        mroster_team = next(
            (
                team
                for team in roster_data.get("teams", [])
                if team.get("id") == team_id
            ),
            None,
        )

        if mroster_team is None:

            print("mRoster: TEAM NOT FOUND")

            mroster = {}

        else:

            mroster = (
                mroster_team.get("roster")
                or {}
            )

        mroster_players = roster_players(mroster)

        # ------------------------------------------------------------
        # Get mBoxscore
        # ------------------------------------------------------------

        box_data, box_url = fetch_mboxscore(
            year,
            sp
        )

        matchup, side_name, side = get_side_from_boxscore(
            box_data,
            team_id
        )

        if side is None:

            print("mBoxscore: TEAM NOT FOUND")

            box_players = {}
            official_score = None
            matchup_id = None

        else:

            matchup_id = matchup.get("id")

            official_score = (
                side.get("pointsByScoringPeriod")
                or {}
            ).get(str(sp))

            box_roster = (
                side.get("rosterForMatchupPeriod")
                or {}
            )

            box_players = roster_players(
                box_roster
            )

            print(
                f"mBoxscore matchup: {matchup_id}"
            )

            print(
                f"mBoxscore side: {side_name}"
            )

            print(
                f"Official ESPN score: {official_score}"
            )

        print()

        print(
            f"mRoster players returned:    "
            f"{len(mroster_players)}"
        )

        print(
            f"mBoxscore players returned:  "
            f"{len(box_players)}"
        )

        print()

        # ------------------------------------------------------------
        # Compare player IDs
        # ------------------------------------------------------------

        only_mroster = [
            player
            for pid, player in mroster_players.items()
            if pid not in box_players
        ]

        only_box = [
            player
            for pid, player in box_players.items()
            if pid not in mroster_players
        ]

        # ------------------------------------------------------------
        # Players in mRoster but not mBoxscore
        # ------------------------------------------------------------

        print(
            "Players in mRoster but NOT mBoxscore:"
        )

        if only_mroster:

            for player in only_mroster:

                print(
                    f"  {player['player_id']:>7} "
                    f"{str(player['name']):<28} "
                    f"slot={player['lineup_slot_id']} "
                    f"mRosterPoints="
                    f"{player['applied_stat_total']}"
                )

        else:

            print("  NONE")

        print()

        # ------------------------------------------------------------
        # Players in mBoxscore but not mRoster
        # ------------------------------------------------------------

        print(
            "Players in mBoxscore but NOT mRoster:"
        )

        if only_box:

            for player in only_box:

                print(
                    f"  {player['player_id']:>7} "
                    f"{str(player['name']):<28} "
                    f"slot={player['lineup_slot_id']} "
                    f"mBoxPoints="
                    f"{player['applied_stat_total']}"
                )

        else:

            print("  NONE")

        print()

        # ------------------------------------------------------------
        # Full mRoster list
        # ------------------------------------------------------------

        print("mRoster full player list:")

        for player in mroster_players.values():

            print(
                f"  {player['player_id']:>7} "
                f"{str(player['name']):<28} "
                f"slot={player['lineup_slot_id']} "
                f"points={player['applied_stat_total']}"
            )

        print()

        # ------------------------------------------------------------
        # Save structured results
        # ------------------------------------------------------------

        all_results.append({
            "year": year,
            "scoring_period": sp,
            "team_id": team_id,
            "matchup_id": matchup_id,
            "official_score": official_score,
            "mroster_count": len(mroster_players),
            "mboxscore_count": len(box_players),
            "only_mroster": only_mroster,
            "only_boxscore": only_box,
            "mroster_url": roster_url,
            "mboxscore_url": box_url,
        })

    # ------------------------------------------------------------
    # Save diagnostic JSON
    # ------------------------------------------------------------

    output_path = (
        "data/analytics/"
        "mroster_boxscore_diagnostic.json"
    )

    os.makedirs(
        "data/analytics",
        exist_ok=True
    )

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            all_results,
            f,
            indent=2
        )

    print("=" * 78)
    print(
        f"Diagnostic saved to {output_path}"
    )
    print("=" * 78)


if __name__ == "__main__":
    main()