import json
from pathlib import Path


TRANSACTION_DIR = Path("data/raw/transactions")

TARGETS = {
    2019: {
        3120348: "JuJu Smith-Schuster",
    },
    2020: {
        -16025: "49ers D/ST",
    },
}


def main():

    print("=" * 80)
    print("INSPECTING MISSING OWNERSHIP TRANSFERS")
    print("=" * 80)

    for year, players in TARGETS.items():

        year_dir = TRANSACTION_DIR / str(year)

        print()
        print("=" * 80)
        print(f"SEASON {year}")
        print("=" * 80)

        for player_id, player_name in players.items():

            print()
            print("-" * 80)
            print(
                f"{player_name} "
                f"(player_id={player_id})"
            )
            print("-" * 80)

            found = []

            for file in sorted(
                year_dir.glob("scoring_period_*.json")
            ):

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

                for tx_index, tx in enumerate(
                    transactions
                ):

                    items = tx.get("items") or []

                    matching_items = []

                    for item_index, item in enumerate(
                        items
                    ):

                        if item.get("playerId") == player_id:

                            matching_items.append({
                                "item_index": item_index,
                                "item": item,
                            })

                    if matching_items:

                        found.append({
                            "scoring_period": scoring_period,
                            "transaction_index": tx_index,
                            "transaction": tx,
                            "matching_items": matching_items,
                        })

            print(
                f"Found {len(found)} transaction records"
            )

            for record in found:

                tx = record["transaction"]

                print()
                print(
                    f"SCORING PERIOD: "
                    f"{record['scoring_period']}"
                )

                print(
                    f"TRANSACTION INDEX: "
                    f"{record['transaction_index']}"
                )

                print(
                    f"TYPE: {tx.get('type')}"
                )

                print(
                    f"STATUS: {tx.get('status')}"
                )

                print(
                    f"ID: {tx.get('id')}"
                )

                print(
                    f"RELATED ID: "
                    f"{tx.get('relatedTransactionId')}"
                )

                print(
                    f"PROCESS DATE: "
                    f"{tx.get('processDate')}"
                )

                print(
                    f"PROPOSED DATE: "
                    f"{tx.get('proposedDate')}"
                )

                print(
                    f"ACCEPTED DATE: "
                    f"{tx.get('acceptedDate')}"
                )

                print("MATCHING ITEMS:")

                for match in record["matching_items"]:

                    print(
                        json.dumps(
                            match["item"],
                            indent=2,
                            ensure_ascii=False
                        )
                    )

    print()
    print("=" * 80)
    print("INSPECTION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()