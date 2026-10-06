import json
from pathlib import Path
from collections import defaultdict

PROCESSED_DIR = Path("data/processed")

DRAFT_FILE = PROCESSED_DIR / "draft_picks.json"
EVENT_FILE = PROCESSED_DIR / "transaction_events.json"

OUTPUT_FILE = PROCESSED_DIR / "ownership_ledger.json"
ISSUES_FILE = PROCESSED_DIR / "ownership_ledger_issues.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def event_sort_key(event):
    """
    Sort ownership events using the best chronological timestamp
    available from ESPN.

    Priority:
      1. effective_date
         - processDate when available
         - proposedDate when processDate is missing
      2. transaction_index
      3. item_index

    The season and scoring period are included so events never
    cross those boundaries.
    """

    effective_date = event.get("effective_date")

    return (
        event["season"],
        event["scoring_period"],

        # Timestamped events first.
        effective_date is None,

        # Best available chronological timestamp.
        effective_date
        if effective_date is not None
        else 0,

        # Stable fallback/tie-breakers.
        event.get("transaction_index", 0),
        event.get("item_index", 0),
    )


def main():

    print("=" * 70)
    print("BUILD OWNERSHIP LEDGER")
    print("=" * 70)

    drafts = load_json(DRAFT_FILE)
    events = load_json(EVENT_FILE)

    print(f"Draft picks loaded:       {len(drafts)}")
    print(f"Transaction events:       {len(events)}")

    # ------------------------------------------------------------
    # Seed ownership from the validated draft data.
    #
    # Key:
    #   (season, player_id)
    #
    # Value:
    #   team that drafted the player
    # ------------------------------------------------------------

    draft_ownership = {}

    draft_rows_by_player = defaultdict(list)

    for draft in drafts:

        season = draft["season"]
        player_id = draft["player_id"]
        team_id = draft["team_id"]

        key = (season, player_id)

        draft_rows_by_player[key].append(draft)

        # A player should normally have one draft owner
        # within a season.
        if key in draft_ownership:

            existing = draft_ownership[key]

            if existing != team_id:
                raise ValueError(
                    f"Player drafted by multiple teams: "
                    f"season={season}, "
                    f"player={player_id}, "
                    f"teams={existing},{team_id}"
                )

        else:
            draft_ownership[key] = team_id

    print(
        f"Unique drafted player-seasons: "
        f"{len(draft_ownership)}"
    )

    # ------------------------------------------------------------
    # Group transaction events by season/player.
    # ------------------------------------------------------------

    events_by_player = defaultdict(list)

    for event in events:

        key = (
            event["season"],
            event["player_id"],
        )

        events_by_player[key].append(event)

    for key in events_by_player:
        events_by_player[key].sort(
            key=event_sort_key
        )

    # ------------------------------------------------------------
    # Build ownership intervals.
    # ------------------------------------------------------------

    ledger = []
    issues = []

    seasons = sorted(
        set(
            season
            for season, _ in draft_ownership.keys()
        )
        |
        set(
            season
            for season, _ in events_by_player.keys()
        )
    )

    for season in seasons:

        player_ids = set()

        player_ids.update(
            player_id
            for (
                event_season,
                player_id
            ) in events_by_player.keys()
            if event_season == season
        )

        player_ids.update(
            player_id
            for (
                draft_season,
                player_id
            ) in draft_ownership.keys()
            if draft_season == season
        )

        print()
        print(
            f"Processing {season}: "
            f"{len(player_ids)} players"
        )

        for player_id in sorted(player_ids):

            key = (season, player_id)

            drafted_team = draft_ownership.get(key)

            player_events = events_by_player.get(
                key,
                []
            )

            # ----------------------------------------------------
            # Players not drafted but appearing in transactions
            # are waiver/free-agent additions.
            # ----------------------------------------------------

            current_team = drafted_team

            current_start_period = 1 if drafted_team else None
            current_start_event = None

            intervals = []

            # ----------------------------------------------------
            # If the player wasn't drafted, ownership begins with
            # the first ADD event.
            # ----------------------------------------------------

            for event in player_events:

                action = event["action"]

                from_team = event["from_team_id"]
                to_team = event["to_team_id"]

                scoring_period = event[
                    "scoring_period"
                ]

                # ------------------------------------------------
                # ADD
                # ------------------------------------------------

                if action == "ADD":

                    if current_team is not None:

                        issues.append({
                            "type": "ADD_WHILE_OWNED",
                            "season": season,
                            "player_id": player_id,
                            "current_team_id": current_team,
                            "new_team_id": to_team,
                            "event": event,
                        })

                        # Do not silently overwrite ownership.
                        continue

                    if to_team is None:

                        issues.append({
                            "type": "ADD_WITHOUT_DESTINATION",
                            "season": season,
                            "player_id": player_id,
                            "event": event,
                        })

                        continue

                    current_team = to_team
                    current_start_period = scoring_period
                    current_start_event = event

                # ------------------------------------------------
                # DROP
                # ------------------------------------------------

                elif action == "DROP":

                    if current_team is None:

                        issues.append({
                            "type": "DROP_WHILE_UNOWNED",
                            "season": season,
                            "player_id": player_id,
                            "drop_team_id": from_team,
                            "event": event,
                        })

                        continue

                    if from_team != current_team:

                        issues.append({
                            "type": "DROP_FROM_WRONG_TEAM",
                            "season": season,
                            "player_id": player_id,
                            "current_team_id": current_team,
                            "event_from_team_id": from_team,
                            "event": event,
                        })

                        continue

                    intervals.append({
                        "season": season,
                        "player_id": player_id,
                        "team_id": current_team,
                        "start_scoring_period":
                            current_start_period,
                        "end_scoring_period":
                            scoring_period,
                        "start_transaction_id":
                            (
                                current_start_event[
                                    "transaction_id"
                                ]
                                if current_start_event
                                else None
                            ),
                        "end_transaction_id":
                            event["transaction_id"],
                        "end_action": "DROP",
                    })

                    current_team = None
                    current_start_period = None
                    current_start_event = None

                # ------------------------------------------------
                # TRADE
                # ------------------------------------------------

                elif action == "TRADE":

                    if current_team is None:

                        issues.append({
                            "type": "TRADE_WHILE_UNOWNED",
                            "season": season,
                            "player_id": player_id,
                            "event": event,
                        })

                        continue

                    if from_team != current_team:

                        issues.append({
                            "type": "TRADE_FROM_WRONG_TEAM",
                            "season": season,
                            "player_id": player_id,
                            "current_team_id": current_team,
                            "event_from_team_id": from_team,
                            "event": event,
                        })

                        continue

                    if to_team is None:

                        issues.append({
                            "type": "TRADE_WITHOUT_DESTINATION",
                            "season": season,
                            "player_id": player_id,
                            "event": event,
                        })

                        continue

                    # Close old ownership interval.
                    intervals.append({
                        "season": season,
                        "player_id": player_id,
                        "team_id": current_team,
                        "start_scoring_period":
                            current_start_period,
                        "end_scoring_period":
                            scoring_period,
                        "start_transaction_id":
                            (
                                current_start_event[
                                    "transaction_id"
                                ]
                                if current_start_event
                                else None
                            ),
                        "end_transaction_id":
                            event["transaction_id"],
                        "end_action": "TRADE",
                    })

                    # Begin new ownership.
                    current_team = to_team
                    current_start_period = scoring_period
                    current_start_event = event

            # ----------------------------------------------------
            # Close ownership at end of season if still owned.
            # ----------------------------------------------------

            if current_team is not None:

                intervals.append({
                    "season": season,
                    "player_id": player_id,
                    "team_id": current_team,
                    "start_scoring_period":
                        current_start_period,
                    "end_scoring_period":
                        None,
                    "start_transaction_id":
                        (
                            current_start_event[
                                "transaction_id"
                            ]
                            if current_start_event
                            else None
                        ),
                    "end_transaction_id":
                        None,
                    "end_action":
                        "SEASON_END",
                })

            ledger.extend(intervals)

    # ------------------------------------------------------------
    # Sort final ledger
    # ------------------------------------------------------------

    ledger.sort(
        key=lambda row: (
            row["season"],
            row["player_id"],
            row["start_scoring_period"],
            row["team_id"],
        )
    )

    # ------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            ledger,
            f,
            indent=2,
            ensure_ascii=False
        )

    with ISSUES_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            issues,
            f,
            indent=2,
            ensure_ascii=False
        )

    # ------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------

    unique_player_seasons = set(
        (
            row["season"],
            row["player_id"]
        )
        for row in ledger
    )

    teams = set(
        row["team_id"]
        for row in ledger
    )

    season_counts = defaultdict(int)

    for row in ledger:
        season_counts[row["season"]] += 1

    print()
    print("=" * 70)
    print("LEDGER SUMMARY")
    print("=" * 70)

    print(
        f"Ownership intervals:       {len(ledger)}"
    )

    print(
        f"Player-seasons:            "
        f"{len(unique_player_seasons)}"
    )

    print(
        f"Teams represented:         "
        f"{len(teams)}"
    )

    print()
    print("INTERVALS BY SEASON")

    for season in sorted(season_counts):
        print(
            f"  {season}: "
            f"{season_counts[season]}"
        )

    # ------------------------------------------------------------
    # Issue summary
    # ------------------------------------------------------------

    issue_counts = defaultdict(int)

    for issue in issues:
        issue_counts[issue["type"]] += 1

    print()
    print("=" * 70)
    print("VALIDATION")
    print("=" * 70)

    if not issues:

        print(
            "PASS: no ownership consistency issues"
        )

    else:

        print(
            f"WARNING: {len(issues)} ownership issues"
        )

        print()
        print("ISSUE TYPES:")

        for issue_type, count in sorted(
            issue_counts.items(),
            key=lambda x: (-x[1], x[0])
        ):
            print(
                f"  {issue_type:30s} {count:5d}"
            )

        print()
        print("FIRST 20 ISSUES:")

        for issue in issues[:20]:

            print(
                json.dumps(
                    issue,
                    indent=2,
                    ensure_ascii=False
                )
            )

    print()
    print(f"Wrote: {OUTPUT_FILE}")
    print(f"Wrote: {ISSUES_FILE}")

    print()
    print("=" * 70)
    print("OWNERSHIP LEDGER COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()