import json
import os
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

LEAGUE_ID = "112536"
START_YEAR = 2011
END_YEAR = 2025
SCORING_PERIODS = range(1, 21)
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
OUTPUT_DIR = Path("data/raw/transactions")

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")
if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError("Missing ESPN_S2 or ESPN_SWID environment variables.")

COOKIES = {"espn_s2": ESPN_S2, "SWID": ESPN_SWID}


def get_url(year):
    if year >= 2018:
        return f"{BASE}/seasons/{year}/segments/0/leagues/{LEAGUE_ID}"
    return f"{BASE}/leagueHistory/{LEAGUE_ID}"


def fetch_transactions(year, scoring_period, session):
    params = {"view": "mTransactions2", "scoringPeriodId": scoring_period}
    if year < 2018:
        params["seasonId"] = year

    last_error = None
    for attempt in range(1, 4):
        try:
            response = session.get(get_url(year), params=params, timeout=45)
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 3:
                delay = attempt * 2
                print(
                    f"    Attempt {attempt}/3 failed for {year} "
                    f"period {scoring_period}; retrying in {delay}s"
                )
                time.sleep(delay)
    else:
        raise RuntimeError(
            f"Unable to fetch {year} scoring period {scoring_period} "
            f"after 3 attempts ({type(last_error).__name__})."
        ) from last_error

    if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], dict):
        payload = payload[0]
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Unexpected ESPN response for {year} period {scoring_period}: "
            f"{type(payload).__name__}"
        )
    if not isinstance(payload.get("transactions"), list):
        raise RuntimeError(
            f"ESPN response for {year} period {scoring_period} "
            "does not contain a transactions array."
        )
    return payload


def atomic_write_json(path, payload):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.cookies.update(COOKIES)
    session.headers.update(
        {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    )

    total_requests = 0
    successful_requests = 0
    total_transactions = 0
    failures = []

    print("=" * 70)
    print("ESPN TRANSACTION COLLECTOR")
    print("=" * 70)
    print(f"League: {LEAGUE_ID}")
    print(f"Years: {START_YEAR}-{END_YEAR}")
    print("Scoring periods per season: 1-20")

    for year in range(START_YEAR, END_YEAR + 1):
        year_dir = OUTPUT_DIR / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        year_transactions = 0
        print()
        print(f"YEAR {year}")

        for scoring_period in SCORING_PERIODS:
            total_requests += 1
            try:
                payload = fetch_transactions(year, scoring_period, session)
                transactions = payload["transactions"]
                output_file = year_dir / f"scoring_period_{scoring_period}.json"
                atomic_write_json(output_file, payload)
                count = len(transactions)
                successful_requests += 1
                year_transactions += count
                total_transactions += count
                print(f"  SP {scoring_period:2d}: {count:3d} transactions")
            except Exception as exc:
                failures.append(
                    {
                        "season": year,
                        "scoring_period": scoring_period,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(
                    f"  ERROR SP {scoring_period:2d}: "
                    f"{type(exc).__name__}: {exc}"
                )
            time.sleep(0.25)

        print(
            f"  {year}: {year_transactions} transactions; "
            f"{successful_requests} successful requests overall"
        )

    print()
    print("=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)
    print(f"Requests attempted:  {total_requests}")
    print(f"Requests successful: {successful_requests}")
    print(f"Transactions saved:  {total_transactions}")
    print(f"Failed periods:      {len(failures)}")

    if failures:
        print(json.dumps(failures, indent=2))
        raise SystemExit(
            "Transaction collection incomplete; refusing to build or deploy."
        )

    expected = (END_YEAR - START_YEAR + 1) * len(SCORING_PERIODS)
    if successful_requests != expected:
        raise SystemExit(
            f"Collection count mismatch: expected {expected}, "
            f"received {successful_requests}."
        )
    print("PASS: every requested season/scoring period was collected.")


if __name__ == "__main__":
    main()
