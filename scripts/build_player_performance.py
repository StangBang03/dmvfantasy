import json
import math
from pathlib import Path

RAW_DIR = Path("data/raw/roster")
PROCESSED_DIR = Path("data/processed")
ANALYTICS_DIR = Path("data/analytics")

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = PROCESSED_DIR / "player_performance.json"
AUDIT_FILE = PROCESSED_DIR / "player_performance_audit.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

    if isinstance(data, dict):
        return data

    return {}


def clean_number(value):
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value):
        return None

    return value


def extract_stats(stats):
    """
    Return:
      season_actual: actual season-total stat object
      weekly_actual: {scoring_period_id: stat object}
    """
    season_actual = None
    weekly_actual = {}

    if not isinstance(stats, list):
        return season_actual, weekly_actual

    for stat in stats:
        if not isinstance(stat, dict):
            continue

        # ESPN actual stats are statSourceId=0.
        # Season totals use statSplitTypeId=0.
        # Weekly/scoring-period entries use statSplitTypeId=1.
        if stat.get("statSourceId") != 0:
            continue

        scoring_period = stat.get("scoringPeriodId")
        split_type = stat.get("statSplitTypeId")

        if split_type == 0 and scoring_period == 0:
            season_actual = stat

        elif split_type == 1 and scoring_period is not None:
            weekly_actual[int(scoring_period)] = stat

    return season_actual, weekly_actual


def player_metadata(player):
    return {
        "player_id": player.get("id"),
        "player_name": player.get("fullName"),
        "first_name": player.get("firstName"),
        "last_name": player.get("lastName"),
        "default_position_id": player.get("defaultPositionId"),
        "pro_team_id": player.get("proTeamId"),
        "active": player.get("active"),
    }


