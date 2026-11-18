from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"

def load(name):
    with (PROCESSED / name).open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    teams = load("teams.json")
    matchups = load("matchups.json")

    team_lookup = {
        (int(t["season"]), int(t["team_id"])): t
        for t in teams
    }

    print("=" * 80)
    print("PLAYOFF STRUCTURE INSPECTION")
    print("=" * 80)

    for season in sorted({int(t["season"]) for t in teams}):
        season_games = [
            m for m in matchups
            if int(m["season"]) == season
        ]

        periods = defaultdict(list)
        for m in season_games:
            periods[m["matchup_period_id"]].append(m)

        print(f"\nSEASON {season}")
        print("-" * 80)

        for period in sorted(periods, key=lambda x: (x is None, x)):
            games = periods[period]
            scored = [
                g for g in games
                if g.get("home_score") is not None
                and g.get("away_score") is not None
            ]

            team_ids = sorted({
                x for g in games
                for x in (g.get("home_team_id"), g.get("away_team_id"))
                if x is not None
            })

            print(
                f"Period {period!r}: "
                f"{len(games)} records, "
                f"{len(scored)} scored games, "
                f"teams={team_ids}"
            )

            # Print actual games for later periods, where playoff games
            # are most likely to live.
            if period is not None and len(periods) > 1:
                max_period = max(
                    p for p in periods
                    if isinstance(p, (int, float))
                )
                if isinstance(period, (int, float)) and period >= max_period - 4:
                    for g in scored:
                        ht = team_lookup.get((season, int(g["home_team_id"])))
                        at = team_lookup.get((season, int(g["away_team_id"])))

                        hn = ht["team_name"] if ht else "UNKNOWN"
                        an = at["team_name"] if at else "UNKNOWN"

                        print(
                            f"    {g['matchup_id']:>3} | "
                            f"{hn} ({g['home_team_id']}) "
                            f"{g['home_score']} - "
                            f"{g['away_score']} "
                            f"({g['away_team_id']}) {an}"
                        )

        print("\nTeam playoff fields:")
        season_teams = [
            t for t in teams
            if int(t["season"]) == season
        ]

        for t in sorted(
            season_teams,
            key=lambda x: (
                x["playoff_seed"] is None,
                x["playoff_seed"] if x["playoff_seed"] is not None else 999,
                x["rank"] if x["rank"] is not None else 999,
            )
        ):
            print(
                f"  Team {t['team_id']:>2} | "
                f"seed={str(t['playoff_seed']):>4} | "
                f"rank={str(t['rank']):>4} | "
                f"{t['team_name']} | "
                f"person={t['person_id']}"
            )

if __name__ == "__main__":
    main()
