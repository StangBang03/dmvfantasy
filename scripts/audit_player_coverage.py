import json
from collections import defaultdict, Counter
from pathlib import Path

ROOT=Path("data/processed")
OUT=Path("artifacts/player_coverage")
OUT.mkdir(parents=True,exist_ok=True)


def load(name):
    path=ROOT/name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def group_ids(rows, season_key="season", player_key="player_id"):
    grouped=defaultdict(set)
    for row in rows:
        try:
            grouped[int(row[season_key])].add(int(row[player_key]))
        except (KeyError,TypeError,ValueError):
            continue
    return grouped


def main():
    pp=load("player_performance.json")
    pp_rows=pp.get("player_seasons") or []
    tx=load("transaction_events.json")
    ledger=load("ownership_ledger.json")
    drafts=load("draft_picks.json")
    supplemental=load("supplemental_trade_events.json")
    pp_ids=group_ids(pp_rows)
    tx_ids=group_ids(tx)
    ledger_ids=group_ids(ledger)
    draft_ids=group_ids(drafts)
    supplemental_ids=group_ids(supplemental)
    years=sorted(set(pp_ids)|set(tx_ids)|set(ledger_ids)|set(draft_ids)|set(supplemental_ids))
    report={
        "source_counts":{
            "player_performance_records":len(pp_rows),
            "transaction_events":len(tx),
            "ownership_ledger_rows":len(ledger),
            "draft_picks":len(drafts),
            "supplemental_trade_events":len(supplemental),
        },
        "seasons":{},
    }
    for year in years:
        sets={
            "player_performance":pp_ids.get(year,set()),
            "transactions":tx_ids.get(year,set()),
            "ownership_ledger":ledger_ids.get(year,set()),
            "draft_picks":draft_ids.get(year,set()),
            "supplemental_trades":supplemental_ids.get(year,set()),
        }
        union=set().union(*sets.values())
        current=sets["player_performance"]
        missing=sorted(union-current)
        report["seasons"][str(year)]={
            "counts":{k:len(v) for k,v in sets.items()},
            "union_player_ids":len(union),
            "player_ids_missing_from_performance":missing,
            "transactions_player_ids_missing_from_performance":sorted(sets["transactions"]-current),
            "draft_player_ids_missing_from_performance":sorted(sets["draft_picks"]-current),
            "ledger_player_ids_missing_from_performance":sorted(sets["ownership_ledger"]-current),
        }
        print(
            f"{year}: performance={len(current)} transactions={len(sets['transactions'])} "
            f"ledger={len(sets['ownership_ledger'])} draft={len(sets['draft_picks'])} "
            f"union={len(union)} missing={len(missing)}"
        )
    (OUT/"player_coverage_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")


if __name__=="__main__": main()
