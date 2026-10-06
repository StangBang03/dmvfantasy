const DATA = {};

const routes = {
  dashboard: "Dashboard",
  seasons: "Seasons",
  owners: "Owners",
  records: "Records",
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
  for (let season = 2011; season <= 2025; season++) {
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
  if (route === "records") return renderRecords();
  if (route === "draft") return renderDraft();
  if (route === "matchups") return renderMatchups();
  if (route === "rivalries") return renderRivalries();
  if (route === "rivalry" && param) { const p=hash.split("/"); return renderRivalry(decodeURIComponent(p[1]),decodeURIComponent(p[2])); }
  location.hash = "dashboard";
}

function renderDashboard() {
  const current = currentRows();
  const week = Math.max(...DATA.matchups.filter(x => x.season === 2026 && x.playoff_tier_type === "NONE" && x.winner !== "UNDECIDED").map(x => x.matchup_period_id));
  const career = DATA.advanced_stats.career.filter(x => x.seasons >= 3).sort((a,b) => b.actual_win_pct - a.actual_win_pct).slice(0,5);
  const champs = Object.values(DATA.champCounts).sort((a,b) => b.count - a.count || a.name.localeCompare(b.name));
  const topPF = [...DATA.advanced_stats.season].sort((a,b) => b.points_for - a.points_for).slice(0,5);

  $("#app").innerHTML = `
    <section class="hero">
      <div class="hero-grid">
        <div>
          <div class="hero-kicker">The archive</div>
          <h1>15 seasons of league history.<br>One place to settle the arguments.</h1>
          <p>Championships, owner careers, H2H history, draft records and advanced analytics from 2011 through the current 2026 season.</p>
        </div>
        <div class="hero-side">
          <div class="hero-big">2026</div>
          <div class="hero-label">CURRENT SEASON · WEEK ${week}</div>
          <div style="margin-top:18px;color:rgba(255,255,255,.72);font-size:13px">${current[0] ? `<strong>${esc(personName(current[0].person_id))}</strong> is currently 2–0.` : "Current standings loading."}</div>
        </div>
      </div>
    </section>

    <div class="stats-grid">
      <div class="stat-card"><div class="stat-label">OWNERS</div><div class="stat-value">${DATA.people.length}</div><div class="stat-meta">canonical league identities</div></div>
      <div class="stat-card"><div class="stat-label">FRANCHISES</div><div class="stat-value">${new Set(DATA.teams.map(x => x.team_id)).size}</div><div class="stat-meta">ESPN team histories</div></div>
      <div class="stat-card"><div class="stat-label">MATCHUPS</div><div class="stat-value">${fmt(DATA.matchups.length)}</div><div class="stat-meta">2011–2026 collected</div></div>
      <div class="stat-card"><div class="stat-label">DRAFT PICKS</div><div class="stat-value">${fmt(DATA.draft_picks.length)}</div><div class="stat-meta">complete draft archive</div></div>
    </div>

    <div class="grid-2">
      <section class="card">
        <div class="card-head"><div><h2>2026 Standings</h2><div class="subtle">Through Week ${week}</div></div><a class="link" href="#seasons">Season archive →</a></div>
        <div class="table-wrap"><table><thead><tr><th>#</th><th>Owner</th><th>Record</th><th>PF</th><th>PA</th></tr></thead><tbody>
          ${current.map((x,i) => `<tr class="clickable" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'">
            <td class="rank">${i+1}</td><td><div class="owner-link">${esc(personName(x.person_id))}</div><div class="team-name">${esc(teamForSeason(2026,x.team_id)?.team_name || '')}</div></td>
            <td class="record">${x.wins}-${x.losses}${x.ties ? `-${x.ties}` : ''}</td><td>${fmt(x.points_for,2)}</td><td>${fmt(x.points_against,2)}</td>
          </tr>`).join("")}
        </tbody></table></div>
      </section>

      <section class="card">
        <div class="card-head"><div><h2>Championships</h2><div class="subtle">2011–2025 decided seasons</div></div><a class="link" href="#records">All records →</a></div>
        <div class="card-body">
          ${champs.slice(0,8).map((x,i) => `<div class="champ-row"><div class="trophy">🏆</div><div class="champ-name"><a class="owner-link" href="#owner/${encodeURIComponent(Object.keys(DATA.champCounts).find(k => DATA.champCounts[k]===x) || '')}">${esc(x.name)}</a><div class="champ-years">${x.years.join(" · ")}</div></div><div class="champ-count">${x.count}</div></div>`).join("")}
        </div>
      </section>
    </div>

    <div class="grid-2" style="margin-top:18px">
      <section class="card">
        <div class="card-head"><div><h2>Best Career Win %</h2><div class="subtle">Minimum 3 seasons</div></div><a class="link" href="#owners">All owners →</a></div>
        <div class="table-wrap"><table><thead><tr><th>Owner</th><th>Seasons</th><th>Record</th><th>Win %</th></tr></thead><tbody>
          ${career.map((x,i) => `<tr class="clickable" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'"><td><span class="rank">${i+1}</span> <span class="owner-link">${esc(x.person_name)}</span></td><td>${x.seasons}</td><td>${x.actual_wins}-${x.actual_losses}${x.actual_ties ? `-${x.actual_ties}` : ''}</td><td class="positive">${pct(x.actual_win_pct)}</td></tr>`).join("")}
        </tbody></table></div>
      </section>

      <section class="card">
        <div class="card-head"><div><h2>Single-Season Point Leaders</h2><div class="subtle">Regular season points for</div></div><a class="link" href="#records">More records →</a></div>
        <div class="table-wrap"><table><thead><tr><th>Season</th><th>Owner</th><th>PF</th><th>PPG</th></tr></thead><tbody>
          ${topPF.map(x => `<tr><td>${x.season}</td><td class="owner-link">${esc(x.person_name)}</td><td>${fmt(x.points_for,2)}</td><td>${fmt(x.points_per_game,2)}</td></tr>`).join("")}
        </tbody></table></div>
      </section>
    </div>
  `;
}

function renderSeasons() {
  const rows = [];
  for (let season=2025; season>=2011; season--) {
    const seasonTeams = DATA.teams.filter(x => x.season === season);
    const games = DATA.matchups.filter(x => x.season === season && x.playoff_tier_type === "NONE");
    const champ = DATA.champions.find(x => x.season === season);
    rows.push({season, teams: seasonTeams.length, games: games.length, champ});
  }
  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">Archive</div><h1>Seasons</h1><p>Every completed season, its champion and the size of the league.</p></div></div>
    <section class="card"><div class="table-wrap"><table><thead><tr><th>Season</th><th>Teams</th><th>Matchups</th><th>Champion</th><th>Final</th></tr></thead><tbody>
      ${rows.map(x => `<tr class="clickable" onclick="location.hash='season/${x.season}'"><td><strong>${x.season}</strong></td><td>${x.teams}</td><td>${x.games}</td><td class="owner-link">${esc(x.champ?.person_name || '—')}</td><td>${x.champ ? `${fmt(x.champ.score,2)} pts` : '—'}</td></tr>`).join("")}
    </tbody></table></div></section>
    <div class="card" style="margin-top:18px"><div class="card-head"><h2>2026</h2><span class="badge">IN PROGRESS</span></div><div class="card-body"><p class="subtle">The current season is intentionally excluded from historical records and championship totals until it is complete.</p></div></div>
  `;
}

function renderSeason(season) {
  const standings = DATA.standings.filter(x => x.season === season).sort((a,b) => b.wins-a.wins || b.points_for-a.points_for);
  const champ = DATA.champions.find(x => x.season === season);
  const playoff = DATA.matchups.filter(x => x.season===season && x.playoff_tier_type==='WINNERS_BRACKET').sort((a,b)=>a.matchup_period_id-b.matchup_period_id);
  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">Season</div><h1>${season}</h1><p>${season === 2026 ? 'Current season' : 'Historical season'} · ${standings.length} teams</p></div><a class="badge" href="#seasons">← All seasons</a></div>
    ${champ ? `<section class="hero"><div class="hero-grid"><div><div class="hero-kicker">Champion</div><h1>${esc(champ.person_name)}</h1><p>Team ${champ.team_id} · Championship score ${fmt(champ.score,2)}</p></div><div class="hero-side"><div class="hero-big">🏆</div><div class="hero-label">${season} CHAMPION</div></div></div></section>` : ''}
    <div class="grid-2" style="margin-top:18px">
      <section class="card"><div class="card-head"><h2>Regular Season</h2></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Owner</th><th>W-L-T</th><th>PF</th><th>PA</th></tr></thead><tbody>${standings.map((x,i)=>`<tr class="clickable" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'"><td>${i+1}</td><td><div class="owner-link">${esc(personName(x.person_id))}</div><div class="team-name">${esc(teamForSeason(season,x.team_id)?.team_name||'')}</div></td><td class="record">${x.wins}-${x.losses}${x.ties?`-${x.ties}`:''}</td><td>${fmt(x.points_for,2)}</td><td>${fmt(x.points_against,2)}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="card"><div class="card-head"><h2>Championship Path</h2></div><div class="card-body">${playoff.map(x=>`<div class="champ-row"><div class="trophy">${x.winner==='UNDECIDED'?'…':'✓'}</div><div class="champ-name"><strong>Week ${x.matchup_period_id}</strong><div class="champ-years">${x.home_team_id ? esc(personName(x.home_person_id)) : 'TBD'} ${x.away_team_id ? `vs ${esc(personName(x.away_person_id))}` : ' · Bye'}</div></div><div>${x.winner_team_id ? `<b>${x.winner_team_id}</b>` : 'TBD'}</div></div>`).join('')}</div></section>
    </div>
  `;
}

function renderOwners() {
  const career = [...DATA.advanced_stats.career].sort((a,b)=>a.person_name.localeCompare(b.person_name));
  $("#app").innerHTML = `
    <div class="page-head"><div><div class="eyebrow">People</div><h1>Owners</h1><p>Career profiles built from normalized regular-season history.</p></div></div>
    <div class="controls"><input id="ownerSearch" placeholder="Search owner…" /></div>
    <div class="owner-grid" id="ownerGrid"></div>
  `;
  const grid = $("#ownerGrid");
  function paint() {
    const q = $("#ownerSearch").value.toLowerCase().trim();
    const filtered = career.filter(x => x.person_name.toLowerCase().includes(q));
    grid.innerHTML = filtered.map(x=>{
      const c = DATA.champCounts[x.person_id]?.count || 0;
      return `<article class="owner-card" onclick="location.hash='owner/${encodeURIComponent(x.person_id)}'"><div class="owner-card-top"><div style="display:flex;gap:11px;align-items:center"><div class="avatar">${initials(x.person_name)}</div><div><h3>${esc(x.person_name)}</h3><div class="mini">${x.seasons} season${x.seasons===1?'':'s'}</div></div></div><div>${c ? `<span class="badge">🏆 ${c}</span>` : ''}</div></div><div class="owner-metrics"><div class="owner-metric"><b>${pct(x.actual_win_pct)}</b><span>WIN %</span></div><div class="owner-metric"><b>${fmt(x.points_per_game,1)}</b><span>PPG</span></div><div class="owner-metric"><b>${fmt(x.expected_wins,1)}</b><span>EXP W</span></div></div></article>`;
    }).join("") || '<div class="empty">No owners found.</div>';
  }
  $("#ownerSearch").addEventListener('input', paint); paint();
}

function renderOwner(id) {
  const x = DATA.advanced_stats.career.find(x=>x.person_id===id);
  if (!x) { $("#app").innerHTML='<div class="empty">Owner not found.</div>'; return; }

  const historicalSeasons = DATA.advanced_stats.season.filter(s=>s.person_id===id && s.season<=2025).sort((a,b)=>b.season-a.season);
  const teams = DATA.teams.filter(t=>t.person_id===id).sort((a,b)=>b.season-a.season);
  const historicalTeams = teams.filter(t=>t.season<=2025);
  const champs = DATA.champions.filter(c=>c.person_id===id);
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
    const h=h2h[opponent]; h.games++;
    if(m.winner==='UNDECIDED') return;
    if((m.winner==='HOME' && m.home_person_id===id)||(m.winner==='AWAY'&&m.away_person_id===id)) h.wins++;
    else if(m.winner==='TIE') h.ties++;
    else h.losses++;
  });
  const rivals=Object.entries(h2h).filter(([k,v])=>v.games>0).sort((a,b)=>b[1].games-a[1].games).slice(0,8);

  const current = DATA.advanced_stats.season.find(s=>s.person_id===id && s.season===2026);
  const draftAvg=draft.avg_first_round_pick;
  const draftTop3=draft.first_round_top3||0;
  const draftTop5=draft.first_round_top5||0;
  const draftFirstOverall=draft.first_overall_picks||0;

  $("#app").innerHTML=
    '<div class="profile-hero"><div class="profile-avatar">'+initials(x.person_name)+'</div><div><div class="eyebrow">Owner résumé</div><h1>'+esc(x.person_name)+'</h1><div class="badges">'+champs.map(c=>'<span class="badge">🏆 '+c.season+'</span>').join('')+(!champs.length?'<span class="badge">No championships yet</span>':'')+'</div></div></div>'+
    '<div class="pulse-grid">'+
      '<div class="pulse-card"><div class="pulse-kicker">CHAMPIONSHIPS</div><div class="pulse-value">'+champs.length+'</div><div class="pulse-meta">'+pct(champRate)+' of historical seasons</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">#1 SEEDS</div><div class="pulse-value">'+oneSeeds+'</div><div class="pulse-meta">'+pct(oneSeedRate)+' of historical seasons</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">PLAYOFF APPEARANCES</div><div class="pulse-value">'+playoffApps+'</div><div class="pulse-meta">'+pct(playoffRate)+' playoff rate</div></div>'+
      '<div class="pulse-card"><div class="pulse-kicker">AVG 1ST-ROUND PICK</div><div class="pulse-value">'+(draftAvg!=null?fmt(draftAvg,1):'—')+'</div><div class="pulse-meta">'+draftTop3+' top-3 · '+draftTop5+' top-5 · '+draftFirstOverall+' #1 overall</div></div>'+
    '</div>'+
    '<div class="grid-2">'+
      '<section class="card"><div class="card-head"><div><h2>Career Résumé</h2><div class="subtle">Historical seasons through 2025</div></div></div><div class="stats-grid" style="margin:0">'+
        '<div class="stat-card"><div class="stat-label">RECORD</div><div class="stat-value">'+wins+'-'+losses+(ties?' - '+ties:'')+'</div><div class="stat-meta">'+pct(winPct)+' win rate</div></div>'+
        '<div class="stat-card"><div class="stat-label">AVG FINISH / SEED</div><div class="stat-value">'+(avgSeed!=null?fmt(avgSeed,1):'—')+'</div><div class="stat-meta">best seed '+(bestSeed??'—')+'</div></div>'+
        '<div class="stat-card"><div class="stat-label">TOP-3 SEASONS</div><div class="stat-value">'+top3Seeds+'</div><div class="stat-meta">'+pct(historicalSeasons.length?top3Seeds/historicalSeasons.length:null)+' rate</div></div>'+
        '<div class="stat-card"><div class="stat-label">CHAMP. CONVERSION</div><div class="stat-value">'+pct(playoffConversion)+'</div><div class="stat-meta">titles per playoff appearance</div></div>'+
      '</div></section>'+
      '<section class="card"><div class="card-head"><div><h2>Draft Profile</h2><div class="subtle">Historical first-round positioning</div></div></div><div class="rank-list">'+
        '<div class="rank-row"><div class="rank-main"><strong>Average 1st-round pick</strong><small>Lower is earlier</small></div><b>'+(draftAvg!=null?fmt(draftAvg,1):'—')+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-3 picks</strong><small>Premium draft slots</small></div><b>'+draftTop3+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-5 picks</strong><small>Premium draft slots</small></div><b>'+draftTop5+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>#1 overall picks</strong><small>Times drafting first</small></div><b>'+draftFirstOverall+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Best 1st-round pick</strong><small>Career best</small></div><b>'+(draft.best_first_round_pick??'—')+'</b></div>'+
      '</div></section>'+
    '</div>'+
    '<div class="grid-2" style="margin-top:18px">'+
      '<section class="card"><div class="card-head"><h2>Season History</h2></div><div class="table-wrap"><table><thead><tr><th>Year</th><th>Record</th><th>Seed</th><th>PF</th><th>PPG</th><th>Luck</th></tr></thead><tbody>'+
        historicalSeasons.map(s=>{const t=historicalTeams.find(t=>t.season===s.season);return '<tr><td><a class="owner-link" href="#season/'+s.season+'">'+s.season+'</a></td><td class="record">'+s.actual_wins+'-'+s.actual_losses+(s.actual_ties?'-'+s.actual_ties:'')+'</td><td>'+(t?.playoff_seed??'—')+'</td><td>'+fmt(s.points_for,1)+'</td><td>'+fmt(s.points_per_game,1)+'</td><td class="'+(s.schedule_luck>=0?'positive':'negative')+'">'+(s.schedule_luck>=0?'+':'')+fmt(s.schedule_luck,1)+'</td></tr>';}).join('')+
      '</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><h2>Postseason Résumé</h2></div><div class="rank-list">'+
        '<div class="rank-row"><div class="rank-main"><strong>Championships</strong><small>'+champs.map(c=>c.season).join(' · ')+'</small></div><b>'+champs.length+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Championship appearances</strong><small>Won or runner-up</small></div><b>'+ (champs.length+championshipAppearances) +'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>#1 seeds</strong><small>Regular-season seed</small></div><b>'+oneSeeds+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Top-3 seeds</strong><small>Regular-season seed</small></div><b>'+top3Seeds+'</b></div>'+
        '<div class="rank-row"><div class="rank-main"><strong>Playoff appearances</strong><small>Historical seasons</small></div><b>'+playoffApps+'</b></div>'+
      '</div></section>'+
    '</div>'+
    '<div class="grid-2" style="margin-top:18px">'+
      '<section class="card"><div class="card-head"><h2>Team History</h2></div><div class="table-wrap"><table><thead><tr><th>Year</th><th>Team</th><th>Seed</th></tr></thead><tbody>'+historicalTeams.map(t=>'<tr><td>'+t.season+'</td><td><strong>'+esc(t.team_name)+'</strong><div class="team-name">'+esc(t.abbrev||'')+'</div></td><td>'+(t.playoff_seed??'—')+'</td></tr>').join('')+'</tbody></table></div></section>'+
      '<section class="card"><div class="card-head"><h2>Most Played Opponents</h2></div><div class="card-body">'+rivals.map(([pid,v])=>'<div class="champ-row"><div class="avatar" style="width:32px;height:32px;border-radius:9px;font-size:10px">'+initials(personName(pid))+'</div><div class="champ-name"><a class="owner-link" href="#owner/'+encodeURIComponent(pid)+'">'+esc(personName(pid))+'</a><div class="champ-years">'+v.games+' games · '+v.wins+'-'+v.losses+(v.ties?' - '+v.ties:'')+'</div></div><div class="record">'+(v.games?pct(v.wins/v.games):'—')+'</div></div>').join('') || '<div class="empty">No H2H data.</div>'+'</div></section>'+
    '</div>'+
    (current ? '<section class="card" style="margin-top:18px"><div class="card-head"><div><h2>2026 Season</h2><div class="subtle">Current season — not included in the historical résumé above</div></div></div><div class="stats-grid" style="margin:0"><div class="stat-card"><div class="stat-label">RECORD</div><div class="stat-value">'+current.actual_wins+'-'+current.actual_losses+(current.actual_ties?'-'+current.actual_ties:'')+'</div></div><div class="stat-card"><div class="stat-label">POINTS</div><div class="stat-value">'+fmt(current.points_for,1)+'</div></div><div class="stat-card"><div class="stat-label">PPG</div><div class="stat-value">'+fmt(current.points_per_game,1)+'</div></div></div></section>' : '');
}

function renderRecords() {
  const seasons = DATA.advanced_stats.season;
  const career = DATA.advanced_stats.career;
  const bestSeason = [...seasons].sort((a,b)=>b.points_for-a.points_for)[0];
  const bestPPG = [...seasons].sort((a,b)=>b.points_per_game-a.points_per_game)[0];
  const bestAllPlay = [...career].filter(x=>x.seasons>=3).sort((a,b)=>b.all_play_win_pct-a.all_play_win_pct)[0];
  const luck = [...seasons].sort((a,b)=>b.schedule_luck-a.schedule_luck)[0];
  const worstLuck = [...seasons].sort((a,b)=>a.schedule_luck-b.schedule_luck)[0];
  let biggestWin=null, highestScore=null;
  for(const m of DATA.matchups){
    if(m.winner==='UNDECIDED' || m.away_team_id==null) continue;
    const margin=Math.abs((m.home_score||0)-(m.away_score||0));
    if(!biggestWin || margin>biggestWin.margin) biggestWin={...m,margin};
    for(const side of ['home','away']){
      const score=side==='home'?m.home_score:m.away_score;
      if(score!=null && (!highestScore || score>highestScore.score)) highestScore={...m,side,score};
    }
  }
  const pairMap={};
  for(const m of DATA.matchups){ if(m.winner==='UNDECIDED' || m.away_team_id==null) continue; const ids=[m.home_person_id,m.away_person_id].sort().join('|'); pairMap[ids] ??= {games:0,combined:0,a:m.home_person_id,b:m.away_person_id}; pairMap[ids].games++; pairMap[ids].combined += (m.home_score||0)+(m.away_score||0); }
  const pairRows=Object.values(pairMap);
  const mostMeetings=pairRows.sort((a,b)=>b.games-a.games)[0];
  const mostCombined=[...pairRows].sort((a,b)=>b.combined-a.combined)[0];
  const recordCards=[
    ['Most points in a season',fmt(bestSeason.points_for,2),bestSeason.person_name,`${bestSeason.season} · ${fmt(bestSeason.points_per_game,2)} PPG`],
    ['Best season PPG',fmt(bestPPG.points_per_game,2),bestPPG.person_name,`${bestPPG.season} · ${fmt(bestPPG.points_for,2)} PF`],
    ['Best career all-play %',pct(bestAllPlay.all_play_win_pct),bestAllPlay.person_name,`${bestAllPlay.seasons} seasons`],
    ['Best schedule luck',`+${fmt(luck.schedule_luck,2)}`,luck.person_name,`${luck.season}`],
    ['Worst schedule luck',fmt(worstLuck.schedule_luck,2),worstLuck.person_name,`${worstLuck.season}`],
    ['Biggest winning margin',fmt(biggestWin.margin,2),'Single matchup',`${biggestWin.season} · ${personName(biggestWin.home_person_id)} ${fmt(biggestWin.home_score,2)}–${fmt(biggestWin.away_score,2)} ${personName(biggestWin.away_person_id)}`],
    ['Highest single-game score',fmt(highestScore.score,2),personName(highestScore.side==='home'?highestScore.home_person_id:highestScore.away_person_id),`${highestScore.season}`],
  ];
  $("#app").innerHTML=`<div class="page-head"><div><div class="eyebrow">League history</div><h1>Records</h1><p>The numbers that will start arguments in the group chat.</p></div></div><div class="owner-grid">${recordCards.map(r=>`<div class="owner-card"><div class="mini">${esc(r[0])}</div><div class="stat-value" style="margin-top:8px">${esc(r[1])}</div><div style="font-weight:800;margin-top:8px">${esc(r[2])}</div><div class="mini" style="margin-top:3px">${esc(r[3])}</div></div>`).join('')}</div>`;
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
    pairs[key] ??= {a:ids[0],b:ids[1],games:0,aWins:0,bWins:0,ties:0,playoffs:0,last:0};
    const p=pairs[key]; p.games++; p.last=Math.max(p.last,m.season);
    if(m.playoff_tier_type!=="NONE") p.playoffs++;
    if(m.winner==="TIE") p.ties++;
    else { const w=m.winner==="HOME"?m.home_person_id:m.away_person_id; if(w===p.a)p.aWins++;else p.bWins++; }
  }
  return Object.values(pairs).sort((a,b)=>(b.games+b.playoffs*2-Math.abs(b.aWins-b.bWins))-(a.games+a.playoffs*2-Math.abs(a.aWins-a.bWins)));
}

