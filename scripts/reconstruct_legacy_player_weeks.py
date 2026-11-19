import csv
import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

PLAYER_CARD_DIR = Path("data/raw/playercard_history")
GAMELOG_DIR = Path("data/raw/legacy_player_gamelogs")
SUMMARY_DIR = Path("data/raw/legacy_game_summaries")
DEFENSIVE_DIR = Path("data/raw/legacy_defensive_gamelogs")
ARTIFACT_OUT = Path("artifacts/legacy_weekly_reconstruction")
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
LEAGUE_ID = 112536
YEARS = range(2011, 2018)

import os
import requests

session = requests.Session()
session.cookies.update({
    "espn_s2": os.getenv("ESPN_S2", ""),
    "SWID": os.getenv("ESPN_SWID", ""),
})
session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
if not session.cookies.get("espn_s2") or not session.cookies.get("SWID"):
    raise RuntimeError("Missing ESPN credentials")


def read_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def get_scoring_items(year):
    response = session.get(
        f"{BASE}/leagueHistory/{LEAGUE_ID}",
        params=[("view", "mSettings"), ("seasonId", str(year))],
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload[0] if isinstance(payload, list) and payload else payload
    return ((data.get("settings") or {}).get("scoringSettings") or {}).get("scoringItems") or []


def n(value):
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in ("-", "--", "N/A"):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def pair(value):
    text = str(value or "").strip()
    if not text:
        return 0.0, 0.0
    separator = "/" if "/" in text else "-" if "-" in text else None
    if separator is None:
        number = n(text)
        return number, number
    left, right = text.split(separator, 1)
    return n(left), n(right)


def normalize_name(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", text)


def resolve_player(team_id, name, lookup):
    if not name:
        return None
    target = normalize_name(name)
    candidates = lookup.get(int(team_id), [])
    exact = [candidate for candidate in candidates if candidate[0] == target]
    if len(exact) == 1:
        return exact[0][1]
    if not candidates:
        return None

    target_tokens = re.findall(r"[a-z0-9]+", str(name).lower())
    target_last = target_tokens[-1] if target_tokens else ""
    target_initial = target_tokens[0][0] if target_tokens and target_tokens[0] else ""
    scored = []
    for normalized, player_id, display in candidates:
        tokens = re.findall(r"[a-z0-9]+", display.lower())
        last = tokens[-1] if tokens else ""
        initial = tokens[0][0] if tokens and tokens[0] else ""
        score = SequenceMatcher(None, target, normalized).ratio()
        if target_last and last == target_last and target_initial and initial == target_initial:
            score = max(score, 0.94)
        elif target_last and last == target_last:
            score = max(score, 0.84)
        scored.append((score, player_id))
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 0.82 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.04):
        return scored[0][1]
    return None


def extract_player_values(groups):
    """Extract player scoring stats from ESPN's game-summary boxscore."""
    groups = groups or {}
    passing = groups.get("passing") or {}
    rushing = groups.get("rushing") or {}
    receiving = groups.get("receiving") or {}
    fumbles = groups.get("fumbles") or {}
    kick_returns = groups.get("kickReturns") or {}
    punt_returns = groups.get("puntReturns") or {}
    values = {}

    passing_yards = n(passing.get("passingYards"))
    rushing_yards = n(rushing.get("rushingYards"))
    receiving_yards = n(receiving.get("receivingYards"))
    receptions = n(receiving.get("receptions"))

    values[4] = n(passing.get("passingTouchdowns"))
    values[8] = int(passing_yards / 25)
    values[17] = 1 if 300 <= passing_yards < 400 else 0
    values[18] = 1 if passing_yards >= 400 else 0
    values[20] = n(passing.get("interceptions"))
    values[25] = n(rushing.get("rushingTouchdowns"))
    values[28] = max(0, int(rushing_yards / 10))
    values[37] = 1 if 100 <= rushing_yards < 200 else 0
    values[38] = 1 if rushing_yards >= 200 else 0
    values[41] = receptions
    values[43] = n(receiving.get("receivingTouchdowns"))
    values[48] = max(0, int(receiving_yards / 10))
    values[53] = receptions
    values[56] = 1 if 100 <= receiving_yards < 200 else 0
    values[57] = 1 if receiving_yards >= 200 else 0
    values[72] = n(fumbles.get("fumblesLost"))
    values[101] = n(kick_returns.get("kickReturnTouchdowns"))
    values[102] = n(punt_returns.get("puntReturnTouchdowns"))
    values[117] = max(0, int(n(kick_returns.get("kickReturnYards")) / 25))
    values[119] = max(0, int(n(punt_returns.get("puntReturnYards")) / 25))
    return values


def extract_kicking_values(stats):
    """Use detailed athlete gamelog distance splits for kicker scoring."""
    stats = stats or {}
    def fg(names):
        for name in names:
            if name in stats:
                return pair(stats[name])
        return None

    fg_1_19 = fg(["fieldGoalsMade1_19-fieldGoalAttempts1_19"])
    fg_20_29 = fg(["fieldGoalsMade20_29-fieldGoalAttempts20_29"])
    fg_30_39 = fg(["fieldGoalsMade30_39-fieldGoalAttempts30_39"])
    fg_40_49 = fg(["fieldGoalsMade40_49-fieldGoalAttempts40_49"])
    fg_50 = fg(["fieldGoalsMade50-fieldGoalAttempts50", "fieldGoalsMade50_59-fieldGoalAttempts50_59"])
    fg_60 = fg(["fieldGoalsMade60Plus-fieldGoalAttempts60Plus"])
    pat = fg(["extraPointsMade-extraPointAttempts"])

    if not any(x is not None for x in (fg_1_19, fg_20_29, fg_30_39, fg_40_49, fg_50, fg_60, pat)):
        return {}

    made_1_19, att_1_19 = fg_1_19 or (0.0, 0.0)
    made_20_29, att_20_29 = fg_20_29 or (0.0, 0.0)
    made_30_39, att_30_39 = fg_30_39 or (0.0, 0.0)
    made_40_49, att_40_49 = fg_40_49 or (0.0, 0.0)
    made_50, att_50 = fg_50 or (0.0, 0.0)
    made_60, att_60 = fg_60 or (0.0, 0.0)
    made_pat, att_pat = pat or (0.0, 0.0)

    made_50_plus, att_50_plus = made_50 + made_60, att_50 + att_60
    made_under_40 = made_1_19 + made_20_29 + made_30_39
    att_under_40 = att_1_19 + att_20_29 + att_30_39
    made_total = made_50_plus + made_40_49 + made_under_40
    att_total = att_50_plus + att_40_49 + att_under_40

    return {
        74: made_50_plus, 75: att_50_plus, 76: att_50_plus - made_50_plus,
        77: made_40_49, 78: att_40_49, 79: att_40_49 - made_40_49,
        80: made_under_40, 81: att_under_40, 82: att_under_40 - made_under_40,
        83: made_total, 84: att_total, 85: att_total - made_total,
        86: made_pat, 87: att_pat, 88: att_pat - made_pat,
    }

def add_value(target, stat_id, value=1):
    target[int(stat_id)] += n(value)


def apply_scoring_plays(event, player_week_values, dst_week_values, dst_player_by_team, name_lookup, unmatched):
    week = int(event.get("week") or 0)
    if not 1 <= week <= 17:
        return

    def dst_target(team_id):
        player_id = dst_player_by_team.get(int(team_id))
        if player_id is None:
            return None
        return dst_week_values[(player_id, week)]

    home_team_id = None
    for team_id_text, score_info in (event.get("scores") or {}).items():
        if score_info.get("home_away") == "home":
            home_team_id = int(team_id_text)
            break
    previous_home_score = 0.0
    previous_away_score = 0.0

    for play in event.get("scoring_plays") or []:
        team_id = play.get("team_id")
        if team_id is None:
            continue
        team_id = int(team_id)
        play_type = str(play.get("type") or "")
        text = str(play.get("text") or "")
        low_type = play_type.lower()
        low_text = text.lower()
        is_td = "touchdown" in low_type or "touchdown" in low_text

        home_score = play.get("home_score")
        away_score = play.get("away_score")
        score_delta = None
        if home_score is not None and away_score is not None:
            home_score = n(home_score)
            away_score = n(away_score)
            if home_team_id is not None:
                score_delta = (home_score - previous_home_score) if team_id == home_team_id else (away_score - previous_away_score)
            previous_home_score = home_score
            previous_away_score = away_score

        pass_match = re.match(r"^(.*?)\s+(\d+)\s+Yd pass from (.*?)(?:\s+\(|$)", text, re.I)
        if is_td and pass_match:
            receiver_name, yardage, passer_name = pass_match.group(1), int(pass_match.group(2)), pass_match.group(3)
            passer_id = resolve_player(team_id, passer_name, name_lookup)
            receiver_id = resolve_player(team_id, receiver_name, name_lookup)
            if passer_id is not None:
                if yardage >= 40:
                    add_value(player_week_values[(passer_id, week)], 15)
                if yardage >= 50:
                    add_value(player_week_values[(passer_id, week)], 16)
            if receiver_id is not None:
                if yardage >= 40:
                    add_value(player_week_values[(receiver_id, week)], 45)
                if yardage >= 50:
                    add_value(player_week_values[(receiver_id, week)], 46)
            if passer_id is None or receiver_id is None:
                unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "passing TD player resolution"})

        run_match = re.match(r"^(.*?)\s+(\d+)\s+Yd Run\b", text, re.I)
        if is_td and run_match:
            runner_id = resolve_player(team_id, run_match.group(1), name_lookup)
            yardage = int(run_match.group(2))
            if runner_id is not None:
                if yardage >= 40:
                    add_value(player_week_values[(runner_id, week)], 35)
                if yardage >= 50:
                    add_value(player_week_values[(runner_id, week)], 36)
            else:
                unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "rushing TD player resolution"})

        if "kickoff return touchdown" in low_type or ("kickoff return" in low_text and is_td):
            target = dst_target(team_id)
            if target is not None: add_value(target, 101)
        if "punt return touchdown" in low_type or ("punt return" in low_text and is_td):
            target = dst_target(team_id)
            if target is not None: add_value(target, 102)
        if "interception return touchdown" in low_type or ("interception return" in low_text and is_td):
            target = dst_target(team_id)
            if target is not None: add_value(target, 103)
        if "fumble return touchdown" in low_type or ("fumble return" in low_text and is_td):
            target = dst_target(team_id)
            if target is not None: add_value(target, 104)
            fumble_match = re.match(r"^(.*?)\s+\d+\s+Yd Fumble Return\b", text, re.I)
            if fumble_match:
                player_id = resolve_player(team_id, fumble_match.group(1), name_lookup)
                if player_id is not None: add_value(player_week_values[(player_id, week)], 63)
                else: unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "fumble return player resolution"})
        if ("blocked punt" in low_type or "blocked field goal" in low_type or "blocked kick" in low_type) and is_td:
            target = dst_target(team_id)
            if target is not None: add_value(target, 93)

        # Older ESPN summaries expose successful 2-point plays as separate scoring events.
        if low_type in ("two point pass", "two point rush", "two point return"):
            successful = (score_delta is not None and score_delta >= 2) or (
                score_delta is None and "is good" in low_text and "no good" not in low_text
            )
            if successful:
                if low_type == "two point pass":
                    conversion = re.match(r"^(.*?)\s+Pass to\s+(.*?)\s+For Two-Point Conversion", text, re.I)
                    if conversion:
                        passer_id = resolve_player(team_id, conversion.group(1), name_lookup)
                        receiver_id = resolve_player(team_id, conversion.group(2), name_lookup)
                        if passer_id is not None:
                            add_value(player_week_values[(passer_id, week)], 19)
                        if receiver_id is not None:
                            add_value(player_week_values[(receiver_id, week)], 44)
                        if passer_id is None or receiver_id is None:
                            unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "separate passing two-point conversion resolution"})
                elif low_type == "two point rush":
                    conversion = re.match(r"^(.*?)\s+Run For Two-Point Conversion", text, re.I)
                    if conversion:
                        runner_id = resolve_player(team_id, conversion.group(1), name_lookup)
                        if runner_id is not None:
                            add_value(player_week_values[(runner_id, week)], 26)
                        else:
                            unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "separate rushing two-point conversion resolution"})
                else:
                    target = dst_target(team_id)
                    if target is not None:
                        add_value(target, 206)

        conversion_match = re.search(r"\((.*?)\)\s*$", text)
        conversion = conversion_match.group(1) if conversion_match else ""
        conversion_low = conversion.lower()
        if "two-point conversion" in conversion_low and "failed" not in conversion_low:
            pass_conversion = re.match(r"^(.*?)\s+Pass to\s+(.*?)\s+for Two-Point Conversion$", conversion, re.I)
            run_conversion = re.match(r"^(.*?)\s+Run for Two-Point Conversion$", conversion, re.I)
            return_conversion = re.match(r"^(.*?)\s+Return for Two-Point Conversion$", conversion, re.I)
            if pass_conversion:
                passer_id = resolve_player(team_id, pass_conversion.group(1), name_lookup)
                receiver_id = resolve_player(team_id, pass_conversion.group(2), name_lookup)
                if passer_id is not None: add_value(player_week_values[(passer_id, week)], 19)
                if receiver_id is not None: add_value(player_week_values[(receiver_id, week)], 44)
                if passer_id is None or receiver_id is None:
                    unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "passing two-point conversion resolution"})
            elif run_conversion:
                runner_id = resolve_player(team_id, run_conversion.group(1), name_lookup)
                if runner_id is not None: add_value(player_week_values[(runner_id, week)], 26)
                else: unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "rushing two-point conversion resolution"})
            elif return_conversion:
                target = dst_target(team_id)
                if target is not None: add_value(target, 206)
            else:
                unmatched.append({"event_id": event.get("event_id"), "text": text, "reason": "unclassified successful two-point conversion"})

        if "safety" in low_type or "safety" in low_text:
            target = dst_target(team_id)
            if target is not None:
                if "one-point" in low_type or "one point" in low_type or "one-point" in low_text or "one point" in low_text:
                    add_value(target, 209)
                else:
                    add_value(target, 98)

