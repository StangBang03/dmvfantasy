import json
from collections import defaultdict
from pathlib import Path

PERFORMANCE_FILE = Path("data/processed/player_performance.json")
AUDIT_FILE = Path("data/processed/player_performance_weekly_audit.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    print("=" * 70)
    print("AUDIT WEEKLY PLAYER PERFORMANCE")
    print("=" * 70)

    data = load_json(PERFORMANCE_FILE)

    player_seasons = data.get("player_seasons", [])
    weekly_rows = data.get("weekly", [])

    if not isinstance(player_seasons, list):
        raise ValueError("'player_seasons' is not a list in player_performance.json")

    if not isinstance(weekly_rows, list):
        raise ValueError("'weekly' is not a list in player_performance.json")

    players_by_season = defaultdict(set)
    weekly_by_season = defaultdict(list)
    weekly_by_player = defaultdict(list)
    weeks_by_season = defaultdict(set)

    for row in player_seasons:
        season = row.get("season")
        player_id = row.get("player_id")
        if season is not None and player_id is not None:
            players_by_season[int(season)].add(int(player_id))

    for row in weekly_rows:
        season = row.get("season")
        player_id = row.get("player_id")
        scoring_period = row.get("scoring_period")

        if season is None or player_id is None:
            continue

        season = int(season)
        player_id = int(player_id)

        weekly_by_season[season].append(row)
        weekly_by_player[(season, player_id)].append(row)

        if scoring_period is not None:
            weeks_by_season[season].add(int(scoring_period))

    audit = {
        "seasons": {},
        "summary": {
            "player_seasons": len(player_seasons),
            "weekly_rows": len(weekly_rows),
            "players_with_weekly": 0,
            "players_without_weekly": 0,
        },
    }

    total_with_weekly = 0
    total_without_weekly = 0

    for season in sorted(players_by_season):
        player_ids = players_by_season[season]
        with_weekly = 0
        without_weekly = 0
        week_counts = defaultdict(int)
        missing_examples = []

        for player_id in sorted(player_ids):
            rows = weekly_by_player.get((season, player_id), [])

            if rows:
                with_weekly += 1
                for row in rows:
                    scoring_period = row.get("scoring_period")
                    if scoring_period is not None:
                        week_counts[int(scoring_period)] += 1
            else:
                without_weekly += 1
                if len(missing_examples) < 10:
                    player_name = None
                    for ps in player_seasons:
                        if (
                            int(ps.get("season", -1)) == season
                            and int(ps.get("player_id", -1)) == player_id
                        ):
                            player_name = ps.get("player_name")
                            break

                    missing_examples.append(
                        {
                            "player_id": player_id,
                            "player_name": player_name,
                        }
                    )

        player_count = len(player_ids)
        coverage = (with_weekly / player_count * 100) if player_count else 0

        total_with_weekly += with_weekly
        total_without_weekly += without_weekly

        audit["seasons"][str(season)] = {
            "player_seasons": player_count,
            "weekly_rows": len(weekly_by_season[season]),
            "players_with_weekly": with_weekly,
            "players_without_weekly": without_weekly,
            "weekly_player_coverage_pct": round(coverage, 2),
            "scoring_periods_present": sorted(weeks_by_season[season]),
            "weekly_rows_by_scoring_period": dict(sorted(week_counts.items())),
            "missing_weekly_examples": missing_examples,
        }

        print(
            f"{season}: "
            f"{player_count:4d} player-seasons, "
            f"{len(weekly_by_season[season]):4d} weekly rows, "
            f"{with_weekly:4d} with weekly, "
            f"{without_weekly:4d} without "
            f"({coverage:5.1f}% coverage), "
            f"weeks={sorted(weeks_by_season[season])}"
        )

    audit["summary"]["players_with_weekly"] = total_with_weekly
    audit["summary"]["players_without_weekly"] = total_without_weekly

    overall_player_coverage = (
        total_with_weekly / len(player_seasons) * 100
        if player_seasons else 0
    )

    audit["summary"]["weekly_player_coverage_pct"] = round(
        overall_player_coverage, 2
    )

    # Flag duplicate weekly records for the same season/player/week.
    duplicate_week_keys = []
    seen = set()

    for row in weekly_rows:
        key = (
            row.get("season"),
            row.get("player_id"),
            row.get("scoring_period"),
        )
        if key in seen:
            duplicate_week_keys.append(key)
        else:
            seen.add(key)

    audit["summary"]["duplicate_weekly_keys"] = len(duplicate_week_keys)
    audit["duplicate_weekly_examples"] = duplicate_week_keys[:25]

    with AUDIT_FILE.open("w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Player-seasons:          {len(player_seasons)}")
    print(f"Weekly rows:             {len(weekly_rows)}")
    print(f"Players with weekly:     {total_with_weekly}")
    print(f"Players without weekly:  {total_without_weekly}")
    print(f"Weekly player coverage:  {overall_player_coverage:.1f}%")
    print(f"Duplicate weekly keys:   {len(duplicate_week_keys)}")
    print()
    print(f"Wrote: {AUDIT_FILE}")


if __name__ == "__main__":
    main()
