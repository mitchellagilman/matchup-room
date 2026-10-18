let parlaySlip = [];
function americanToDecimal(odds){ odds = Number(odds); return odds > 0 ? 1 + odds/100 : 1 + 100/Math.abs(odds); }
function decimalToAmerican(dec){ if(dec >= 2) return '+' + Math.round((dec-1)*100); return Math.round(-100/(dec-1)).toString(); }
// Fallback probability estimate for when the learned model (train_model.py)
// isn't trained yet -- built from the SAME calibrated thresholds
// confidenceTier already uses, so it stays consistent with what "Strong"
// vs "Moderate" already means in this app rather than introducing a
// second, disconnected scale. Deliberately capped well short of 100% --
// this whole session's worth of backtesting found real, sometimes severe
// limits to this model's reliability, and a heuristic guess should never
// claim more confidence than the trained model itself would.
function edgeToProbability(edge, usedSP, league){
  const leagueCal = MODEL_CALIBRATION && MODEL_CALIBRATION[league];
  const strongThreshold = (leagueCal && leagueCal.calibrated) ? leagueCal.strong_threshold : 7;
  let prob = 0.5 + edge * (0.12/strongThreshold);
  if(league==='CFB' && !usedSP) prob = 0.5 + (prob-0.5)*0.6; // same "less trustworthy without SP+/SRS backing" discount confidenceTier already applies via the Strong* star
  return Math.max(0.5, Math.min(0.75, prob));
}
// Probability for a bet at ANY line, positive or negative edge. Built on the
// calibrated edge->probability curve only (not the learned model), because the
// learned model was trained on picks that already had a positive edge and
// includes a favorite/underdog switch at line 0 -- extrapolating it to small or
// negative edges made -1.5 read 50% while -0.5 read 48%. This version is
// symmetric around 50% and never decreases as a line gets easier:
// more points for the same side (or a lower number for an Over, a higher number
// for an Under) can only raise the probability.
function signedBetProbability(signedEdge, usedSP, league){
  const lift = edgeToProbability(Math.abs(signedEdge), usedSP, league) - 0.5;
  return 0.5 + (signedEdge<0 ? -lift : lift);
}
// Moneyline win chance. The market is a strong prior, so the model's margin is
// only allowed to move the market's expected margin part of the way (35%):
// a model that disagrees with the market by 6 points does NOT get to claim the
// underdog is the likely winner. marketMargin = how many points the team is
// favored by in the market (negative for an underdog), or null if no market line.
function marketMarginFor(team, opp){
  const m = findMarketLine(team, opp);
  if(!m) return null;
  const s = teamNamesMatch(m.aTeam, team) ? m.aSpread : m.bSpread;
  return (s===null || s===undefined) ? null : -s;
}
function mlWinProb(league, modelMargin, marketMargin){
  const sd = league==='CFB' ? 16 : 13.5;
  const m = (marketMargin===null || marketMargin===undefined) ? modelMargin : marketMargin + 0.35*(modelMargin-marketMargin);
  return Math.max(0.1, Math.min(0.9, normCdf(m/sd)));
}
function pickProbability(edge, usedSP, league, isFavorite, learnedProbOverride){
  if(learnedProbOverride!==null && learnedProbOverride!==undefined) return learnedProbOverride;
  const learned = predictHitProbability(edge, isFavorite===undefined ? true : isFavorite, league==='CFB');
  if(learned!==null) return learned;
  return edgeToProbability(edge, usedSP, league);
}
function probabilityCategory(prob){
  if(prob>=0.70) return {label:'Very Strong', style:'background:rgba(51,211,153,0.18);color:#5eead4;'};
  if(prob>=0.60) return {label:'Strong', style:'background:rgba(240,185,61,0.18);'};
  if(prob>=0.50) return {label:'Moderate', style:'background:rgba(136,146,176,0.18);'};
  if(prob>=0.35) return {label:'Not Likely', style:'background:rgba(242,139,125,0.12);'};
  return {label:'Very Unlikely', style:'background:rgba(242,139,125,0.2);color:#f28b7d;'};
}
function addLeg(label, odds, probability, meta, est){
  let prob = (probability===undefined?null:probability);
  // Legs that carry structured bet info (league/teams/line) get a model read
  // even when added from the Odds Board, and can be re-scored by the parlay analyzer.
  if(prob===null && meta){ const ev = evalBet(meta); if(ev) prob = ev.prob; }
  parlaySlip.push({label:label, odds: Number(odds), probability: prob, meta: meta||null, est: !!est});
  renderParlaySlip();
}

let ALL_ODDS = [];
let oddsFilter = 'ALL';

// Real NFL week boundaries for the 2026 season (verified against the live
// schedule) -- used to label odds-board sections "Week 1", "Week 2", etc.
// instead of leaving hundreds of games in one flat list.
const NFL_WEEK_BOUNDARIES = {
  1: ["2026-09-09","2026-09-14"], 2: ["2026-09-17","2026-09-21"], 3: ["2026-09-24","2026-09-28"],
  4: ["2026-10-01","2026-10-05"], 5: ["2026-10-08","2026-10-12"], 6: ["2026-10-15","2026-10-19"],
  7: ["2026-10-22","2026-10-26"], 8: ["2026-10-29","2026-11-02"], 9: ["2026-11-05","2026-11-09"],
  10: ["2026-11-12","2026-11-16"], 11: ["2026-11-19","2026-11-23"], 12: ["2026-11-25","2026-11-30"],
  13: ["2026-12-03","2026-12-07"], 14: ["2026-12-10","2026-12-14"], 15: ["2026-12-17","2026-12-21"],
  16: ["2026-12-24","2026-12-28"], 17: ["2026-12-31","2027-01-04"], 18: ["2027-01-10","2027-01-10"]
};
function nflWeekForDate(dateStr){
  const d = (dateStr||'').slice(0,10);
  if(!d) return null;
  for(const wk in NFL_WEEK_BOUNDARIES){
    const [start,end] = NFL_WEEK_BOUNDARIES[wk];
    if(d>=start && d<=end) return Number(wk);
  }
  return null;
}
function friendlyDate(dateStr){
  const d = (dateStr||'').slice(0,10);
  if(!d) return 'Date TBD';
  const dt = new Date(d+'T12:00:00Z');
  if(isNaN(dt)) return d;
  return dt.toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric', timeZone:'UTC'});
}
function groupLabelFor(g){
  if(g.league==='NFL'){
    const wk = nflWeekForDate(g.date);
    return wk ? ('Week '+wk) : friendlyDate(g.date);
  }
  return friendlyDate(g.date);
}
function groupOdds(odds){
  const groups = {};
  odds.forEach(function(g){
    const label = groupLabelFor(g);
    if(!groups[label]) groups[label] = { label, sortKey: (g.date||'').slice(0,10), games: [] };
    groups[label].games.push(g);
  });
  return Object.values(groups).sort(function(a,b){ return a.sortKey < b.sortKey ? -1 : (a.sortKey > b.sortKey ? 1 : 0); });
}

async function loadAllOdds(){
  const liveOdds = await fetchJSON('./data/odds.json');
  const nflWeekOdds = await fetchJSON('./data/nfl-week-odds.json');
  const combined = [];
  const seen = new Set();
  (nflWeekOdds || []).forEach(function(g){ combined.push(g); seen.add(g.game); });
  (liveOdds || []).forEach(function(g){ if(!seen.has(g.game)){ combined.push(g); seen.add(g.game); } });
  ALL_ODDS = combined.length ? combined : ODDS_SEED;
  return ALL_ODDS;
}

