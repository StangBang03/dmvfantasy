import json
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

LEAGUE_ID = 112536
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
REPORT = Path("data/analytics/boxscore_reconciliation.json")

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
    "User-Agent": "FantasyLeagueHistory/1.0"
})


def unwrap(data):
    if isinstance(data, list) and len(data) == 1:
        return data[0]
    return data


def url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"

    return f"{BASE}/leagueHistory/{LEAGUE_ID}?seasonId={year}"


def main():
    report = json.loads(
        REPORT.read_text(encoding="utf-8")
    )

    failures = report.get("failures", [])[:5]

    for n, f in enumerate(failures, 1):

        year = int(f["season"])
        sp = int(f["scoring_period"])
        mp = int(f["matchup_period"])
        matchup_id = f["matchup_id"]
        team_id = f["team_id"]

        response = session.get(
            url(year),
            params=[
                ("view", "mBoxscore"),
                ("view", "mMatchupScore"),
                ("matchupPeriodId", str(mp)),
                ("scoringPeriodId", str(sp)),
            ],
            timeout=60,
        )

        response.raise_for_status()

        data = unwrap(response.json())

        matchup = next(
            x for x in data["schedule"]
            if str(x.get("id")) == str(matchup_id)
        )

        if matchup["home"].get("teamId") == team_id:
            side = matchup["home"]
        else:
            side = matchup["away"]

        roster = side.get("rosterForMatchupPeriod") or {}
        entries = roster.get("entries") or []

        entry_sum = sum(
            float(
                (e.get("playerPoolEntry") or {})
                .get("appliedStatTotal") or 0
            )
            for e in entries
        )

        team_score = (
            side.get("pointsByScoringPeriod") or {}
        ).get(str(sp))

        print("=" * 72)
        print(
            f"{n}. {year} SP{sp} "
            f"matchup {matchup_id} "
            f"team {team_id}"
        )

        print(
            f"ESPN team score:                  "
            f"{team_score}"
        )

        print(
            f"rosterForMatchupPeriod total:     "
            f"{roster.get('appliedStatTotal')}"
        )

        print(
            f"sum of roster entries:             "
            f"{entry_sum}"
        )

        print(
            f"entry count:                       "
            f"{len(entries)}"
        )

        print()
        print("Entries:")

        for e in entries:

            pool = e.get("playerPoolEntry") or {}
            player = pool.get("player") or {}

            print(
                f"  player={e.get('playerId')} "
                f"{player.get('fullName', '?'):<28} "
                f"slot={e.get('lineupSlotId')} "
                f"points={pool.get('appliedStatTotal')}"
            )

        print()


if __name__ == "__main__":
    main()