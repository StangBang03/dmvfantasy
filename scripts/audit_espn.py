import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

LEAGUE_ID = 112536
START_YEAR = 2011
END_YEAR = 2026

VIEWS = [
    "mSettings",
    "mTeam",
    "mStandings",
    "mSchedule",
    "mMatchupScore",
    "mDraftDetail",
]

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

RAW_DIR = Path("data/raw")
REPORT_FILE = Path("data/audit_report.json")

ESPN_S2 = os.getenv("ESPN_S2")
ESPN_SWID = os.getenv("ESPN_SWID")

if not ESPN_S2 or not ESPN_SWID:
    raise RuntimeError(
        "Missing ESPN_S2 or ESPN_SWID in .env"
    )

COOKIES = {
    "espn_s2": ESPN_S2,
    "SWID": ESPN_SWID,
}


def get_season(year, view):
    if year >= 2018:
        url = (
            f"{BASE_URL}/seasons/{year}/segments/0/"
            f"leagues/{LEAGUE_ID}"
        )

        params = {
            "view": view
        }

    else:
        url = (
            f"{BASE_URL}/leagueHistory/{LEAGUE_ID}"
        )

        params = {
            "seasonId": year,
            "view": view
        }

    response = requests.get(
        url,
        params=params,
        cookies=COOKIES,
        timeout=30,
    )

    return response


def save_json(year, view, data):
    year_dir = RAW_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    filename = year_dir / f"{view}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return filename


def fetch_all():
    report = {
        "league_id": LEAGUE_ID,
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "views": {},
    }

    total = len(range(START_YEAR, END_YEAR + 1)) * len(VIEWS)
    completed = 0

    print()
    print("=" * 60)
    print(f" ESPN FANTASY LEAGUE {LEAGUE_ID}")
    print(f" Fetching {START_YEAR}-{END_YEAR}")
    print("=" * 60)
    print()

    for year in range(START_YEAR, END_YEAR + 1):
        report["views"][str(year)] = {}

        print(f"===== {year} =====")

        for view in VIEWS:
            completed += 1

            try:
                response = get_season(year, view)

                status = response.status_code
                size = len(response.content)

                result = {
                    "status": status,
                    "bytes": size,
                }

                if status == 200:
                    data = response.json()

                    path = save_json(year, view, data)

                    result["file"] = str(path)

                    print(
                        f"[{completed:02}/{total}] "
                        f"{view:<18} "
                        f"200  "
                        f"{size:>8} bytes"
                    )

                else:
                    result["error"] = response.text[:500]

                    print(
                        f"[{completed:02}/{total}] "
                        f"{view:<18} "
                        f"{status}"
                    )

                report["views"][str(year)][view] = result

            except Exception as e:
                report["views"][str(year)][view] = {
                    "status": "ERROR",
                    "error": str(e),
                }

                print(
                    f"[{completed:02}/{total}] "
                    f"{view:<18} ERROR: {e}"
                )

            # Be polite to ESPN.
            time.sleep(0.25)

        print()

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print()
    print(f"Raw data: {RAW_DIR}")
    print(f"Audit:    {REPORT_FILE}")
    print()


if __name__ == "__main__":
    fetch_all()