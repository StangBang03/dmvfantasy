import json
from pathlib import Path

AUDIT = Path("artifacts/player_performance_candidate/player_performance_candidate_audit.json")


def main():
    if not AUDIT.exists():
        raise SystemExit(f"Missing candidate audit: {AUDIT}")
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    print(json.dumps({
        "production_ready": audit.get("production_ready"),
        "legacy_ready": audit.get("legacy_ready"),
        "modern_ready": audit.get("modern_ready"),
        "coverage_ready": audit.get("coverage_ready"),
        "player_seasons": audit.get("player_seasons"),
        "weekly_rows": audit.get("weekly_rows"),
        "added_player_seasons_vs_current": audit.get("added_player_seasons_vs_current"),
        "season_total_changes_vs_current": audit.get("season_total_changes_vs_current"),
        "missing_legacy_week_archives": audit.get("missing_legacy_week_archives"),
        "source_errors": audit.get("source_errors"),
    }, indent=2))
    if not audit.get("production_ready"):
        raise SystemExit("Candidate is quarantined: one or more validation gates have not passed.")
    print("Candidate passed all production-readiness gates.")


if __name__ == "__main__":
    main()
