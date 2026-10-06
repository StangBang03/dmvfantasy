import json
import statistics
from collections import defaultdict
from pathlib import Path

PROJECT = Path(
    r"C:\Users\yatesd01\OneDrive - Montgomery County Government\Documents\Fantasy\ffl-site"
)

PROCESSED = PROJECT / "data" / "processed"
ANALYTICS = PROJECT / "data" / "analytics"


def load(name):
    with (PROCESSED / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    ANALYTICS.mkdir(parents=True, exist_ok=True)

    path = ANALYTICS / name

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            obj,
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.write("\n")

    return path


def completed_matchups(matchups):
    """
    Return only played matchups with both teams and usable scores.

    Future/unplayed ESPN rows are excluded. Historical playoff bye
    rows are also excluded because they do not have two teams.
    """

    out = []

    for m in matchups:

        home_team_id = m.get("home_team_id")
        away_team_id = m.get("away_team_id")

        home_score = m.get("home_score")
        away_score = m.get("away_score")

        if (
            home_team_id is None
            or away_team_id is None
            or home_score is None
            or away_score is None
        ):
            continue

        try:
            home_score = float(home_score)
            away_score = float(away_score)

        except (TypeError, ValueError):
            continue

        # Future/unplayed ESPN rows are generally represented
        # as 0-0 with an undecided/no result.
        if (
            home_score == 0
            and away_score == 0
            and m.get("winner") in (None, "UNDECIDED")
        ):
            continue

        row = dict(m)

        row["home_score"] = home_score
        row["away_score"] = away_score

        out.append(row)

    return out


def result_for_team(m, team_id):
    """
    Determine the official result for a team.

    ESPN's recorded winner is authoritative. If ESPN records
    no winner and the scores are equal, the result is a tie.

    This preserves the historical tiebreaker behavior already
    validated in the normalized data.
    """

    if m.get("winner") == "HOME":

        return (
            "W"
            if team_id == m.get("home_team_id")
            else "L"
        )

    if m.get("winner") == "AWAY":

        return (
            "W"
            if team_id == m.get("away_team_id")
            else "L"
        )

    home_score = float(m["home_score"])
    away_score = float(m["away_score"])

    if abs(home_score - away_score) <= 0.01:
        return "T"

    if team_id == m.get("home_team_id"):

        return (
            "W"
            if home_score > away_score
            else "L"
        )

    return (
        "W"
        if away_score > home_score
        else "L"
    )


def completed_seasons(matchups):
    """
    Determine which seasons are complete by looking for a
    decided final matchup in the WINNERS_BRACKET.

    This avoids hard-coding playoff periods.
    """

    completed = []

    seasons = sorted(
        {
            m["season"]
            for m in matchups
        }
    )

    for season in seasons:

        winners_bracket = [
            m
            for m in matchups
            if (
                m["season"] == season
                and m.get("playoff_tier_type")
                == "WINNERS_BRACKET"
            )
        ]

        if not winners_bracket:
            continue

        final_period = max(
            m.get("matchup_period_id", -1)
            for m in winners_bracket
        )

        finals = [
            m
            for m in winners_bracket
            if m.get("matchup_period_id")
            == final_period
        ]

        if any(
            m.get("winner")
            in ("HOME", "AWAY")
            for m in finals
        ):
            completed.append(season)

    return completed


def percentile_rank(values, value):
    """
    Percentile-style rank:

    observations strictly below the value
    plus half of observations equal to the value.

    Returns a value from 0 to 1.
    """

    if not values:
        return None

    below = sum(
        v < value
        for v in values
    )

    equal = sum(
        abs(v - value) <= 0.01
        for v in values
    )

    return (
        below
        + 0.5 * equal
    ) / len(values)


def build_weekly_observations(
    matchups,
    team_person,
):
    """
    Build one observation per team per regular-season
    scoring period.

    These observations are the foundation for:

    - all-play
    - expected wins
    - schedule luck
    - median performance
    - weekly scoring percentile
    - weekly schedule context
    """

    by_season_period = defaultdict(list)

    for m in matchups:

        if (
            m.get("playoff_tier_type")
            != "NONE"
        ):
            continue

        by_season_period[
            (
                m["season"],
                m.get("matchup_period_id"),
            )
        ].append(m)

    weekly = defaultdict(list)

    for (
        season,
        period,
    ), games in by_season_period.items():

        observations = []

        for m in games:

            home_person = team_person.get(
                (
                    season,
                    m["home_team_id"],
                )
            )

            away_person = team_person.get(
                (
                    season,
                    m["away_team_id"],
                )
            )

            if home_person:

                observations.append(
                    {
                        "season": season,
                        "period": period,
                        "team_id": m[
                            "home_team_id"
                        ],
                        "person_id": home_person,
                        "score": float(
                            m["home_score"]
                        ),
                        "opponent_team_id": m[
                            "away_team_id"
                        ],
                        "opponent_person_id": away_person,
                        "opponent_score": float(
                            m["away_score"]
                        ),
                        "actual_result": result_for_team(
                            m,
                            m["home_team_id"],
                        ),
                        "margin": (
                            float(
                                m["home_score"]
                            )
                            - float(
                                m["away_score"]
                            )
                        ),
                    }
                )

            if away_person:

                observations.append(
                    {
                        "season": season,
                        "period": period,
                        "team_id": m[
                            "away_team_id"
                        ],
                        "person_id": away_person,
                        "score": float(
                            m["away_score"]
                        ),
                        "opponent_team_id": m[
                            "home_team_id"
                        ],
                        "opponent_person_id": home_person,
                        "opponent_score": float(
                            m["home_score"]
                        ),
                        "actual_result": result_for_team(
                            m,
                            m["away_team_id"],
                        ),
                        "margin": (
                            float(
                                m["away_score"]
                            )
                            - float(
                                m["home_score"]
                            )
                        ),
                    }
                )

        scores = [
            o["score"]
            for o in observations
        ]

        # Compare each team against every OTHER team
        # in that same scoring period.
        for index, observation in enumerate(
            observations
        ):

            other_scores = [
                o["score"]
                for i, o in enumerate(
                    observations
                )
                if i != index
            ]

            wins = sum(
                observation["score"]
                > score + 0.01
                for score in other_scores
            )

            ties = sum(
                abs(
                    observation["score"]
                    - score
                )
                <= 0.01
                for score in other_scores
            )

            opponents = len(
                other_scores
            )

            all_play_win_pct = (
                (
                    wins
                    + 0.5 * ties
                )
                / opponents
                if opponents
                else None
            )

            observation[
                "league_size"
            ] = len(scores)

            observation[
                "all_play_wins"
            ] = wins

            observation[
                "all_play_ties"
            ] = ties

            observation[
                "all_play_opponents"
            ] = opponents

            observation[
                "all_play_win_pct"
            ] = all_play_win_pct

            observation[
                "score_percentile"
            ] = percentile_rank(
                scores,
                observation["score"],
            )

            weekly[
                (
                    season,
                    observation["person_id"],
                )
            ].append(
                observation
            )

    return weekly


def build_season_rows(
    weekly,
    names,
):
    """
    Aggregate weekly observations into one row
    per owner-season.
    """

    season_rows = []

    for (
        season,
        person_id,
    ), rows in sorted(
        weekly.items()
    ):

        rows.sort(
            key=lambda x: (
                x["period"] is None,
                x["period"],
            )
        )

        scores = [
            r["score"]
            for r in rows
        ]

        margins = [
            r["margin"]
            for r in rows
        ]

        opponent_scores = [
            r["opponent_score"]
            for r in rows
        ]

        actual_wins = sum(
            r["actual_result"] == "W"
            for r in rows
        )

        actual_losses = sum(
            r["actual_result"] == "L"
            for r in rows
        )

        actual_ties = sum(
            r["actual_result"] == "T"
            for r in rows
        )

        all_play_wins = sum(
            r["all_play_wins"]
            for r in rows
        )

        all_play_ties = sum(
            r["all_play_ties"]
            for r in rows
        )

        all_play_games = sum(
            r["all_play_opponents"]
            for r in rows
        )

        expected_wins = sum(
            r["all_play_win_pct"]
            for r in rows
            if r["all_play_win_pct"]
            is not None
        )

        close_5 = [
            r
            for r in rows
            if abs(r["margin"]) <= 5
        ]

        close_10 = [
            r
            for r in rows
            if abs(r["margin"]) <= 10
        ]

        blowout_20 = [
            r
            for r in rows
            if abs(r["margin"]) >= 20
        ]

        blowout_30 = [
            r
            for r in rows
            if abs(r["margin"]) >= 30
        ]

        close_5_wins = sum(
            r["actual_result"] == "W"
            for r in close_5
        )

        close_5_ties = sum(
            r["actual_result"] == "T"
            for r in close_5
        )

        close_10_wins = sum(
            r["actual_result"] == "W"
            for r in close_10
        )

        close_10_ties = sum(
            r["actual_result"] == "T"
            for r in close_10
        )

        blowout_20_wins = sum(
            r["margin"] >= 20
            for r in blowout_20
        )

        blowout_30_wins = sum(
            r["margin"] >= 30
            for r in blowout_30
        )

        median_plus_wins = 0
        median_plus_losses = 0
        median_plus_ties = 0

        for r in rows:

            period_observations = weekly[
                (
                    season,
                    r["person_id"],
                )
            ]

            # Get all scores for this specific scoring period.
            period_scores = []

            for (
                key,
                candidates,
            ) in weekly.items():

                if (
                    key[0] == season
                    and any(
                        x["period"]
                        == r["period"]
                        for x in candidates
                    )
                ):
                    period_scores.extend(
                        x["score"]
                        for x in candidates
                        if x["period"]
                        == r["period"]
                    )

            if not period_scores:
                continue

            median = statistics.median(
                period_scores
            )

            if r["score"] > median + 0.01:
                median_plus_wins += 1

            elif r["score"] < median - 0.01:
                median_plus_losses += 1

            else:
                median_plus_ties += 1

        regular_season_games = len(
            rows
        )

        actual_win_pct = (
            (
                actual_wins
                + 0.5 * actual_ties
            )
            / regular_season_games
            if regular_season_games
            else None
        )

        all_play_win_pct = (
            (
                all_play_wins
                + 0.5 * all_play_ties
            )
            / all_play_games
            if all_play_games
            else None
        )

        row = {
            "season": season,
            "person_id": person_id,
            "person_name": names.get(
                person_id,
                person_id,
            ),
            "regular_season_games": regular_season_games,
            "actual_wins": actual_wins,
            "actual_losses": actual_losses,
            "actual_ties": actual_ties,
            "actual_win_pct": actual_win_pct,
            "points_for": sum(scores),
            "points_against": sum(
                opponent_scores
            ),
            "points_per_game": (
                statistics.mean(scores)
                if scores
                else None
            ),
            "median_score": (
                statistics.median(scores)
                if scores
                else None
            ),
            "score_std_dev": (
                statistics.stdev(scores)
                if len(scores) > 1
                else 0.0
            ),
            "best_score": (
                max(scores)
                if scores
                else None
            ),
            "worst_score": (
                min(scores)
                if scores
                else None
            ),
            "point_differential": sum(
                margins
            ),
            "all_play_wins": all_play_wins,
            "all_play_ties": all_play_ties,
            "all_play_games": all_play_games,
            "all_play_win_pct": all_play_win_pct,
            "expected_wins": expected_wins,
            "schedule_luck": (
                actual_wins
                + 0.5 * actual_ties
                - expected_wins
            ),
            "opponent_points_per_game": (
                statistics.mean(
                    opponent_scores
                )
                if opponent_scores
                else None
            ),
            "opponent_median_score": (
                statistics.median(
                    opponent_scores
                )
                if opponent_scores
                else None
            ),
            "close_games_5": len(
                close_5
            ),
            "close_games_5_wins": (
                close_5_wins
            ),
            "close_game_win_pct_5": (
                (
                    close_5_wins
                    + 0.5 * close_5_ties
                )
                / len(close_5)
                if close_5
                else None
            ),
            "close_games_10": len(
                close_10
            ),
            "close_games_10_wins": (
                close_10_wins
            ),
            "close_game_win_pct_10": (
                (
                    close_10_wins
                    + 0.5 * close_10_ties
                )
                / len(close_10)
                if close_10
                else None
            ),
            "blowout_wins_20": (
                blowout_20_wins
            ),
            "blowout_wins_30": (
                blowout_30_wins
            ),
            "blowout_games_20": len(
                blowout_20
            ),
            "blowout_games_30": len(
                blowout_30
            ),
            "median_plus_wins": (
                median_plus_wins
            ),
            "median_plus_losses": (
                median_plus_losses
            ),
            "median_plus_ties": (
                median_plus_ties
            ),
            "median_plus_win_pct": (
                (
                    median_plus_wins
                    + 0.5
                    * median_plus_ties
                )
                / regular_season_games
                if regular_season_games
                else None
            ),
        }

        season_rows.append(
            row
        )

    return season_rows


def build_career_rows(
    historical_rows,
    historical_regular,
    team_person,
    names,
):
    """
    Aggregate completed-season advanced metrics into
    career owner profiles.
    """

    career = defaultdict(list)

    for row in historical_rows:
        career[
            row["person_id"]
        ].append(row)

    career_rows = []

    for (
        person_id,
        rows,
    ) in sorted(career.items()):

        total_games = sum(
            r["regular_season_games"]
            for r in rows
        )

        actual_wins = sum(
            r["actual_wins"]
            for r in rows
        )

        actual_losses = sum(
            r["actual_losses"]
            for r in rows
        )

        actual_ties = sum(
            r["actual_ties"]
            for r in rows
        )

        all_play_games = sum(
            r["all_play_games"]
            for r in rows
        )

        all_play_wins = sum(
            r["all_play_wins"]
            for r in rows
        )

        all_play_ties = sum(
            r["all_play_ties"]
            for r in rows
        )

        expected_wins = sum(
            r["expected_wins"]
            for r in rows
        )

        all_scores = []
        opponent_scores = []

        for m in historical_regular:

            home_person = team_person.get(
                (
                    m["season"],
                    m["home_team_id"],
                )
            )

            away_person = team_person.get(
                (
                    m["season"],
                    m["away_team_id"],
                )
            )

            if home_person == person_id:

                all_scores.append(
                    float(
                        m["home_score"]
                    )
                )

                opponent_scores.append(
                    float(
                        m["away_score"]
                    )
                )

            elif away_person == person_id:

                all_scores.append(
                    float(
                        m["away_score"]
                    )
                )

                opponent_scores.append(
                    float(
                        m["home_score"]
                    )
                )

        actual_win_pct = (
            (
                actual_wins
                + 0.5 * actual_ties
            )
            / total_games
            if total_games
            else None
        )

        all_play_win_pct = (
            (
                all_play_wins
                + 0.5 * all_play_ties
            )
            / all_play_games
            if all_play_games
            else None
        )

        career_rows.append(
            {
                "person_id": person_id,
                "person_name": names.get(
                    person_id,
                    person_id,
                ),
                "seasons": len(rows),
                "regular_season_games": total_games,
                "actual_wins": actual_wins,
                "actual_losses": actual_losses,
                "actual_ties": actual_ties,
                "actual_win_pct": actual_win_pct,
                "points_for": sum(
                    r["points_for"]
                    for r in rows
                ),
                "points_against": sum(
                    r["points_against"]
                    for r in rows
                ),
                "points_per_game": (
                    statistics.mean(
                        all_scores
                    )
                    if all_scores
                    else None
                ),
                "median_score": (
                    statistics.median(
                        all_scores
                    )
                    if all_scores
                    else None
                ),
                "score_std_dev": (
                    statistics.stdev(
                        all_scores
                    )
                    if len(all_scores) > 1
                    else 0.0
                ),
                "point_differential": sum(
                    r["point_differential"]
                    for r in rows
                ),
                "all_play_wins": all_play_wins,
                "all_play_ties": all_play_ties,
                "all_play_games": all_play_games,
                "all_play_win_pct": (
                    all_play_win_pct
                ),
                "expected_wins": expected_wins,
                "schedule_luck": (
                    actual_wins
                    + 0.5 * actual_ties
                    - expected_wins
                ),
                "opponent_points_per_game": (
                    statistics.mean(
                        opponent_scores
                    )
                    if opponent_scores
                    else None
                ),
                "close_games_5": sum(
                    r["close_games_5"]
                    for r in rows
                ),
                "close_games_5_wins": sum(
                    r["close_games_5_wins"]
                    for r in rows
                ),
                "close_games_10": sum(
                    r["close_games_10"]
                    for r in rows
                ),
                "close_games_10_wins": sum(
                    r["close_games_10_wins"]
                    for r in rows
                ),
                "blowout_wins_20": sum(
                    r["blowout_wins_20"]
                    for r in rows
                ),
                "blowout_wins_30": sum(
                    r["blowout_wins_30"]
                    for r in rows
                ),
            }
        )

    return career_rows


def main():

    people = load(
        "people.json"
    )

    teams = load(
        "teams.json"
    )

    matchups = load(
        "matchups.json"
    )

    names = {
        p["person_id"]:
        p.get(
            "name",
            p["person_id"],
        )
        for p in people
    }

    team_person = {
        (
            t["season"],
            t["team_id"],
        ):
        t.get("person_id")
        for t in teams
    }

    all_seasons = sorted(
        {
            m["season"]
            for m in matchups
        }
    )

    historical_seasons = completed_seasons(
        matchups
    )

    current_seasons = [
        s
        for s in all_seasons
        if s not in historical_seasons
    ]

    current_season = (
        max(current_seasons)
        if current_seasons
        else None
    )

    played = completed_matchups(
        matchups
    )

    historical_games = [
        m
        for m in played
        if m["season"]
        in historical_seasons
    ]

    current_games = [
        m
        for m in played
        if m["season"]
        == current_season
    ] if current_season is not None else []

    historical_regular = [
        m
        for m in historical_games
        if m.get("playoff_tier_type")
        == "NONE"
    ]

    current_regular = [
        m
        for m in current_games
        if m.get("playoff_tier_type")
        == "NONE"
    ]

    # ---------------------------------------------------------
    # WEEKLY OBSERVATIONS
    # ---------------------------------------------------------

    historical_weekly = build_weekly_observations(
        historical_regular,
        team_person,
    )

    current_weekly = build_weekly_observations(
        current_regular,
        team_person,
    )

    # ---------------------------------------------------------
    # SEASON ROWS
    # ---------------------------------------------------------

    historical_rows = build_season_rows(
        historical_weekly,
        names,
    )

    current_rows = build_season_rows(
        current_weekly,
        names,
    )

    # ---------------------------------------------------------
    # CAREER ROWS
    # ---------------------------------------------------------

    career_rows = build_career_rows(
        historical_rows,
        historical_regular,
        team_person,
        names,
    )

    # ---------------------------------------------------------
    # FLATTEN WEEKLY DATA
    # ---------------------------------------------------------

    historical_weekly_rows = []

    for key in sorted(
        historical_weekly
    ):

        historical_weekly_rows.extend(
            historical_weekly[key]
        )

    current_weekly_rows = []

    for key in sorted(
        current_weekly
    ):

        current_weekly_rows.extend(
            current_weekly[key]
        )

    # ---------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------

    meta = {
        "historical_seasons":
            historical_seasons,

        "current_season":
            current_season,

        "historical_excludes_current":
            True,

        "scope":
            "regular_season_only",

        "definitions": {

            "all_play_win_pct":
                (
                    "For each regular-season scoring "
                    "period, compare a team's score "
                    "against every other team's score "
                    "that period. Wins count as 1 and "
                    "ties count as 0.5."
                ),

            "expected_wins":
                (
                    "Sum of weekly all-play win "
                    "percentages."
                ),

            "schedule_luck":
                (
                    "Actual W-L equivalent minus "
                    "expected wins. Ties count as 0.5."
                ),

            "strength_of_schedule":
                (
                    "Opponent scoring metrics from "
                    "actual regular-season opponents."
                ),

            "median_plus_win_pct":
                (
                    "Weekly record against the "
                    "league scoring median."
                ),

            "close_game_5":
                (
                    "Games decided by 5.0 points "
                    "or fewer."
                ),

            "close_game_10":
                (
                    "Games decided by 10.0 points "
                    "or fewer."
                ),

            "blowout_20":
                (
                    "Games decided by 20.0 points "
                    "or more."
                ),

            "blowout_30":
                (
                    "Games decided by 30.0 points "
                    "or more."
                ),

            "score_std_dev":
                (
                    "Sample standard deviation of "
                    "weekly regular-season scores."
                ),
        },
    }

    historical_output = {
        "meta":
            meta,

        "season":
            historical_rows,

        "career":
            career_rows,

        "weekly":
            historical_weekly_rows,
    }

    current_output = {
        "season":
            current_season,

        "standings":
            current_rows,

        "weekly":
            current_weekly_rows,

        "meta":
            meta,
    }

    save(
        "advanced_stats.json",
        historical_output,
    )

    save(
        "current_advanced_stats.json",
        current_output,
    )

    # ---------------------------------------------------------
    # REPORT
    # ---------------------------------------------------------

    print(
        "=== ADVANCED ANALYTICS ENGINE ==="
    )

    print(
        f"Historical seasons: "
        f"{historical_seasons[0]}-"
        f"{historical_seasons[-1]} "
        f"({len(historical_seasons)})"
    )

    print(
        f"Current season: "
        f"{current_season}"
    )

    print(
        f"Historical owner-season rows: "
        f"{len(historical_rows)}"
    )

    print(
        f"Historical weekly observations: "
        f"{len(historical_weekly_rows)}"
    )

    print(
        f"Career owner rows: "
        f"{len(career_rows)}"
    )

    print(
        f"Current owner-season rows: "
        f"{len(current_rows)}"
    )

    print(
        "\nWrote:"
    )

    print(
        f"  {ANALYTICS / 'advanced_stats.json'}"
    )

    print(
        f"  {ANALYTICS / 'current_advanced_stats.json'}"
    )

    # ---------------------------------------------------------
    # SANITY CHECKS
    # ---------------------------------------------------------

    print(
        "\n=== SANITY CHECKS ==="
    )

    assert all(
        r["season"]
        in historical_seasons
        for r in historical_rows
    )

    assert all(
        r["season"]
        in historical_seasons
        for r in historical_weekly_rows
    )

    if current_season is not None:

        assert all(
            r["season"]
            == current_season
            for r in current_rows
        )

        assert all(
            r["season"]
            == current_season
            for r in current_weekly_rows
        )

    # All-play opponent count must equal
    # league size minus the team itself.
    assert all(
        r["all_play_opponents"]
        == r["league_size"] - 1

        for r in historical_weekly_rows

        if r["league_size"] > 0
    )

    # W/L/T must reconcile to games.
    assert all(
        (
            r["actual_wins"]
            + r["actual_losses"]
            + r["actual_ties"]
        )
        == r["regular_season_games"]

        for r in historical_rows
    )

    # Each weekly all-play record must have
    # a sensible range.
    assert all(
        0
        <= r["all_play_win_pct"]
        <= 1

        for r in historical_weekly_rows

        if r["all_play_win_pct"]
        is not None
    )

    print(
        "PASS: historical/current separation"
    )

    print(
        "PASS: all-play opponent counts"
    )

    print(
        "PASS: season W/L/T reconciliation"
    )

    print(
        "PASS: all-play percentages valid"
    )

    print(
        "PASS: advanced analytics engine completed"
    )


if __name__ == "__main__":
    main()