function legBtn(label, oddsVal, bookName, meta){
  const b = document.createElement('button');
  b.className = 'secondary leg-btn';
  b.dataset.leglabel = label;
  const shown = (oddsVal===null || oddsVal===undefined) ? '—' : (oddsVal>0?'+':'')+oddsVal;
  b.textContent = label+' '+shown;
  b.title = bookName ? ('Best price via '+bookName) : '';
  b.disabled = (oddsVal===null || oddsVal===undefined);
  if(parlaySlip.some(function(l){ return l.label===label; })) b.classList.add('selected');
  b.addEventListener('click', function(){
    if(oddsVal===null || oddsVal===undefined) return;
    const existing = parlaySlip.findIndex(function(l){ return l.label===label; });
    if(existing>=0){ parlaySlip.splice(existing,1); renderParlaySlip(); } // tap again to remove, like a sportsbook
    else addLeg(label, oddsVal, undefined, meta);
  });
  return b;
}
function buildGameRow(g){
  const wrap = document.createElement('div');
  wrap.style.cssText = 'border-bottom:1px solid var(--line);padding:10px 0;';
  const head = document.createElement('div');
  head.style.cssText = 'font-weight:700;font-size:0.88rem;margin-bottom:6px;';
  const bookCount = (g.books||[]).length;
  head.innerHTML = g.game+' <span class="pill">'+g.league+'</span> <span class="game-date">'+g.date+'</span>'+(bookCount>1?' <span class="pill" style="background:rgba(51,211,153,0.15);color:#5eead4;">'+bookCount+' books compared</span>':'');
  wrap.appendChild(head);

  const row1 = document.createElement('div'); row1.className = 'grid3';
  row1.appendChild(legBtn(g.aTeam+' ML', g.aML, g.aMLBook, {league:g.league,type:'ml',team:g.aTeam,opp:g.bTeam,line:0}));
  row1.appendChild(legBtn(g.aTeam+' '+(g.aSpread>0?'+':'')+g.aSpread, g.aSpreadOdds, g.aSpreadOddsBook, {league:g.league,type:'spread',team:g.aTeam,opp:g.bTeam,line:g.aSpread}));
  row1.appendChild(legBtn('Over '+g.total, g.overOdds, g.overOddsBook, {league:g.league,type:'total',dir:'over',team:g.aTeam,opp:g.bTeam,line:g.total}));
  wrap.appendChild(row1);

  const row2 = document.createElement('div'); row2.className = 'grid3'; row2.style.marginTop = '6px';
  row2.appendChild(legBtn(g.bTeam+' ML', g.bML, g.bMLBook, {league:g.league,type:'ml',team:g.bTeam,opp:g.aTeam,line:0}));
  row2.appendChild(legBtn(g.bTeam+' '+(g.bSpread>0?'+':'')+g.bSpread, g.bSpreadOdds, g.bSpreadOddsBook, {league:g.league,type:'spread',team:g.bTeam,opp:g.aTeam,line:g.bSpread}));
  row2.appendChild(legBtn('Under '+g.total, g.underOdds, g.underOddsBook, {league:g.league,type:'total',dir:'under',team:g.aTeam,opp:g.bTeam,line:g.total}));
  wrap.appendChild(row2);

  if(bookCount>1){
    const toggle = document.createElement('button');
    toggle.className = 'secondary';
    toggle.style.cssText = 'margin-top:6px;font-size:0.76rem;padding:5px 10px;';
    toggle.textContent = 'Compare all '+bookCount+' books';
    const table = document.createElement('div');
    table.style.cssText = 'display:none;margin-top:8px;font-size:0.78rem;';
    table.innerHTML = g.books.map(function(bk){
      return '<div class="history-item"><span>'+bk.book+'</span><span>'+g.aTeam+' '+(bk.aSpread!=null?((bk.aSpread>0?'+':'')+bk.aSpread+' ('+bk.aSpreadOdds+')'):'—')+' · '+g.bTeam+' '+(bk.bSpread!=null?((bk.bSpread>0?'+':'')+bk.bSpread+' ('+bk.bSpreadOdds+')'):'—')+' · Total '+(bk.total!=null?bk.total:'—')+'</span></div>';
    }).join('');
    toggle.addEventListener('click', function(){
      const showing = table.style.display!=='none';
      table.style.display = showing ? 'none' : 'block';
      toggle.textContent = showing ? ('Compare all '+bookCount+' books') : 'Hide comparison';
    });
    wrap.appendChild(toggle);
    wrap.appendChild(table);
  }
  return wrap;
}

async function renderOddsBoard(){
  await loadAllOdds();
  const list = document.getElementById('odds-board-list');
  const countEl = document.getElementById('odds-board-count');
  const odds = oddsFilter==='ALL' ? ALL_ODDS : ALL_ODDS.filter(function(g){ return g.league===oddsFilter; });
  if(countEl) countEl.textContent = odds.length + ' game' + (odds.length===1?'':'s');
  list.innerHTML = '';
  if(odds.length===0){
    list.innerHTML = '<div class="empty">No odds loaded for this filter yet.</div>';
    return;
  }
  const groups = groupOdds(odds);
  groups.forEach(function(group){
    const heading = document.createElement('div');
    heading.style.cssText = 'font-weight:800;font-size:0.82rem;color:var(--accent);margin:16px 0 4px;padding-bottom:4px;border-bottom:2px solid var(--accent);';
    heading.textContent = group.label + ' · ' + group.games.length + ' game' + (group.games.length===1?'':'s');
    list.appendChild(heading);
    group.games.forEach(function(g){ list.appendChild(buildGameRow(g)); });
  });
}
document.querySelectorAll('#odds-filter [data-oddsfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    oddsFilter = btn.dataset.oddsfilter;
    document.querySelectorAll('#odds-filter [data-oddsfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderOddsBoard();
  });
});