function renderRivalries() {
  const rows=rivalryRows();
  $("#app").innerHTML='<div class="page-head"><div><div class="eyebrow">Head to head</div><h1>Rivalries</h1><p>The owner matchups with the deepest history and biggest stakes.</p></div></div><section class="rivalry-hero"><div><div class="hero-kicker">Rivalry board</div><h2>'+rows.length+' owner pairings</h2><p>Meetings, playoff appearances and competitive balance shape the ranking.</p></div><div class="rivalry-count">'+rows.length+'</div></section><div class="rivalry-grid">'+rows.slice(0,12).map((r,i)=>'<article class="rivalry-card" onclick="location.hash=\'rivalry/'+encodeURIComponent(r.a)+'/'+encodeURIComponent(r.b)+'\'"><div class="rivalry-rank">#'+(i+1)+'</div><div class="rivalry-names"><strong>'+esc(personName(r.a))+'</strong><span>vs.</span><strong>'+esc(personName(r.b))+'</strong></div><div class="rivalry-record"><b>'+r.aWins+'-'+r.bWins+(r.ties?' - '+r.ties:'')+'</b><span>'+r.games+' meetings</span></div><div class="rivalry-meta"><span>'+r.playoffs+' playoff'+(r.playoffs===1?'':'s')+'</span><span>Last '+r.last+'</span></div></article>').join('')+'</div>';
}

