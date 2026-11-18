import json
from pathlib import Path

TRANSACTION_DIR = Path("data/raw/transactions")

TARGET_TYPES = {
    "TRADE_ACCEPT",
    "TRADE_UPHOLD",
    "TRADE_VETO",
    "ROSTER",
}


def main():
    print("=" * 70)
    print("TRANSACTION TYPE INSPECTION")
    print("=" * 70)

    found = {
        tx_type: []
        for tx_type in TARGET_TYPES
    }

    for year_dir in sorted(TRANSACTION_DIR.iterdir()):

        if not year_dir.is_dir():
            continue

        year = int(year_dir.name)

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

            for tx in data.get(
                "transactions",
                []
            ):

                tx_type = tx.get("type")

                if tx_type not in TARGET_TYPES:
                    continue

                if len(found[tx_type]) >= 3:
                    continue

                found[tx_type].append({
                    "year": year,
                    "scoring_period": scoring_period,
                    "transaction": tx,
                })

    for tx_type in TARGET_TYPES:

        print()
        print("=" * 70)
        print(f"{tx_type}")
        print("=" * 70)

        examples = found[tx_type]

        if not examples:
            print("No examples found.")
            continue

        for example in examples:

            print()
            print(
                f"YEAR: {example['year']}  "
                f"SCORING PERIOD: {example['scoring_period']}"
            )

            print(
                json.dumps(
                    example["transaction"],
                    indent=2,
                    ensure_ascii=False
                )
            )


if __name__ == "__main__":
    main()