// ---------- Parlay analyzer ----------
// Resolves a market/odds-board team name to the key teamsCache uses.
function resolveTeamKey(name, league){
  if(!name) return null;
  if(teamsCache[name]) return name;
  const keys = Object.keys(teamsCache);
  for(let i=0;i<keys.length;i++){
    if(teamNamesMatch(keys[i], name) && (!league || teamsCache[keys[i]].league===league)) return keys[i];
  }
  return null;
}
// Which team is "A" (away) matters for home-field math, so reuse the
// week schedule's orientation whenever the game is on it.
function orientGame(t1, t2, league){
  const k1 = resolveTeamKey(t1, league), k2 = resolveTeamKey(t2, league);
  if(!k1 || !k2) return null;
  const games = league==='CFB' ? CFB_WEEK_GAMES : NFL_WEEK_GAMES;
  const g = games.find(function(x){ return (x.a===k1 && x.b===k2) || (x.a===k2 && x.b===k1); });
  if(g) return {a:g.a, b:g.b, date:g.date, k1:k1};
  const m = findMarketLine(k1, k2);
  return {a:k1, b:k2, date: m && m.date, k1:k1};
}
// Re-scores any bet described as {league,type:'spread'|'ml'|'total',team,opp,line,dir}
// with the same signed-edge logic as "Check a bet".
function evalBet(meta){
  try{
    if(!meta || meta.line===null || meta.line===undefined || isNaN(meta.line)) return null;
    const o = orientGame(meta.team, meta.opp, meta.league);
    if(!o) return null;
    const proj = computeProjection(o.a, o.b, meta.league, o.date);
    if(!proj) return null;
    let signedEdge, isFav;
    if(meta.type==='total'){
      const raw = proj.total - meta.line;
      signedEdge = meta.dir==='over' ? raw : -raw;
      isFav = false;
    } else {
      const line = meta.type==='ml' ? 0 : meta.line;
      const sideIsA = resolveTeamKey(meta.team, meta.league)===o.a;
      const lineAsAFavored = sideIsA ? -line : line;
      const raw = proj.spread - lineAsAFavored;
      signedEdge = sideIsA ? raw : -raw;
      isFav = meta.type==='ml' ? signedEdge>0 : line<0;
    }
    const evProb = meta.type==='ml' ? mlWinProb(meta.league, signedEdge, marketMarginFor(meta.team, meta.opp)) : signedBetProbability(signedEdge, proj.usedSP, meta.league);
    return {prob: evProb, signedEdge: signedEdge, gameId: [o.a,o.b].sort().join('|'), proj: proj, orient: o};
  }catch(e){ return null; }
}
function fmtLine(n){ return (n>0?'+':'')+n; }
function betLabel(meta){
  if(meta.type==='total') return (meta.dir==='over'?'Over ':'Under ')+meta.line;
  if(meta.type==='ml') return meta.team+' ML';
  return meta.team+' '+(meta.line===0 ? 'PK' : fmtLine(meta.line));
}
function parlayTierName(geo, weakest, dupes){
  let lvl = geo>=0.64 ? 3 : geo>=0.58 ? 2 : geo>=0.53 ? 1 : 0;
  if(weakest!==null && weakest<0.5) lvl = Math.max(0, lvl-1);
  if(dupes) lvl = Math.max(0, lvl-1);
  return [
    {label:'Weak', style:'background:rgba(242,139,125,0.2);color:#f28b7d;'},
    {label:'Shaky', style:'background:rgba(242,139,125,0.12);'},
    {label:'Decent', style:'background:rgba(240,185,61,0.18);'},
    {label:'Strong', style:'background:rgba(51,211,153,0.18);color:#5eead4;'},
  ][lvl];
}
let PARLAY_ACTIONS = [];
function buildParlayAnalysisHtml(){
  PARLAY_ACTIONS = [];
  if(parlaySlip.length===0) return '';
  const items = parlaySlip.map(function(leg, i){
    const ev = leg.meta ? evalBet(leg.meta) : null;
    const prob = ev ? ev.prob : (leg.probability!==undefined ? leg.probability : null);
    return {i:i, leg:leg, ev:ev, prob:prob, gameId: ev ? ev.gameId : null};
  });
  const rated = items.filter(function(x){ return x.prob!==null && x.prob!==undefined; });
  if(rated.length===0){
    return '<div class="card" style="background:var(--card-2);margin-top:12px;"><h2>Parlay check</h2><div class="note" style="margin:0;">None of these legs has a model read yet. Add legs from the Odds Board, Top Bets or Check a bet and I can rate the slip and suggest changes.</div></div>';
  }
  // Same-game legs are correlated; flag the weaker of each pair.
  const byGame = {};
  items.forEach(function(x){ if(x.gameId){ (byGame[x.gameId] = byGame[x.gameId] || []).push(x); } });
  const dupeIdx = {};
  Object.keys(byGame).forEach(function(k){
    const arr = byGame[k];
    if(arr.length>1){
      arr.slice().sort(function(a,b){ return (b.prob||0)-(a.prob||0); }).slice(1).forEach(function(x){ dupeIdx[x.i] = true; });
    }
  });
  const dupeCount = Object.keys(dupeIdx).length;
  const logSum = rated.reduce(function(a,x){ return a+Math.log(x.prob); }, 0);
  const geo = Math.exp(logSum/rated.length);
  const combined = rated.reduce(function(a,x){ return a*x.prob; }, 1);
  const weakestProb = Math.min.apply(null, rated.map(function(x){ return x.prob; }));
  const tier = parlayTierName(geo, weakestProb, dupeCount>0);
  const dec = rated.reduce(function(a,x){ return a*americanToDecimal(x.leg.odds); }, 1); // rated legs only, to match the model's combined % above
  const breakEven = 1/dec;
  let html = '<div class="card" style="background:var(--card-2);margin-top:12px;"><h2>Parlay check <span class="pill" style="'+tier.style+'">'+tier.label+'</span></h2>'
    + '<div class="note" style="margin:0 0 8px;">Average leg: <b>'+Math.round(geo*100)+'%</b> · weakest leg: <b>'+Math.round(weakestProb*100)+'%</b> · all '+rated.length+' hit: <b>'+Math.round(combined*100)+'%</b> (model) vs <b>'+Math.round(breakEven*100)+'%</b> needed to break even at these odds.'
    + (rated.length<parlaySlip.length ? ' '+(parlaySlip.length-rated.length)+' leg(s) have no model read and are not counted.' : '')
    + (rated.length>=5 ? ' '+rated.length+' legs is a long shot even when every leg looks good.' : '')
    + '</div>';

  // Weak legs: under 55%, the model leaning the other way, or a same-game duplicate.
  const weak = rated.filter(function(x){ return x.prob<0.55 || dupeIdx[x.i]; });
  const unrated = items.filter(function(x){ return x.prob===null || x.prob===undefined; });
  let swapPool = null;
  function getSwapPool(){
    if(swapPool) return swapPool;
    swapPool = [];
    ['NFL','CFB'].forEach(function(lg){
      try{ computeAllBetCandidates(lg==='NFL'?NFL_WEEK_GAMES:CFB_WEEK_GAMES, lg).forEach(function(c){
        if(c.oddsPrice===null || c.oddsPrice===undefined || !c.meta) return;
        const e = evalBet(c.meta);
        swapPool.push({c:c, prob: pickProbability(c.edge, c.usedSP, c.league, c.isFavorite, c.learnedProb), gameId: e ? e.gameId : null});
      }); }catch(e){}
    });
    return swapPool;
  }
  const usedGames = {};
  items.forEach(function(x){ if(x.gameId) usedGames[x.gameId] = true; });

  function addAction(fn){ PARLAY_ACTIONS.push(fn); return PARLAY_ACTIONS.length-1; }
  function suggestionRow(text, sub, idx, btnText){
    return '<div class="history-item"><span>'+text+(sub?'<span class="team-meta" style="display:block;font-weight:400;">'+sub+'</span>':'')+'</span><button class="secondary" data-pact="'+idx+'" style="font-size:0.76rem;padding:5px 10px;">'+btnText+'</button></div>';
  }

  if(weak.length===0 && unrated.length===0){
    html += '<div class="note" style="margin:0;color:#5eead4;">No weak legs: every leg is 55%+ and no two legs share a game.</div>';
  }
  weak.sort(function(a,b){ return a.prob-b.prob; }).forEach(function(x){
    const why = x.prob<0.5 ? 'the model leans the other way' : (dupeIdx[x.i] && x.prob>=0.55 ? 'same game as another leg (correlated)' : 'only '+Math.round(x.prob*100)+'% by the model');
    html += '<div style="margin-top:12px;"><div style="font-weight:700;font-size:0.9rem;">Weakest: '+x.leg.label+' <span class="pill" style="'+probabilityCategory(x.prob).style+'">'+Math.round(x.prob*100)+'%</span></div><div class="team-meta" style="margin-bottom:4px;">'+why+'</div>';
    const m = x.leg.meta;
    let rows = '';
    if(m){
      // 1. flip sides when the model prefers the other side
      if(x.prob<0.5){
        const fm = Object.assign({}, m);
        if(m.type==='total'){ fm.dir = m.dir==='over'?'under':'over'; }
        else if(m.type==='ml'){ fm.team = m.opp; fm.opp = m.team; }
        else { fm.team = m.opp; fm.opp = m.team; fm.line = -m.line; }
        const fe = evalBet(fm);
        if(fe){
          const idx = addAction(function(){ parlaySlip[x.i] = {label: betLabel(fm)+' ('+m.team+' vs '+m.opp+')', odds: -110, probability: fe.prob, meta: fm}; });
          rows += suggestionRow('Flip to '+betLabel(fm), Math.round(fe.prob*100)+'% · '+probabilityCategory(fe.prob).label+' · odds set to -110 est., check your book', idx, 'Flip');
        }
      }
      // 2. buy points on the same game: smallest line changes that reach 55% / 60%
      if(m.type!=='ml'){
        let hit55 = null, hit60 = null, best = null;
        for(let step=0.5; step<=4.01; step+=0.5){
          const sm = Object.assign({}, m);
          if(m.type==='total') sm.line = m.dir==='over' ? m.line-step : m.line+step; else sm.line = m.line+step;
          const se = evalBet(sm);
          if(!se) continue;
          best = {m:sm, e:se, step:step};
          if(!hit55 && se.prob>=0.55) hit55 = best;
          if(!hit60 && se.prob>=0.60){ hit60 = best; break; }
        }
        const picks = [];
        if(hit55) picks.push(hit55);
        if(hit60 && (!hit55 || hit60.step!==hit55.step)) picks.push(hit60);
        if(!picks.length && best && best.e.prob-x.prob>=0.05) picks.push(best);
        picks.forEach(function(p){
          const idx = addAction(function(){ parlaySlip[x.i] = {label: betLabel(p.m)+' ('+m.team+' vs '+m.opp+')', odds: -110, probability: p.e.prob, meta: p.m}; });
          rows += suggestionRow('Change line to '+betLabel(p.m), Math.round(p.e.prob*100)+'% · '+probabilityCategory(p.e.prob).label+' · pays less than your current price (odds set to -110 est.; check the alt line at your book)', idx, 'Use line');
        });
      }
    }
    // 3. swap for a stronger bet in a different game
    const floor = Math.max(x.prob+0.04, 0.55);
    const swaps = getSwapPool().filter(function(p){
      if(p.prob<floor) return false;
      if(p.gameId && usedGames[p.gameId]) return false;
      if(m && m.league && p.c.league!==m.league) return false;
      return true;
    }).sort(function(a,b){ return b.prob-a.prob; });
    // keep only the best bet per game
    const bestPerGame = {};
    swaps.forEach(function(p){ if(!bestPerGame[p.gameId]) bestPerGame[p.gameId] = p; });
    Object.keys(bestPerGame).map(function(k){ return bestPerGame[k]; }).sort(function(a,b){ return b.prob-a.prob; }).slice(0,3).forEach(function(p){
      const idx = addAction(function(){ parlaySlip[x.i] = {label: p.c.label+' ('+p.c.gameKey+')', odds: p.c.oddsPrice, probability: p.prob, meta: p.c.meta}; });
      rows += suggestionRow('Swap to '+p.c.label, p.c.gameKey+' · '+Math.round(p.prob*100)+'% · '+probabilityCategory(p.prob).label+' · '+fmtLine(p.c.oddsPrice), idx, 'Swap in');
    });
    // 4. drop it
    if(parlaySlip.length>2){
      const rest = rated.filter(function(r){ return r.i!==x.i; });
      const restCombined = rest.reduce(function(a,r){ return a*r.prob; }, 1);
      const idx = addAction(function(){ parlaySlip.splice(x.i,1); });
      rows += suggestionRow('Drop this leg', 'Hit chance goes from '+Math.round(combined*100)+'% to '+Math.round(restCombined*100)+'% (payout shrinks too)', idx, 'Drop');
    }
    html += (rows || '<div class="note" style="margin:0;">No stronger alternatives found this week.</div>') + '</div>';
  });
  if(unrated.length){
    html += '<div class="note" style="margin-top:10px;">No model read for: '+unrated.map(function(x){ return x.leg.label; }).join('; ')+'. Custom legs and player props can\'t be rated.</div>';
  }
  html += '<div class="note" style="margin-top:10px;">Probabilities are model estimates (capped at 75% per leg), not guarantees. Alt-line prices are estimates.</div></div>';
  return html;
}
function wireParlayActions(root){
  root.querySelectorAll('[data-pact]').forEach(function(btn){
    btn.addEventListener('click', function(){
      const fn = PARLAY_ACTIONS[Number(btn.dataset.pact)];
      if(fn){ fn(); renderParlaySlip(); }
    });
  });
}


