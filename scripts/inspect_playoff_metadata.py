from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROCESSED = ROOT / "data" / "processed"

def load(name):
    with (PROCESSED / name).open("r", encoding="utf-8") as f:
        return json.load(f)

def main():
    matchups = load("matchups.json")
    teams = load("teams.json")

    print("=" * 90)
    print("PLAYOFF MATCHUP METADATA INSPECTION")
    print("=" * 90)

    # Inspect representative late-season records. We want to find ESPN's
    # own bracket/tier/winner metadata before defining championships.
    for season in [2011, 2015, 2020, 2021, 2025]:
        rows = [
            m for m in matchups
            if int(m["season"]) == season
            and m.get("matchup_period_id") is not None
            and int(m["matchup_period_id"]) >= 14
        ]

        print(f"\nSEASON {season}")
        print("-" * 90)

        for m in rows[:20]:
            raw = m.get("raw", {})
            interesting = {}

            for key in [
                "id", "matchupPeriodId", "scoringPeriodId",
                "playoffTierType", "playoffBracketType",
                "winner", "winnerTeamId", "loserTeamId",
                "isPlayoff", "isConsolation",
                "home", "away"
            ]:
                if key in raw:
                    interesting[key] = raw[key]

            print(json.dumps(interesting, ensure_ascii=False, default=str))

    print("\nRAW KEYS FOUND IN LATE-SEASON MATCHUPS")
    print("-" * 90)

    keys = set()
    for m in matchups:
        if m.get("matchup_period_id") is not None and int(m["matchup_period_id"]) >= 14:
            keys.update(m.get("raw", {}).keys())

    for key in sorted(keys):
        print(key)

if __name__ == "__main__":
    main()
