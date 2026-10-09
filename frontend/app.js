const DATA = {};

const routes = {
  dashboard: "Dashboard",
  seasons: "Seasons",
  owners: "Owners",
  career: "Career",
  records: "Records",
  analytics: "Analytics",
  draft: "Draft",
  matchups: "Matchups",
  rivalries: "Rivalries",
};

const $ = (s) => document.querySelector(s);
const fmt = (n, digits = 0) => Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
const pct = (n, digits = 1) => `${(Number(n || 0) * 100).toFixed(digits)}%`;
const esc = (s) => String(s ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[c]));
const initials = (name) => String(name || "?").split(/\s+/).filter(Boolean).slice(0,2).map(x => x[0]).join("").toUpperCase();

async function loadOne(candidates) {
  let lastError = null;
  for (const path of candidates) {
    try {
      const r = await fetch(path);
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return await r.json();
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("Data file not found");
}

async function loadData() {
  const sources = {
    advanced_stats: ["data/analytics/advanced_stats.json", "data/advanced_stats.json"],
    teams: ["data/processed/teams.json", "data/teams.json"],
    people: ["data/processed/people.json", "data/people.json"],
    matchups: ["data/processed/matchups.json", "data/matchups.json"],
    draft_picks: ["data/processed/draft_picks.json", "data/draft_picks.json"],
    standings: ["data/processed/standings.json", "data/standings.json"],
    seasons: ["data/processed/seasons.json", "data/seasons.json"],
    draft_analytics: ["data/analytics/draft_analytics.json", "data/draft_analytics.json"],
    owner_records: ["data/analytics/owner_records.json", "data/owner_records.json"],
    championships: ["data/analytics/championships.json", "data/championships.json"],
  };
  const names = Object.keys(sources);
  const vals = await Promise.all(names.map(n => loadOne(sources[n])));
  names.forEach((n,i) => DATA[n] = vals[i]);

  DATA.personNames = {};
  for (const x of DATA.advanced_stats.career) DATA.personNames[x.person_id] = x.person_name;
  for (const x of DATA.people) DATA.personNames[x.person_id] = x.name;

  DATA.champions = buildChampions();
  DATA.podiums = buildPodiums();
  DATA.podiumCounts = {};
  for (const p of DATA.podiums) {
    for (const [place, id] of [["championships", p.champion_person_id], ["runner_ups", p.runner_up_person_id], ["third_place_finishes", p.third_place_person_id]]) {
      DATA.podiumCounts[id] ??= { championships: 0, runner_ups: 0, third_place_finishes: 0 };
      DATA.podiumCounts[id][place]++;
    }
  }
  DATA.champCounts = {};
  for (const c of DATA.champions) {
    DATA.champCounts[c.person_id] ??= { name: c.person_name, count: 0, years: [] };
    DATA.champCounts[c.person_id].count++;
    DATA.champCounts[c.person_id].years.push(c.season);
  }
}

function personName(id) {
  return DATA.personNames[id] || "Unknown Owner";
}

function buildChampions() {
  const out = [];
  const completedSeasons = (DATA.championships || []).filter(x => x.status === "COMPLETE").map(x => Number(x.season));
  for (const season of completedSeasons) {
    const rows = DATA.matchups.filter(x => x.season === season && x.playoff_tier_type === "WINNERS_BRACKET" && x.away_team_id != null && x.winner !== "UNDECIDED");
    if (!rows.length) continue;
    const maxPeriod = Math.max(...rows.map(x => x.matchup_period_id));
    const finals = rows.filter(x => x.matchup_period_id === maxPeriod);
    if (finals.length !== 1) continue;
    const f = finals[0];
    const pid = f.winner === "HOME" ? f.home_person_id : f.away_person_id;
    out.push({ season, person_id: pid, person_name: personName(pid), team_id: f.winner_team_id, score: f.winner === "HOME" ? f.home_score : f.away_score, matchup_id: f.matchup_id });
  }
  return out;
}

function buildPodiums() {
  const out = [];
  for (let season = 2011; season <= 2025; season++) {
    const winners = DATA.matchups.filter(m =>
      m.season === season &&
      m.playoff_tier_type === "WINNERS_BRACKET" &&
      m.away_team_id != null &&
      m.winner !== "UNDECIDED"
    );
    if (!winners.length) continue;

    const finalPeriod = Math.max(...winners.map(m => m.matchup_period_id));
    const finals = winners.filter(m => m.matchup_period_id === finalPeriod);
    if (finals.length !== 1) continue;

    const priorRound = winners.filter(m => m.matchup_period_id === finalPeriod - 1);
    const semifinalLosers = new Set(
      priorRound.map(m => m.winner === "HOME" ? m.away_team_id : m.home_team_id)
    );

    const thirdGames = DATA.matchups.filter(m =>
      m.season === season &&
      m.playoff_tier_type === "WINNERS_CONSOLATION_LADDER" &&
      m.matchup_period_id === finalPeriod &&
      m.away_team_id != null &&
      m.winner !== "UNDECIDED" &&
      semifinalLosers.has(m.home_team_id) &&
      semifinalLosers.has(m.away_team_id)
    );
    if (thirdGames.length !== 1) continue;

    const final = finals[0];
    const thirdGame = thirdGames[0];
    out.push({
      season,
      champion_person_id: final.winner === "HOME" ? final.home_person_id : final.away_person_id,
      runner_up_person_id: final.winner === "HOME" ? final.away_person_id : final.home_person_id,
      third_place_person_id: thirdGame.winner === "HOME" ? thirdGame.home_person_id : thirdGame.away_person_id
    });
  }
  return out;
}

function playoffFinishForSeason(season) {
  const seasonTeams = DATA.teams.filter(t => t.season === season && t.playoff_seed != null);
  if (!seasonTeams.length) return {};

  const seedByTeam = {};
  for (const t of seasonTeams) seedByTeam[t.team_id] = t.playoff_seed;

  const winners = DATA.matchups.filter(m =>
    m.season === season &&
    m.playoff_tier_type === "WINNERS_BRACKET" &&
    m.away_team_id != null &&
    m.winner !== "UNDECIDED"
  );
  if (!winners.length) return {};

  const finalPeriod = Math.max(...winners.map(m => m.matchup_period_id));
  const finals = winners.filter(m => m.matchup_period_id === finalPeriod);
  if (finals.length !== 1) return {};

  const finish = {};
  const final = finals[0];
  const championId = final.winner === "HOME" ? final.home_team_id : final.away_team_id;
  const runnerUpId = final.winner === "HOME" ? final.away_team_id : final.home_team_id;
  finish[championId] = 1;
  finish[runnerUpId] = 2;

  // Teams eliminated in later rounds finish ahead of teams eliminated earlier.
  // The final-period WINNERS_CONSOLATION_LADDER games settle those placement groups.
  const eliminationGroups = {};
  const winnerPeriods = [...new Set(winners.map(m => m.matchup_period_id))].sort((a,b) => a-b);

  for (const period of winnerPeriods.slice(0, -1)) {
    for (const game of winners.filter(m => m.matchup_period_id === period)) {
      const loserId = game.winner === "HOME" ? game.away_team_id : game.home_team_id;
      const appearsLater = winners.some(m =>
        m.matchup_period_id > period &&
        (m.home_team_id === loserId || m.away_team_id === loserId)
      );
      if (!appearsLater) {
        (eliminationGroups[period] ||= []).push(loserId);
      }
    }
  }

  let nextFinish = 3;
  const eliminationRounds = Object.keys(eliminationGroups)
    .map(Number)
    .sort((a,b) => b-a);

  for (const period of eliminationRounds) {
    const teams = eliminationGroups[period];
    if (teams.length !== 2) continue;

    const placementGame = DATA.matchups.find(m =>
      m.season === season &&
      m.matchup_period_id === finalPeriod &&
      m.playoff_tier_type === "WINNERS_CONSOLATION_LADDER" &&
      ((m.home_team_id === teams[0] && m.away_team_id === teams[1]) ||
       (m.home_team_id === teams[1] && m.away_team_id === teams[0])) &&
      m.winner !== "UNDECIDED"
    );

    if (placementGame) {
      const winnerId = placementGame.winner === "HOME"
        ? placementGame.home_team_id
        : placementGame.away_team_id;
      const loserId = placementGame.winner === "HOME"
        ? placementGame.away_team_id
        : placementGame.home_team_id;
      finish[winnerId] = nextFinish;
      finish[loserId] = nextFinish + 1;
    } else {
      teams.sort((a,b) => seedByTeam[a] - seedByTeam[b]);
      finish[teams[0]] = nextFinish;
      finish[teams[1]] = nextFinish + 1;
    }

    nextFinish += 2;
  }

  // ESPN's LOSERS_CONSOLATION_LADDER is a moving ladder:
  // winners move toward the top, losers toward the bottom.
  // Start with the regular-season playoff seeds, then replay each ladder round.
  const playoffTeams = new Set(Object.keys(finish).map(Number));
  let ladder = seasonTeams
    .filter(t => !playoffTeams.has(t.team_id))
    .sort((a,b) => a.playoff_seed - b.playoff_seed)
    .map(t => t.team_id);

  const ladderGames = DATA.matchups
    .filter(m =>
      m.season === season &&
      m.playoff_tier_type === "LOSERS_CONSOLATION_LADDER" &&
      m.away_team_id != null &&
      m.winner !== "UNDECIDED"
    )
    .sort((a,b) => a.matchup_period_id - b.matchup_period_id);

  const ladderPeriods = [...new Set(ladderGames.map(m => m.matchup_period_id))].sort((a,b) => a-b);

  for (const period of ladderPeriods) {
    const games = ladderGames.filter(m => m.matchup_period_id === period);
    const positions = {};
    ladder.forEach((teamId, index) => { positions[teamId] = index; });
    const updated = ladder.slice();

    for (const game of games) {
      const homePos = positions[game.home_team_id];
      const awayPos = positions[game.away_team_id];
      if (homePos == null || awayPos == null) continue;

      const topPos = Math.min(homePos, awayPos);
      const bottomPos = Math.max(homePos, awayPos);
      const winnerId = game.winner === "HOME" ? game.home_team_id : game.away_team_id;
      const loserId = game.winner === "HOME" ? game.away_team_id : game.home_team_id;

      updated[topPos] = winnerId;
      updated[bottomPos] = loserId;
    }

    ladder = updated;
  }

  ladder.forEach((teamId, index) => {
    finish[teamId] = nextFinish + index;
  });

  return finish;
}

function teamForSeason(season, teamId) {
  return DATA.teams.find(x => x.season === season && x.team_id === teamId);
}

function currentRows() {
  const standings = DATA.standings.filter(x => x.season === 2026);
  return standings.sort((a,b) => b.wins - a.wins || b.points_for - a.points_for);
}

function nav(route) {
  document.querySelectorAll(".nav a").forEach(a => a.classList.toggle("active", a.dataset.route === route));
  $("#breadcrumbs").textContent = `League / ${routes[route] || "Dashboard"}`;
}

function render() {
  const hash = location.hash.replace("#", "") || "dashboard";
  const [route, param] = hash.split("/");
  nav(route);
  if (route === "owner" && param) return renderOwner(param);
  if (route === "season" && param) return renderSeason(Number(param));
  if (route === "dashboard") return renderDashboard();
  if (route === "seasons") return renderSeasons();
  if (route === "owners") return renderOwners();
  if (route === "career") return renderCareer();
  if (route === "records") return renderRecords();
  if (route === "analytics") return renderAnalytics();
  if (route === "draft") return renderDraft();
  if (route === "matchups") return renderMatchups();
  if (route === "rivalries") return renderRivalries();
  if (route === "rivalry" && param) { const p=hash.split("/"); return renderRivalry(decodeURIComponent(p[1]),decodeURIComponent(p[2])); }
  location.hash = "dashboard";
}

function renderDashboard() {
  const current = currentRows();
  const completed2026 = DATA.matchups.filter(x => x.season === 2026 && x.playoff_tier_type === "NONE" && x.winner !== "UNDECIDED");
  const week = completed2026.length ? Math.max(...completed2026.map(x => x.matchup_period_id)) : 0;

  const historicalCareer = DATA.advanced_stats.career.filter(x => x.seasons >= 3);
  const career = [...historicalCareer].sort((a,b) => b.actual_win_pct - a.actual_win_pct).slice(0,5);
  const champs = Object.entries(DATA.champCounts).map(([person_id,v]) => ({person_id,...v})).sort((a,b) => b.count-a.count || a.name.localeCompare(b.name));
  const topPF = [...DATA.advanced_stats.season].filter(x => Number(x.season) <= 2025).sort((a,b) => b.points_for-a.points_for).slice(0,5);

  const currentLeader = current[0];
  const currentScoring = [...current].sort((a,b)=>b.points_for-a.points_for)[0];
  const currentLowScoring = [...current].sort((a,b)=>a.points_for-b.points_for)[0];
  const defending = DATA.champions[DATA.champions.length-1];
  const allTimeChamp = champs[0];

  let recentGames = completed2026.slice().sort((a,b)=>b.matchup_period_id-a.matchup_period_id || b.matchup_id-a.matchup_id).slice(0,6);
  if (!recentGames.length) recentGames = historicalCareer.length ? [] : [];

  const historicalMatchups = DATA.matchups.filter(x=>Number(x.season)<=2025 && x.away_team_id!=null && x.winner!=="UNDECIDED");
  let biggestBlowout = null, highestScore = null;
  for (const m of historicalMatchups) {
    const margin=Math.abs((m.home_score||0)-(m.away_score||0));
    if(!biggestBlowout || margin>biggestBlowout.margin) biggestBlowout={...m,margin};
    for(const side of ["home","away"]){
      const score=side==="home"?m.home_score:m.away_score;
      if(score!=null && (!highestScore || score>highestScore.score)) highestScore={...m,side,score};
    }
  }

  const currentRowsHtml = current.map((x,i) => "<tr class=\"clickable\" onclick=\"location.hash='owner/"+encodeURIComponent(x.person_id)+"\"><td class=\"rank\">"+(i+1)+"</td><td><div class=\"owner-link\">"+esc(personName(x.person_id))+"</div><div class=\"team-name\">"+esc(teamForSeason(2026,x.team_id)?.team_name||"")+"</div></td><td class=\"record\">"+x.wins+"-"+x.losses+(x.ties?"-"+x.ties:"")+"</td><td>"+fmt(x.points_for,2)+"</td><td>"+fmt(x.points_against,2)+"</td></tr>").join("");

  const recentHtml = recentGames.map(m => {
    const tie=m.winner==="TIE", hw=m.winner==="HOME", winner=tie?null:(hw?m.home_person_id:m.away_person_id);
    const result=tie?"TIE":esc(personName(winner));
    return "<div class=\"champ-row\"><div class=\"trophy\">⚔</div><div class=\"champ-name\"><strong>"+esc(personName(m.home_person_id))+" vs "+esc(personName(m.away_person_id))+"</strong><div class=\"champ-years\">Week "+m.matchup_period_id+" · "+fmt(m.home_score,2)+"–"+fmt(m.away_score,2)+"</div></div><div class=\""+(tie?"":"positive")+"\">"+result+"</div></div>";
  }).join("");

  const champHtml = champs.slice(0,6).map(x => "<div class=\"champ-row\"><div class=\"trophy\">🏆</div><div class=\"champ-name\"><a class=\"owner-link\" href=\"#owner/"+encodeURIComponent(x.person_id)+"\">"+esc(x.name)+"</a><div class=\"champ-years\">"+x.years.join(" · ")+"</div></div><div class=\"champ-count\">"+x.count+"</div></div>").join("");

  $("#app").innerHTML =
    "<section class=\"hero\"><div class=\"hero-grid\"><div><div class=\"hero-kicker\">DMV Fantasy Football · League HQ</div><h1>15 seasons of history.<br>One place to settle the arguments.</h1><p>Championships, owner careers, H2H history, draft records and advanced analytics from 2011 through the current 2026 season.</p></div><div class=\"hero-side\"><div class=\"hero-big\">2026</div><div class=\"hero-label\">CURRENT SEASON · WEEK "+week+"</div><div style=\"margin-top:18px;color:rgba(255,255,255,.72);font-size:13px\">"+(currentLeader?"<strong>"+esc(personName(currentLeader.person_id))+"</strong> leads at "+currentLeader.wins+"–"+currentLeader.losses+".":"Season data loading.")+"</div></div></div></section>"+
    "<div class=\"stats-grid\"><div class=\"stat-card\"><div class=\"stat-label\">CURRENT LEADER</div><div class=\"stat-value\">"+esc(currentLeader?personName(currentLeader.person_id):"—")+"</div><div class=\"stat-meta\">"+(currentLeader?currentLeader.wins+"–"+currentLeader.losses+" through Week "+week:"—")+"</div></div><div class=\"stat-card\"><div class=\"stat-label\">DEFENDING CHAMPION</div><div class=\"stat-value\">"+esc(defending?.person_name||"—")+"</div><div class=\"stat-meta\">"+(defending?defending.season+" champion":"—")+"</div></div><div class=\"stat-card\"><div class=\"stat-label\">ALL-TIME TITLES</div><div class=\"stat-value\">"+(allTimeChamp?.count||0)+"</div><div class=\"stat-meta\">"+esc(allTimeChamp?.name||"—")+" leads the league</div></div><div class=\"stat-card\"><div class=\"stat-label\">DRAFT PICKS</div><div class=\"stat-value\">"+fmt(DATA.draft_picks.length)+"</div><div class=\"stat-meta\">Complete draft archive</div></div></div>"+
    "<div class=\"grid-2\"><section class=\"card\"><div class=\"card-head\"><div><h2>2026 Standings</h2><div class=\"subtle\">Through Week "+week+"</div></div><a class=\"link\" href=\"#seasons\">Season archive →</a></div><div class=\"table-wrap\"><table><thead><tr><th>#</th><th>Owner</th><th>Record</th><th>PF</th><th>PA</th></tr></thead><tbody>"+currentRowsHtml+"</tbody></table></div></section>"+
    "<section class=\"card\"><div class=\"card-head\"><div><h2>2026 Scoring Race</h2><div class=\"subtle\">Points for through Week "+week+"</div></div><a class=\"link\" href=\"#matchups\">Matchups →</a></div><div class=\"card-body\"><div class=\"pulse-card\"><div class=\"pulse-kicker\">LEADING SCORER</div><div class=\"pulse-value\">"+esc(currentScoring?personName(currentScoring.person_id):"—")+"</div><div class=\"pulse-meta\">"+(currentScoring?fmt(currentScoring.points_for,2)+" points":"—")+"</div></div><div class=\"pulse-card\" style=\"margin-top:10px\"><div class=\"pulse-kicker\">LOWEST CURRENT SCORE</div><div class=\"pulse-value\">"+esc(currentLowScoring?personName(currentLowScoring.person_id):"—")+"</div><div class=\"pulse-meta\">"+(currentLowScoring?fmt(currentLowScoring.points_for,2)+" points":"—")+"</div></div></div></section></div>"+
    "<div class=\"grid-2\" style=\"margin-top:18px\"><section class=\"card\"><div class=\"card-head\"><div><h2>Recent 2026 Results</h2><div class=\"subtle\">Latest completed games</div></div><a class=\"link\" href=\"#matchups\">Full archive →</a></div><div class=\"card-body\">"+(recentHtml||"<div class=\"empty\">No completed games yet.</div>")+"</div></section>"+
    "<section class=\"card\"><div class=\"card-head\"><div><h2>Championship Race</h2><div class=\"subtle\">2011–2025 decided seasons</div></div><a class=\"link\" href=\"#records\">Records →</a></div><div class=\"card-body\">"+champHtml+"</div></section></div>"+
    "<div class=\"grid-2\" style=\"margin-top:18px\"><section class=\"card\"><div class=\"card-head\"><div><h2>Career Win % Leaders</h2><div class=\"subtle\">Minimum 3 seasons</div></div><a class=\"link\" href=\"#owners\">All owners →</a></div><div class=\"table-wrap\"><table><thead><tr><th>Owner</th><th>Seasons</th><th>Record</th><th>Win %</th></tr></thead><tbody>"+career.map((x,i)=>"<tr class=\"clickable\" onclick=\"location.hash='owner/"+encodeURIComponent(x.person_id)+"\"><td><span class=\"rank\">"+(i+1)+"</span> <span class=\"owner-link\">"+esc(x.person_name)+"</span></td><td>"+x.seasons+"</td><td>"+x.actual_wins+"-"+x.actual_losses+(x.actual_ties?"-"+x.actual_ties:"")+"</td><td class=\"positive\">"+pct(x.actual_win_pct)+"</td></tr>").join("")+"</tbody></table></div></section>"+
    "<section class=\"card\"><div class=\"card-head\"><div><h2>League History Nuggets</h2><div class=\"subtle\">The numbers worth remembering</div></div><a class=\"link\" href=\"#records\">More records →</a></div><div class=\"card-body\"><div class=\"champ-row\"><div class=\"trophy\">💥</div><div class=\"champ-name\"><strong>Biggest blowout</strong><div class=\"champ-years\">"+(biggestBlowout?fmt(biggestBlowout.margin,2)+" points · "+biggestBlowout.season+" · "+personName(biggestBlowout.home_person_id)+" vs "+personName(biggestBlowout.away_person_id):"—")+"</div></div></div><div class=\"champ-row\"><div class=\"trophy\">🔥</div><div class=\"champ-name\"><strong>Highest single-game score</strong><div class=\"champ-years\">"+(highestScore?fmt(highestScore.score,2)+" · "+personName(highestScore.side==="home"?highestScore.home_person_id:highestScore.away_person_id)+" · "+highestScore.season:"—")+"</div></div></div><div class=\"champ-row\"><div class=\"trophy\">👥</div><div class=\"champ-name\"><strong>Canonical owners</strong><div class=\"champ-years\">"+DATA.people.length+" identities across the league archive</div></div></div></div></section></div>";
}
function renderSeasons() {
  const rows = [];
  for (let season=2025; season>=2011; season--) {
    const seasonTeams = DATA.teams.filter(x => x.season === season);
    const standings = DATA.standings.filter(x => x.season === season);
    const games = DATA.matchups.filter(x => x.season === season && x.away_team_id != null && x.winner !== "UNDECIDED");
    const regularGames = games.filter(x => x.playoff_tier_type === "NONE");
    const champ = DATA.champions.find(x => x.season === season);
    const oneSeed = seasonTeams.find(x => x.playoff_seed === 1);
    const bestRecord = standings.slice().sort((a,b) => {
      const aw = (a.wins || 0) + (a.ties || 0) * 0.5;
      const bw = (b.wins || 0) + (b.ties || 0) * 0.5;
      return bw-aw || (b.points_for || 0)-(a.points_for || 0);
    })[0];
    const topScorer = standings.slice().sort((a,b) => (b.points_for || 0)-(a.points_for || 0))[0];
    rows.push({season, teams: seasonTeams.length, games: regularGames.length, completed: games.length, champ, oneSeed, bestRecord, topScorer});
  }

  const latest = rows[0];
  const allTimeTeams = DATA.teams.filter(x => Number(x.season) <= 2025);
  const uniqueOwners = new Set(allTimeTeams.map(x => x.person_id)).size;
  const largestSeason = rows.slice().sort((a,b)=>b.teams-a.teams || b.season-a.season)[0];
  const mostGames = rows.slice().sort((a,b)=>b.games-a.games || b.season-a.season)[0];
  const currentStandings = currentRows();
  const currentGames = DATA.matchups.filter(x => x.season === 2026 && x.away_team_id != null && x.winner !== "UNDECIDED");
  const currentWeek = currentGames.length ? Math.max(...currentGames.map(x=>x.matchup_period_id)) : 0;
  const recordText = x => x ? `${x.wins}-${x.losses}${x.ties ? `-${x.ties}` : ""}` : "—";
  const seedText = x => x?.playoff_seed != null ? `#${x.playoff_seed}` : "—";

  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">Archive</div><h1>Seasons</h1><p>A season-by-season record of champions, regular-season performance and how the league evolved.</p></div></div>
    <div class="pulse-grid">
      <div class="pulse-card"><div class="pulse-kicker">SEASONS COMPLETE</div><div class="pulse-value">15</div><div class="pulse-meta">2011–2025 · 2026 is in progress</div></div>
      <div class="pulse-card"><div class="pulse-kicker">CURRENT SEASON</div><div class="pulse-value">2026</div><div class="pulse-meta">Week ${currentWeek} · ${currentStandings.length} teams</div></div>
      <div class="pulse-card"><div class="pulse-kicker">LARGEST LEAGUE</div><div class="pulse-value">${largestSeason.teams}</div><div class="pulse-meta">${largestSeason.season} · teams</div></div>
      <div class="pulse-card"><div class="pulse-kicker">OWNERS IN ARCHIVE</div><div class="pulse-value">${uniqueOwners}</div><div class="pulse-meta">Canonical identities across all seasons</div></div>
    </div>
    <div class="section-title"><h2>Season Archive</h2><span class="mini">Click any season for the full page</span></div>
    <section class="card"><div class="table-wrap"><table><thead><tr><th>Season</th><th>Champion</th><th>#1 Seed</th><th>Best Record</th><th>Top Scorer</th><th>Games</th></tr></thead><tbody>
      ${rows.map(x => `
        <tr class="clickable" onclick="location.hash='season/${x.season}'">
          <td><strong>${x.season}</strong></td>
          <td><span class="owner-link">${esc(x.champ?.person_name || "—")}</span>${x.champ ? `<div class="team-name">${fmt(x.champ.score,0)} pts in final</div>` : ""}</td>
          <td>${esc(personName(x.oneSeed?.person_id))}<div class="team-name">${seedText(x.oneSeed)}</div></td>
          <td><b>${recordText(x.bestRecord)}</b><div class="team-name">${esc(personName(x.bestRecord?.person_id))}</div></td>
          <td>${esc(personName(x.topScorer?.person_id))}<div class="team-name">${fmt(x.topScorer?.points_for,0)} PF</div></td>
          <td>${x.games}</td>
        </tr>`).join("")}
    </tbody></table></div></section>
    <div class="grid-2" style="margin-top:18px">
      <section class="card"><div class="card-head"><div><h2>2026 Season</h2><div class="subtle">Current league state</div></div><span class="badge">IN PROGRESS</span></div><div class="card-body">
        <div class="champ-row"><div class="trophy">📈</div><div class="champ-name"><strong>Current leader</strong><div class="champ-years">${currentStandings[0] ? esc(personName(currentStandings[0].person_id)) + " · " + recordText(currentStandings[0]) : "—"}</div></div></div>
        <div class="champ-row"><div class="trophy">🔥</div><div class="champ-name"><strong>Current scoring leader</strong><div class="champ-years">${currentStandings.slice().sort((a,b)=>(b.points_for||0)-(a.points_for||0))[0] ? esc(personName(currentStandings.slice().sort((a,b)=>(b.points_for||0)-(a.points_for||0))[0].person_id)) : "—"}</div></div></div>
        <p class="subtle" style="margin:14px 0 0;line-height:1.6">The current season is intentionally kept out of historical championship and record totals until the season is complete.</p>
      </div></section>
      <section class="card"><div class="card-head"><div><h2>League Evolution</h2><div class="subtle">How the format has changed</div></div></div><div class="card-body">
        <div class="champ-row"><div class="trophy">👥</div><div class="champ-name"><strong>Team count</strong><div class="champ-years">The league grew from ${rows[rows.length-1].teams} teams in 2011 to ${latest.teams} in 2025.</div></div></div>
        <div class="champ-row"><div class="trophy">⚔</div><div class="champ-name"><strong>Most regular-season games</strong><div class="champ-years">${mostGames.season} · ${mostGames.games} completed regular-season matchups</div></div></div>
        <div class="champ-row"><div class="trophy">🏆</div><div class="champ-name"><strong>Championship history</strong><div class="champ-years">15 decided seasons · ${new Set(DATA.champions.map(x=>x.person_id)).size} different champions</div></div></div>
      </div></section>
    </div>
  `;
}
function renderSeason(season) {
  const standings = DATA.standings.filter(x => x.season === season).sort((a,b) => b.wins-a.wins || b.points_for-a.points_for);
  const teamRows = DATA.teams.filter(x => x.season === season);
  const champ = DATA.champions.find(x => x.season === season);
  const championship = DATA.championships.find(x => x.season === season);
  const playoff = DATA.matchups.filter(x => x.season===season && x.playoff_tier_type!=="NONE" && x.away_team_id!=null).sort((a,b)=>a.matchup_period_id-b.matchup_period_id || a.matchup_id-b.matchup_id);
  const oneSeed = teamRows.find(x => x.playoff_seed === 1);
  const topScorer = standings.slice().sort((a,b)=>(b.points_for||0)-(a.points_for||0))[0];
  const highestGame = DATA.matchups.filter(x=>x.season===season && x.away_team_id!=null && x.winner!=="UNDECIDED").reduce((best,m)=>{
    const hs=Number(m.home_score||0), as=Number(m.away_score||0);
    if(!best || hs>best.score) best={score:hs,person_id:m.home_person_id};
    if(as>best.score) best={score:as,person_id:m.away_person_id};
    return best;
  },null);

  const playoffRows = playoff.map(x => {
    const home = personName(x.home_person_id);
    const away = x.away_team_id == null ? "Bye" : personName(x.away_person_id);
    const decided = x.winner !== "UNDECIDED";
    const result = x.winner==="HOME" ? home : x.winner==="AWAY" ? away : x.winner==="TIE" ? "Tie" : "TBD";
    return `<div class="champ-row"><div class="trophy">${decided?'✓':'…'}</div><div class="champ-name"><strong>Week ${x.matchup_period_id}</strong><div class="champ-years">${esc(home)}${x.away_team_id!=null ? ` vs ${esc(away)}` : " · Bye"}</div></div><div>${decided ? `${esc(result)} · ${fmt(x.home_score,2)}–${fmt(x.away_score,2)}` : "TBD"}</div></div>`;
  }).join("");

  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">Season</div><h1>${season}</h1><p>${season === 2026 ? "Current season" : "Historical season"} · ${standings.length} teams</p></div><a class="badge" href="#seasons">← All seasons</a></div>
    ${champ ? `<section class="hero"><div class="hero-grid"><div><div class="hero-kicker">Champion</div><h1>${esc(champ.person_name)}</h1><p>Team ${champ.team_id} · Championship score ${fmt(champ.score,2)}</p></div><div class="hero-side"><div class="hero-big">🏆</div><div class="hero-label">${season} CHAMPION</div></div></div></section>` : `<section class="hero"><div class="hero-grid"><div><div class="hero-kicker">Season in progress</div><h1>2026</h1><p>The championship has not been decided yet. Current standings and completed games are shown below.</p></div><div class="hero-side"><div class="hero-big">2026</div><div class="hero-label">CURRENT SEASON</div></div></div></section>`}
    <div class="pulse-grid">
      <div class="pulse-card"><div class="pulse-kicker">#1 SEED</div><div class="pulse-value">${esc(personName(oneSeed?.person_id))}</div><div class="pulse-meta">${oneSeed ? esc(oneSeed.team_name) : "Seed not finalized"}</div></div>
      <div class="pulse-card"><div class="pulse-kicker">BEST RECORD</div><div class="pulse-value">${standings[0] ? standings[0].wins+"–"+standings[0].losses : "—"}</div><div class="pulse-meta">${standings[0] ? esc(personName(standings[0].person_id)) : "—"}</div></div>
      <div class="pulse-card"><div class="pulse-kicker">TOP SCORER</div><div class="pulse-value">${esc(personName(topScorer?.person_id))}</div><div class="pulse-meta">${topScorer ? fmt(topScorer.points_for,2)+" points" : "—"}</div></div>
      <div class="pulse-card"><div class="pulse-kicker">HIGH SCORE</div><div class="pulse-value">${fmt(highestGame?.score,2)}</div><div class="pulse-meta">${highestGame ? esc(personName(highestGame.person_id)) : "—"}</div></div>
    </div>
    <div class="grid-2" style="margin-top:18px">
      <section class="card"><div class="card-head"><div><h2>Regular Season</h2><div class="subtle">Official standings and points</div></div></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Owner</th><th>Seed</th><th>Final Finish</th><th>W-L-T</th><th>PF</th><th>PA</th></tr></thead><tbody>${standings.map((x,i)=>`<tr class="clickable" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'"><td>${i+1}</td><td><div class="owner-link">${esc(personName(x.person_id))}</div><div class="team-name">${esc(teamRows.find(t=>t.team_id===x.team_id)?.team_name||"")}</div></td><td>${teamRows.find(t=>t.team_id===x.team_id)?.playoff_seed ?? "—"}</td><td>${(() => { const f=playoffFinishForSeason(season)[x.team_id]; return f ? f+(f===1?'st':f===2?'nd':f===3?'rd':'th') : '—'; })()}</td><td class="record">${x.wins}-${x.losses}${x.ties?`-${x.ties}`:""}</td><td>${fmt(x.points_for,2)}</td><td>${fmt(x.points_against,2)}</td></tr>`).join("")}</tbody></table></div></section>
      <section class="card"><div class="card-head"><div><h2>Championship Path</h2><div class="subtle">${championship ? "Final bracket · official championship record" : "Completed playoff games"}</div></div></div><div class="card-body">${playoffRows || `<div class="empty">No playoff games have been played yet.</div>`}</div></section>
    </div>
  `;
}
function renderOwners() {
  const career = [...DATA.advanced_stats.career].sort((a,b)=>a.person_name.localeCompare(b.person_name));
  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">People</div><h1>Owners</h1><p>League résumés, championships, playoff history and draft positioning.</p></div></div>
    <div class="controls"><input id="ownerSearch" placeholder="Search owner…" /></div>
    <div class="owner-grid" id="ownerGrid"></div>
  `;
  const grid = $("#ownerGrid");
  function paint() {
    const q = $("#ownerSearch").value.toLowerCase().trim();
    const filtered = career.filter(x => x.person_name.toLowerCase().includes(q));
    grid.innerHTML = filtered.map(x=>{
      const c = DATA.champCounts[x.person_id]?.count || 0;
      const rec = DATA.owner_records.find(r=>r.person_id===x.person_id) || {};
      const teamRows = DATA.teams.filter(t=>t.person_id===x.person_id && t.season<=2025 && t.playoff_seed!=null);
      const oneSeeds = teamRows.filter(t=>t.playoff_seed===1).length;
      const draft = DATA.draft_analytics.career.find(d=>d.person_id===x.person_id) || {};
      return `<article class="owner-card" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'">
        <div class="owner-card-top">
          <div style="display:flex;gap:11px;align-items:center"><div class="avatar">${initials(x.person_name)}</div><div><h3>${esc(x.person_name)}</h3><div class="mini">${x.seasons} season${x.seasons===1?'':'s'}</div></div></div>
          <div>${c ? `<span class="badge">🏆 ${c}</span>` : ''}</div>
        </div>
        <div class="owner-metrics">
          <div class="owner-metric"><b>${pct(x.actual_win_pct)}</b><span>WIN %</span></div>
          <div class="owner-metric"><b>${rec.playoff_appearances||0}</b><span>PLAYOFFS</span></div>
          <div class="owner-metric"><b>${oneSeeds}</b><span>#1 SEEDS</span></div>
          <div class="owner-metric"><b>${draft.avg_first_round_pick!=null?fmt(draft.avg_first_round_pick,1):'—'}</b><span>AVG 1ST</span></div>
        </div>
      </article>`;
    }).join("") || '<div class="empty">No owners found.</div>';
  }
  $("#ownerSearch").addEventListener('input', paint); paint();
}

function renderCareer() {
  const career = [...DATA.advanced_stats.career].sort((a,b)=>a.person_name.localeCompare(b.person_name));
  const careerTableRows = career.map(x => {
    const seasons = DATA.teams.filter(t => t.person_id === x.person_id && t.season <= 2025 && t.rank != null);
    const rec = DATA.owner_records.find(r => r.person_id === x.person_id) || {};
    const games = x.regular_season_games || 0;
    const titles = DATA.champCounts[x.person_id]?.count || 0;
    const podium = DATA.podiumCounts?.[x.person_id] || {};
    const avgFinish = seasons.length ? seasons.reduce((sum, t) => sum + Number(t.rank), 0) / seasons.length : null;
    const playoffResults = seasons
      .map(t => playoffFinishForSeason(t.season)[t.team_id])
      .filter(v => Number.isFinite(Number(v)))
      .map(Number);
    const avgFinalFinish = playoffResults.length
      ? playoffResults.reduce((sum, v) => sum + v, 0) / playoffResults.length
      : null;
    const bestFinalFinish = playoffResults.length ? Math.min(...playoffResults) : null;
    const playoffApps = rec.playoff_appearances || 0;
    return {...x, games, avgFinish, avgFinalFinish, bestFinalFinish, wins:x.actual_wins||0, losses:x.actual_losses||0, ties:x.actual_ties||0, pointsFor:x.points_for||0, pointsAgainst:x.points_against||0, ppg:games?(x.points_for||0)/games:0, playoffApps, playoffRate:x.seasons?playoffApps/x.seasons:0, titles, runnerUps:podium.runner_ups||0};
  });

  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">League history</div><h1>Career</h1><p>The all-time owner leaderboard — longevity, regular-season performance, scoring and postseason success.</p></div></div>
    <section class="card"><div class="card-head"><div><h2>Career Leaderboard</h2><div class="subtle">Historical regular-season performance through 2025 · click any owner to open their résumé</div></div></div>
      <div class="controls"><input id="careerSearch" placeholder="Search owner…" /><select id="careerSort">
        <option value="seasons">Seasons</option><option value="wins">Total wins</option><option value="actual_win_pct">Win %</option><option value="avgFinish">Avg regular-season finish</option><option value="pointsFor">Points for</option><option value="titles">Championships</option>
      </select></div>
      <div class="table-wrap"><table><thead><tr><th>Owner</th><th>Seasons</th><th>Record</th><th>Win %</th><th>Avg Finish</th><th>Avg Final Finish</th><th>PF</th><th>PA</th><th>PPG</th><th>Playoffs</th><th>Titles</th><th>Runner Up</th></tr></thead><tbody id="careerRows"></tbody></table></div>
    </section>`;
  const careerRowsBody = $("#careerRows");
  function paintCareerTable() {
    const q=$("#careerSearch").value.toLowerCase().trim(), sort=$("#careerSort").value;
    const filtered=careerTableRows.filter(x=>x.person_name.toLowerCase().includes(q));
    filtered.sort((a,b)=>{
      if(sort==="avgFinish") return (a.avgFinish??999)-(b.avgFinish??999);
      if(sort==="actual_win_pct") return b.actual_win_pct-a.actual_win_pct;
      if(sort==="wins") return b.wins-a.wins || b.seasons-a.seasons;
      if(sort==="pointsFor") return b.pointsFor-a.pointsFor;
      if(sort==="titles") return b.titles-a.titles || b.runnerUps-a.runnerUps;
      return b.seasons-a.seasons || b.wins-a.wins;
    });
    careerRowsBody.innerHTML = filtered.map(x => `
      <tr class="clickable" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'">
        <td><strong>${esc(x.person_name)}</strong></td>
        <td>${x.seasons}</td>
        <td class="record">${x.wins}-${x.losses}${x.ties ? ' - '+x.ties : ''}</td>
        <td>${pct(x.actual_win_pct)}</td>
        <td>${x.avgFinish != null ? fmt(x.avgFinish,1) : '—'}</td>
        <td>${x.avgFinalFinish != null ? fmt(x.avgFinalFinish,1) : '—'}</td>
        <td>${fmt(x.pointsFor,1)}</td>
        <td>${fmt(x.pointsAgainst,1)}</td>
        <td>${fmt(x.ppg,1)}</td>
        <td>${x.playoffApps} (${pct(x.playoffRate)})</td>
        <td>${x.titles}</td>
        <td>${x.runnerUps}</td>
      </tr>`).join('') || '<tr><td colspan="12">No owners found.</td></tr>';
  }
  $("#careerSearch").addEventListener('input',paintCareerTable);
  $("#careerSort").addEventListener('change',paintCareerTable);
  paintCareerTable();
}

function renderOwner(id) {
  const x = DATA.advanced_stats.career.find(x=>x.person_id===id);
  if (!x) { $("#app").innerHTML='<div class="empty">Owner not found.</div>'; return; }

  const historicalSeasons = DATA.advanced_stats.season.filter(s=>s.person_id===id && s.season<=2025).sort((a,b)=>b.season-a.season);
  const teams = DATA.teams.filter(t=>t.person_id===id).sort((a,b)=>b.season-a.season);
  const historicalTeams = teams.filter(t=>t.season<=2025);
  const playoffFinishes = {};
  for (const season of [...new Set(historicalTeams.map(t=>t.season))]) {
    playoffFinishes[season] = playoffFinishForSeason(season);
  }
  const champs = DATA.champions.filter(c=>c.person_id===id);
  const podiums = (DATA.podiums || []).filter(p => p.champion_person_id===id || p.runner_up_person_id===id || p.third_place_person_id===id).sort((a,b)=>b.season-a.season);
  const podiumCounts = DATA.podiumCounts?.[id] || { championships: 0, runner_ups: 0, third_place_finishes: 0 };
  const ownerRecord = DATA.owner_records.find(r=>r.person_id===id) || {};
  const championshipAppearances = DATA.championships?.filter(c=>c.runner_up_person_id===id).length || 0;
  const draft = DATA.draft_analytics.career.find(d=>d.person_id===id) || {};
  const draftRounds = DATA.draft_picks.filter(d=>d.person_id===id && d.season<=2025 && d.round===1).map(d=>d.overall_pick);

  const wins=historicalSeasons.reduce((n,s)=>n+(s.actual_wins||0),0);
  const losses=historicalSeasons.reduce((n,s)=>n+(s.actual_losses||0),0);
  const ties=historicalSeasons.reduce((n,s)=>n+(s.actual_ties||0),0);
  const points=historicalSeasons.reduce((n,s)=>n+(s.points_for||0),0);
  const games=wins+losses+ties;
  const winPct=games?(wins+ties*.5)/games:null;
  const avgPF=historicalSeasons.length?points/historicalSeasons.length:null;

  const seedRows=historicalTeams.filter(t=>t.playoff_seed!=null);
  const oneSeeds=seedRows.filter(t=>t.playoff_seed===1).length;
  const top3Seeds=seedRows.filter(t=>t.playoff_seed<=3).length;
  const avgSeed=seedRows.length?seedRows.reduce((n,t)=>n+t.playoff_seed,0)/seedRows.length:null;
  const bestSeed=seedRows.length?Math.min(...seedRows.map(t=>t.playoff_seed)):null;
  const playoffApps=ownerRecord.playoff_appearances||0;
  const playoffRate=historicalSeasons.length?playoffApps/historicalSeasons.length:null;
  const champRate=historicalSeasons.length?champs.length/historicalSeasons.length:null;
  const playoffConversion=playoffApps?champs.length/playoffApps:null;
  const oneSeedRate=historicalSeasons.length?oneSeeds/historicalSeasons.length:null;

  const h2h = {};
  DATA.matchups.filter(m=>m.home_person_id===id || m.away_person_id===id).forEach(m=>{
    const opponent = m.home_person_id===id ? m.away_person_id : m.home_person_id;
    if (!opponent) return;
    h2h[opponent] ??= {games:0,wins:0,losses:0,ties:0};
    if(m.winner==='UNDECIDED' || m.away_team_id==null) return;
    const h=h2h[opponent]; h.games++;
    if((m.winner==='HOME' && m.home_person_id===id)||(m.winner==='AWAY'&&m.away_person_id===id)) h.wins++;
    else if(m.winner==='TIE') h.ties++;
    else h.losses++;
  });
  const rivals=Object.entries(h2h).filter(([k,v])=>v.games>0).sort((a,b)=>b[1].games-a[1].games).slice(0,8);
  const allTimeVs = {};
  DATA.matchups.filter(m => m.winner !== 'UNDECIDED' && m.away_team_id != null && m.home_person_id && m.away_person_id &&
    (m.home_person_id === id || m.away_person_id === id) &&
    Number.isFinite(Number(m.home_score)) && Number.isFinite(Number(m.away_score))
  ).forEach(m => {
    const isHome = m.home_person_id === id;
    const opponent = isHome ? m.away_person_id : m.home_person_id;
    if (!opponent || opponent === id) return;
    allTimeVs[opponent] ??= {games:0,wins:0,losses:0,ties:0,pf:0,pa:0};
    const v = allTimeVs[opponent];
    const ownScore = Number(isHome ? m.home_score : m.away_score);
    const oppScore = Number(isHome ? m.away_score : m.home_score);
    v.games++; v.pf += ownScore; v.pa += oppScore;
    if (m.winner === 'TIE') v.ties++;
    else if ((m.winner === 'HOME' && isHome) || (m.winner === 'AWAY' && !isHome)) v.wins++;
    else v.losses++;
  });
  const allTimeVsRows = Object.entries(allTimeVs)
    .filter(([pid,v]) => v.games > 0 && DATA.owners?.some(o => o.person_id === pid))
    .sort((a,b) => b[1].games-a[1].games || personName(a[0]).localeCompare(personName(b[0])))
    .map(([pid,v]) => '<tr><td><a class="owner-link" href="#owner/'+encodeURIComponent(pid)+'">'+esc(personName(pid))+'</a></td><td>'+v.games+'</td><td>'+v.wins+'-'+v.losses+(v.ties?' - '+v.ties:'')+'</td><td>'+pct(v.wins/v.games)+'</td><td>'+fmt(v.pf,1)+'</td><td>'+fmt(v.pa,1)+'</td><td>'+fmt(v.pf/v.games,1)+'</td><td>'+fmt(v.pa/v.games,1)+'</td></tr>').join('');

  const current = DATA.advanced_stats.season.find(s=>s.person_id===id && s.season===2026);
  const draftAvg=draft.avg_first_round_pick;
  const draftTop3=draft.first_round_top3||0;
  const draftTop5=draft.first_round_top5||0;
  const draftFirstOverall=draft.first_overall_picks||0;

  $("#app").innerHTML=
    '<div class="profile-hero"><div class="profile-avatar">'+initials(x.person_name)+'</div><div><div class="eyebrow">Owner résumé</div><h1>'+esc(x.person_name)+'</h1><div class="badges">'+champs.map(c=>'<span class="badge">🏆 '+c.season+'</span>').join('')+(!champs.length?'<span class="badge">No championships yet</span>':'')+'</div></div></div>'+
    '<div class="pulse-grid">'+
      '<div class="pulse-card"><div class="pulse-kicker">CHAMPIONSHIPS</div><div class="pulse-value">'+champs.length+'</div><div class="pulse-meta">'+pct(champRate)+' of historical seasons</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">RUNNER-UP FINISHES</div><div class="pulse-value">'+podiumCounts.runner_ups+'</div><div class="pulse-meta">Championship-game appearances</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">3RD-PLACE FINISHES</div><div class="pulse-value">'+podiumCounts.third_place_finishes+'</div><div class="pulse-meta">Official 3rd-place games</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">#1 SEEDS - REGULAR SEASON</div><div class="pulse-value">'+oneSeeds+'</div><div class="pulse-meta">'+pct(oneSeedRate)+' of historical seasons</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">PLAYOFF APPEARANCES</div><div class="pulse-value">'+playoffApps+'</div><div class="pulse-meta">'+pct(playoffRate)+' playoff rate</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">AVG DRAFT POSITION</div><div class="pulse-value">'+(draftAvg!=null?fmt(draftAvg,1):'—')+'</div><div class="pulse-meta">'+draftTop3+' top-3 · '+draftTop5+' top-5 · '+draftFirstOverall+' #1 overall</div></div>'+
    '</div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><div><h2>Career Résumé</h2><div class="subtle">Historical seasons through 2025</div></div></div><div class="stats-grid" style="margin:0">'+
        '<div class="stat-card"><div class="stat-label">RECORD</div><div class="stat-value">'+wins+'-'+losses+(ties?' - '+ties:'')+'</div><div class="stat-meta">'+pct(winPct)+' win rate</div></div>'+
        '<div class="stat-card"><div class="stat-label">AVG REGULAR-SEASON SEED</div><div class="stat-value">'+(avgSeed!=null?fmt(avgSeed,1):'—')+'</div><div class="stat-meta">best seed '+(bestSeed??'—')+'</div></div>'+
        '<div class="stat-card"><div class="stat-label">TOP 3 PLAYOFF FINISH</div><div class="stat-value">'+top3Seeds+'</div><div class="stat-meta">'+pct(historicalSeasons.length?top3Seeds/historicalSeasons.length:null)+' rate</div></div>'+
        '<div class="stat-card"><div class="stat-label">CHAMP. CONVERSION</div><div class="stat-value">'+pct(playoffConversion)+'</div><div class="stat-meta">titles per playoff appearance</div></div>'+
      '</div></section>'+
      '<section class="card"><div class="card-head"><div><h2>Draft Profile</h2><div class="subtle">Historical first-round positioning</div></div></div><div class="rank-list">'+
        '<div class="rank-row"><div class="rank-main"><strong>Average Draft Position</strong><small>Lower is earlier</small></div><b>'+(draftAvg!=null?fmt(draftAvg,1):'—')+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-3 picks</strong><small>Premium draft slots</small></div><b>'+draftTop3+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-5 picks</strong><small>Premium draft slots</small></div><b>'+draftTop5+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>#1 overall picks</strong><small>Times drafting first</small></div><b>'+draftFirstOverall+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Best 1st-round pick</strong><small>Career best</small></div><b>'+(draft.best_first_round_pick??'—')+'</b></div>'+
      '</div></section>'+
    '</div>'+
    '<div class="grid-2" style="margin-top:18px">'+
      '<section class="card"><div class="card-head"><div><h2>Team History</h2><div class="subtle">Historical seasons through 2025</div></div></div><div class="table-wrap"><table><thead><tr><th>Year</th><th>Team</th><th>Record</th><th>Regular Season</th><th>Final Standings</th><th>Draft Position</th><th>PF</th><th>PA</th><th>PPG</th><th>PA/G</th><th>Luck</th></tr></thead><tbody>'+
        historicalSeasons.map(s=>{const t=historicalTeams.find(t=>t.season===s.season);return '<tr><td><a class="owner-link" href="#season/'+s.season+'">'+s.season+'</a></td><td><strong>'+esc(t?.team_name||'—')+'</strong><div class="team-name">'+esc(t?.abbrev||'')+'</div></td><td>'+s.actual_wins+'-'+s.actual_losses+(s.actual_ties?'-'+s.actual_ties:'')+'</td><td>'+(t?.playoff_seed != null ? t.playoff_seed+(t.playoff_seed===1?'st':t.playoff_seed===2?'nd':t.playoff_seed===3?'rd':'th') : '—')+'</td><td>'+(playoffFinishes[s.season]?.[t?.team_id] ? playoffFinishes[s.season][t.team_id]+(playoffFinishes[s.season][t.team_id]===1?'st':playoffFinishes[s.season][t.team_id]===2?'nd':playoffFinishes[s.season][t.team_id]===3?'rd':'th') : '—')+'</td><td>'+(()=>{const picks=DATA.draft_picks.filter(d=>d.season===s.season&&d.team_id===t?.team_id&&d.overall_pick!=null).map(d=>Number(d.overall_pick));const p=picks.length?Math.min(...picks):null;return p!=null?p+(p===1?'st':p===2?'nd':p===3?'rd':'th'):'—';})()+'</td><td>'+fmt(s.points_for,1)+'</td><td>'+fmt(s.points_against,1)+'</td><td>'+fmt(s.points_per_game,1)+'</td><td>'+fmt((s.actual_wins+s.actual_losses+(s.actual_ties||0))?s.points_against/(s.actual_wins+s.actual_losses+(s.actual_ties||0)):null,1)+'</td><td class="'+(s.schedule_luck>=0?'positive':'negative')+'">'+(s.schedule_luck>=0?'+':'')+fmt(s.schedule_luck,1)+'</td></tr>';}).join('')+
      '</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><h2>Postseason Résumé</h2></div><div class="rank-list">'+
        '<div class="rank-row"><div class="rank-main"><strong>Championships</strong><small>'+champs.map(c=>c.season).join(' · ')+'</small></div><b>'+champs.length+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Runner Up</strong><small>'+podiums.filter(p=>p.runner_up_person_id===id).map(p=>p.season).join(' · ')+'</small></div><b>'+podiumCounts.runner_ups+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>3rd Place</strong><small>'+podiums.filter(p=>p.third_place_person_id===id).map(p=>p.season).join(' · ')+'</small></div><b>'+podiumCounts.third_place_finishes+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top 3 Playoff Finish</strong><small>'+podiums.map(p=>p.season).join(' · ')+'</small></div><b>'+podiums.length+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Championship appearances</strong><small>Won or runner-up</small></div><b>'+ (champs.length+championshipAppearances) +'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>#1 Seeds - Regular Season</strong><small>Regular-season seed</small></div><b>'+oneSeeds+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-3 seeds</strong><small>Regular-season seed</small></div><b>'+top3Seeds+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Playoff appearances</strong><small>Historical seasons</small></div><b>'+playoffApps+'</b></div>'+
      '</div></section>'+
    '</div>'+
    '<section class="card" style="margin-top:18px"><div class="card-head"><div><h2>All-Time vs. Managers</h2><div class="subtle">All completed regular-season, playoff and consolation matchups</div></div></div><div class="table-wrap"><table><thead><tr><th>Manager</th><th>Games</th><th>Record</th><th>Win %</th><th>PF</th><th>PA</th><th>PF/G</th><th>PA/G</th></tr></thead><tbody>'+ (allTimeVsRows || '<tr><td colspan="8">No completed head-to-head matchups.</td></tr>') +'</tbody></table></div></section>'+
    '<div class="grid-2" style="margin-top:18px">'+
      '<section class="card"><div class="card-head"><h2>Most Played Opponents</h2></div><div class="card-body">'+rivals.map(([pid,v])=>'<div class="champ-row"><div class="avatar" style="width:32px;height:32px;border-radius:9px;font-size:10px">'+initials(personName(pid))+'</div><div class="champ-name"><a class="owner-link" href="#owner/'+encodeURIComponent(pid)+'">'+esc(personName(pid))+'</a><div class="champ-years">'+v.games+' games · '+v.wins+'-'+v.losses+(v.ties?' - '+v.ties:'')+'</div></div><div class="record">'+(v.games?pct(v.wins/v.games):'—')+'</div></div>').join('') || '<div class="empty">No H2H data.</div>'+'</div></section>'+
    '</div>'+
    (current ? '<section class="card" style="margin-top:18px"><div class="card-head"><div><h2>2026 Season</h2><div class="subtle">Current season — not included in the historical résumé above</div></div></div><div class="stats-grid" style="margin:0"><div class="stat-card"><div class="stat-label">RECORD</div><div class="stat-value">'+current.actual_wins+'-'+current.actual_losses+(current.actual_ties?'-'+current.actual_ties:'')+'</div></div><div class="stat-card"><div class="stat-label">POINTS</div><div class="stat-value">'+fmt(current.points_for,1)+'</div></div><div class="stat-card"><div class="stat-label">PPG</div><div class="stat-value">'+fmt(current.points_per_game,1)+'</div></div></div></section>' : '');
}


function renderAnalytics() {
  const historical = DATA.advanced_stats.season.filter(x => Number(x.season) <= 2025);
  const career = DATA.advanced_stats.career.filter(x => x.seasons >= 3);
  const current = DATA.advanced_stats.season.filter(x => Number(x.season) === 2026);

  const bestActual = [...career].sort((a,b)=>b.actual_win_pct-a.actual_win_pct)[0];
  const bestAllPlay = [...career].sort((a,b)=>b.all_play_win_pct-a.all_play_win_pct)[0];
  const luckiest = [...career].sort((a,b)=>b.schedule_luck-a.schedule_luck)[0];
  const unluckiest = [...career].sort((a,b)=>a.schedule_luck-b.schedule_luck)[0];
  const bestPPG = [...career].sort((a,b)=>b.points_per_game-a.points_per_game)[0];
  const toughest = [...career].sort((a,b)=>b.opponent_points_per_game-a.opponent_points_per_game)[0];

  const seasonRows = [...historical].sort((a,b)=>b.schedule_luck-a.schedule_luck);
  const recent = [...historical].sort((a,b)=>b.season-a.season).slice(0,5);
  const currentRows = [...current].sort((a,b)=>b.actual_win_pct-a.actual_win_pct || b.points_for-a.points_for);

  const card = (label, value, name, meta) =>
    '<div class="pulse-card"><div class="pulse-kicker">'+esc(label)+'</div><div class="pulse-value">'+esc(String(value))+'</div><div class="pulse-meta">'+esc(name)+' · '+esc(meta)+'</div></div>';

  const luckRows = seasonRows.slice(0,8).map(x =>
    '<tr class="clickable" onclick="location.hash=\'owner/'+encodeURIComponent(x.person_id)+'\\"><td>'+x.season+'</td><td>'+esc(x.person_name)+'</td><td class="positive">+'+fmt(x.schedule_luck,1)+'</td><td>'+fmt(x.actual_wins + 0.5*x.actual_ties,1)+'</td><td>'+fmt(x.expected_wins,1)+'</td></tr>'
  ).join("");

  const toughRows = [...historical].sort((a,b)=>b.opponent_points_per_game-a.opponent_points_per_game).slice(0,8).map(x =>
    '<tr class="clickable" onclick="location.hash=\'owner/'+encodeURIComponent(x.person_id)+'\\"><td>'+x.season+'</td><td>'+esc(x.person_name)+'</td><td>'+fmt(x.opponent_points_per_game,1)+'</td><td>'+pct(x.actual_win_pct)+'%</td><td>'+pct(x.all_play_win_pct)+'%</td></tr>'
  ).join("");

  const consistency = [...career].sort((a,b)=>a.score_std_dev-b.score_std_dev).slice(0,8);
  const median = [...career].sort((a,b)=>b.median_score-a.median_score).slice(0,8);
  const currentHtml = currentRows.map(x =>
    '<tr><td>'+esc(x.person_name)+'</td><td>'+x.actual_wins+'-'+x.actual_losses+(x.actual_ties?' '+x.actual_ties+'T':'')+'</td><td>'+pct(x.actual_win_pct)+'</td><td>'+pct(x.all_play_win_pct)+'%</td><td>'+fmt(x.schedule_luck,1)+'</td></tr>'
  ).join("");

  $("#app").innerHTML =
    '<div class="page-head"><div><div class="eyebrow">Advanced Analytics</div><h1>Beyond the Standings</h1><p>Regular-season performance measured against the league, the schedule and the scoring environment.</p></div></div>'+
    '<div class="pulse-grid">'+
      card("BEST CAREER WIN %",pct(bestActual?.actual_win_pct),bestActual?.person_name||"—","minimum 3 seasons")+
      card("BEST ALL-PLAY %",pct(bestAllPlay?.all_play_win_pct),bestAllPlay?.person_name||"—","beats the field, not just the opponent")+
      card("LUCKIEST SCHEDULE",fmt(luckiest?.schedule_luck,1),luckiest?.person_name||"—","career wins above expected")+
      card("UNLUCKIEST SCHEDULE",fmt(unluckiest?.schedule_luck,1),unluckiest?.person_name||"—","career wins below expected")+
    '</div>'+
    '<section class="hero" style="margin-top:18px"><div class="hero-grid"><div><div class="hero-kicker">The useful stuff</div><h1>Were you actually good?</h1><p>All-play win percentage asks how often your weekly score would have beaten every other team in the league that week. Schedule luck compares your actual record to that performance baseline.</p></div><div class="hero-side"><div class="hero-big">Σ</div><div class="hero-label">2011–2025 HISTORICAL</div></div></div></section>'+
    '<div class="grid-2" style="margin-top:18px">'+
      '<section class="card"><div class="card-head"><div><h2>Schedule Luck</h2><div class="subtle">Actual W-L equivalent minus expected wins</div></div></div><div class="table-wrap"><table><thead><tr><th>Season</th><th>Owner</th><th>Luck</th><th>Actual</th><th>Expected</th></tr></thead><tbody>'+luckRows+'</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><div><h2>Toughest Schedules</h2><div class="subtle">Opponent scoring average</div></div></div><div class="table-wrap"><table><thead><tr><th>Season</th><th>Owner</th><th>Opp PPG</th><th>Win %</th><th>All-Play</th></tr></thead><tbody>'+toughRows+'</tbody></table></div></section>'+
    '</div>'+
    '<div class="section-title"><h2>Career Profiles</h2><span class="mini">Minimum 3 completed seasons</span></div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><h2>Scoring & Consistency</h2></div><div class="card-body"><div class="champ-row"><div class="trophy">🔥</div><div class="champ-name"><strong>Highest career PPG</strong><div class="champ-years">'+esc(bestPPG?.person_name||"—")+' · '+fmt(bestPPG?.points_per_game,1)+'</div></div></div><div class="champ-row"><div class="trophy">🎯</div><div class="champ-name"><strong>Highest career median</strong><div class="champ-years">'+esc(median[0]?.person_name||"—")+' · '+fmt(median[0]?.median_score,1)+'</div></div></div><div class="champ-row"><div class="trophy">🧊</div><div class="champ-name"><strong>Most consistent scoring</strong><div class="champ-years">'+esc(consistency[0]?.person_name||"—")+' · σ '+fmt(consistency[0]?.score_std_dev,1)+'</div></div></div><div class="champ-row"><div class="trophy">💪</div><div class="champ-name"><strong>Toughest career schedule</strong><div class="champ-years">'+esc(toughest?.person_name||"—")+' · '+fmt(toughest?.opponent_points_per_game,1)+' Opp PPG</div></div></div></div></section>'+
      '<section class="card"><div class="card-head"><h2>Recent Historical Seasons</h2><div class="subtle">2021–2025</div></div><div class="table-wrap"><table><thead><tr><th>Year</th><th>Owner</th><th>PPG</th><th>All-Play</th><th>Median+</th></tr></thead><tbody>'+recent.map(x=>'<tr><td>'+x.season+'</td><td>'+esc(x.person_name)+'</td><td>'+fmt(x.points_per_game,1)+'</td><td>'+pct(x.all_play_win_pct)+'</td><td>'+pct(x.median_plus_win_pct)+'</td></tr>').join("")+'</tbody></table></div></section>'+
    '</div>'+
    '<div class="section-title"><h2>2026 Live Analytics</h2><span class="mini">Current season · not included in historical leaderboards</span></div>'+
    '<section class="card"><div class="table-wrap"><table><thead><tr><th>Owner</th><th>Record</th><th>Win %</th><th>All-Play</th><th>Schedule Luck</th></tr></thead><tbody>'+currentHtml+'</tbody></table></div></section>'+
    '<div class="card" style="margin-top:18px"><div class="card-head"><h2>How to Read This</h2></div><div class="card-body"><p class="subtle" style="line-height:1.7"><strong>All-Play %</strong> measures your weekly score against every other team that week. <strong>Expected Wins</strong> is the sum of those weekly all-play percentages. <strong>Schedule Luck</strong> is your actual W-L equivalent minus expected wins: positive means the schedule helped; negative means it hurt. <strong>Opponent PPG</strong> measures the scoring strength of the teams you actually faced.</p></div></div>';
}

function renderRecords() {
  const historicalSeasons = DATA.advanced_stats.season.filter(x => Number(x.season) <= 2025);
  const historicalCareer = DATA.advanced_stats.career.map(x => ({...x}));

  const champCounts = {};
  for (const c of DATA.champions || []) champCounts[c.person_id] = (champCounts[c.person_id] || 0) + 1;

  const titleRunnerUps = {};
  for (const c of DATA.championships || []) {
    if (c.runner_up_person_id != null) titleRunnerUps[c.runner_up_person_id] = (titleRunnerUps[c.runner_up_person_id] || 0) + 1;
  }

  const teamRows = DATA.teams.filter(t => Number(t.season) <= 2025 && t.playoff_seed != null);
  const byOwner = {};
  for (const t of teamRows) (byOwner[t.person_id] ??= []).push(t);

  function streakFor(id, predicate) {
    const rows = (byOwner[id] || []).slice().sort((a,b)=>a.season-b.season);
    let best = 0, run = 0, prev = null;
    for (const r of rows) {
      const consecutive = prev != null && Number(r.season) === Number(prev) + 1;
      run = consecutive && predicate(r) ? run + 1 : (predicate(r) ? 1 : 0);
      best = Math.max(best, run);
      prev = Number(r.season);
    }
    return best;
  }

  const careerRows = historicalCareer.map(x => {
    const rows = byOwner[x.person_id] || [];
    const playoffs = rows.filter(r => r.playoff_seed <= 6).length;
    const top3 = rows.filter(r => r.playoff_seed <= 3).length;
    const oneSeeds = rows.filter(r => r.playoff_seed === 1).length;
    const titles = champCounts[x.person_id] || 0;
    const titleGames = titles + (titleRunnerUps[x.person_id] || 0);
    return {
      ...x,
      championships: titles,
      runner_ups: (DATA.podiumCounts?.[x.person_id]?.runner_ups || 0),
      third_place_finishes: (DATA.podiumCounts?.[x.person_id]?.third_place_finishes || 0),
      podium_finishes: titles + (DATA.podiumCounts?.[x.person_id]?.runner_ups || 0) + (DATA.podiumCounts?.[x.person_id]?.third_place_finishes || 0),
      playoff_appearances: playoffs,
      top3_seeds: top3,
      one_seeds: oneSeeds,
      avg_seed: rows.length ? rows.reduce((s,r)=>s+r.playoff_seed,0) / rows.length : null,
      playoff_rate: rows.length ? playoffs / rows.length : 0,
      one_seed_rate: rows.length ? oneSeeds / rows.length : 0,
      playoff_streak: streakFor(x.person_id, r => r.playoff_seed <= 6),
      one_seed_streak: streakFor(x.person_id, r => r.playoff_seed === 1),
      title_appearances: titleGames,
      title_conversion: titleGames ? titles / titleGames : 0
    };
  });

  const qualified = careerRows.filter(x => x.seasons >= 5);
  const qualifiedTitles = careerRows.filter(x => x.title_appearances >= 3);

  const best = (rows, key, reverse=false) => [...rows].sort((a,b) => {
    const av = a[key] ?? (reverse ? -Infinity : Infinity);
    const bv = b[key] ?? (reverse ? -Infinity : Infinity);
    return reverse ? bv-av : av-bv;
  })[0];

  const mostRunnerUps = best(careerRows, "runner_ups", true);
  const mostThirds = best(careerRows, "third_place_finishes", true);
  const mostPodiums = best(careerRows, "podium_finishes", true);

  const mostTitles = best(careerRows, "championships", true);
  const mostPlayoffs = best(careerRows, "playoff_appearances", true);
  const mostOneSeeds = best(careerRows, "one_seeds", true);
  const mostTop3 = best(careerRows, "top3_seeds", true);
  const mostWins = best(careerRows, "actual_wins", true);
  const bestWinPct = best(qualified, "actual_win_pct", true);
  const bestPlayoffRate = best(qualified, "playoff_rate", true);
  const bestOneSeedRate = best(qualified, "one_seed_rate", true);
  const bestAvgSeed = best(qualified, "avg_seed", false);
  const bestConversion = best(qualifiedTitles, "title_conversion", true);
  const longestPlayoff = best(careerRows, "playoff_streak", true);
  const longestOneSeed = best(careerRows, "one_seed_streak", true);

  let biggestWin = null, highestScore = null;
  for (const m of DATA.matchups) {
    if (Number(m.season) > 2025 || m.winner === "UNDECIDED" || m.away_team_id == null) continue;
    const margin = Math.abs((m.home_score || 0) - (m.away_score || 0));
    if (!biggestWin || margin > biggestWin.margin) biggestWin = {...m, margin};
    for (const side of ["home","away"]) {
      const score = side === "home" ? m.home_score : m.away_score;
      if (score != null && (!highestScore || score > highestScore.score)) highestScore = {...m, side, score};
    }
  }

  const bestSeason = [...historicalSeasons].sort((a,b)=>b.points_for-a.points_for)[0];
  const bestPPG = [...historicalSeasons].sort((a,b)=>b.points_per_game-a.points_per_game)[0];
  const bestAllPlay = [...historicalCareer].filter(x=>x.seasons>=3).sort((a,b)=>b.all_play_win_pct-a.all_play_win_pct)[0];
  const luck = [...historicalSeasons].sort((a,b)=>b.schedule_luck-a.schedule_luck)[0];
  const worstLuck = [...historicalSeasons].sort((a,b)=>a.schedule_luck-b.schedule_luck)[0];

  const careerCards = [
    ["Most championships", mostTitles.championships, mostTitles.person_name, "Career titles"],
    ["Most runner-up finishes", mostRunnerUps.runner_ups, mostRunnerUps.person_name, "Championship-game losses"],
    ["Most 3rd-place finishes", mostThirds.third_place_finishes, mostThirds.person_name, "Official 3rd-place games"],
    ["Most top-3 finishes", mostPodiums.podium_finishes, mostPodiums.person_name, "Championship + runner-up + 3rd"],
    ["Most playoff appearances", mostPlayoffs.playoff_appearances, mostPlayoffs.person_name, mostPlayoffs.seasons + " seasons"],
    ["Most #1 seeds", mostOneSeeds.one_seeds, mostOneSeeds.person_name, "Regular-season #1 seeds"],
    ["Most top-3 seeds", mostTop3.top3_seeds, mostTop3.person_name, "Regular-season top-3 finishes"],
    ["Most career wins", mostWins.wins, mostWins.person_name, mostWins.seasons + " seasons"],
    ["Best career win %", pct(bestWinPct.actual_win_pct), bestWinPct.person_name, "Minimum 5 seasons"],
    ["Best playoff rate", pct(bestPlayoffRate.playoff_rate), bestPlayoffRate.person_name, "Minimum 5 seasons"],
    ["Best #1 seed rate", pct(bestOneSeedRate.one_seed_rate), bestOneSeedRate.person_name, "Minimum 5 seasons"],
    ["Best average seed", fmt(bestAvgSeed.avg_seed,2), bestAvgSeed.person_name, "Lower is better · minimum 5 seasons"],
    ["Best title conversion", pct(bestConversion.title_conversion), bestConversion.person_name, bestConversion.title_appearances + " title-game appearances"],
    ["Longest playoff streak", longestPlayoff.playoff_streak, longestPlayoff.person_name, "Consecutive seasons"],
    ["Longest #1 seed streak", longestOneSeed.one_seed_streak, longestOneSeed.person_name, "Consecutive seasons"]
  ];

  const seasonCards = [
    ["Most points in a season", fmt(bestSeason.points_for,2), bestSeason.person_name, bestSeason.season + " · " + fmt(bestSeason.points_per_game,2) + " PPG"],
    ["Best season PPG", fmt(bestPPG.points_per_game,2), bestPPG.person_name, bestPPG.season + " · " + fmt(bestPPG.points_for,2) + " PF"],
    ["Best career all-play %", pct(bestAllPlay.all_play_win_pct), bestAllPlay.person_name, bestAllPlay.seasons + " seasons"],
    ["Best schedule luck", "+" + fmt(luck.schedule_luck,2), luck.person_name, String(luck.season)],
    ["Worst schedule luck", fmt(worstLuck.schedule_luck,2), worstLuck.person_name, String(worstLuck.season)],
    ["Biggest winning margin", fmt(biggestWin.margin,2), "Single matchup", biggestWin.season + " · " + personName(biggestWin.home_person_id) + " " + fmt(biggestWin.home_score,2) + "–" + fmt(biggestWin.away_score,2) + " " + personName(biggestWin.away_person_id)],
    ["Highest single-game score", fmt(highestScore.score,2), personName(highestScore.side==="home"?highestScore.home_person_id:highestScore.away_person_id), String(highestScore.season)]
  ];

  const podiumRows = (DATA.podiums || []).slice().sort((a,b)=>b.season-a.season).map(p =>
    '<tr><td><a class="owner-link" href="#season/'+p.season+'">'+p.season+'</a></td><td>🏆 '+esc(personName(p.champion_person_id))+'</td><td>🥈 '+esc(personName(p.runner_up_person_id))+'</td><td>🥉 '+esc(personName(p.third_place_person_id))+'</td></tr>'
  ).join("");

  const card = r => "<div class=\"owner-card\"><div class=\"mini\">" + esc(r[0]) + "</div><div class=\"stat-value\" style=\"margin-top:8px\">" + esc(String(r[1])) + "</div><div style=\"font-weight:800;margin-top:8px\">" + esc(r[2]) + "</div><div class=\"mini\" style=\"margin-top:3px\">" + esc(r[3]) + "</div></div>";

  $("#app").innerHTML =
    "<div class=\"page-head\"><div><div class=\"eyebrow\">League history</div><h1>Records</h1><p>The numbers that will start arguments in the group chat.</p></div></div>" +
    "<div class=\"section-title\"><h2>Career Résumé Records</h2><span class=\"mini\">2011–2025 · 5-season minimum where noted</span></div>" +
    "<div class=\"owner-grid\">" + careerCards.map(card).join("") + "</div>" +
    "<div class=\"section-title\" style=\"margin-top:26px\"><h2>Season &amp; Game Records</h2><span class=\"mini\">Historical seasons only · 2026 excluded</span></div>" +
    "<div class=\"owner-grid\">" + seasonCards.map(card).join("") + "</div>" +
    "<div class=\"section-title\" style=\"margin-top:26px\"><h2>Playoff Podium History</h2><span class=\"mini\">2011–2025 · official championship, runner-up and 3rd-place finishes</span></div>" +
    "<section class=\"card\"><div class=\"table-wrap\"><table><thead><tr><th>Season</th><th>Champion</th><th>Runner-Up</th><th>3rd Place</th></tr></thead><tbody>" + podiumRows + "</tbody></table></div></section>";
}

function renderDraft() {
  const a=DATA.draft_analytics;
  const career=(a.career||[]).slice().sort((x,y)=>(x.avg_first_round_pick??999)-(y.avg_first_round_pick??999));
  const qualified=career.filter(x=>(x.first_round_picks||0)>=5);
  const topAvg=qualified[0];
  const top1=(a.records?.most_first_overall_picks||[])[0];
  const top3=(a.records?.most_first_round_top3||[])[0];
  const recent=DATA.draft_picks.filter(x=>x.season===2026).sort((x,y)=>x.overall_pick-y.overall_pick).slice(0,24);

  const positionRows=qualified.map(r=>'<tr class="clickable" onclick="location.hash=\'owner/'+encodeURIComponent(r.person_id)+'\'"><td class="owner-link">'+esc(r.person_name)+'</td><td>'+r.first_round_picks+'</td><td><strong>'+fmt(r.avg_first_round_pick,1)+'</strong></td><td>'+r.first_round_top3+'</td><td>'+r.first_round_top5+'</td><td>'+r.first_overall_picks+'</td><td>'+r.best_first_round_pick+'</td></tr>').join('');
  const leaders=qualified.slice().sort((x,y)=>y.first_round_top5-x.first_round_top5 || y.first_round_top3-x.first_round_top3).slice(0,8);
  const leaderRows=leaders.map((r,i)=>'<div class="rank-row"><span class="rank-num">'+String(i+1).padStart(2,"0")+'</span><div class="rank-main"><strong>'+esc(r.person_name)+'</strong><small>'+r.first_round_top5+' top-5 picks · '+r.first_round_top3+' top-3 · '+r.first_overall_picks+' #1</small></div><b>'+fmt(r.avg_first_round_pick,1)+'</b></div>').join('');
  const slotRows=qualified.map(r=>'<tr><td class="owner-link">'+esc(r.person_name)+'</td><td>'+r.first_round_picks+'</td><td>'+fmt(r.avg_first_round_pick,1)+'</td><td>'+fmt(r.first_round_pick_std_dev,1)+'</td><td>'+r.best_first_round_pick+'</td><td>'+r.worst_first_round_pick+'</td></tr>').join('');
  const recentRows=recent.map(d=>'<tr><td><strong>'+d.overall_pick+'</strong></td><td class="owner-link">'+esc(personName(d.person_id))+'</td><td>'+d.round+'</td></tr>').join('');

  $("#app").innerHTML='<div class="page-head"><div><div class="eyebrow">Draft room</div><h1>Draft History</h1><p>Who actually got the premium draft slots — and how often?</p></div></div>'+
    '<div class="pulse-grid">'+
      '<div class="pulse-card"><div class="pulse-kicker">BEST AVG 1ST-ROUND SLOT</div><div class="pulse-value">'+esc(topAvg?.person_name||"—")+'</div><div class="pulse-meta">'+(topAvg ? "Pick "+fmt(topAvg.avg_first_round_pick,1)+" across "+topAvg.first_round_picks+" drafts" : "—")+'</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">MOST #1 OVERALL PICKS</div><div class="pulse-value">'+esc(top1?.person_name||"—")+'</div><div class="pulse-meta">'+(top1?.first_overall_picks||0)+' times at pick 1</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">MOST TOP-3 PICKS</div><div class="pulse-value">'+esc(top3?.person_name||"—")+'</div><div class="pulse-meta">'+(top3?.first_round_top3||0)+' first-round picks in the top 3</div></div>'+
    '</div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><div><h2>First-Round Draft Position</h2><div class="subtle">Historical first-round slot, 2011–2025 · minimum 5 first-round drafts</div></div></div>'+
      '<div class="table-wrap"><table><thead><tr><th>Owner</th><th>1st Rnd</th><th>Avg Pick</th><th>Top 3</th><th>Top 5</th><th>#1</th><th>Best</th></tr></thead><tbody>'+positionRows+'</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><div><h2>Draft Position Leaders</h2><div class="subtle">Owners who have lived in the premium slots</div></div></div><div class="rank-list">'+leaderRows+'</div></section>'+
    '</div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><div><h2>Draft Slot Profile</h2><div class="subtle">How consistently each owner has received their first pick</div></div></div>'+
      '<div class="table-wrap"><table><thead><tr><th>Owner</th><th>Drafts</th><th>Avg 1st Pick</th><th>Slot σ</th><th>Best</th><th>Worst</th></tr></thead><tbody>'+slotRows+'</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><div><h2>2026 Draft</h2><div class="subtle">First 24 picks</div></div></div><div class="table-wrap"><table><thead><tr><th>Pick</th><th>Owner</th><th>Round</th></tr></thead><tbody>'+recentRows+'</tbody></table></div></section>'+
    '</div>'+
    '<div class="card"><div class="card-head"><div><h2>How to Read This</h2><div class="subtle">This is draft-position history, not a measure of draft skill.</div></div></div><p class="subtle" style="margin:0;line-height:1.7">First-round metrics use the actual overall pick number from each historical draft. A lower average means an owner has generally drafted earlier. Top-3, top-5, and #1 counts show how often they landed in premium draft slots. The leaderboard uses a five-draft minimum so one-season owners do not dominate the averages.</p></div>';
}
function rivalryRows() {
  const pairs = {};
  for (const m of DATA.matchups) {
    if (m.winner === "UNDECIDED" || m.away_team_id == null || !m.home_person_id || !m.away_person_id) continue;
    const ids = [m.home_person_id, m.away_person_id].sort();
    const key = ids.join("|");
    pairs[key] ??= {
      a:ids[0], b:ids[1], games:0, aWins:0, bWins:0, ties:0,
      playoffs:0, playoffWinsA:0, playoffWinsB:0, last:0,
      pointsA:0, pointsB:0, biggestMargin:0, biggestGame:null,
      currentRunOwner:null, currentRun:0
    };
    const p=pairs[key];
    p.games++;
    p.last=Math.max(p.last,m.season);
    const aHome=m.home_person_id===p.a;
    const sa=aHome?m.home_score:m.away_score;
    const sb=aHome?m.away_score:m.home_score;
    p.pointsA+=sa||0; p.pointsB+=sb||0;
    const playoff=m.playoff_tier_type!=="NONE";
    if(playoff) p.playoffs++;
    const margin=Math.abs((sa||0)-(sb||0));
    if(margin>p.biggestMargin){p.biggestMargin=margin;p.biggestGame=m;}
    if(m.winner==="TIE"){p.ties++;p.currentRunOwner=null;p.currentRun=0;}
    else {
      const winner=m.winner==="HOME"?m.home_person_id:m.away_person_id;
      if(winner===p.a){p.aWins++;if(playoff)p.playoffWinsA++;}
      else {p.bWins++;if(playoff)p.playoffWinsB++;}
    }
  }
  return Object.values(pairs).map(p=>{
    const competitive = Math.min(p.aWins,p.bWins);
    const balance = p.games ? competitive / p.games : 0;
    const intensity = p.games + p.playoffs*2 + balance*8;
    return {...p, balance, intensity};
  }).sort((a,b)=>b.intensity-a.intensity);
}

function renderRivalries() {
  const rows=rivalryRows();
  const active=rows.filter(r=>r.games>=5);
  const mostMeetings=[...rows].sort((a,b)=>b.games-a.games)[0];
  const mostPlayoffs=[...rows].sort((a,b)=>b.playoffs-a.playoffs)[0];
  const closest=active.slice().sort((a,b)=>b.balance-a.balance || b.games-a.games)[0];
  const mostOneSided=active.slice().sort((a,b)=>Math.abs(b.aWins-b.bWins)-Math.abs(a.aWins-a.bWins))[0];

  const card=(label,value,meta)=>'<div class="pulse-card"><div class="pulse-kicker">'+esc(label)+'</div><div class="pulse-value">'+esc(String(value))+'</div><div class="pulse-meta">'+esc(meta)+'</div></div>';

  $("#app").innerHTML=
    '<div class="page-head"><div><div class="eyebrow">Head to head</div><h1>Rivalries</h1><p>The owner matchups with the deepest history, biggest stakes and most competitive balance.</p></div></div>'+
    '<div class="pulse-grid">'+
      card("MOST MEETINGS",mostMeetings?.games||0,mostMeetings?personName(mostMeetings.a)+" vs "+personName(mostMeetings.b):"—")+
      card("MOST PLAYOFF MEETINGS",mostPlayoffs?.playoffs||0,mostPlayoffs?personName(mostPlayoffs.a)+" vs "+personName(mostPlayoffs.b):"—")+
      card("CLOSEST LONG-TERM RIVALRY",closest?personName(closest.a)+" vs "+personName(closest.b):"—",closest?closest.games+" meetings · "+closest.aWins+"–"+closest.bWins+(closest.ties?"–"+closest.ties:""):"—")+
      card("MOST ONE-SIDED",mostOneSided?personName(mostOneSided.a)+" vs "+personName(mostOneSided.b):"—",mostOneSided?mostOneSided.aWins+"–"+mostOneSided.bWins+" across "+mostOneSided.games+" games":"—")+
    '</div>'+
    '<section class="rivalry-hero"><div><div class="hero-kicker">Rivalry board</div><h2>'+active.length+' established rivalries</h2><p>Ranked by history, playoff intensity and competitive balance. Minimum five meetings.</p></div><div class="rivalry-count">'+active.length+'</div></section>'+
    '<div class="rivalry-grid">'+active.slice(0,15).map((r,i)=>
      '<article class="rivalry-card" onclick="location.hash=\'rivalry/'+encodeURIComponent(r.a)+'/'+encodeURIComponent(r.b)+'\'">'+
      '<div class="rivalry-rank">#'+(i+1)+' · '+r.playoffs+' PLAYOFF'+(r.playoffs===1?'':'S')+'</div>'+
      '<div class="rivalry-names"><strong>'+esc(personName(r.a))+'</strong><span>vs.</span><strong>'+esc(personName(r.b))+'</strong></div>'+
      '<div class="rivalry-record"><b>'+r.aWins+'-'+r.bWins+(r.ties?' - '+r.ties:'')+'</b><span>'+r.games+' meetings</span></div>'+
      '<div class="rivalry-meta"><span>Pts '+fmt(r.pointsA,0)+'–'+fmt(r.pointsB,0)+'</span><span>Last '+r.last+'</span></div>'+
      '</article>').join('')+
    '</div>';
}

function renderRivalry(a,b) {
  const rows=DATA.matchups.filter(m=>m.winner!=="UNDECIDED"&&m.away_team_id!=null&&((m.home_person_id===a&&m.away_person_id===b)||(m.home_person_id===b&&m.away_person_id===a))).sort((x,y)=>x.season-y.season||x.matchup_period_id-y.matchup_period_id);
  if(!rows.length){$("#app").innerHTML='<div class="empty">Rivalry not found.</div>';return;}

  let aw=0,bw=0,t=0,ap=0,bp=0,playoffGames=0,playoffAw=0,playoffBw=0,biggestWin=null,closest=null;
  rows.forEach(m=>{
    const ah=m.home_person_id===a,sa=ah?m.home_score:m.away_score,sb=ah?m.away_score:m.home_score;
    ap+=sa||0; bp+=sb||0;
    const margin=Math.abs((sa||0)-(sb||0));
    if(!biggestWin||margin>biggestWin.margin) biggestWin={m,margin,sa,sb};
    if(!closest||margin<closest.margin) closest={m,margin,sa,sb};
    const isPlayoff=m.playoff_tier_type!=="NONE";
    if(isPlayoff) playoffGames++;
    if(m.winner==="TIE") t++;
    else {
      const aWon=(m.winner==="HOME"&&m.home_person_id===a)||(m.winner==="AWAY"&&m.away_person_id===a);
      if(aWon){aw++;if(isPlayoff)playoffAw++;}else{bw++;if(isPlayoff)playoffBw++;}
    }
  });

  const games=rows.length;
  const avgA=ap/games, avgB=bp/games;
  const recordEdge=Math.abs(aw-bw);
  const competitive=recordEdge<=1;
  const latest=rows[rows.length-1];

  $("#app").innerHTML=
    '<div class="page-head"><div><div class="eyebrow">Rivalry</div><h1>'+esc(personName(a))+' <span style="color:var(--muted)">vs.</span> '+esc(personName(b))+'</h1><p>'+games+' meetings · '+playoffGames+' playoff meetings · last played '+latest.season+'</p></div><a class="badge" href="#rivalries">← Rivalries</a></div>'+
    '<div class="pulse-grid">'+
      '<div class="pulse-card"><div class="pulse-kicker">'+esc(personName(a))+'</div><div class="pulse-value">'+aw+'–'+bw+'</div><div class="pulse-meta">'+playoffAw+' playoff wins</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">'+esc(personName(b))+'</div><div class="pulse-value">'+bw+'–'+aw+'</div><div class="pulse-meta">'+playoffBw+' playoff wins</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">AVERAGE SCORE</div><div class="pulse-value">'+fmt(avgA,1)+'–'+fmt(avgB,1)+'</div><div class="pulse-meta">'+esc(personName(a))+' perspective</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">COMPETITION</div><div class="pulse-value">'+(competitive?"Nail-biter":"Lopsided")+'</div><div class="pulse-meta">'+recordEdge+' win'+(recordEdge===1?'':'s')+' separates them</div></div>'+
    '</div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><h2>Rivalry Snapshot</h2></div><div class="card-body">'+
        '<div class="champ-row"><div class="trophy">⚔</div><div class="champ-name"><strong>Regular-season record</strong><div class="champ-years">'+(aw-playoffAw)+'–'+(bw-playoffBw)+'</div></div></div>'+
        '<div class="champ-row"><div class="trophy">🏆</div><div class="champ-name"><strong>Playoff record</strong><div class="champ-years">'+playoffAw+'–'+playoffBw+(playoffGames-(playoffAw+playoffBw)?'–'+(playoffGames-playoffAw-playoffBw):'')+'</div></div></div>'+
        '<div class="champ-row"><div class="trophy">💥</div><div class="champ-name"><strong>Biggest margin</strong><div class="champ-years">'+fmt(biggestWin.margin,2)+' · '+biggestWin.m.season+' Week '+biggestWin.m.matchup_period_id+'</div></div></div>'+
        '<div class="champ-row"><div class="trophy">🎯</div><div class="champ-name"><strong>Closest game</strong><div class="champ-years">'+fmt(closest.margin,2)+' · '+closest.m.season+' Week '+closest.m.matchup_period_id+'</div></div></div>'+
      '</div></section>'+
      '<section class="card"><div class="card-head"><h2>Scoring Battle</h2></div><div class="card-body">'+
        '<div class="stat-card"><div class="stat-label">'+esc(personName(a))+' POINTS</div><div class="stat-value">'+fmt(ap,1)+'</div></div>'+
        '<div class="stat-card" style="margin-top:10px"><div class="stat-label">'+esc(personName(b))+' POINTS</div><div class="stat-value">'+fmt(bp,1)+'</div></div>'+
      '</div></section>'+
    '</div>'+
    '<section class="card" style="margin-top:18px"><div class="card-head"><h2>Matchup History</h2><div class="subtle">Oldest → newest</div></div><div class="table-wrap"><table><thead><tr><th>Season</th><th>Week</th><th>Type</th><th>'+esc(personName(a))+'</th><th>'+esc(personName(b))+'</th><th>Result</th></tr></thead><tbody>'+
    rows.slice().reverse().map(m=>{
      const ah=m.home_person_id===a,sa=ah?m.home_score:m.away_score,sb=ah?m.away_score:m.home_score;
      const res=m.winner==="TIE"?"T":((m.winner==="HOME"&&m.home_person_id===a)||(m.winner==="AWAY"&&m.away_person_id===a))?"W":"L";
      return '<tr><td>'+m.season+'</td><td>'+m.matchup_period_id+'</td><td><span class="badge">'+(m.playoff_tier_type==="NONE"?"REGULAR":"PLAYOFF")+'</span></td><td>'+fmt(sa,2)+'</td><td>'+fmt(sb,2)+'</td><td class="'+(res==="W"?"positive":res==="L"?"negative":"")+'">'+res+'</td></tr>';
    }).join('')+
    '</tbody></table></div></section>';
}
function renderMatchups() {
  const historical = DATA.matchups.filter(x => Number(x.season) <= 2025 && x.away_team_id != null && x.winner !== "UNDECIDED");
  const current = DATA.matchups.filter(x => Number(x.season) === 2026 && x.away_team_id != null && x.winner !== "UNDECIDED");

  const pairMap = {};
  for (const m of historical) {
    const ids = [m.home_person_id, m.away_person_id].sort();
    const key = ids.join("|");
    const p = (pairMap[key] ??= {
      a: ids[0], b: ids[1], games: 0, aWins: 0, bWins: 0, ties: 0,
      pointsA: 0, pointsB: 0, biggestMargin: 0, biggestMarginGame: null
    });
    const aIsHome = m.home_person_id === p.a;
    const aScore = aIsHome ? m.home_score : m.away_score;
    const bScore = aIsHome ? m.away_score : m.home_score;
    p.games++;
    p.pointsA += aScore || 0;
    p.pointsB += bScore || 0;
    if (m.winner === "TIE") p.ties++;
    else if ((m.winner === "HOME" && aIsHome) || (m.winner === "AWAY" && !aIsHome)) p.aWins++;
    else p.bWins++;
    const margin = Math.abs((aScore || 0) - (bScore || 0));
    if (margin > p.biggestMargin) {
      p.biggestMargin = margin;
      p.biggestMarginGame = m;
    }
  }

  const pairs = Object.values(pairMap);
  const mostMeetings = [...pairs].sort((a,b)=>b.games-a.games)[0];
  const biggestRivalry = [...pairs].filter(x=>x.games>=5).sort((a,b)=>(Math.abs(b.aWins-b.bWins))-(Math.abs(a.aWins-a.bWins)))[0] || pairs[0];

  let biggestBlowout = null, closestGame = null, highestCombined = null;
  for (const m of historical) {
    const margin = Math.abs((m.home_score||0) - (m.away_score||0));
    const combined = (m.home_score||0) + (m.away_score||0);
    if (!biggestBlowout || margin > biggestBlowout.margin) biggestBlowout={...m,margin};
    if (!closestGame || margin < closestGame.margin) closestGame={...m,margin};
    if (!highestCombined || combined > highestCombined.combined) highestCombined={...m,combined};
  }

  const statCards = [
    ["Games played", historical.length.toLocaleString(), "2011–2025", "Completed head-to-head games"],
    ["Most meetings", mostMeetings?.games ?? 0, mostMeetings ? personName(mostMeetings.a) + " vs " + personName(mostMeetings.b) : "—", "Regular + playoff"],
    ["Biggest blowout", fmt(biggestBlowout?.margin ?? 0,2), biggestBlowout ? personName(biggestBlowout.home_person_id) : "—", biggestBlowout ? biggestBlowout.season + " · " + personName(biggestBlowout.away_person_id) : "—"],
    ["Closest game", fmt(closestGame?.margin ?? 0,2), closestGame ? personName(closestGame.home_person_id) + " vs " + personName(closestGame.away_person_id) : "—", closestGame ? String(closestGame.season) : "—"],
    ["Highest combined score", fmt(highestCombined?.combined ?? 0,2), highestCombined ? personName(highestCombined.home_person_id) + " + " + personName(highestCombined.away_person_id) : "—", highestCombined ? String(highestCombined.season) : "—"]
  ];

  const seasons=[...new Set(DATA.matchups.map(x=>x.season))].sort((a,b)=>b-a);
  $("#app").innerHTML =
    "<div class=\"page-head\"><div><div class=\"eyebrow\">Head to head</div><h1>Matchups</h1><p>Every completed matchup in league history, with the arguments distilled down to numbers.</p></div></div>" +
    "<div class=\"pulse-grid\">" + statCards.map(r=>"<div class=\"pulse-card\"><div class=\"pulse-kicker\">" + esc(r[0]) + "</div><div class=\"pulse-value\">" + esc(String(r[1])) + "</div><div class=\"pulse-meta\">" + esc(r[2]) + " · " + esc(r[3]) + "</div></div>").join("") + "</div>" +
    "<div class=\"section-title\"><h2>Head-to-Head Leaders</h2><span class=\"mini\">Historical · minimum 5 meetings</span></div>" +
    "<section class=\"card\"><div class=\"table-wrap\"><table><thead><tr><th>Matchup</th><th>Games</th><th>Record</th><th>Points</th><th>Edge</th></tr></thead><tbody id=\"h2hRows\"></tbody></table></div></section>" +
    "<div class=\"section-title\" style=\"margin-top:26px\"><h2>Matchup Archive</h2><span class=\"mini\">2026 is included below as games are completed</span></div>" +
    "<div class=\"controls\"><select id=\"matchupSeason\">" + seasons.map(y=>"<option value=\""+y+"\">"+y+"</option>").join("") + "</select><select id=\"matchupType\"><option value=\"all\">All games</option><option value=\"regular\">Regular season</option><option value=\"playoffs\">Playoffs</option></select><input id=\"matchupSearch\" placeholder=\"Search owner…\" /></div>" +
    "<section class=\"card\"><div class=\"table-wrap\"><table><thead><tr><th>Season</th><th>Week</th><th>Home</th><th>Score</th><th>Away</th><th>Score</th><th>Result</th></tr></thead><tbody id=\"matchupRows\"></tbody></table></div></section>";

  const h2hBody=$("#h2hRows");
  const leaders=[...pairs].filter(x=>x.games>=5).sort((a,b)=>b.games-a.games).slice(0,15);
  h2hBody.innerHTML=leaders.map(x=>{
    const totalA=x.aWins, totalB=x.bWins;
    const edge=totalA===totalB ? "Tied" : personName(totalA>totalB?x.a:x.b) + " +" + Math.abs(totalA-totalB);
    return "<tr><td><b>"+esc(personName(x.a))+"</b> <span class=\"mini\">vs</span> <b>"+esc(personName(x.b))+"</b></td><td>"+x.games+"</td><td>"+totalA+"–"+totalB+(x.ties?"–"+x.ties:"")+"</td><td>"+fmt(x.pointsA,1)+"–"+fmt(x.pointsB,1)+"</td><td>"+esc(edge)+"</td></tr>";
  }).join("") || "<tr><td colspan=\"5\">No matchup pairs have reached five meetings yet.</td></tr>";

  const seasonSel=$("#matchupSeason"), typeSel=$("#matchupType"), search=$("#matchupSearch"), body=$("#matchupRows");
  function paint(){
    const y=Number(seasonSel.value), type=typeSel.value, q=search.value.toLowerCase().trim();
    let rows=DATA.matchups.filter(x=>Number(x.season)===y);
    if(type==="regular") rows=rows.filter(x=>x.playoff_tier_type==="NONE");
    if(type==="playoffs") rows=rows.filter(x=>x.playoff_tier_type!=="NONE");
    if(q) rows=rows.filter(x=>personName(x.home_person_id).toLowerCase().includes(q) || personName(x.away_person_id).toLowerCase().includes(q));
    rows.sort((a,b)=>b.matchup_period_id-a.matchup_period_id || b.matchup_id-a.matchup_id);
    body.innerHTML=rows.map(x=>"<tr><td>"+x.season+"</td><td>"+x.matchup_period_id+"</td><td class=\"owner-link\">"+esc(personName(x.home_person_id))+"</td><td>"+(x.home_score==null?"—":fmt(x.home_score,2))+"</td><td class=\"owner-link\">"+(x.away_team_id==null?"Bye":esc(personName(x.away_person_id)))+"</td><td>"+(x.away_score==null?"—":fmt(x.away_score,2))+"</td><td>"+(x.winner==="HOME"?"H":x.winner==="AWAY"?"A":x.winner==="TIE"?"T":"—")+"</td></tr>").join("") || "<tr><td colspan=\"7\">No games match those filters.</td></tr>";
  }
  seasonSel.addEventListener("change",paint); typeSel.addEventListener("change",paint); search.addEventListener("input",paint); paint();
}


window.addEventListener('hashchange', render);
$("#mobileMenu").addEventListener('click',()=>$(".sidebar").classList.toggle('open'));
document.querySelectorAll(".sidebar nav a").forEach(link=>{
  link.addEventListener("click",()=>$(".sidebar").classList.remove("open"));
});

loadData().then(render).catch(err=>{
  console.error(err);
  $("#app").innerHTML=`<div class="empty"><h2>Couldn’t load league data.</h2><p>${esc(err.message)}</p><p>Serve this folder through a local web server rather than opening index.html directly.</p></div>`;
});
