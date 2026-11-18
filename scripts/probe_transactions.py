import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LEAGUE_ID = "112536"
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

cookies = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

OUTPUT_DIR = Path("data/raw/transactions_probe")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_url(year):
    if year >= 2018:
        return (
            f"{BASE}/seasons/{year}/segments/0/"
            f"leagues/{LEAGUE_ID}"
        )
    else:
        return (
            f"{BASE}/leagueHistory/{LEAGUE_ID}"
            f"?seasonId={year}"
        )


def unwrap(data):
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            return data[0]

    if isinstance(data, dict):
        return data

    return {}


def probe(year):
    url = get_url(year)

    print()
    print("=" * 70)
    print(f"YEAR {year}")
    print("=" * 70)
    print(url)

    response = requests.get(
        url,
        params={
            "view": "mTransactions2",
            "scoringPeriodId": 1,
        },
        cookies=cookies,
        timeout=30,
    )

    print(f"HTTP STATUS: {response.status_code}")

    if response.status_code != 200:
        print("Response:")
        print(response.text[:1000])
        return

    try:
        raw = response.json()
    except Exception:
        print("Response was not JSON:")
        print(response.text[:1000])
        return

    output_file = OUTPUT_DIR / f"{year}_mTransactions2.json"

    with output_file.open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)

    data = unwrap(raw)

    print(f"Saved: {output_file}")

    print()
    print("TOP-LEVEL KEYS:")
    if isinstance(data, dict):
        for key in data.keys():
            print(f"  - {key}")
    else:
        print(f"  Unexpected type: {type(data).__name__}")

    transactions = data.get("transactions", [])

    print()
    print(f"TRANSACTIONS FOUND: {len(transactions)}")

    if not transactions:
        print("No transactions returned for scoringPeriodId=1.")
        return

    print()
    print("FIRST TRANSACTIONS:")

    for tx in transactions[:10]:
        print("-" * 60)

        print(f"ID:               {tx.get('id')}")
        print(f"STATUS:           {tx.get('status')}")
        print(f"TYPE:             {tx.get('type')}")
        print(f"TEAM ID:          {tx.get('teamId')}")
        print(f"SCORING PERIOD:   {tx.get('scoringPeriodId')}")
        print(f"PROCESS DATE:     {tx.get('processDate')}")
        print(f"BID AMOUNT:       {tx.get('bidAmount')}")

        print("ITEMS:")

        for item in tx.get("items", []):
            print(
                f"  player={item.get('playerId')} "
                f"type={item.get('type')} "
                f"from={item.get('fromTeamId')} "
                f"to={item.get('toTeamId')}"
            )


for year in [2018, 2020, 2025]:
    probe(year)

print()
print("=" * 70)
print("PROBE COMPLETE")
print("=" * 70)