def dst_values_for_event(event, dst_team_ids, extra_defense):
    result = {}
    teams = event.get("teams") or []
    scores = event.get("scores") or {}
    team_by_id = {
        int(team["team_id"]): team
        for team in teams
        if team.get("team_id") is not None
    }
    players_by_team = defaultdict(list)
    for player in event.get("players") or []:
        if player.get("team_id") is not None:
            players_by_team[int(player["team_id"])].append(player)

    # Sum defensive player stats directly from ESPN's game-summary boxscore.
    defense_by_team = defaultdict(lambda: {"fumbles_forced": 0.0, "kicks_blocked": 0.0})
    for team_id, players in players_by_team.items():
        for player in players:
            groups = player.get("groups") or {}
            fumbles = groups.get("fumbles") or {}
            defense_by_team[team_id]["fumbles_forced"] += n(fumbles.get("fumblesForced"))
            defense_by_team[team_id]["kicks_blocked"] += n(fumbles.get("kicksBlocked"))

    for team_id in dst_team_ids:
        if team_id not in team_by_id:
            continue
        opponent_ids = [other for other in team_by_id if other != team_id]
        if not opponent_ids:
            continue
        opponent_id = opponent_ids[0]
        opponent_stats = team_by_id[opponent_id].get("statistics") or {}
        points_allowed = n((scores.get(str(opponent_id)) or {}).get("score"))
        yards_allowed = n(opponent_stats.get("totalYards"))
        sacks, _ = pair(opponent_stats.get("sacksYardsLost"))
        interceptions = n(opponent_stats.get("interceptions"))
        fumbles_recovered = n(opponent_stats.get("fumblesLost"))

        # ESPN boxscore player data is the preferred source for forced fumbles and blocked kicks.
        # Use the separate athlete-gamelog aggregation only as a fallback when boxscore is absent.
        summary_defense = defense_by_team.get(team_id) or {}
        extra = extra_defense.get(f"{team_id}:{int(event.get('week') or 0)}") or {}
        forced = summary_defense.get("fumbles_forced", 0.0)
        blocked = summary_defense.get("kicks_blocked", 0.0)
        if forced == 0 and extra:
            forced = n(extra.get("fumbles_forced"))
        if blocked == 0 and extra:
            blocked = n(extra.get("kicks_blocked"))

        values = {
            95: interceptions,
            96: fumbles_recovered,
            97: blocked,
            99: sacks,
            106: forced,
            117: 0,
            119: 0,
        }

        # Defensive/special-teams return yardage is the sum of player returns.
        kick_yards = sum(n((p.get("groups") or {}).get("kickReturns", {}).get("kickReturnYards")) for p in players_by_team[team_id])
        punt_yards = sum(n((p.get("groups") or {}).get("puntReturns", {}).get("puntReturnYards")) for p in players_by_team[team_id])
        values[117] = int(kick_yards / 25)
        values[119] = int(punt_yards / 25)

        # Points-allowed buckets. Keep raw opponent score in the audit so this can be refined if
        # ESPN's defensive points-allowed definition excludes opponent defensive/special-teams scores.
        buckets = [(89, 0, 0), (90, 1, 6), (91, 7, 13), (92, 14, 17), (121, 18, 21), (122, 22, 27), (123, 28, 34), (124, 35, 45), (125, 46, 10**9)]
        for stat_id, lower, upper in buckets:
            if lower <= points_allowed <= upper:
                values[stat_id] = 1

        yard_buckets = [(128, 0, 99), (129, 100, 199), (130, 200, 299), (131, 300, 349), (132, 350, 399), (133, 400, 449), (134, 450, 499), (135, 500, 549), (136, 550, 10**9)]
        for stat_id, lower, upper in yard_buckets:
            if lower <= yards_allowed <= upper:
                values[stat_id] = 1
        result[team_id] = values
    return result


