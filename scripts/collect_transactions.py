import os
import json
import time
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LEAGUE_ID = "112536"
START_YEAR = 2018
END_YEAR = 2025

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

cookies = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

OUTPUT_DIR = Path("data/raw/transactions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_url(year):
    return (
        f"{BASE}/seasons/{year}/segments/0/"
        f"leagues/{LEAGUE_ID}"
    )


def fetch_transactions(year, scoring_period):
    url = get_url(year)

    response = requests.get(
        url,
        params={
            "view": "mTransactions2",
            "scoringPeriodId": scoring_period,
        },
        cookies=cookies,
        timeout=30,
    )

    if response.status_code != 200:
        print(
            f"    HTTP {response.status_code} "
            f"for scoring period {scoring_period}"
        )
        return None

    return response.json()


def main():
    print("=" * 70)
    print("ESPN TRANSACTION COLLECTOR")
    print("=" * 70)
    print(f"League: {LEAGUE_ID}")
    print(f"Years:  {START_YEAR}-{END_YEAR}")
    print()

    total_requests = 0
    successful_requests = 0
    total_transactions = 0

    for year in range(START_YEAR, END_YEAR + 1):

        print()
        print("-" * 70)
        print(f"YEAR {year}")
        print("-" * 70)

        year_dir = OUTPUT_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        year_transactions = 0
        year_requests = 0

        # Fantasy football regular season + playoffs.
        # 20 gives us plenty of coverage and the API simply
        # returns an empty transaction list when appropriate.
        for scoring_period in range(1, 21):

            total_requests += 1
            year_requests += 1

            data = fetch_transactions(
                year,
                scoring_period
            )

            if data is None:
                continue

            successful_requests += 1

            output_file = (
                year_dir /
                f"scoring_period_{scoring_period}.json"
            )

            with output_file.open(
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    data,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            transactions = data.get(
                "transactions",
                []
            )

            count = len(transactions)

            year_transactions += count
            total_transactions += count

            print(
                f"  SP {scoring_period:2d}: "
                f"{count:3d} transactions"
            )

            # Be polite to ESPN.
            time.sleep(0.15)

        print()
        print(
            f"  {year}: {year_transactions} transactions "
            f"across {year_requests} scoring periods"
        )

    print()
    print("=" * 70)
    print("COLLECTION COMPLETE")
    print("=" * 70)

    print(f"Requests attempted:  {total_requests}")
    print(f"Requests successful: {successful_requests}")
    print(f"Transactions saved:  {total_transactions}")
    print()
    print(f"Raw data: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()