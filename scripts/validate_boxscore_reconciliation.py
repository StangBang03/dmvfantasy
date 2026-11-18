import json
import math
from pathlib import Path

BOX_DIR = Path("data/raw/boxscore_v2")

TOLERANCE = 0.01


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main():
    files = sorted(BOX_DIR.rglob("matchup_*.json"))

    if not files:
        raise RuntimeError(f"No matchup files found under {BOX_DIR}")

    total_rows = 0
    passed = 0
    failed = 0
    skipped = 0
    failures = []

    season_stats = {}

    print("=" * 70)
    print("ESPN BOXSCORE PLAYER-TO-TEAM SCORE RECONCILIATION")
    print("=" * 70)
    print(f"Files found: {len(files):,}")
    print()

    for path in files:
        payload = load_json(path)

        season = payload.get("season")
        scoring_period = payload.get("scoring_period")
        matchup_period = payload.get("matchup_period")
        matchup_id = payload.get("matchup_id")

        for side in payload.get("sides", []):
            total_rows += 1

            team_id = side.get("team_id")
            expected = side.get("points_for_scoring_period")

            entries = side.get("lineup_entries") or []

            # No player lineup means there is nothing to reconcile.
            if not entries:
                skipped += 1
                continue

            actual = 0.0
            missing_points = []

            for entry in entries:
                points = entry.get("applied_points")

                if points is None:
                    missing_points.append(entry.get("player_id"))
                else:
                    actual += float(points)

            if expected is None or missing_points:
                skipped += 1
                continue

            difference = actual - float(expected)

            stats = season_stats.setdefault(
                season,
                {
                    "rows": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "max_abs_difference": 0.0,
                },
            )

            stats["rows"] += 1
            stats["max_abs_difference"] = max(
                stats["max_abs_difference"],
                abs(difference),
            )

            if math.isclose(actual, float(expected), abs_tol=TOLERANCE):
                passed += 1
                stats["passed"] += 1
            else:
                failed += 1
                stats["failed"] += 1

                failure = {
                    "season": season,
                    "scoring_period": scoring_period,
                    "matchup_period": matchup_period,
                    "matchup_id": matchup_id,
                    "team_id": team_id,
                    "player_count": len(entries),
                    "player_points_sum": round(actual, 4),
                    "espn_team_score": round(float(expected), 4),
                    "difference": round(difference, 4),
                    "players": [
                        {
                            "player_id": e.get("player_id"),
                            "player_name": e.get("player_name"),
                            "slot": e.get("lineup_slot_id"),
                            "points": e.get("applied_points"),
                        }
                        for e in entries
                    ],
                }

                failures.append(failure)

    print("OVERALL")
    print("-" * 70)
    print(f"Team/scoring-period rows examined: {total_rows:,}")
    print(f"PASSED:                           {passed:,}")
    print(f"FAILED:                           {failed:,}")
    print(f"SKIPPED:                          {skipped:,}")
    print()

    print("BY SEASON")
    print("-" * 70)

    for season in sorted(season_stats):
        s = season_stats[season]
        print(
            f"{season}: "
            f"rows={s['rows']} "
            f"pass={s['passed']} "
            f"fail={s['failed']} "
            f"max_diff={s['max_abs_difference']:.4f}"
        )

    report = {
        "description": (
            "Reconciliation of sum(player.applied_points) against "
            "ESPN team points for the requested scoring period."
        ),
        "tolerance": TOLERANCE,
        "files_examined": len(files),
        "team_period_rows_examined": total_rows,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "season_stats": season_stats,
        "failures": failures,
    }

    output = Path("data/analytics/boxscore_reconciliation.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print()
    print("=" * 70)

    if failed == 0:
        print("RESULT: PASS")
        print(
            "Every reconciled lineup's player-point total matches "
            "ESPN's team score within tolerance."
        )
    else:
        print("RESULT: FAIL")
        print(f"Found {failed} mismatched team/scoring-period rows.")

        print()
        print("FIRST 10 FAILURES")
        print("-" * 70)

        for failure in failures[:10]:
            print(
                f"{failure['season']} "
                f"SP{failure['scoring_period']} "
                f"team={failure['team_id']}: "
                f"players={failure['player_points_sum']} "
                f"ESPN={failure['espn_team_score']} "
                f"diff={failure['difference']}"
            )

    print()
    print(f"Wrote: {output}")


if __name__ == "__main__":
    main()