function renderRivalry(a,b) {
  const rows=DATA.matchups.filter(m=>m.winner!=="UNDECIDED"&&m.away_team_id!=null&&((m.home_person_id===a&&m.away_person_id===b)||(m.home_person_id===b&&m.away_person_id===a))).sort((x,y)=>y.season-x.season||y.matchup_period_id-x.matchup_period_id);
  if(!rows.length){$("#app").innerHTML='<div class="empty">Rivalry not found.</div>';return;}
  let aw=0,bw=0,t=0,ap=0,bp=0;
  rows.forEach(m=>{const ah=m.home_person_id===a,sa=ah?m.home_score:m.away_score,sb=ah?m.away_score:m.home_score;ap+=sa||0;bp+=sb||0;if(m.winner==="TIE")t++;else if((m.winner==="HOME"&&m.home_person_id===a)||(m.winner==="AWAY"&&m.away_person_id===a))aw++;else bw++;});
  $("#app").innerHTML='<div class="page-head"><div><div class="eyebrow">Rivalry</div><h1>'+esc(personName(a))+' <span style="color:var(--muted)">vs.</span> '+esc(personName(b))+'</h1><p>'+rows.length+' meetings · '+rows.filter(x=>x.playoff_tier_type!=="NONE").length+' playoff meetings</p></div><a class="badge" href="#rivalries">← Rivalries</a></div><div class="stats-grid"><div class="stat-card"><div class="stat-label">'+esc(personName(a))+'</div><div class="stat-value">'+aw+'</div><div class="stat-meta">wins</div></div><div class="stat-card"><div class="stat-label">'+esc(personName(b))+'</div><div class="stat-value">'+bw+'</div><div class="stat-meta">wins</div></div><div class="stat-card"><div class="stat-label">MEETINGS</div><div class="stat-value">'+rows.length+'</div><div class="stat-meta">'+t+' ties</div></div><div class="stat-card"><div class="stat-label">AVG SCORE</div><div class="stat-value">'+fmt(ap/rows.length,1)+'–'+fmt(bp/rows.length,1)+'</div><div class="stat-meta">'+esc(personName(a))+' perspective</div></div></div><section class="card"><div class="card-head"><h2>Matchup History</h2></div><div class="table-wrap"><table><thead><tr><th>Season</th><th>Week</th><th>Type</th><th>'+esc(personName(a))+'</th><th>'+esc(personName(b))+'</th><th>Result</th></tr></thead><tbody>'+rows.map(m=>{const ah=m.home_person_id===a,sa=ah?m.home_score:m.away_score,sb=ah?m.away_score:m.home_score;const res=m.winner==="TIE"?"T":((m.winner==="HOME"&&m.home_person_id===a)||(m.winner==="AWAY"&&m.away_person_id===a))?"W":"L";return '<tr><td>'+m.season+'</td><td>'+m.matchup_period_id+'</td><td><span class="badge">'+(m.playoff_tier_type==="NONE"?"REGULAR":"PLAYOFF")+'</span></td><td>'+fmt(sa,2)+'</td><td>'+fmt(sb,2)+'</td><td class="'+(res==="W"?"positive":res==="L"?"negative":"")+'">'+res+'</td></tr>';}).join('')+'</tbody></table></div></section>';
}