def main():
    print("=" * 70)
    print("BUILD PLAYER PERFORMANCE")
    print("=" * 70)

    seasons = []
    player_seasons = []
    weekly_rows = []

    audit = {
        "seasons": [],
        "total_roster_rows": 0,
        "unique_player_seasons": 0,
        "season_actual_rows": 0,
        "weekly_actual_rows": 0,
        "missing_season_actual": [],
        "duplicate_player_seasons": [],
        "source_counts": {},
        "split_counts": {},
    }

    # First pass: extract unique player-season production records.
    records = {}

    for year_dir in sorted(RAW_DIR.iterdir()):
        if not year_dir.is_dir():
            continue

        year = int(year_dir.name)
        file = year_dir / "mRoster.json"

        if not file.exists():
            print(f"WARNING: missing {file}")
            continue

        raw = load_json(file)
        data = unwrap(raw)

        teams = data.get("teams", [])

        season_roster_rows = 0
        season_players = set()

        for team in teams:
            team_id = team.get("id")

            roster = team.get("roster", {})
            entries = roster.get("entries", [])

            if not isinstance(entries, list):
                continue

            for entry in entries:
                season_roster_rows += 1
                audit["total_roster_rows"] += 1

                player_id = entry.get("playerId")

                if player_id is None:
                    continue

                player_pool = entry.get("playerPoolEntry") or {}
                player = player_pool.get("player") or {}

                # Some ESPN responses may not duplicate player ID here.
                if player.get("id") is None:
                    player["id"] = player_id

                key = (year, int(player_id))

                if key in records:
                    # A player can appear on multiple roster records in
                    # the same season due to ownership/acquisition history.
                    # We only want one production record per player-season.
                    audit["duplicate_player_seasons"].append(
                        {
                            "season": year,
                            "player_id": int(player_id),
                            "team_id": team_id,
                        }
                    )

                season_players.add(int(player_id))

                stats = player.get("stats", [])
                season_actual, weekly_actual = extract_stats(stats)

                # Preserve the first useful metadata we encounter.
                if key not in records:
                    record = player_metadata(player)
                    record.update(
                        {
                            "season": year,
                            "player_id": int(player_id),
                            "roster_team_ids": [],
                            "acquisition_types": [],
                            "season_fantasy_points": None,
                            "season_applied_average": None,
                            "season_stats": {},
                            "weeks": {},
                        }
                    )
                    records[key] = record

                record = records[key]

                if team_id not in record["roster_team_ids"]:
                    record["roster_team_ids"].append(team_id)

                acquisition_type = entry.get("acquisitionType")

                if (
                    acquisition_type
                    and acquisition_type
                    not in record["acquisition_types"]
                ):
                    record["acquisition_types"].append(
                        acquisition_type
                    )

                # Actual season total.
                if season_actual is not None:
                    applied_total = clean_number(
                        season_actual.get("appliedTotal")
                    )

                    # If multiple roster copies exist, prefer a populated
                    # actual season total over a missing one.
                    if (
                        record["season_fantasy_points"] is None
                        and applied_total is not None
                    ):
                        record["season_fantasy_points"] = applied_total
                        record["season_applied_average"] = clean_number(
                            season_actual.get("appliedAverage")
                        )
                        record["season_stats"] = (
                            season_actual.get("stats") or {}
                        )

                # Actual weekly production.
                for week, stat in weekly_actual.items():
                    applied_total = clean_number(
                        stat.get("appliedTotal")
                    )

                    if applied_total is None:
                        continue

                    record["weeks"][str(week)] = {
                        "scoring_period": week,
                        "fantasy_points": applied_total,
                        "stats": stat.get("stats") or {},
                        "applied_average": clean_number(
                            stat.get("appliedAverage")
                        ),
                    }

                season_roster_rows += 0

        seasons.append(year)

        audit["seasons"].append(
            {
                "season": year,
                "teams": len(teams),
                "roster_rows": season_roster_rows,
                "unique_players": len(season_players),
            }
        )

        print(
            f"{year}: "
            f"{len(teams)} teams, "
            f"{season_roster_rows} roster rows, "
            f"{len(season_players)} unique players"
        )

    # Finalize records and build flat weekly table.
    for (year, player_id), record in sorted(records.items()):
        weeks = record["weeks"]

        if record["season_fantasy_points"] is None:
            audit["missing_season_actual"].append(
                {
                    "season": year,
                    "player_id": player_id,
                    "player_name": record.get("player_name"),
                }
            )

        if record["season_fantasy_points"] is not None:
            audit["season_actual_rows"] += 1

        audit["weekly_actual_rows"] += len(weeks)

        player_seasons.append(record)

        for week_key, week in sorted(
            weeks.items(),
            key=lambda x: int(x[0]),
        ):
            weekly_rows.append(
                {
                    "season": year,
                    "scoring_period": int(week_key),
                    "player_id": player_id,
                    "player_name": record.get("player_name"),
                    "fantasy_points": week["fantasy_points"],
                }
            )

    audit["unique_player_seasons"] = len(player_seasons)

    # Add source/split metadata summary from the records we accepted.
    audit["source_counts"] = {
        "actual": audit["season_actual_rows"]
    }

    audit["split_counts"] = {
        "season_total": audit["season_actual_rows"],
        "weekly": audit["weekly_actual_rows"],
    }

    output = {
        "meta": {
            "description": (
                "Normalized ESPN player fantasy production. "
                "Season totals and weekly totals use actual stats only."
            ),
            "actual_stat_source_id": 0,
            "season_split_type_id": 0,
            "weekly_split_type_id": 1,
        },
        "player_seasons": player_seasons,
        "weekly": weekly_rows,
        "audit": audit,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    with AUDIT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            audit,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Seasons:                 {len(seasons)}")
    print(f"Unique player-seasons:   {len(player_seasons)}")
    print(f"Season actual rows:      {audit['season_actual_rows']}")
    print(f"Weekly actual rows:      {audit['weekly_actual_rows']}")
    print(
        f"Missing season totals:   "
        f"{len(audit['missing_season_actual'])}"
    )
    print(
        f"Duplicate roster copies: "
        f"{len(audit['duplicate_player_seasons'])}"
    )

    print()
    print(f"Wrote: {OUTPUT_FILE}")
    print(f"Wrote: {AUDIT_FILE}")

    print()
    print("=" * 70)
    print("PLAYER PERFORMANCE BUILD COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
