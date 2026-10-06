import json
import os
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

LEAGUE_ID = 112536
YEARS = range(2018, 2026)

BASE_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
)

RAW_TX_DIR = Path("data/raw/transactions")
PROCESSED_DIR = Path("data/processed")
RAW_AUDIT_DIR = Path("data/raw/trade_audit")
OUTPUT_FILE = PROCESSED_DIR / "trade_audit.json"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
RAW_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError(
        "ESPN_S2 and ESPN_SWID must be present in .env"
    )

COOKIES = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}

SESSION = requests.Session()
SESSION.cookies.update(COOKIES)
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0",
})


def get_json(url, params=None, headers=None, retries=3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = SESSION.get(
                url,
                params=params,
                headers=headers,
                timeout=90,
            )

            if response.status_code == 200:
                return response.json()

            last_error = RuntimeError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        except Exception as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(2 * attempt)

    raise last_error


def load_trade_periods():
    """
    Find scoring periods containing executed trade activity in the
    existing mTransactions2 archive.

    We deliberately include TRADE_ACCEPT and TRADE_UPHOLD because ESPN
    may expose the workflow rows differently depending on the season.
    """
    periods = defaultdict(set)

    for year in YEARS:
        year_dir = RAW_TX_DIR / str(year)

        for file in sorted(year_dir.glob("scoring_period_*.json")):
            scoring_period = int(
                file.stem.split("_")[-1]
            )

            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for tx in data.get("transactions", []):
                if tx.get("status") != "EXECUTED":
                    continue

                tx_type = tx.get("type")

                if tx_type in {
                    "TRADE",
                    "TRADE_ACCEPT",
                    "TRADE_UPHOLD",
                }:
                    periods[year].add(scoring_period)

    return periods


def load_player_ids_by_year():
    """
    Build the player universe we need to inspect from the data we already
    archived locally.

    This is deliberately broader than the trade periods themselves:
    a player can be traded and then immediately dropped, so relying only
    on a roster snapshot can miss the player. Draft picks plus every
    transaction item cover players who entered the league through draft,
    waiver/free agency, or a transaction.
    """
    player_ids_by_year = {
        year: set()
        for year in YEARS
    }

    # Drafted players.
    draft_file = PROCESSED_DIR / "draft_picks.json"

    with draft_file.open("r", encoding="utf-8") as f:
        draft_picks = json.load(f)

    for pick in draft_picks:
        year = pick.get("season")
        if year not in player_ids_by_year:
            continue

        player_id = pick.get("player_id")
        if player_id is not None:
            player_ids_by_year[year].add(player_id)

    # Players appearing in any archived transaction item.
    for year in YEARS:
        year_dir = RAW_TX_DIR / str(year)

        for file in sorted(
            year_dir.glob("scoring_period_*.json")
        ):
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for tx in data.get("transactions", []):
                for item in tx.get("items") or []:
                    player_id = item.get("playerId")
                    if player_id is not None:
                        player_ids_by_year[year].add(
                            player_id
                        )

    return {
        year: sorted(player_ids)
        for year, player_ids in player_ids_by_year.items()
    }


def get_player_cards(year, scoring_period, player_ids):
    """
    Pull kona_playercard in batches.

    Player cards contain the detailed transaction history that can
    recover trade legs missing from mTransactions2.
    """
    results = []

    url = (
        f"{BASE_URL}/seasons/{year}"
        f"/segments/0/leagues/{LEAGUE_ID}"
    )

    # Keep batches conservative. Player cards can be large.
    batch_size = 50

    raw_dir = (
        RAW_AUDIT_DIR /
        str(year) /
        f"scoring_period_{scoring_period}"
    )
    raw_dir.mkdir(parents=True, exist_ok=True)

    for batch_number, start in enumerate(
        range(0, len(player_ids), batch_size),
        start=1,
    ):
        batch = player_ids[start:start + batch_size]

        output_file = (
            raw_dir /
            f"playercards_{batch_number:03d}.json"
        )

        if output_file.exists():
            with output_file.open(
                "r",
                encoding="utf-8"
            ) as f:
                data = json.load(f)
        else:
            fantasy_filter = {
                "players": {
                    "filterIds": {
                        "value": batch
                    }
                }
            }

            data = get_json(
                url,
                params={
                    "view": "kona_playercard",
                },
                headers={
                    "X-Fantasy-Filter":
                        json.dumps(fantasy_filter)
                },
            )

            with output_file.open(
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    data,
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            time.sleep(0.15)

        results.append(data)

    return results


def extract_trade_legs(player_card_responses):
    """
    Extract unique TRADE items from player-card transaction history.

    The same trade transaction appears on multiple player cards, so
    dedupe by transaction + player + from/to.
    """
    legs = {}

    for response in player_card_responses:
        for player_entry in response.get("players", []):
            player_obj = player_entry.get("player") or {}

            card_player_id = (
                player_obj.get("id")
                if player_obj.get("id") is not None
                else player_entry.get("id")
            )

            transactions = (
                player_obj.get("transactions")
                or player_entry.get("transactions")
                or []
            )

            for tx in transactions:
                if tx.get("status") != "EXECUTED":
                    continue

                for item_index, item in enumerate(
                    tx.get("items") or []
                ):
                    if item.get("type") != "TRADE":
                        continue

                    player_id = item.get("playerId")

                    if player_id is None:
                        player_id = card_player_id

                    from_team = item.get("fromTeamId")
                    to_team = item.get("toTeamId")

                    if from_team in (-1, 0):
                        from_team = None

                    if to_team in (-1, 0):
                        to_team = None

                    if from_team is None or to_team is None:
                        continue

                    key = (
                        tx.get("id"),
                        player_id,
                        from_team,
                        to_team,
                    )

                    legs[key] = {
                        "transaction_id": tx.get("id"),
                        "related_transaction_id":
                            tx.get("relatedTransactionId"),
                        "player_id": player_id,
                        "from_team_id": from_team,
                        "to_team_id": to_team,
                        "scoring_period":
                            tx.get("scoringPeriodId"),
                        "process_date":
                            tx.get("processDate"),
                        "proposed_date":
                            tx.get("proposedDate"),
                        "transaction_type":
                            tx.get("type"),
                        "card_player_id":
                            card_player_id,
                    }

    return list(legs.values())


def load_existing_trade_events():
    file = PROCESSED_DIR / "transaction_events.json"

    if not file.exists():
        raise FileNotFoundError(
            f"Missing {file}. Run build_transaction_events.py first."
        )

    with file.open("r", encoding="utf-8") as f:
        events = json.load(f)

    trades = {}

    for event in events:
        if event.get("action") != "TRADE":
            continue

        key = (
            event.get("season"),
            event.get("scoring_period"),
            event.get("player_id"),
            event.get("from_team_id"),
            event.get("to_team_id"),
        )

        trades[key] = event

    return trades


def load_ledger():
    file = PROCESSED_DIR / "ownership_ledger.json"

    if not file.exists():
        raise FileNotFoundError(
            f"Missing {file}. Run build_ownership_ledger.py first."
        )

    with file.open("r", encoding="utf-8") as f:
        return json.load(f)


def owner_before_trade(ledger, season, player_id, period):
    """
    Find the team owning the player immediately before the trade
    based on the current ledger.
    """
    candidates = []

    for row in ledger:
        if (
            row.get("season") == season
            and row.get("player_id") == player_id
        ):
            start = row.get("start_scoring_period")
            end = row.get("end_scoring_period")

            if start is None:
                continue

            if start <= period:
                candidates.append(row)

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: row["start_scoring_period"],
        reverse=True,
    )

    return candidates[0].get("team_id")


def main():
    print("=" * 80)
    print("FULL ESPN TRADE AUDIT")
    print("=" * 80)
    print()
    print(
        "Source 1: mTransactions2 archive"
    )
    print(
        "Source 2: kona_playercard transaction history"
    )
    print()

    periods = load_trade_periods()

    for year in YEARS:
        print(
            f"{year}: trade activity in scoring periods "
            f"{sorted(periods.get(year, []))}"
        )

    existing_trades = load_existing_trade_events()
    ledger = load_ledger()
    player_ids_by_year = load_player_ids_by_year()

    all_card_trades = []

    for year in YEARS:
        trade_periods = sorted(periods.get(year, []))

        if not trade_periods:
            continue

        player_ids = player_ids_by_year[year]

        print()
        print(
            f"Processing {year}: "
            f"{len(player_ids)} player IDs"
        )

        # Player transaction history is season-wide. We only need to
        # inspect seasons that contain trade activity.
        responses = get_player_cards(
            year,
            0,
            player_ids,
        )

        trades = extract_trade_legs(responses)

        print(
            f"  Trade legs found: {len(trades)}"
        )

        for trade in trades:
            trade["season"] = year
            all_card_trades.append(trade)

    # Deduplicate across scoring periods.
    unique = {}

    for trade in all_card_trades:
        key = (
            trade["season"],
            trade["player_id"],
            trade["from_team_id"],
            trade["to_team_id"],
            trade["transaction_id"],
        )

        unique[key] = trade

    card_trades = list(unique.values())

    missing_from_transactions = []
    matched = []

    for trade in card_trades:
        key = (
            trade["season"],
            trade["scoring_period"],
            trade["player_id"],
            trade["from_team_id"],
            trade["to_team_id"],
        )

        existing = existing_trades.get(key)

        if existing:
            matched.append({
                "card_trade": trade,
                "transaction_event": existing,
            })
        else:
            expected_owner = owner_before_trade(
                ledger,
                trade["season"],
                trade["player_id"],
                trade["scoring_period"],
            )

            missing_from_transactions.append({
                "trade": trade,
                "ledger_owner_before_trade":
                    expected_owner,
                "source_gap":
                    "kona_playercard trade not present in "
                    "mTransactions2 transaction_events",
            })

    # Find transaction-event trade legs that card audit did not find.
    card_keys = {
        (
            trade["season"],
            trade["scoring_period"],
            trade["player_id"],
            trade["from_team_id"],
            trade["to_team_id"],
        )
        for trade in card_trades
    }

    transaction_only = []

    for key, event in existing_trades.items():
        if key not in card_keys:
            transaction_only.append(event)

    report = {
        "league_id": LEAGUE_ID,
        "seasons_audited": list(YEARS),
        "trade_scoring_periods": {
            str(year): sorted(periods.get(year, []))
            for year in YEARS
        },
        "kona_trade_legs": len(card_trades),
        "matched_trade_legs": len(matched),
        "missing_from_mtransactions2":
            len(missing_from_transactions),
        "transaction_only_trade_legs":
            len(transaction_only),
        "missing_trades":
            sorted(
                missing_from_transactions,
                key=lambda x: (
                    x["trade"]["season"],
                    x["trade"]["scoring_period"],
                    x["trade"]["player_id"],
                ),
            ),
        "transaction_only":
            sorted(
                transaction_only,
                key=lambda x: (
                    x["season"],
                    x["scoring_period"],
                    x["player_id"],
                ),
            ),
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print("=" * 80)
    print("TRADE AUDIT SUMMARY")
    print("=" * 80)
    print(
        f"kona_playercard trade legs: "
        f"{len(card_trades)}"
    )
    print(
        f"Matched in mTransactions2: "
        f"{len(matched)}"
    )
    print(
        f"Missing from mTransactions2: "
        f"{len(missing_from_transactions)}"
    )
    print(
        f"Transaction-only trade legs: "
        f"{len(transaction_only)}"
    )

    print()

    if missing_from_transactions:
        print("MISSING TRADE LEGS")
        print("-" * 80)

        for item in report["missing_trades"]:
            trade = item["trade"]

            print(
                f'{trade["season"]} SP{trade["scoring_period"]} '
                f'player={trade["player_id"]}: '
                f'Team {trade["from_team_id"]} -> '
                f'Team {trade["to_team_id"]} '
                f'(tx={trade["transaction_id"]})'
            )

            print(
                f'  Ledger owner before trade: '
                f'{item["ledger_owner_before_trade"]}'
            )

    print()
    print(f"Wrote: {OUTPUT_FILE}")
    print()
    print("=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