function renderMatchups() {
  const seasons=[...new Set(DATA.matchups.map(x=>x.season))].sort((a,b)=>b-a);
  $("#app").innerHTML=`<div class="page-head"><div><div class="eyebrow">Head to head</div><h1>Matchups</h1><p>Browse the normalized matchup archive. Current-season games update as the season progresses.</p></div></div><div class="controls"><select id="matchupSeason">${seasons.map(y=>`<option value="${y}">${y}</option>`).join('')}</select><select id="matchupType"><option value="all">All games</option><option value="regular">Regular season</option><option value="playoffs">Playoffs</option></select></div><section class="card"><div class="table-wrap"><table><thead><tr><th>Season</th><th>Week</th><th>Home</th><th>Score</th><th>Away</th><th>Score</th><th>Result</th></tr></thead><tbody id="matchupRows"></tbody></table></div></section>`;
  const seasonSel=$("#matchupSeason"), typeSel=$("#matchupType"), body=$("#matchupRows");
  function paint(){
    const y=Number(seasonSel.value), type=typeSel.value;
    let rows=DATA.matchups.filter(x=>x.season===y);
    if(type==='regular') rows=rows.filter(x=>x.playoff_tier_type==='NONE');
    if(type==='playoffs') rows=rows.filter(x=>x.playoff_tier_type!=='NONE');
    rows.sort((a,b)=>b.matchup_period_id-a.matchup_period_id || b.matchup_id-a.matchup_id);
    body.innerHTML=rows.map(x=>`<tr><td>${x.season}</td><td>${x.matchup_period_id}</td><td class="owner-link">${esc(personName(x.home_person_id))}</td><td>${x.home_score==null?'—':fmt(x.home_score,2)}</td><td class="owner-link">${x.away_team_id==null?'Bye':esc(personName(x.away_person_id))}</td><td>${x.away_score==null?'—':fmt(x.away_score,2)}</td><td>${x.winner==='HOME'?'H':x.winner==='AWAY'?'A':x.winner==='TIE'?'T':'—'}</td></tr>`).join('');
  }
  seasonSel.addEventListener('change',paint); typeSel.addEventListener('change',paint); paint();
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
