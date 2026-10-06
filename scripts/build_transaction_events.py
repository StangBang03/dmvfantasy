import json
from pathlib import Path

SOURCE_DIR = Path("data/raw/transactions")
OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "transaction_events.json"
SUPPLEMENTAL_FILE = OUTPUT_DIR / "supplemental_trade_events.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_team_id(team_id):
    """
    ESPN uses negative/zero values to represent no actual fantasy team.

    -1 = free agent / no previous team
     0 = no destination team
    """
    if team_id is None:
        return None

    if team_id in (-1, 0):
        return None

    return team_id


def effective_date(tx):
    """Use processDate when present, otherwise proposedDate."""
    if tx.get("processDate"):
        return tx.get("processDate"), "processDate"

    if tx.get("proposedDate"):
        return tx.get("proposedDate"), "proposedDate"

    return None, "none"


def make_event(
    *,
    year,
    scoring_period,
    transaction_index,
    item_index,
    transaction_id,
    transaction_type,
    status,
    player_id,
    action,
    from_team_id,
    to_team_id,
    raw_from_team_id=None,
    raw_to_team_id=None,
    process_date=None,
    proposed_date=None,
    effective_date_value=None,
    effective_date_source="none",
    supplemental=False,
    verification_source=None,
):
    return {
        "season": year,
        "scoring_period": scoring_period,
        "transaction_index": transaction_index,
        "item_index": item_index,
        "transaction_id": transaction_id,
        "transaction_type": transaction_type,
        "status": status,
        "player_id": player_id,
        "action": action,
        "from_team_id": from_team_id,
        "to_team_id": to_team_id,
        "raw_from_team_id": raw_from_team_id,
        "raw_to_team_id": raw_to_team_id,
        "process_date": process_date,
        "proposed_date": proposed_date,
        "effective_date": effective_date_value,
        "effective_date_source": effective_date_source,
        "supplemental": supplemental,
        "verification_source": verification_source,
    }


def build_related_trade_items(all_transactions):
    """
    Some TRADE_UPHOLD records have no items but point back to a
    TRADE_ACCEPT transaction through relatedTransactionId.

    Build a lookup so the executed TRADE_UPHOLD can recover those
    trade legs when necessary.
    """
    by_id = {}

    for tx in all_transactions:
        tx_id = tx.get("id")
        if tx_id:
            by_id[tx_id] = tx

    return by_id