// ---------- Alt lines ----------
let ALT_ACTIONS = [];
function normCdf(z){
  // Abramowitz-Stegun approximation of the standard normal CDF
  const t = 1/(1+0.2316419*Math.abs(z));
  const d = 0.3989423*Math.exp(-z*z/2);
  const p = d*t*(0.3193815+t*(-0.3565638+t*(1.781478+t*(-1.821256+t*1.330274))));
  return z>0 ? 1-p : p;
}
function probToAmerican(p){
  const pv = Math.max(0.03, Math.min(0.97, p*1.045)); // ~4.5% sportsbook margin baked in
  const am = pv>=0.5 ? -(100*pv/(1-pv)) : (100*(1-pv)/pv);
  const r = Math.round(am/5)*5;
  return Math.abs(r)<100 ? (r<0?-100:100) : r;
}
// Estimated sportsbook price for an alt line, derived from the market line
// (normal approximation of the final margin / total). It's an estimate, NOT
// a real DraftKings price, so legs added this way are flagged "est." and the
// odds box in the slip is editable.
function estAltOdds(meta){
  try{
    const lg = meta.league;
    const market = findMarketLine(meta.team, meta.opp);
    const ev = evalBet(meta);
    if(!ev) return null;
    const marginSd = lg==='CFB' ? 16 : 13.5, totalSd = lg==='CFB' ? 12 : 10;
    if(meta.type==='total'){
      const center = (market && market.total!==null && market.total!==undefined) ? market.total : ev.proj.total;
      const pOver = 1 - normCdf((meta.line-center)/totalSd);
      return probToAmerican(meta.dir==='over' ? pOver : 1-pOver);
    }
    let expMargin; // expected margin for the side being bet
    if(market){
      const isEntryA = teamNamesMatch(market.aTeam, meta.team);
      const mk = isEntryA ? market.aSpread : market.bSpread;
      if(mk!==null && mk!==undefined) expMargin = -mk;
    }
    if(expMargin===undefined){
      const sideIsA = resolveTeamKey(meta.team, meta.league)===ev.orient.a;
      expMargin = sideIsA ? ev.proj.spread : -ev.proj.spread;
    }
    if(meta.type==='ml'){
      if(market){ const ml = teamNamesMatch(market.aTeam, meta.team) ? market.aML : market.bML; if(ml!==null && ml!==undefined) return ml; }
      return probToAmerican(normCdf(expMargin/marginSd));
    }
    return probToAmerican(normCdf((expMargin + meta.line)/marginSd));
  }catch(e){ return null; }
}
function renderAltLadder(elId, meta, legIndex){
  const el = document.getElementById(elId);
  if(!el) return;
  ALT_ACTIONS = ALT_ACTIONS || [];
  const chips = [];
  for(let off=-6; off<=6; off++){
    const m = Object.assign({}, meta); m.line = meta.line + off;
    const ev = evalBet(m);
    if(!ev) continue;
    const est = estAltOdds(m);
    const idx = ALT_ACTIONS.push({m:m, prob:ev.prob, est:est}) - 1;
    const cat = probabilityCategory(ev.prob);
    const cur = off===0;
    const lab = m.type==='total' ? ((m.dir==='over'?'O ':'U ')+m.line) : fmtLine(m.line);
    chips.push('<button class="secondary" data-altchip="'+idx+'" style="margin:0;padding:6px 4px;font-size:0.76rem;line-height:1.25;'+(cur?'border-color:var(--accent);':'')+'"><b>'+lab+'</b><br><span style="'+cat.style+'padding:1px 6px;border-radius:999px;">'+Math.round(ev.prob*100)+'%</span>'+(est!==null?'<br><span class="team-meta">est '+(est>0?'+':'')+est+'</span>':'')+'</button>');
  }
  const who = meta.type==='total' ? ((meta.dir==='over'?'Over':'Under')+' · '+meta.team+' vs '+meta.opp) : meta.team;
  el.innerHTML = '<div class="team-meta" style="margin:6px 0;">'+who+' — probability by line (est. prices, edit odds to match your book)</div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;">'+chips.join('')+'</div>';
  el.querySelectorAll('[data-altchip]').forEach(function(btn){
    btn.addEventListener('click', function(e){
      e.stopPropagation();
      const a = ALT_ACTIONS[Number(btn.dataset.altchip)];
      const label = betLabel(a.m)+' ('+a.m.team+' vs '+a.m.opp+')';
      const odds = a.est!==null ? a.est : -110;
      if(legIndex===null || legIndex===undefined){
        addLeg(label, odds, a.prob, a.m, true);
      } else {
        parlaySlip[legIndex] = {label:label, odds:odds, probability:a.prob, meta:a.m, est:true, _altOpen:true};
        renderParlaySlip();
      }
    });
  });
}

