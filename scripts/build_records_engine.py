import json
from collections import defaultdict
from pathlib import Path

PROJECT = Path(rCUsersyatesd01OneDrive - Montgomery County GovernmentDocumentsFantasyffl-site)
PROCESSED = PROJECT  data  processed
ANALYTICS = PROJECT  data  analytics


def load(name, folder=PROCESSED)
    with (folder  name).open(r, encoding=utf-8) as f
        return json.load(f)


def save(name, obj)
    ANALYTICS.mkdir(parents=True, exist_ok=True)
    path = ANALYTICS  name
    with path.open(w, encoding=utf-8) as f
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write(n)
    return path


def completed_matchups(matchups)
    Return played games with both teams and usable scores.
    out = []
    for m in matchups
        h = m.get(home_team_id)
        a = m.get(away_team_id)
        hs = m.get(home_score)
        aws = m.get(away_score)
        if h is None or a is None or hs is None or aws is None
            continue
        try
            hs = float(hs)
            aws = float(aws)
        except (TypeError, ValueError)
            continue

        # Futureunplayed ESPN rows in 2026 appear as 0-0 with no result.
        if hs == 0 and aws == 0 and m.get(winner) in (None, UNDECIDED)
            continue

        row = dict(m)
        row[home_score] = hs
        row[away_score] = aws
        out.append(row)
    return out


def result_for_team(m, team_id)
    Use ESPN winner first; equal-score no-winner is a genuine tie.
    if team_id not in (m.get(home_team_id), m.get(away_team_id))
        return None

    if m.get(winner) == HOME
        return W if team_id == m.get(home_team_id) else L
    if m.get(winner) == AWAY
        return W if team_id == m.get(away_team_id) else L

    hs = float(m[home_score])
    aws = float(m[away_score])
    if abs(hs - aws) = 0.01
        return T

    # Defensive fallback for any historical row where ESPN omitted winner.
    if team_id == m.get(home_team_id)
        return W if hs  aws else L
    return W if aws  hs else L


def person_name_map(people)
    return {p[person_id] p.get(name) or p[person_id] for p in people}


def team_person_map(teams)
    return {(t[season], t[team_id]) t.get(person_id) for t in teams}


def build_head_to_head(matchups, teams)
    Career head-to-head records by canonical person_id.
    team_person = team_person_map(teams)
    stats = {}

    def pair_key(a, b)
        return tuple(sorted((a, b)))

    for m in completed_matchups(matchups)
        a_pid = team_person.get((m[season], m[home_team_id]))
        b_pid = team_person.get((m[season], m[away_team_id]))
        if not a_pid or not b_pid or a_pid == b_pid
            continue

        key = pair_key(a_pid, b_pid)
        row = stats.setdefault(key, {
            person_a_id key[0],
            person_b_id key[1],
            games 0,
            person_a_wins 0,
            person_b_wins 0,
            ties 0,
            person_a_points_for 0.0,
            person_b_points_for 0.0,
            first_season m[season],
            last_season m[season],
            regular_season_games 0,
            playoff_games 0,
        })

        a_is_home = a_pid == a_pid  # explicit for readability below
        home_pid = a_pid
        away_pid = b_pid
        home_result = result_for_team(m, m[home_team_id])

        row[games] += 1
        row[first_season] = min(row[first_season], m[season])
        row[last_season] = max(row[last_season], m[season])
        row[person_a_points_for] += float(m[home_score]) if home_pid == key[0] else float(m[away_score])
        row[person_b_points_for] += float(m[away_score]) if away_pid == key[1] else float(m[home_score])

        tier = m.get(playoff_tier_type)
        if tier == NONE
            row[regular_season_games] += 1
        else
            row[playoff_games] += 1

        # Determine result from each canonical person's team.
        if home_result == W
            winner_pid = home_pid
        elif home_result == L
            winner_pid = away_pid
        else
            winner_pid = None

        if winner_pid is None
            row[ties] += 1
        elif winner_pid == key[0]
            row[person_a_wins] += 1
        else
            row[person_b_wins] += 1

    return sorted(stats.values(), key=lambda x (x[person_a_id], x[person_b_id]))


