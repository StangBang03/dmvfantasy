import json
from pathlib import Path
from collections import Counter, defaultdict

TRANSACTION_DIR = Path("data/raw/transactions")


def main():
    print("=" * 70)
    print("ESPN TRANSACTION ANALYSIS")
    print("=" * 70)

    all_transaction_ids = defaultdict(list)

    overall_types = Counter()
    overall_statuses = Counter()
    overall_item_types = Counter()

    overall_transactions = 0
    overall_items = 0

    yearly = {}

    for year_dir in sorted(TRANSACTION_DIR.iterdir()):

        if not year_dir.is_dir():
            continue

        year = int(year_dir.name)

        type_counts = Counter()
        status_counts = Counter()
        item_counts = Counter()

        transaction_count = 0
        item_count = 0

        multi_item_transactions = 0
        weird_transactions = []

        for file in sorted(year_dir.glob("scoring_period_*.json")):

            scoring_period = int(
                file.stem.split("_")[-1]
            )

            with file.open(
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            transactions = data.get(
                "transactions",
                []
            )

            for tx in transactions:

                tx_id = tx.get("id")
                tx_type = tx.get("type")
                status = tx.get("status")
                items = tx.get("items", [])

                transaction_count += 1
                overall_transactions += 1

                type_counts[tx_type] += 1
                status_counts[status] += 1

                overall_types[tx_type] += 1
                overall_statuses[status] += 1

                if len(items) > 1:
                    multi_item_transactions += 1

                if tx_id:
                    all_transaction_ids[tx_id].append(
                        (year, scoring_period)
                    )

                for item in items:

                    item_type = item.get("type")

                    item_count += 1
                    overall_items += 1

                    item_counts[item_type] += 1
                    overall_item_types[item_type] += 1

                    from_team = item.get("fromTeamId")
                    to_team = item.get("toTeamId")
                    player_id = item.get("playerId")

                    if (
                        player_id is None
                        or from_team is None
                        or to_team is None
                    ):
                        weird_transactions.append({
                            "file": str(file),
                            "transaction_id": tx_id,
                            "transaction_type": tx_type,
                            "item_type": item_type,
                            "player_id": player_id,
                            "from_team_id": from_team,
                            "to_team_id": to_team,
                        })

        yearly[year] = {
            "transactions": transaction_count,
            "items": item_count,
            "types": type_counts,
            "statuses": status_counts,
            "item_types": item_counts,
            "multi_item": multi_item_transactions,
            "weird": weird_transactions,
        }

    # ------------------------------------------------------------
    # YEARLY SUMMARY
    # ------------------------------------------------------------

    print()
    print("YEARLY SUMMARY")
    print("-" * 70)

    for year, data in yearly.items():

        print(
            f"{year}: "
            f"{data['transactions']} transactions, "
            f"{data['items']} items, "
            f"{data['multi_item']} multi-item"
        )

        print(
            "    types: "
            + ", ".join(
                f"{k}={v}"
                for k, v in data["types"].most_common()
            )
        )

        print(
            "    items: "
            + ", ".join(
                f"{k}={v}"
                for k, v in data["item_types"].most_common()
            )
        )

        print(
            "    status: "
            + ", ".join(
                f"{k}={v}"
                for k, v in data["statuses"].most_common()
            )
        )

    # ------------------------------------------------------------
    # OVERALL
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("OVERALL")
    print("=" * 70)

    print(f"Transactions: {overall_transactions}")
    print(f"Items:        {overall_items}")

    print()
    print("TRANSACTION TYPES")

    for key, value in overall_types.most_common():
        print(f"  {str(key):15s} {value:5d}")

    print()
    print("TRANSACTION STATUSES")

    for key, value in overall_statuses.most_common():
        print(f"  {str(key):15s} {value:5d}")

    print()
    print("ITEM TYPES")

    for key, value in overall_item_types.most_common():
        print(f"  {str(key):15s} {value:5d}")

    # ------------------------------------------------------------
    # DUPLICATE TRANSACTION IDS
    # ------------------------------------------------------------

    duplicates = {
        tx_id: locations
        for tx_id, locations
        in all_transaction_ids.items()
        if len(locations) > 1
    }

    print()
    print("=" * 70)
    print("DUPLICATE TRANSACTION IDS")
    print("=" * 70)

    print(
        f"Unique transaction IDs: {len(all_transaction_ids)}"
    )

    print(
        f"Duplicate IDs:          {len(duplicates)}"
    )

    if duplicates:

        for tx_id, locations in list(
            duplicates.items()
        )[:20]:

            print(
                f"  {tx_id}: {locations}"
            )

    # ------------------------------------------------------------
    # WEIRD ITEMS
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("ITEMS WITH MISSING CORE FIELDS")
    print("=" * 70)

    total_weird = sum(
        len(data["weird"])
        for data in yearly.values()
    )

    print(
        f"Items with missing player/from/to fields: "
        f"{total_weird}"
    )

    if total_weird:

        shown = 0

        for year, data in yearly.items():

            for item in data["weird"]:

                print(
                    json.dumps(
                        item,
                        indent=2
                    )
                )

                shown += 1

                if shown >= 20:
                    break

            if shown >= 20:
                break

    # ------------------------------------------------------------
    # MULTI-ITEM EXAMPLES
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("MULTI-ITEM TRANSACTION EXAMPLES")
    print("=" * 70)

    shown = 0

    for year_dir in sorted(
        TRANSACTION_DIR.iterdir()
    ):

        if not year_dir.is_dir():
            continue

        for file in sorted(
            year_dir.glob("scoring_period_*.json")
        ):

            with file.open(
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)

            for tx in data.get(
                "transactions",
                []
            ):

                if len(tx.get("items", [])) <= 1:
                    continue

                print()
                print(
                    f"Year: {year_dir.name} "
                    f"File: {file.name}"
                )

                print(
                    f"Transaction: {tx.get('id')}"
                )

                print(
                    f"Type: {tx.get('type')}"
                )

                for item in tx.get(
                    "items",
                    []
                ):

                    print(
                        f"  {item.get('type'):8s} "
                        f"player={item.get('playerId')} "
                        f"from={item.get('fromTeamId')} "
                        f"to={item.get('toTeamId')}"
                    )

                shown += 1

                if shown >= 15:
                    break

            if shown >= 15:
                break

        if shown >= 15:
            break

    print()
    print("=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()