// ---------- My Bets tracker ----------
const MYBETS_KEY = 'mr_my_bets_v1';
let MY_BETS = [];
let myBetsFilter = 'ALL';
function loadMyBets(){ try{ MY_BETS = JSON.parse(localStorage.getItem(MYBETS_KEY)||'[]') || []; }catch(e){ MY_BETS = []; } }
function saveMyBets(){ try{ localStorage.setItem(MYBETS_KEY, JSON.stringify(MY_BETS)); }catch(e){} }
loadMyBets();
function betDecimal(b){ return b.legs.reduce(function(a,l){ return a*americanToDecimal(l.odds); }, 1); }
function betProfit(b){
  if(b.status==='won') return b.stake*(betDecimal(b)-1);
  if(b.status==='lost') return -b.stake;
  return 0;
}
function placeSlipAsBet(){
  if(parlaySlip.length===0) return;
  const stakeEl = document.getElementById('slip-dock-stake') || document.getElementById('parlay-stake');
  const stake = parseFloat(stakeEl.value);
  if(!stake || stake<=0){ alert('Enter a stake first.'); return; }
  const legs = parlaySlip.map(function(l){ return {label:l.label, odds:l.odds, prob:(l.probability===undefined?null:l.probability), meta:l.meta||null, result:null}; });
  MY_BETS.unshift({id:Date.now(), ts:new Date().toISOString(), stake:stake, legs:legs, status:'pending', manual:false});
  saveMyBets();
  parlaySlip.length = 0;
  document.getElementById('slip-dock').classList.remove('open');
  renderParlaySlip();
  renderMyBets();
  activateTopTab('parlay'); activateSubTab('my-bets');
  window.scrollTo({top:0, behavior:'smooth'});
}
function gradeLeg(leg){
  // best-effort: only works for games in this week's loaded schedule with a final score
  const m = leg.meta;
  if(!m) return null;
  const o = orientGame(m.team, m.opp, m.league);
  if(!o) return null;
  const f = findFinalScoreForMatchup(m.league, o.a, o.b);
  if(!f) return null;
  if(m.type==='total'){
    const tot = f.awayScore + f.homeScore;
    if(tot===m.line) return 'push';
    return ((m.dir==='over') === (tot>m.line)) ? 'won' : 'lost';
  }
  const teamKey = resolveTeamKey(m.team, m.league);
  const margin = teamKey===f.away ? f.awayScore-f.homeScore : f.homeScore-f.awayScore;
  const line = m.type==='ml' ? 0 : m.line;
  const v = margin + line;
  if(m.type==='ml') return margin>0 ? 'won' : (margin<0 ? 'lost' : 'push');
  return v>0 ? 'won' : (v<0 ? 'lost' : 'push');
}
function autoGradeBets(){
  let n = 0;
  MY_BETS.forEach(function(b){
    if(b.status!=='pending') return;
    b.legs.forEach(function(l){ if(!l.result){ const r = gradeLeg(l); if(r) l.result = r; } });
    if(b.legs.some(function(l){ return l.result==='lost'; })){ b.status='lost'; n++; }
    else if(b.legs.every(function(l){ return l.result; })){
      b.status = b.legs.every(function(l){ return l.result==='push'; }) ? 'push' : 'won'; n++;
      // pushed legs are removed from a won parlay (odds recomputed without them)
      if(b.status==='won'){ b.legs = b.legs.filter(function(l){ return l.result!=='push'; }); }
    }
  });
  saveMyBets(); renderMyBets();
  return n;
}
function renderMyBets(){
  const listEl = document.getElementById('mb-list');
  if(!listEl) return;
  const settled = MY_BETS.filter(function(b){ return b.status!=='pending'; });
  const pending = MY_BETS.filter(function(b){ return b.status==='pending'; });
  const won = settled.filter(function(b){ return b.status==='won'; }).length;
  const lost = settled.filter(function(b){ return b.status==='lost'; }).length;
  const push = settled.filter(function(b){ return b.status==='push'; }).length;
  const profit = settled.reduce(function(a,b){ return a+betProfit(b); }, 0);
  const staked = settled.filter(function(b){ return b.status!=='push'; }).reduce(function(a,b){ return a+b.stake; }, 0);
  const atRisk = pending.reduce(function(a,b){ return a+b.stake; }, 0);
  document.getElementById('mb-count').textContent = MY_BETS.length+' bet'+(MY_BETS.length===1?'':'s');
  const withP = settled.filter(function(b){ return b.legs.every(function(l){ return l.prob!==null && l.prob!==undefined; }) && b.status!=='push'; });
  let calib = '';
  if(withP.length>=3){
    const avg = withP.reduce(function(a,b){ return a + b.legs.reduce(function(x,l){ return x*l.prob; },1); },0)/withP.length;
    const act = withP.filter(function(b){ return b.status==='won'; }).length/withP.length;
    calib = '<div class="note">Model said these '+withP.length+' settled bets would hit about <b>'+Math.round(avg*100)+'%</b> of the time; you hit <b>'+Math.round(act*100)+'%</b>.</div>';
  }
  document.getElementById('mb-summary').innerHTML = '<div class="proj-score" style="padding-top:8px;"><div><div class="num">'+won+'-'+lost+(push?'-'+push:'')+'</div><div class="lbl">record</div></div><div><div class="num" style="color:'+(profit>=0?'#5eead4':'#f28b7d')+';">'+(profit>=0?'+':'-')+'$'+Math.abs(profit).toFixed(2)+'</div><div class="lbl">net profit</div></div><div><div class="num">'+(staked>0?Math.round(profit/staked*100)+'%':'—')+'</div><div class="lbl">ROI</div></div></div><div class="note">'+pending.length+' pending · $'+atRisk.toFixed(2)+' at risk</div>'+calib;
  let list = MY_BETS;
  if(myBetsFilter==='pending') list = pending;
  if(myBetsFilter==='settled') list = settled;
  if(list.length===0){ listEl.innerHTML = '<div class="empty">Nothing here yet.</div>'; return; }
  const stStyle = {pending:'', won:'background:rgba(51,211,153,0.18);color:#5eead4;', lost:'background:rgba(242,139,125,0.2);color:#f28b7d;', push:'background:rgba(136,146,176,0.18);'};
  listEl.innerHTML = list.map(function(b){
    const dec = betDecimal(b);
    const d = new Date(b.ts);
    const legRows = b.legs.map(function(l){
      const r = l.result ? ' <span class="pill" style="'+stStyle[l.result]+'">'+l.result+'</span>' : '';
      const p = (l.prob!==null && l.prob!==undefined) ? ' <span class="team-meta">'+Math.round(l.prob*100)+'%</span>' : '';
      return '<div class="history-item"><span>'+l.label+p+r+'</span><span>'+(l.odds>0?'+':'')+l.odds+'</span></div>';
    }).join('');
    const pl = b.status==='pending' ? 'To win $'+(b.stake*(dec-1)).toFixed(2) : (b.status==='push' ? 'Refunded' : (betProfit(b)>=0?'+':'-')+'$'+Math.abs(betProfit(b)).toFixed(2));
    return '<div class="card" style="background:var(--card-2);margin-bottom:10px;"><div style="display:flex;justify-content:space-between;align-items:center;"><div style="font-weight:800;">'+(b.legs.length===1?'Straight':b.legs.length+'-leg parlay')+' <span class="pill" style="'+stStyle[b.status]+'">'+b.status+'</span></div><div style="font-weight:800;">'+decimalToAmerican(dec)+'</div></div>'
      + '<div class="team-meta" style="margin:2px 0 6px;">'+d.toLocaleDateString()+' · $'+b.stake.toFixed(2)+' stake · '+pl+'</div>'+legRows
      + '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;">'
      + (b.status==='pending'
          ? '<button class="secondary" data-mbset="won" data-mbid="'+b.id+'" style="margin:0;padding:6px 12px;">Won</button><button class="secondary" data-mbset="lost" data-mbid="'+b.id+'" style="margin:0;padding:6px 12px;">Lost</button><button class="secondary" data-mbset="push" data-mbid="'+b.id+'" style="margin:0;padding:6px 12px;">Push</button>'
          : '<button class="secondary" data-mbset="pending" data-mbid="'+b.id+'" style="margin:0;padding:6px 12px;">Reopen</button>')
      + '<button class="danger" data-mbdel="'+b.id+'" style="margin:0 0 0 auto;">Delete</button></div></div>';
  }).join('');
  listEl.querySelectorAll('[data-mbset]').forEach(function(btn){
    btn.addEventListener('click', function(){
      const b = MY_BETS.find(function(x){ return String(x.id)===btn.dataset.mbid; });
      if(b){ b.status = btn.dataset.mbset; saveMyBets(); renderMyBets(); }
    });
  });
  listEl.querySelectorAll('[data-mbdel]').forEach(function(btn){
    btn.addEventListener('click', function(){
      if(!confirm('Delete this bet?')) return;
      MY_BETS = MY_BETS.filter(function(x){ return String(x.id)!==btn.dataset.mbdel; });
      saveMyBets(); renderMyBets();
    });
  });
}
document.getElementById('mb-add').addEventListener('click', function(){
  const desc = document.getElementById('mb-desc').value.trim();
  const odds = Number(document.getElementById('mb-odds').value);
  const stake = parseFloat(document.getElementById('mb-stake').value);
  if(!desc || !odds || Math.abs(odds)<100 || !stake || stake<=0){ alert('Enter a description, American odds (like +250 or -110) and a stake.'); return; }
  MY_BETS.unshift({id:Date.now(), ts:new Date().toISOString(), stake:stake, legs:[{label:desc, odds:odds, prob:null, meta:null, result:null}], status:'pending', manual:true});
  saveMyBets();
  document.getElementById('mb-desc').value = ''; document.getElementById('mb-odds').value = '';
  renderMyBets();
});
document.querySelectorAll('#mb-filter [data-mbfilter]').forEach(function(b){
  b.addEventListener('click', function(){
    myBetsFilter = b.dataset.mbfilter;
    document.querySelectorAll('#mb-filter [data-mbfilter]').forEach(function(x){ x.classList.toggle('active', x===b); });
    renderMyBets();
  });
});
document.getElementById('mb-autograde').addEventListener('click', function(){
  const n = autoGradeBets();
  alert(n ? n+' bet(s) settled from final scores.' : 'No pending bets could be graded automatically. Only games on this week\'s loaded schedule with a final score can be, so settle older or player-prop bets with the Won / Lost buttons.');
});
document.querySelector('[data-subtab="my-bets"]').addEventListener('click', renderMyBets);
renderMyBets();
// ---------- Sportsbook-style bet slip dock ----------
let SLIP_PREV_COUNT = 0;
function syncNavHeight(){
  const nav = document.querySelector('.bottom-nav');
  document.documentElement.style.setProperty('--nav-h', (nav ? nav.offsetHeight : 70)+'px');
}
window.addEventListener('resize', syncNavHeight);
function renderSlipDock(){
  syncNavHeight();
  const dock = document.getElementById('slip-dock');
  const n = parlaySlip.length;
  // Highlight every matching odds button
  document.querySelectorAll('.leg-btn').forEach(function(b){
    b.classList.toggle('selected', parlaySlip.some(function(l){ return l.label===b.dataset.leglabel; }));
  });
  if(n===0){ dock.classList.remove('show','open'); document.body.style.paddingBottom=''; SLIP_PREV_COUNT = 0; return; }
  dock.classList.add('show');
  const dec = parlaySlip.reduce(function(a,l){ return a*americanToDecimal(l.odds); }, 1);
  const stake = parseFloat((document.getElementById('slip-dock-stake')||document.getElementById('parlay-stake')).value) || 0;
  document.getElementById('slip-count').textContent = n;
  document.getElementById('slip-bar-label').textContent = n===1 ? 'Straight bet' : n+'-leg parlay';
  document.getElementById('slip-bar-right').textContent = decimalToAmerican(dec)+'  ·  '+(dock.classList.contains('open')?'Hide ▾':'View ▴');
  const sheet = document.getElementById('slip-sheet');
  ALT_ACTIONS = [];
  const rows = parlaySlip.map(function(l,i){
    const hasP = l.probability!==null && l.probability!==undefined;
    const pill = hasP ? '<span class="pill" style="margin-left:0;'+probabilityCategory(l.probability).style+'">'+Math.round(l.probability*100)+'%</span>' : '';
    const canAlt = l.meta && l.meta.type!=='ml';
    const altBtn = canAlt ? ' <button class="secondary" data-dockalt="'+i+'" style="font-size:0.7rem;padding:2px 8px;margin:0 0 0 6px;">'+(l._altOpen?'Hide alt lines':'Alt lines')+'</button>' : '';
    return '<div class="slip-leg" style="flex-wrap:wrap;"><div style="min-width:0;flex:1;"><div style="font-weight:700;">'+l.label+'</div><div class="team-meta">'+pill+altBtn+(l.est?' <span class="team-meta">odds are an estimate &mdash; edit to match your book</span>':'')+'</div></div><div style="white-space:nowrap;display:flex;align-items:center;gap:4px;"><input type="number" data-dockodds="'+i+'" value="'+l.odds+'" style="width:76px;padding:6px 8px;text-align:right;"><button class="slip-x" data-dockrm="'+i+'" aria-label="Remove">✕</button></div>'+(l._altOpen ? '<div style="width:100%;" id="dock-ladder-'+i+'"></div>' : '')+'</div>';
  }).join('');
  const prevStake = document.getElementById('slip-dock-stake') ? document.getElementById('slip-dock-stake').value : document.getElementById('parlay-stake').value;
  sheet.innerHTML = rows
    + '<div style="display:flex;align-items:center;gap:10px;margin-top:10px;"><label style="font-size:0.8rem;color:var(--muted);">Stake $</label><input id="slip-dock-stake" type="number" value="'+prevStake+'" style="max-width:110px;"><div style="margin-left:auto;text-align:right;font-size:0.82rem;">To win <b style="color:#5eead4;">$'+fmt(stake*dec - stake)+'</b></div></div>'
    + '<div style="display:flex;gap:8px;margin-top:10px;"><button id="slip-dock-place" style="flex:1.3;">Place bet</button><button class="secondary" id="slip-dock-analyze" style="flex:1;">Analyze</button><button class="danger" id="slip-dock-clear" style="padding:9px 14px;">Clear</button></div>';
  parlaySlip.forEach(function(l,i){ if(l._altOpen && l.meta) renderAltLadder('dock-ladder-'+i, l.meta, i); });
  sheet.querySelectorAll('[data-dockalt]').forEach(function(b){
    b.addEventListener('click', function(e){ e.stopPropagation(); const l = parlaySlip[Number(b.dataset.dockalt)]; l._altOpen = !l._altOpen; renderSlipDock(); });
  });
  sheet.querySelectorAll('[data-dockodds]').forEach(function(inp){
    inp.addEventListener('change', function(){
      const v = Number(inp.value);
      if(!v || Math.abs(v)<100){ renderSlipDock(); return; }
      const l = parlaySlip[Number(inp.dataset.dockodds)]; l.odds = v; l.est = false; renderParlaySlip();
    });
  });
  document.getElementById('slip-dock-place').addEventListener('click', function(){ placeSlipAsBet(); });
  sheet.querySelectorAll('[data-dockrm]').forEach(function(b){
    b.addEventListener('click', function(e){ e.stopPropagation(); parlaySlip.splice(Number(b.dataset.dockrm),1); renderParlaySlip(); });
  });
  document.getElementById('slip-dock-stake').addEventListener('input', function(){
    document.getElementById('parlay-stake').value = this.value;
    const st = parseFloat(this.value)||0;
    this.parentNode.querySelector('b').textContent = '$'+fmt(st*dec - st);
    renderParlaySlipMain();
  });
  document.getElementById('slip-dock-clear').addEventListener('click', function(){ parlaySlip.length = 0; renderParlaySlip(); });
  document.getElementById('slip-dock-analyze').addEventListener('click', function(){
    dock.classList.remove('open');
    activateTopTab('parlay'); activateSubTab('parlay-calc');
    window.scrollTo({top:0, behavior:'smooth'});
    renderSlipDock();
  });
  document.body.style.paddingBottom = (60 + (dock.offsetHeight||0))+'px';
  if(n>SLIP_PREV_COUNT){ const bar = document.getElementById('slip-bar'); bar.classList.remove('bump'); void bar.offsetWidth; bar.classList.add('bump'); }
  SLIP_PREV_COUNT = n;
}
document.getElementById('slip-bar').addEventListener('click', function(){
  document.getElementById('slip-dock').classList.toggle('open');
  renderSlipDock();
});
window.addEventListener('load', syncNavHeight);
function renderParlaySlip(){
  try{ renderSlipDock(); }catch(e){ console.warn('dock failed', e); }
  renderParlaySlipMain();
}
function renderParlaySlipMain(){
  const slipEl = document.getElementById('parlay-slip');
  const resultEl = document.getElementById('parlay-result');
  if(parlaySlip.length===0){
    slipEl.innerHTML = '<div class="empty">No legs added yet — tap odds above or add a custom one.</div>';
    resultEl.innerHTML = '';
    return;
  }
  slipEl.innerHTML = parlaySlip.map(function(leg,i){
    const hasProb = leg.probability!==null && leg.probability!==undefined;
    const cat = hasProb ? probabilityCategory(leg.probability) : null;
    const probHtml = hasProb
      ? '<span class="pill" style="margin-left:6px;'+cat.style+'">'+Math.round(leg.probability*100)+'% · '+cat.label+'</span>'
      : '<span class="team-meta" style="margin-left:6px;">no model read</span>';
    return '<div class="history-item"><span>'+leg.label+probHtml+'</span><span>'+(leg.odds>0?'+':'')+leg.odds+(leg.est?' <span class="team-meta">est.</span>':'')+' <button class="danger" data-rmleg="'+i+'" style="margin-left:8px;">✕</button></span></div>';
  }).join('');
  slipEl.querySelectorAll('[data-rmleg]').forEach(function(btn){
    btn.addEventListener('click', function(){ parlaySlip.splice(Number(btn.dataset.rmleg), 1); renderParlaySlip(); });
  });
  const stake = parseFloat(document.getElementById('parlay-stake').value) || 0;
  const combinedDecimal = parlaySlip.reduce(function(acc,leg){return acc*americanToDecimal(leg.odds);}, 1);
  const payout = stake * combinedDecimal;
  const profit = payout - stake;
  const legsWithProb = parlaySlip.filter(function(l){ return l.probability!==null && l.probability!==undefined; });
  let combinedProbHtml = '';
  if(legsWithProb.length>0){
    // Independence assumption -- multiplying each leg's own probability
    // is the standard way to combine them, but it's only exactly correct
    // if the legs don't influence each other. Two legs from the SAME
    // game (e.g. a team's spread AND that same game's total) are a real
    // counterexample -- their outcomes are correlated, not independent --
    // so this is a reasonable estimate, not an exact one, and said so
    // plainly rather than implying more precision than it has.
    const combinedProb = legsWithProb.reduce(function(acc,l){ return acc*l.probability; }, 1);
    const cat = probabilityCategory(combinedProb);
    const missingNote = legsWithProb.length<parlaySlip.length ? ' ('+(parlaySlip.length-legsWithProb.length)+' leg(s) with no model read excluded from this estimate)' : '';
    combinedProbHtml = '<div style="text-align:center;margin:10px 0 0;"><span class="pill" style="'+cat.style+'">'+Math.round(combinedProb*100)+'% · '+cat.label+' overall'+'</span></div>'
      + '<div class="note" style="margin-top:6px;">Assumes each leg is independent -- legs from the same game (e.g. a team\'s spread and that game\'s total) aren\'t really independent, so treat this as a reasonable estimate, not an exact one.'+missingNote+'</div>';
  }
  resultEl.innerHTML = '<div class="proj-score" style="padding-top:16px;"><div><div class="num">'+decimalToAmerican(combinedDecimal)+'</div><div class="lbl">combined odds</div></div><div><div class="num">$'+fmt(payout)+'</div><div class="lbl">total payout</div></div><div><div class="num" style="color:#5eead4;">+$'+fmt(profit)+'</div><div class="lbl">profit</div></div></div><div class="note">'+parlaySlip.length+' leg'+(parlaySlip.length===1?'':'s')+' · every leg has to hit for the parlay to pay out.</div>'+combinedProbHtml;
  try{ resultEl.insertAdjacentHTML('beforeend', buildParlayAnalysisHtml()); wireParlayActions(resultEl); }catch(e){ console.warn('parlay analysis failed', e); }
}
document.getElementById('chk-league').addEventListener('change', populateCheckSelects);
document.getElementById('chk-teamA').addEventListener('change', populateCheckSideSelect);
document.getElementById('chk-teamB').addEventListener('change', populateCheckSideSelect);
document.getElementById('chk-type').addEventListener('change', function(){
  const isSpread = this.value==='spread' || this.value==='ml';
  document.getElementById('chk-spread-fields').style.display = isSpread ? '' : 'none';
  document.getElementById('chk-total-fields').style.display = isSpread ? 'none' : '';
  const lineField = document.getElementById('chk-line').closest('.field');
  if(lineField) lineField.style.display = this.value==='ml' ? 'none' : '';
});
document.getElementById('chk-check-btn').addEventListener('click', function(){
  const league = document.getElementById('chk-league').value;
  const nameA = document.getElementById('chk-teamA').value;
  const nameB = document.getElementById('chk-teamB').value;
  const resultEl = document.getElementById('chk-result');
  if(!nameA || !nameB || nameA===nameB){ resultEl.innerHTML = '<div class="empty">Pick two different teams first.</div>'; return; }
  const chkMarket = findMarketLine(nameA, nameB);
  const proj = computeProjection(nameA, nameB, league, chkMarket && chkMarket.date);
  if(!proj){ resultEl.innerHTML = '<div class="empty">Missing stats for one of those teams.</div>'; return; }
  const betType = document.getElementById('chk-type').value;
  let signedEdge, label, isFavorite, oddsGuess=-110;
  if(betType==='spread'){
    const rawLine = parseFloat(document.getElementById('chk-line').value);
    if(isNaN(rawLine)){ resultEl.innerHTML = '<div class="empty">Enter a line, e.g. -6.5 or +3.5.</div>'; return; }
    const side = document.getElementById('chk-side').value; // 'A' or 'B'
    const sideName = side==='A' ? nameA : nameB;
    // proj.spread convention: positive = nameA favored. Convert the typed
    // line (as the USER'S chosen side would see it on a real book) into
    // that same "positive = A favored" convention to diff against.
    //
    // BUG FIX, confirmed live: this used to take Math.abs() of this
    // difference immediately, which throws away the sign -- and
    // confirmed, checking the same side at +4.5 vs +5.5 (a strictly more
    // favorable line) produced a LOWER probability, not higher, because
    // the absolute distance to the model's point estimate happened to
    // shrink as the line moved past it. Keeping the sign here and only
    // taking the magnitude at the very end (after picking which side of
    // it wins) keeps this monotonic in the line, the way it always should
    // have been -- more points for the same side can only ever raise the
    // probability, never lower it.
    const lineAsAFavored = side==='A' ? -rawLine : rawLine;
    // BUG FIX, confirmed live: Bears vs Bills, checking EITHER team at
    // -0.5 both came back under 50% -- impossible, since one of them has
    // to be the more likely winner. Root cause: a bet on side B needs the
    // OPPOSITE condition on A's margin that a bet on side A does (A's
    // margin needs to be ABOVE a threshold for an A-side bet to hit, but
    // BELOW that same threshold for a B-side bet to hit) -- computing
    // proj.spread minus the line the same way for both sides silently
    // used A's winning condition even when checking B. Flipping the sign
    // specifically for side B corrects this.
    const rawSignedEdge = proj.spread - lineAsAFavored;
    signedEdge = side==='A' ? rawSignedEdge : -rawSignedEdge;
    isFavorite = rawLine<0;
    label = sideName+' '+(rawLine>0?'+':'')+rawLine;
  } else if(betType==='ml'){
    const mSide = document.getElementById('chk-side').value;
    const mName = mSide==='A' ? nameA : nameB;
    const mRaw = proj.spread; // positive = A favored
    signedEdge = mSide==='A' ? mRaw : -mRaw;
    isFavorite = signedEdge>0;
    label = mName+' ML';
    if(chkMarket){
      const mIsEntryA = teamNamesMatch(chkMarket.aTeam, mName);
      const mlOdds = mIsEntryA ? chkMarket.aML : chkMarket.bML;
      if(mlOdds!==null && mlOdds!==undefined) oddsGuess = mlOdds;
    }
  } else {
    const totalLine = parseFloat(document.getElementById('chk-total-line').value);
    if(isNaN(totalLine)){ resultEl.innerHTML = '<div class="empty">Enter a total line, e.g. 47.5.</div>'; return; }
    const direction = document.getElementById('chk-direction').value;
    const rawTotalEdge = proj.total - totalLine; // positive = model leans over
    isFavorite = false;
    label = (direction==='over'?'Over':'Under')+' '+totalLine;
    // Same signed convention as spread above: positive signedEdge always
    // means "this chosen side," negative always means "the other side,"
    // regardless of over/under -- so the SAME inversion logic below
    // handles both bet types identically instead of needing special-cased
    // total-only handling.
    signedEdge = direction==='over' ? rawTotalEdge : -rawTotalEdge;
  }
  let chkMeta;
  if(betType==='ml'){
    const mS = document.getElementById('chk-side').value;
    chkMeta = {league: league, type:'ml', team: mS==='A'?nameA:nameB, opp: mS==='A'?nameB:nameA, line: 0};
  } else if(betType==='spread'){
    const cSide = document.getElementById('chk-side').value;
    chkMeta = {league: league, type:'spread', team: cSide==='A'?nameA:nameB, opp: cSide==='A'?nameB:nameA, line: parseFloat(document.getElementById('chk-line').value)};
  } else {
    chkMeta = {league: league, type:'total', dir: document.getElementById('chk-direction').value, team: nameA, opp: nameB, line: parseFloat(document.getElementById('chk-total-line').value)};
  }
  const finalProb = chkMeta.type==='ml' ? mlWinProb(league, signedEdge, marketMarginFor(chkMeta.team, chkMeta.opp)) : signedBetProbability(signedEdge, proj.usedSP, league);
  const cat = probabilityCategory(finalProb);
  resultEl.innerHTML = '<div class="proj-score" style="padding-top:12px;"><div><div class="num">'+Math.round(finalProb*100)+'%</div><div class="lbl">estimated likelihood</div></div></div>'
    + '<div style="text-align:center;margin:6px 0 10px;"><span class="pill" style="'+cat.style+'">'+cat.label+'</span></div>'
    + '<div class="note" style="margin-top:0;">'+label+' · '+nameA+' vs '+nameB+' · calibrated estimate, consistent across lines'+'</div>'
    + '<button class="secondary" id="chk-add-btn" style="margin-top:8px;">Add to slip</button>'
    + (chkMeta.type!=='ml' ? '<div style="font-weight:700;font-size:0.86rem;margin-top:14px;">Alt lines <span class="team-meta" style="font-weight:400;">tap one to add it to your slip</span></div><div id="chk-ladder"></div>' : '');
  const chkEst = betType!=='ml' ? estAltOdds(chkMeta) : null;
  const chkOdds = (betType!=='ml' && chkEst!==null) ? chkEst : oddsGuess;
  document.getElementById('chk-add-btn').addEventListener('click', function(){
    addLeg(label+' ('+nameA+' vs '+nameB+')', chkOdds, finalProb, chkMeta, betType!=='ml');
  });
  if(chkMeta.type!=='ml') renderAltLadder('chk-ladder', chkMeta, null);
});
document.getElementById('add-custom-leg').addEventListener('click', ()=>{
  const label = document.getElementById('cl-label').value.trim();
  const odds = document.getElementById('cl-odds').value;
  if(!label || !odds){ alert('Enter a description and odds'); return; }
  addLeg(label, odds);
  document.getElementById('cl-label').value = '';
  document.getElementById('cl-odds').value = '';
});
document.getElementById('parlay-stake').addEventListener('input', renderParlaySlip);
document.getElementById('copy-slip-btn').addEventListener('click', function(){
  if(parlaySlip.length===0){ alert('Your slip is empty.'); return; }
  const stake = parseFloat(document.getElementById('parlay-stake').value) || 0;
  const combinedDecimal = parlaySlip.reduce(function(acc,leg){return acc*americanToDecimal(leg.odds);}, 1);
  const payout = stake * combinedDecimal;
  let text = 'Parlay (' + parlaySlip.length + ' legs):\n';
  parlaySlip.forEach(function(leg){ text += '- ' + leg.label + ' (' + (leg.odds>0?'+':'') + leg.odds + ')\n'; });
  text += 'Combined odds: ' + decimalToAmerican(combinedDecimal) + '\n';
  text += 'Stake: $' + fmt(stake) + ' -> Payout: $' + fmt(payout);
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(text).then(function(){ alert('Slip copied to clipboard.'); }).catch(function(){ prompt('Copy this:', text); });
  } else {
    prompt('Copy this:', text);
  }
});