def build_streaks(matchups, teams)
    Longest WLT streaks for each canonical person, plus current streak.
    team_person = team_person_map(teams)
    games = []
    for m in completed_matchups(matchups)
        # Regular season only for streaks; playoff runs are tracked separately.
        if m.get(playoff_tier_type) != NONE
            continue
        for side in (home, away)
            team_id = m.get(f{side}_team_id)
            pid = team_person.get((m[season], team_id))
            if not pid
                continue
            games.append({
                person_id pid,
                season m[season],
                period m.get(matchup_period_id),
                matchup_id m.get(matchup_id),
                result result_for_team(m, team_id),
            })

    games.sort(key=lambda x (x[person_id], x[season], x[period] if x[period] is not None else -1, str(x[matchup_id])))
    out = {}

    for pid in sorted({g[person_id] for g in games})
        mine = [g for g in games if g[person_id] == pid]
        best = {W 0, L 0, T 0}
        current = None
        current_len = 0
        current_start = None
        longest_detail = {}

        for g in mine
            r = g[result]
            if r == current
                current_len += 1
            else
                current = r
                current_len = 1
                current_start = g

            if current_len  best[r]
                best[r] = current_len
                longest_detail[r] = {
                    length current_len,
                    start_season current_start[season],
                    start_period current_start[period],
                    end_season g[season],
                    end_period g[period],
                }

        out[pid] = {
            person_id pid,
            regular_season_longest_win_streak best[W],
            regular_season_longest_loss_streak best[L],
            regular_season_longest_tie_streak best[T],
            regular_season_current_streak {
                result current,
                length current_len,
            },
            longest_streak_details longest_detail,
        }

    return sorted(out.values(), key=lambda x x[person_id])


def build_league_records(matchups, standings, teams)
    Produce raw league records; no subjective rankings.
    team_person = team_person_map(teams)
    played = completed_matchups(matchups)
    records = {
        career {},
        single_season {},
        single_game {},
    }

    # Career totals from official standings.
    career = defaultdict(lambda {
        person_id None, seasons 0, games 0,
        wins 0, losses 0, ties 0,
        points_for 0.0, points_against 0.0,
    })
    for s in standings
        pid = s.get(person_id)
        if not pid
            continue
        c = career[pid]
        c[person_id] = pid
        c[seasons] += 1
        c[wins] += int(s.get(wins) or 0)
        c[losses] += int(s.get(losses) or 0)
        c[ties] += int(s.get(ties) or 0)
        c[points_for] += float(s.get(points_for) or 0)
        c[points_against] += float(s.get(points_against) or 0)
        c[games] += int(s.get(wins) or 0) + int(s.get(losses) or 0) + int(s.get(ties) or 0)

    for c in career.values()
        c[win_pct] = (c[wins] + 0.5  c[ties])  c[games] if c[games] else None
        c[points_per_game] = c[points_for]  c[games] if c[games] else None
        c[point_differential] = c[points_for] - c[points_against]
    records[career] = sorted(career.values(), key=lambda x x[person_id])

    # Single-season teamperson records.
    season_rows = []
    for s in standings
        pid = s.get(person_id)
        if not pid
            continue
        games = int(s.get(wins) or 0) + int(s.get(losses) or 0) + int(s.get(ties) or 0)
        pf = float(s.get(points_for) or 0)
        pa = float(s.get(points_against) or 0)
        season_rows.append({
            season s[season],
            team_id s[team_id],
            person_id pid,
            wins int(s.get(wins) or 0),
            losses int(s.get(losses) or 0),
            ties int(s.get(ties) or 0),
            games games,
            win_pct (int(s.get(wins) or 0) + 0.5  int(s.get(ties) or 0))  games if games else None,
            points_for pf,
            points_against pa,
            points_per_game pf  games if games else None,
            point_differential pf - pa,
            rank s.get(rank),
            final_standing s.get(final_standing),
        })
    records[single_season] = season_rows

    # Single-game records, one observation per matchup.
    game_rows = []
    for m in played
        hs = float(m[home_score])
        aws = float(m[away_score])
        game_rows.append({
            season m[season],
            matchup_id m[matchup_id],
            matchup_period_id m.get(matchup_period_id),
            playoff_tier_type m.get(playoff_tier_type),
            home_team_id m[home_team_id],
            away_team_id m[away_team_id],
            home_person_id team_person.get((m[season], m[home_team_id])),
            away_person_id team_person.get((m[season], m[away_team_id])),
            home_score hs,
            away_score aws,
            combined_score hs + aws,
            margin abs(hs - aws),
            winner m.get(winner),
        })
    records[single_game] = game_rows

    return records