def main():
    print("=" * 70)
    print("BUILD TRANSACTION EVENTS")
    print("=" * 70)

    events = []

    source_transactions = 0
    executed_transactions = 0
    ignored_transactions = 0
    ignored_items = 0

    action_counts = {
        "ADD": 0,
        "DROP": 0,
        "TRADE": 0,
    }

    transaction_type_counts = {}

    effective_date_sources = {
        "processDate": 0,
        "proposedDate": 0,
        "none": 0,
    }

    # ------------------------------------------------------------
    # Load all source transactions first.
    # This lets us resolve TRADE_UPHOLD -> TRADE_ACCEPT relationships.
    # ------------------------------------------------------------

    source_rows = []

    for year_dir in sorted(SOURCE_DIR.iterdir()):
        if not year_dir.is_dir():
            continue

        year = int(year_dir.name)

        for file in sorted(year_dir.glob("scoring_period_*.json")):
            scoring_period = int(file.stem.split("_")[-1])

            data = load_json(file)

            transactions = data.get("transactions", [])

            for transaction_index, tx in enumerate(transactions):
                source_rows.append(
                    {
                        "year": year,
                        "scoring_period": scoring_period,
                        "transaction_index": transaction_index,
                        "tx": tx,
                    }
                )

    all_transactions = [row["tx"] for row in source_rows]
    tx_by_id = build_related_trade_items(all_transactions)

    print(f"Source transaction records loaded: {len(source_rows)}")

    # ------------------------------------------------------------
    # Convert ESPN transactions into ownership events.
    # ------------------------------------------------------------

    for row in source_rows:
        year = row["year"]
        scoring_period = row["scoring_period"]
        transaction_index = row["transaction_index"]
        tx = row["tx"]

        source_transactions += 1

        tx_type = tx.get("type")
        status = tx.get("status")

        transaction_type_counts[tx_type] = (
            transaction_type_counts.get(tx_type, 0) + 1
        )

        # Only executed transactions can change actual ownership.
        if status != "EXECUTED":
            ignored_transactions += 1
            continue

        executed_transactions += 1

        transaction_id = tx.get("id")

        items = tx.get("items", [])

        # --------------------------------------------------------
        # TRADE_UPHOLD special case.
        #
        # Some executed TRADE_UPHOLD records contain no items and
        # reference a preceding TRADE_ACCEPT containing the trade legs.
        # --------------------------------------------------------

        if (
            tx_type == "TRADE_UPHOLD"
            and not items
            and tx.get("relatedTransactionId")
        ):
            related_id = tx.get("relatedTransactionId")
            related_tx = tx_by_id.get(related_id)

            if related_tx:
                items = related_tx.get("items", [])

        for item_index, item in enumerate(items):
            item_type = item.get("type")

            # Lineup changes do not affect ownership.
            if item_type == "LINEUP":
                ignored_items += 1
                continue

            # Only actual ownership-changing items.
            if item_type not in {
                "ADD",
                "DROP",
                "TRADE",
                "DRAFT",
            }:
                ignored_items += 1
                continue

            # Draft ownership is handled by validated mDraftDetail data.
            if item_type == "DRAFT":
                ignored_items += 1
                continue

            player_id = item.get("playerId")

            if player_id is None:
                raise ValueError(
                    f"Missing playerId in "
                    f"{year}/scoring_period_{scoring_period}.json "
                    f"transaction {transaction_id}"
                )

            from_team_id = normalize_team_id(
                item.get("fromTeamId")
            )

            to_team_id = normalize_team_id(
                item.get("toTeamId")
            )

            process_date = tx.get("processDate")
            proposed_date = tx.get("proposedDate")

            effective_value, effective_source = effective_date(tx)

            event = make_event(
                year=year,
                scoring_period=scoring_period,
                transaction_index=transaction_index,
                item_index=item_index,
                transaction_id=transaction_id,
                transaction_type=tx_type,
                status=status,
                player_id=player_id,
                action=item_type,
                from_team_id=from_team_id,
                to_team_id=to_team_id,
                raw_from_team_id=item.get("fromTeamId"),
                raw_to_team_id=item.get("toTeamId"),
                process_date=process_date,
                proposed_date=proposed_date,
                effective_date_value=effective_value,
                effective_date_source=effective_source,
            )

            events.append(event)

            action_counts[item_type] += 1

            if effective_source in effective_date_sources:
                effective_date_sources[effective_source] += 1

    # ------------------------------------------------------------
    # Load verified supplemental trade legs.
    #
    # These are real ESPN-verified trades that are absent from the
    # normal mTransactions2 ownership event stream.
    # ------------------------------------------------------------

    supplemental_count = 0
    supplemental_duplicates = 0

    if SUPPLEMENTAL_FILE.exists():
        supplemental = load_json(SUPPLEMENTAL_FILE)

        # Existing event identity used to prevent accidental duplication.
        existing_trade_keys = {
            (
                event["season"],
                event["scoring_period"],
                event["player_id"],
                event["from_team_id"],
                event["to_team_id"],
            )
            for event in events
            if event["action"] == "TRADE"
        }

        # Give supplemental events a negative transaction index so they
        # occur before normal same-period waiver/free-agent activity.
        #
        # We know the verified trade happened during the scoring period,
        # but the missing source event does not provide a usable primary
        # transaction timestamp. Placing it at the start of that scoring
        # period preserves the required ownership transition before later
        # drops/adds that caused the validation failures.
        #
        # item_index is only used to keep multiple supplemental legs stable.
        supplemental_position_by_period = {}

        for trade in supplemental:
            season = int(trade["season"])
            scoring_period = int(trade["scoring_period"])
            player_id = int(trade["player_id"])
            from_team_id = normalize_team_id(
                trade.get("from_team_id")
            )
            to_team_id = normalize_team_id(
                trade.get("to_team_id")
            )

            key = (
                season,
                scoring_period,
                player_id,
                from_team_id,
                to_team_id,
            )

            if key in existing_trade_keys:
                supplemental_duplicates += 1
                continue

            position = supplemental_position_by_period.get(
                (season, scoring_period),
                0,
            )

            event = make_event(
                year=season,
                scoring_period=scoring_period,
                transaction_index=-100000 - position,
                item_index=position,
                transaction_id=trade.get(
                    "transaction_id",
                    f"SUPP-{season}-{scoring_period}-{player_id}",
                ),
                transaction_type="SUPPLEMENTAL_TRADE",
                status="EXECUTED",
                player_id=player_id,
                action="TRADE",
                from_team_id=from_team_id,
                to_team_id=to_team_id,
                raw_from_team_id=from_team_id,
                raw_to_team_id=to_team_id,
                process_date=None,
                proposed_date=None,
                effective_date_value=None,
                effective_date_source="none",
                supplemental=True,
                verification_source=trade.get(
                    "verification_source"
                ),
            )

            events.append(event)
            existing_trade_keys.add(key)

            supplemental_count += 1
            supplemental_position_by_period[
                (season, scoring_period)
            ] = position + 1

    else:
        print()
        print(
            f"WARNING: supplemental file not found: "
            f"{SUPPLEMENTAL_FILE}"
        )

    # ------------------------------------------------------------
    # Sort events.
    #
    # Primary ordering is season/scoring period, then effective date
    # where available. For records without a date, transaction_index
    # preserves ESPN's source ordering. Supplemental events have a
    # deliberately negative transaction index so they precede later
    # same-period transactions.
    # ------------------------------------------------------------

    events.sort(
        key=lambda x: (
            x["season"],
            x["scoring_period"],
            x["transaction_index"],
            x["item_index"],
        )
    )

    # ------------------------------------------------------------
    # Write output.
    # ------------------------------------------------------------

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            events,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # ------------------------------------------------------------
    # Summary.
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(
        f"Source transactions:       {source_transactions}"
    )

    print(
        f"Executed transactions:     {executed_transactions}"
    )

    print(
        f"Ignored transactions:      {ignored_transactions}"
    )

    print(
        f"Ownership events:          {len(events)}"
    )

    print(
        f"Ignored items:             {ignored_items}"
    )

    print()
    print("OWNERSHIP EVENTS")

    for action, count in action_counts.items():
        # Include supplemental trades in the TRADE count.
        if action == "TRADE":
            count = sum(
                1
                for event in events
                if event["action"] == "TRADE"
            )

        print(
            f"  {action:8s} {count:5d}"
        )

    print()
    print("SUPPLEMENTAL TRADES")
    print(
        f"  Loaded:                  {supplemental_count:5d}"
    )
    print(
        f"  Duplicates skipped:      {supplemental_duplicates:5d}"
    )

    print()
    print("TRANSACTION TYPES SEEN")

    for tx_type, count in sorted(
        transaction_type_counts.items(),
        key=lambda x: (-x[1], str(x[0])),
    ):
        print(
            f"  {str(tx_type):20s} {count:5d}"
        )

    print()
    print("EFFECTIVE DATE SOURCES")

    for source, count in effective_date_sources.items():
        print(
            f"  {source:20s} {count:5d}"
        )

    print()
    print(f"Wrote: {OUTPUT_FILE}")

    print()
    print("=" * 70)
    print("TRANSACTION EVENT BUILD COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