// ---- Home page ----
const ICON_CALENDAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
const ICON_TARGET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/></svg>';
const ICON_CHART = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>';
const ICON_HEALTH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>';
const ICON_CALC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="11" x2="8" y2="11.01"/><line x1="12" y1="11" x2="12" y2="11.01"/><line x1="16" y1="11" x2="16" y2="11.01"/><line x1="8" y1="15" x2="8" y2="15.01"/><line x1="12" y1="15" x2="12" y2="15.01"/><line x1="16" y1="15" x2="16" y2="15.01"/></svg>';

function renderHome(){
  const container = document.getElementById('home-content');
  if(!container) return;
  let topPick = null;
  try{
    const nflBets = computeTopBets(NFL_WEEK_GAMES, 'NFL');
    const cfbBets = computeTopBets(CFB_WEEK_GAMES, 'CFB');
    const allBets = nflBets.concat(cfbBets).sort(function(a,b){ return b.edge-a.edge; });
    topPick = allBets[0] || null;
  }catch(e){}

  let heroHtml = '<div class="home-hero"><div class="home-hero-label">This week\'s top pick</div>';
  if(topPick){
    heroHtml += '<div class="home-hero-title">'+topPick.label+'</div><div class="team-meta">'+topPick.sub+'</div><div style="margin-top:8px;"><span class="pill" style="background:rgba(240,185,61,0.18);">'+topPick.tier.label+'</span> <span class="pill">edge '+fmt(topPick.edge)+'</span></div>';
  } else {
    heroHtml += '<div class="home-hero-title">Loading this week\'s picks...</div><div class="note" style="margin-top:2px;">Check back once team stats and odds have loaded.</div>';
  }
  heroHtml += '</div>';

  const cards = [
    { icon: ICON_CALENDAR, title:'NFL This Week', sub: (NFL_WEEK_GAMES||[]).length+' games', tab:'nfl', sub_:'nfl-week' },
    { icon: ICON_CALENDAR, title:'CFB This Week', sub: (CFB_WEEK_GAMES||[]).length+' ranked matchups', tab:'cfb', sub_:'cfb-week' },
    { icon: ICON_TARGET, title:'Top Bets', sub: 'Model vs. market, every game', tab:'topbets', sub_:null },
    { icon: ICON_CHART, title:'Track Record', sub: 'Weekly + all-time accuracy', tab:'track', sub_:null },
    { icon: ICON_HEALTH, title:'Injury Report', sub: 'NFL questionable/doubtful/out', tab:'nfl', sub_:'nfl-injuries' },
    { icon: ICON_CALC, title:'Parlay Calculator', sub: 'Build and price your own slip', tab:'parlay', sub_:'parlay-calc' },
  ];
  const gridHtml = '<div class="home-grid">'+cards.map(function(c,i){
    return '<div class="home-card" data-home-card="'+i+'"><div class="home-card-icon">'+c.icon+'</div><div class="home-card-title">'+c.title+'</div><div class="home-card-sub">'+c.sub+'</div></div>';
  }).join('')+'</div>';
  const brandHtml = '<div class="home-brand"><div class="home-brand-badge">MG</div><div class="home-brand-title">MG Analytics</div><div class="home-brand-tag">Real stats, real odds, no guesswork.</div></div>';

  container.innerHTML = heroHtml + gridHtml + brandHtml;
  container.querySelectorAll('[data-home-card]').forEach(function(el){
    el.addEventListener('click', function(){
      const c = cards[Number(el.dataset.homeCard)];
      activateTopTab(c.tab);
      if(c.sub_) activateSubTab(c.sub_);
    });
  });
}