def sort_numeric(rows, key, reverse=True)
    return sorted(rows, key=lambda r (r.get(key) is not None, r.get(key) if r.get(key) is not None else float(-inf)), reverse=reverse)

def top_single_team_scores(games, reverse=True, n=10):
    """
    Rank individual team scores across all completed matchups.
    Includes both home and away teams.
    """
    rows = []

    for g in games:
        rows.append({
            **g,
            "team_side": "home",
            "person_id": g["home_person_id"],
            "score": g["home_score"],
        })

        rows.append({
            **g,
            "team_side": "away",
            "person_id": g["away_person_id"],
            "score": g["away_score"],
        })

    return sorted(
        rows,
        key=lambda x: x["score"],
        reverse=reverse
    )[:n]

def build_league_record_catalog(records)
    Human-friendly record lists consumed directly by the future frontend.
    season = records[single_season]
    games = records[single_game]
    career = records[career]

    def top(rows, key, n=10)
        return sort_numeric(rows, key)[n]

    return {
        career {
            most_wins top(career, wins),
            most_points_for top(career, points_for),
            most_games top(career, games),
            best_win_pct [r for r in sorted(career, key=lambda x (x[games] = 20, x[win_pct] or 0), reverse=True)[10]],
            most_point_differential top(career, point_differential),
        },
        single_season {
            most_wins top(season, wins),
            most_points_for top(season, points_for),
            highest_points_per_game top(season, points_per_game),
            largest_point_differential top(season, point_differential),
            best_win_pct [r for r in sorted(season, key=lambda x (x[games] = 8, x[win_pct] or 0), reverse=True)[10]],
        },
          "single_game": {
            "highest_score": top_single_team_scores(games, reverse=True),
            "lowest_score": top_single_team_scores(games, reverse=False),
            "biggest_blowout": sorted(
                games,
                key=lambda x: x["margin"],
                reverse=True
            )[:10],
            "closest_games": sorted(
                games,
                key=lambda x: x["margin"]
            )[:10],
            "highest_combined_score": sorted(
                games,
                key=lambda x: x["combined_score"],
                reverse=True
            )[:10],
            "lowest_combined_score": sorted(
                games,
                key=lambda x: x["combined_score"]
            )[:10],
        },
    }


def main()
    people = load(people.json)
    teams = load(teams.json)
    matchups = load(matchups.json)
    standings = load(standings.json)

    names = person_name_map(people)
    h2h = build_head_to_head(matchups, teams)
    streaks = build_streaks(matchups, teams)
    records = build_league_records(matchups, standings, teams)
    catalog = build_league_record_catalog(records)

    # Add display names while preserving canonical IDs as the keys used by the app.
    for row in h2h
        row[person_a_name] = names.get(row[person_a_id], row[person_a_id])
        row[person_b_name] = names.get(row[person_b_id], row[person_b_id])
    for row in streaks
        row[person_name] = names.get(row[person_id], row[person_id])
    for row in records[career]
        row[person_name] = names.get(row[person_id], row[person_id])
    for row in records[single_season]
        row[person_name] = names.get(row[person_id], row[person_id])

    save(head_to_head.json, h2h)
    save(streaks.json, streaks)
    save(league_records.json, records)
    save(league_record_catalog.json, catalog)

    print(=== RECORDS ENGINE ===)
    print(fHead-to-head pairings {len(h2h)})
    print(fStreak profiles {len(streaks)})
    print(fCareer records {len(records['career'])})
    print(fSeason records {len(records['single_season'])})
    print(fPlayed games {len(records['single_game'])})
    print(nWrote)
    for name in (head_to_head.json, streaks.json, league_records.json, league_record_catalog.json)
        print(f  {ANALYTICS  name})

    # Useful sanity checks.
    total_h2h_games = sum(r[games] for r in h2h)
    unique_people = len({t.get(person_id) for t in teams if t.get(person_id)})
    print(n=== SANITY CHECKS ===)
    print(fCanonical people with team history {unique_people})
    print(fH2H games represented {total_h2h_games})
    print(PASS records engine completed)


if __name__ == __main__
    main()