def calculate_points(values, items, is_dst=False):
    total = 0.0
    for item in items:
        stat_id = int(item["statId"])
        points = item.get("points", 0)
        overrides = item.get("pointsOverrides") or {}
        if is_dst and "16" in overrides:
            points = overrides["16"]
        total += n(values.get(stat_id, 0)) * n(points)
    return round(total, 4)


def main():
    ARTIFACT_OUT.mkdir(parents=True, exist_ok=True)
    audit = {"seasons": {}, "errors": []}

    for year in YEARS:
        pc_path = PLAYER_CARD_DIR / f"playercard_{year}.json.gz"
        gl_path = GAMELOG_DIR / f"legacy_player_gamelogs_{year}.json.gz"
        sm_path = SUMMARY_DIR / f"legacy_game_summaries_{year}.json.gz"
        def_path = DEFENSIVE_DIR / f"legacy_defensive_gamelogs_{year}.json.gz"
        if not all(path.exists() for path in (pc_path, gl_path, sm_path, def_path)):
            audit["errors"].append({"season": year, "error": "Missing one or more source archives"})
            continue

        pc = read_gzip(pc_path)
        boxscore_rows = pc.get("boxscore_weekly_points") or []
        gamelog = read_gzip(gl_path)
        summaries = read_gzip(sm_path)
        defensive = read_gzip(def_path)
        items = get_scoring_items(year)
        players = {int(player["player_id"]): player for player in pc.get("players") or []}
        dst_player_by_team = {
            int(player["pro_team_id"]): int(player["player_id"])
            for player in pc.get("players") or []
            if int(player.get("player_id", 0)) < 0 and player.get("pro_team_id") is not None
        }
        dst_team_ids = set(dst_player_by_team)
        extra_defense = defensive.get("team_week_counts") or {}

        player_logs = {int(player["player_id"]): player for player in gamelog.get("players") or []}
        player_week_values = defaultdict(lambda: defaultdict(float))
        dst_week_values = defaultdict(lambda: defaultdict(float))
        missing_player_logs = []
        kicking_week_values = defaultdict(dict)
        for player_id in players:
            if player_id < 0:
                continue
            log = player_logs.get(player_id)
            if not log or log.get("http_status") != 200:
                missing_player_logs.append(player_id)
                continue
            for event in log.get("events") or []:
                week = int(event.get("week") or 0)
                if not 1 <= week <= 17:
                    continue
                kicking_values = extract_kicking_values(event.get("stats") or {})
                if kicking_values:
                    kicking_week_values[(player_id, week)] = kicking_values

        unmatched = []
        failed_events = []
        for event in summaries.get("events") or []:
            if event.get("http_status") != 200:
                failed_events.append({"event_id": event.get("event_id"), "status": event.get("http_status")})
                continue
            week = int(event.get("week") or 0)
            if not 1 <= week <= 17:
                continue
            name_lookup = defaultdict(list)
            for player in event.get("players") or []:
                if player.get("team_id") is not None:
                    name_lookup[int(player["team_id"])].append((
                        normalize_name(player.get("name")),
                        int(player["player_id"]),
                        player.get("name") or "",
                    ))
                player_id = int(player.get("player_id") or 0)
                if player_id in players and player_id > 0:
                    base_values = extract_player_values(player.get("groups") or {})
                    target = player_week_values[(player_id, week)]
                    for stat_id, value in base_values.items():
                        target[int(stat_id)] += n(value)
            apply_scoring_plays(event, player_week_values, dst_week_values, dst_player_by_team, name_lookup, unmatched)
            for team_id, values in dst_values_for_event(event, dst_team_ids, extra_defense).items():
                target = dst_week_values[(dst_player_by_team[team_id], week)]
                for stat_id, value in values.items():
                    target[int(stat_id)] += n(value)

        # Overlay exact kicking distance splits and PATs from athlete game logs.
        for player_week, kicking_values in kicking_week_values.items():
            player_week_values[player_week].update(kicking_values)

        direct_week_points = defaultdict(list)
        multiweek_matchup_points = defaultdict(list)
        unknown_boxscore_rows = 0
        for row in boxscore_rows:
            try:
                pid = int(row["player_id"])
            except (KeyError, TypeError, ValueError):
                continue
            points = n(row.get("matchup_points"))
            if row.get("points_type") == "single_scoring_period" and row.get("scoring_period") is not None:
                direct_week_points[(pid, int(row["scoring_period"]))].append(points)
            elif row.get("points_type") == "multi_scoring_period_matchup_total":
                periods = tuple(sorted(int(x) for x in row.get("matchup_scoring_periods") or []))
                if periods:
                    multiweek_matchup_points[(pid, periods)].append(points)
            else:
                unknown_boxscore_rows += 1

        season_records = []
        mismatch_count = 0
        multiweek_matchup_audit = []
        direct_week_mismatches = []
        direct_week_conflicts = []
        stat_gap_counts = Counter()
        mismatch_sample = []
        missing_season_totals = []
        total_week_rows = 0
        for player_id, player in players.items():
            is_dst = player_id < 0
            week_values = dst_week_values if is_dst else player_week_values
            weeks = {}
            stat_sums = defaultdict(float)
            for week in range(1, 18):
                values = dict(week_values.get((player_id, week), {}))
                reconstructed_points = calculate_points(values, items, is_dst=is_dst)
                direct_values = direct_week_points.get((player_id, week), [])
                direct_unique = sorted(set(round(value, 4) for value in direct_values))
                points = direct_unique[0] if len(direct_unique) == 1 else reconstructed_points
                points_source = "ESPN mBoxscore appliedStatTotal" if len(direct_unique) == 1 else "ESPN game-summary reconstruction"
                if len(direct_unique) > 1:
                    direct_week_conflicts.append({"player_id": player_id, "week": week, "actual_values": direct_unique})
                elif len(direct_unique) == 1 and abs(direct_unique[0] - reconstructed_points) > 0.02:
                    direct_week_mismatches.append({
                        "player_id": player_id,
                        "name": player.get("player_name"),
                        "week": week,
                        "mBoxscore_points": direct_unique[0],
                        "reconstructed_points": reconstructed_points,
                        "difference": round(direct_unique[0] - reconstructed_points, 4),
                    })
                for stat_id, value in values.items():
                    stat_sums[int(stat_id)] += n(value)
                weeks[str(week)] = {
                    "week": week,
                    "fantasy_points": points,
                    "reconstructed_fantasy_points": reconstructed_points,
                    "points_source": points_source,
                    "stats": {str(key): value for key, value in sorted(values.items()) if value},
                }
                total_week_rows += 1

            expected = player.get("season_total")
            if expected is None:
                missing_season_totals.append(player_id)
            mismatch = None
            if expected is not None:
                calculated = round(sum(entry["fantasy_points"] for entry in weeks.values()), 4)
                if abs(calculated - float(expected)) > 0.02:
                    mismatch = {
                        "player_id": player_id,
                        "name": player.get("player_name"),
                        "position_id": player.get("position_id"),
                        "season_total": expected,
                        "weekly_sum": calculated,
                        "difference": round(float(expected) - calculated, 4),
                    }

            gaps = []
            season_stats = player.get("season_stats") or {}
            for item in items:
                stat_id = int(item["statId"])
                points = item.get("points", 0)
                overrides = item.get("pointsOverrides") or {}
                if is_dst and "16" in overrides:
                    points = overrides["16"]
                if n(points) == 0:
                    continue
                expected_stat = n(season_stats.get(str(stat_id), 0))
                actual_stat = stat_sums.get(stat_id, 0)
                if abs(expected_stat - actual_stat) > 0.01:
                    gaps.append({
                        "stat_id": stat_id,
                        "expected_stat": expected_stat,
                        "weekly_stat_sum": actual_stat,
                        "points": n(points),
                    })
                    stat_gap_counts[str(stat_id)] += 1
            if mismatch:
                mismatch["stat_gaps"] = gaps
                mismatch_count += 1
                if len(mismatch_sample) < 100:
                    mismatch_sample.append(mismatch)

            for (pid, periods), actual_values in multiweek_matchup_points.items():
                if pid != player_id:
                    continue
                actual_unique = sorted(set(round(value, 4) for value in actual_values))
                if len(actual_unique) != 1:
                    multiweek_matchup_audit.append({
                        "player_id": pid,
                        "periods": list(periods),
                        "actual_values": actual_unique,
                        "status": "conflicting_source_rows",
                        "matches": False,
                    })
                    continue
                reconstructed_sum = round(sum(
                    n((weeks.get(str(period)) or {}).get("reconstructed_fantasy_points"))
                    for period in periods if 1 <= period <= 17
                ), 4)
                actual_sum = actual_unique[0]
                multiweek_matchup_audit.append({
                    "player_id": pid,
                    "periods": list(periods),
                    "actual_matchup_points": actual_sum,
                    "reconstructed_weekly_sum": reconstructed_sum,
                    "difference": round(actual_sum - reconstructed_sum, 4),
                    "matches": abs(actual_sum - reconstructed_sum) <= 0.02,
                })

            season_records.append({
                "season": year,
                "player_id": player_id,
                "player_name": player.get("player_name"),
                "position_id": player.get("position_id"),
                "pro_team_id": player.get("pro_team_id"),
                "season_fantasy_points": expected,
                "calculated_weekly_points": round(sum(entry["fantasy_points"] for entry in weeks.values()), 4),
                "season_total_match": mismatch is None,
                "stat_gaps": gaps,
                "weeks": weeks,
                "season_stats": season_stats,
                "data_source": "ESPN player gamelogs + game-summary scoring plays + league scoring settings",
            })

        season_records.sort(key=lambda record: record["player_id"])
        output = {
            "meta": {
                "season": year,
                "player_count": len(season_records),
                "source": "ESPN player gamelogs + game summaries",
                "weeks": 17,
            },
            "players": season_records,
        }
        with gzip.open(ARTIFACT_OUT / f"legacy_weekly_reconstruction_{year}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

        with (ARTIFACT_OUT / f"legacy_weekly_points_{year}.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["season", "player_id", "player_name", "position_id", "week", "fantasy_points"])
            for record in season_records:
                for week, entry in record["weeks"].items():
                    writer.writerow([year, record["player_id"], record["player_name"], record["position_id"], week, entry["fantasy_points"]])

        audit["seasons"][str(year)] = {
            "player_seasons_reconstructed": len(season_records),
            "positive_player_seasons": sum(1 for record in season_records if record["player_id"] > 0),
            "dst_seasons": sum(1 for record in season_records if record["player_id"] < 0),
            "weekly_rows": total_week_rows,
            "season_total_matches": len(season_records) - mismatch_count - len(missing_season_totals),
            "season_total_mismatches": mismatch_count,
            "stat_gap_counts": dict(stat_gap_counts),
            "unmatched_scoring_plays": len(unmatched),
            "unmatched_scoring_play_sample": unmatched[:100],
            "failed_summary_events": failed_events,
            "missing_player_logs": missing_player_logs,
            "missing_season_totals": missing_season_totals,
            "boxscore_single_week_rows": sum(len(values) for values in direct_week_points.values()),
            "boxscore_single_week_player_weeks": len(direct_week_points),
            "boxscore_single_week_reconstruction_mismatches": len(direct_week_mismatches),
            "boxscore_single_week_mismatch_sample": direct_week_mismatches[:50],
            "boxscore_single_week_conflicts": direct_week_conflicts,
            "boxscore_multiweek_rows": sum(len(values) for values in multiweek_matchup_points.values()),
            "boxscore_multiweek_matchup_checks": len(multiweek_matchup_audit),
            "boxscore_multiweek_mismatches": sum(1 for row in multiweek_matchup_audit if not row.get("matches", False)),
            "boxscore_multiweek_mismatch_sample": [row for row in multiweek_matchup_audit if not row.get("matches", False)][:50],
            "mismatch_sample": mismatch_sample,
        }
        print(
            f"{year}: players={len(season_records)} matches={audit['seasons'][str(year)]['season_total_matches']} "
            f"mismatches={mismatch_count} missing_logs={len(missing_player_logs)} "
            f"unmatched_plays={len(unmatched)} stat_gaps={dict(stat_gap_counts)}"
        )

    audit_path = ARTIFACT_OUT / "legacy_weekly_reconstruction_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Wrote {audit_path}")

    total_mismatches = sum(v.get("season_total_mismatches", 0) for v in audit["seasons"].values())
    total_gaps = sum(sum(v.get("stat_gap_counts", {}).values()) for v in audit["seasons"].values())
    total_multiweek_mismatches = sum(v.get("boxscore_multiweek_mismatches", 0) for v in audit["seasons"].values())
    total_multiweek_conflicts = sum(len(v.get("boxscore_single_week_conflicts", [])) for v in audit["seasons"].values())
    if audit["errors"] or total_mismatches or total_gaps or total_multiweek_mismatches or total_multiweek_conflicts:
        raise SystemExit(
            f"VALIDATION FAIL: source errors={len(audit['errors'])}; "
            f"season mismatches={total_mismatches}; scored stat gaps={total_gaps}; "
            f"multiweek matchup mismatches={total_multiweek_mismatches}; "
            f"single-week source conflicts={total_multiweek_conflicts}. "
            "Do not promote legacy weekly data."
        )
    print("VALIDATION PASS: player-season totals, scored stat categories, and playoff matchup totals reconcile.")


if __name__ == "__main__":
    main()