// ---- Global search ----
function performGlobalSearch(query){
  const q = query.trim().toLowerCase();
  if(q.length < 2) return [];
  const results = [];
  Object.keys(teamsCache).forEach(function(name){
    if(name.toLowerCase().indexOf(q)!==-1){
      const t = teamsCache[name];
      results.push({ type:'team', league:t.league, name:name, meta:t.league+(t.conf?' · '+t.conf:'')+(t.record?' · '+t.record:'') });
    }
  });
  Object.keys(playersCache).forEach(function(name){
    if(name.toLowerCase().indexOf(q)!==-1){
      const p = playersCache[name];
      results.push({ type:'player', league:p.league, name:name, meta:p.league+' · '+p.pos+(p.team?' · '+p.team:'') });
    }
  });
  return results.slice(0, 20);
}
function goToSearchResult(r){
  const lg = r.league.toLowerCase();
  const resultsEl = document.getElementById('global-search-results');
  if(resultsEl) resultsEl.classList.remove('open');
  const inputEl = document.getElementById('global-search');
  if(inputEl) inputEl.value = '';
  activateTopTab(lg);
  if(r.type==='team'){
    activateSubTab(lg+'-teams');
    renderTeamDetail(lg, r.name);
    const detailEl = document.getElementById(lg+'-team-detail');
    if(detailEl) detailEl.scrollIntoView({behavior:'smooth', block:'start'});
  } else {
    activateSubTab(lg+'-players');
    renderPlayerDetail(lg, r.name);
    const detailEl = document.getElementById(lg+'-player-detail');
    if(detailEl) detailEl.scrollIntoView({behavior:'smooth', block:'start'});
  }
}
function renderSearchResults(results){
  const el = document.getElementById('global-search-results');
  if(!el) return;
  if(results.length===0){ el.classList.remove('open'); el.innerHTML=''; return; }
  el.innerHTML = results.map(function(r,i){
    return '<div class="search-result-row" data-result-idx="'+i+'"><div><div class="search-result-name">'+r.name+'</div><div class="search-result-meta">'+r.meta+'</div></div><span class="pill">'+(r.type==='team'?'Team':'Player')+'</span></div>';
  }).join('');
  el.classList.add('open');
  el.querySelectorAll('[data-result-idx]').forEach(function(row){
    row.addEventListener('click', function(){ goToSearchResult(results[Number(row.dataset.resultIdx)]); });
  });
}
const globalSearchInput = document.getElementById('global-search');
if(globalSearchInput){
  globalSearchInput.addEventListener('input', function(){ renderSearchResults(performGlobalSearch(this.value)); });
  document.addEventListener('click', function(e){
    const wrap = document.querySelector('.search-wrap');
    if(wrap && !wrap.contains(e.target)){
      const el = document.getElementById('global-search-results');
      if(el) el.classList.remove('open');
    }
  });
}

(async function init(){
  try{ MODEL_CALIBRATION = await fetchJSON('./data/calibration.json'); }catch(e){ MODEL_CALIBRATION = null; }
  try{ MODEL_WEIGHTS = await fetchJSON('./data/model_weights.json'); }catch(e){ MODEL_WEIGHTS = null; }
  try{
    const injData = await fetchJSON('./data/nfl-injuries.json');
    INJURIES_CACHE = {};
    (injData.entries||[]).forEach(function(e){ (INJURIES_CACHE[e.team] = INJURIES_CACHE[e.team]||[]).push(e); });
  }catch(e){ INJURIES_CACHE = {}; }
  try{ WEATHER_CACHE = await fetchJSON('./data/weather.json'); }catch(e){ WEATHER_CACHE = {}; }
  try{ const trData = await fetchJSON('./data/track-record.json'); TRACK_RECORD_PICKS = trData.picks || []; }catch(e){ TRACK_RECORD_PICKS = []; }
  try{ PLAYER_PROPS_ODDS = await fetchJSON('./data/player-props-odds.json'); }catch(e){ PLAYER_PROPS_ODDS = {}; }
  const calNote = document.getElementById('calibration-note');
  if(calNote && MODEL_CALIBRATION){
    const parts = ['NFL','CFB'].map(function(lg){
      const c = MODEL_CALIBRATION[lg];
      if(!c) return null;
      return c.calibrated
        ? lg+': calibrated from '+c.sample_size+' graded picks (hit rate '+Math.round(c.hit_rate*100)+'%) — Strong at edge '+c.strong_threshold+', Moderate at '+c.moderate_threshold
        : lg+': still the original fixed 7 / 3.5 — only '+c.sample_size+' of '+c.min_sample_size+' graded picks needed exist so far';
    }).filter(Boolean);
    calNote.textContent = parts.join('. ')+ (parts.length ? '.' : '');
  }
  const learnedNote = document.getElementById('learned-model-note');
  if(learnedNote && MODEL_WEIGHTS){
    learnedNote.textContent = MODEL_WEIGHTS.trained
      ? 'A learned model (trained on '+MODEL_WEIGHTS.sample_size+' real graded picks) is now also filtering Top Bets -- a pick clearing the edge threshold but predicted below a 55% hit probability gets held back. Training accuracy '+Math.round(MODEL_WEIGHTS.train_accuracy*100)+'% (on the data it was trained on, not a held-out test -- take that number with real caution at this sample size).'
      : 'Real learned model: not active yet -- only '+MODEL_WEIGHTS.sample_size+' of the '+MODEL_WEIGHTS.min_sample_size+' graded team bets needed exist so far. Falls back to the calibrated thresholds above until then.';
  }
  try{ await ensureSeeded(); }catch(e){ teamsCache = Object.assign({}, NFL_SEED, CFB_SEED); }
  await renderSchedule();
  await renderCfbSchedule();
  renderRankings();
  try{ await renderInjuries(); }catch(e){}
  await renderOddsBoard();
  renderParlaySlip();
  try{ refreshTeamLists(); }catch(e){ populateSelects(); }
  try{ await ensurePlayersSeeded(); }catch(e){ playersCache = JSON.parse(JSON.stringify(PLAYERS_SEED)); }
  try{ refreshPlayersLists(); }catch(e){ populatePlayerSelects(); }
  try{ await renderTopBets(); }catch(e){}
  try{ await renderTrackRecord(); }catch(e){}
  try{ renderHome(); }catch(e){}
})();