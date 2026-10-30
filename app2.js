function edgeRow(label, aVal, bVal, higherIsBetterForA){
  if(higherIsBetterForA===undefined) higherIsBetterForA = true;
  const aWins = higherIsBetterForA ? aVal>bVal : aVal<bVal;
  return '<div class="edge-row"><div class="edge-val '+(aWins?'win':'lose')+'">'+fmt(aVal)+'</div><div class="edge-label">'+label+'</div><div class="edge-val '+(!aWins?'win':'lose')+'">'+fmt(bVal)+'</div></div>';
}

// Shared projection model, used by both the Matchup tab and Top Bets so
// they can never drift out of sync with each other. Convention: nameB is
// treated as the home team -- this matches how schedule games are always
// built (a = away, b = home) and how the click-through flow uses it.
// Beyond the original offense-vs-defense yardage averaging, this adds:
//  - Home-field advantage (a flat points bump to the home side)
//  - Turnover margin, applied as an actual point adjustment rather than
//    just displayed as a reference stat
//  - For CFB, a blend with CFBD's SP+ rating when available on both teams
//    -- SP+ is opponent-adjusted (accounts for strength of schedule),
//    which raw box-score yards/points don't, so blending it in should
//    meaningfully help accuracy, especially early season.
const HOME_ADV = {NFL: 2.0, CFB: 2.5};
const TO_FACTOR = 1.5; // points per turnover-margin-per-game
const SHRINK_PRIOR_GAMES = 3; // "pseudo-games" of prior weight blended into small samples
// A team's ppg/pa/turnover-margin from just 1-2 games is an extreme-outlier-
// prone sample -- confirmed live: an NFL team's turnover margin input was
// literally just their single Week 1 game's result (+/-3.0, the single most
// extreme value across the whole league), with nothing to smooth it, and no
// opponent-adjusted rating exists for NFL the way SP+ does for CFB to help
// correct it. This blends a raw stat toward a PRIOR, weighted by how many
// real games the current-season number is actually built from -- 1 game
// gets pulled hard toward the prior, 8+ games are barely touched.
//
// PRIOR CHOICE, confirmed live this matters a lot: a flat LEAGUE AVERAGE
// was the only prior available at first, which meant a team with a real,
// multi-year track record of being bad (or good) got treated as a
// coin-flip-average team for the first few weeks of every new season --
// e.g. Bills vs Jets projecting near a pick'em when a real opening market
// line had Bills favored by 9.5. Falls back to league average only when a
// team has no previous-season data at all (fetch_nfl.py/fetch_cfb.py
// couldn't find a prior year, e.g. a new/relocated team) -- not a claim
// that a team can't improve or decline between seasons, just a more
// informed starting point than "assume average" for the early weeks
// before this season's own sample size takes over.
function shrinkStat(rawStat, teamPrior, leagueAvg, gamesPlayed){
  const prior = (teamPrior!==null && teamPrior!==undefined) ? teamPrior : leagueAvg;
  if(!gamesPlayed || gamesPlayed<=0 || prior===null || prior===undefined) return rawStat;
  return (rawStat*gamesPlayed + prior*SHRINK_PRIOR_GAMES) / (gamesPlayed + SHRINK_PRIOR_GAMES);
}
// Nested shrinkage for home/away splits, confirmed live this was a real
// gap: every team previously got one blended ppg/pa average regardless of
// venue, plus the same flat HOME_ADV constant applied to every team
// equally, with no way to reflect a team that's genuinely stronger at
// home (or on the road) than average. venueGames is naturally small
// (often 1-2 games apiece, even deep into a season) -- shrinking the
// venue-specific number toward the ALREADY-shrunk season-wide number
// (rather than toward a flat league average directly) keeps this
// properly conservative: a team's one road game so far gets pulled hard
// toward their overall (already prior-blended) level, not treated as a
// reliable "this is their road identity" signal on its own.
function venueAdjustedStat(venueStat, venueGames, seasonShrunkStat){
  if(venueStat===null || venueStat===undefined || !venueGames) return seasonShrunkStat;
  return (venueStat*venueGames + seasonShrunkStat*SHRINK_PRIOR_GAMES) / (venueGames + SHRINK_PRIOR_GAMES);
}
function computeProjection(nameA, nameB, league, gameDate){
  const A = teamsCache[nameA], B = teamsCache[nameB];
  if(!A || !B) return null;
  const aPassOffS = shrunkTeamStat(A, 'passOff', league), aRushOffS = shrunkTeamStat(A, 'rushOff', league);
  const aPassDefS = shrunkTeamStat(A, 'passDef', league), aRushDefS = shrunkTeamStat(A, 'rushDef', league);
  const bPassOffS = shrunkTeamStat(B, 'passOff', league), bRushOffS = shrunkTeamStat(B, 'rushOff', league);
  const bPassDefS = shrunkTeamStat(B, 'passDef', league), bRushDefS = shrunkTeamStat(B, 'rushDef', league);
  const aPassProj = (aPassOffS + bPassDefS)/2;
  const bPassProj = (bPassOffS + aPassDefS)/2;
  const aRushProj = (aRushOffS + bRushDefS)/2;
  const bRushProj = (bRushOffS + aRushDefS)/2;

  const aGamesPlayed = (A.games && A.games.length) || 0;
  const bGamesPlayed = (B.games && B.games.length) || 0;
  const leagueAvgPpg = leagueAvgDefStat(league, 'ppg');
  const leagueAvgPa = leagueAvgDefStat(league, 'pa');
  const leagueAvgTo = leagueAvgDefStat(league, 'to');
  // A is treated as the away team, B as home -- same convention this
  // whole app already uses for HOME_ADV below, so away-specific stats
  // apply to A and home-specific stats to B.
  const aPpgSeason = shrinkStat(A.ppg, A.prevPpg, leagueAvgPpg, aGamesPlayed);
  const aPaSeason = shrinkStat(A.pa, A.prevPa, leagueAvgPa, aGamesPlayed);
  const aTo = shrinkStat(A.to||0, A.prevTo, leagueAvgTo, aGamesPlayed);
  const bPpgSeason = shrinkStat(B.ppg, B.prevPpg, leagueAvgPpg, bGamesPlayed);
  const bPaSeason = shrinkStat(B.pa, B.prevPa, leagueAvgPa, bGamesPlayed);
  const bTo = shrinkStat(B.to||0, B.prevTo, leagueAvgTo, bGamesPlayed);
  const aPpg = venueAdjustedStat(A.awayPpg, A.awayGames, aPpgSeason);
  const aPa = venueAdjustedStat(A.awayPa, A.awayGames, aPaSeason);
  const bPpg = venueAdjustedStat(B.homePpg, B.homeGames, bPpgSeason);
  const bPa = venueAdjustedStat(B.homePa, B.homeGames, bPaSeason);

  const aQbFlag = detectBackupQB(nameA, league);
  const bQbFlag = detectBackupQB(nameB, league);
  const aRestAdj = restAdjustment(A, gameDate);
  const bRestAdj = restAdjustment(B, gameDate);
  const aPpgAdj = (aQbFlag ? aPpg - BACKUP_QB_PENALTY : aPpg) + aRestAdj;
  const bPpgAdj = (bQbFlag ? bPpg - BACKUP_QB_PENALTY : bPpg) + bRestAdj;

  const homeAdv = HOME_ADV[league] || 2.0;
  let aScoreBox = (aPpgAdj + bPa)/2 - homeAdv/2 + aTo*TO_FACTOR;
  let bScoreBox = (bPpgAdj + aPa)/2 + homeAdv/2 + bTo*TO_FACTOR;
  let total = aScoreBox + bScoreBox;
  let spread = aScoreBox - bScoreBox; // positive = A favored
  let usedSP = false;
  let marketAnchored = false;

  if(league==='CFB' && typeof A.spPlus==='number' && typeof B.spPlus==='number'){
    // SP+ is opponent-adjusted (accounts for who a team has actually played);
    // raw box-score ppg/pa isn't, and is a single-digit-game sample this
    // early in the season -- confirmed live: a team that put up 80 points
    // in one blowout had their box-score offense look elite even though
    // that same game barely moved their (much more trustworthy) SP+
    // rating. A 50/50 blend let that one extreme box-score outlier drag a
    // good, opponent-adjusted signal down to a near-toss-up projection for
    // a game that was really a ~30-point mismatch. SP+ exists specifically
    // to correct for this, so it's weighted well above box-score-only here
    // rather than split evenly with it.
    const spSpread = (A.spPlus - B.spPlus) - homeAdv; // SP+ is neutral-field; apply home adv when converting to a game line
    spread = spread*0.25 + spSpread*0.75;
    usedSP = true;
  } else if(league==='CFB' && A.division && B.division && A.division!==B.division && findMarketLine(nameA, nameB) && findMarketLine(nameA, nameB).aSpread!=null){
    // FBS vs FCS, and a real market line exists for this specific game:
    // box-score averaging has no way to know the talent gap -- each team's
    // stats only reflect their own division's competition level.
    // Confirmed live against a real matchup: box-score-only math said
    // "Louisville by 1.5" while the real market had Louisville favored by
    // 36.5 -- a 35-point error, not early-season noise but a structural
    // blind spot. SP+ can't rescue this either, since FCS teams never get
    // an SP+ rating. When a real market line exists for this exact game,
    // it's prioritized over SRS below -- live bookmaker consensus reflects
    // more current information (injuries, current form, etc.) than any
    // season-long rating can, so lean heavily on it, with a small
    // remaining weight for our own box-score read.
    const market = findMarketLine(nameA, nameB);
    const aIsEntryA = teamNamesMatch(market.aTeam, nameA);
    const marketFavA = aIsEntryA ? -market.aSpread : market.aSpread;
    spread = spread*0.25 + marketFavA*0.75;
    marketAnchored = true;
  } else if(league==='CFB' && typeof A.srs==='number' && typeof B.srs==='number'){
    // Neither SP+ nor a usable market line was available for this game --
    // confirmed live: Indiana (ranked, has SP+) vs. Howard (FCS, no SP+,
    // and no market line loaded for this specific game) fell through both
    // safeguards above, landing on raw box-score-only math for a game that
    // should've been a blowout. SRS (CFBD's simpler, schedule-adjusted
    // scoring-margin rating) covers FCS teams too, unlike SP+, so it fills
    // exactly this gap. Trusted a bit less than SP+ (SRS is a simpler
    // methodology) but still far more than an unprotected box score.
    const srsSpread = (A.srs - B.srs) - homeAdv; // SRS is also neutral-field
    spread = spread*0.3 + srsSpread*0.7;
    usedSP = true; // treated the same as SP+ for confidence-tier purposes -- both are real opponent-adjusted signals
  }

  const weatherAdj = weatherAdjustment(nameB, league); // B is the home team, see HOME_ADV convention above -- the game is played at B's stadium
  total += weatherAdj;

  const aScore = Math.round((total + spread)/2);
  const bScore = Math.round((total - spread)/2);
  return {
    // total/spread are the UNROUNDED model numbers (1 decimal), not aScore-bScore: those
    // are whole-number scores, so a true 3.4-point margin used to read as exactly 3 and
    // a market line of -3 gave a 0.0 edge that picked the wrong side at random.
    aScore, bScore, total: Math.round(total*10)/10, spread: Math.round(spread*10)/10,
    aPassProj, bPassProj, aRushProj, bRushProj, usedSP, marketAnchored,
    aQbFlag, bQbFlag, aRestAdj, bRestAdj, weatherAdj,
  };
}

// ---- Per-game "top bets" shown when a specific matchup is opened (from
// This Week or Matchup tab) -- reuses the exact same team-bet model as the
// global Top Bets list and the exact same player-matchup logic as Player
// Props, just scoped to the two teams in this one game instead of ranking
// across the whole week's slate.
function computeGameBets(nameA, nameB){
  const league = (teamsCache[nameA] || teamsCache[nameB] || {}).league;
  const teamBets = [];
  const proj = projectMatchup(nameA, nameB);
  const market = findMarketLine(nameA, nameB);
  if(proj && market){
    const aIsEntryA = teamNamesMatch(market.aTeam, nameA);
    const marketFavA = (market.aSpread===null || market.aSpread===undefined) ? null : (aIsEntryA ? -market.aSpread : market.aSpread);
    if(marketFavA!==null){
      const spreadEdge = proj.spread - marketFavA;
      if(Math.abs(spreadEdge)>=MIN_BET_EDGE){
      const favoredTeam = spreadEdge>0 ? nameA : nameB;
      const favoredLine = aIsEntryA ? (spreadEdge>0 ? market.aSpread : market.bSpread) : (spreadEdge>0 ? market.bSpread : market.aSpread);
      teamBets.push({
        label: favoredTeam+' '+(favoredLine>0?'+':'')+favoredLine,
        edge: Math.abs(spreadEdge),
        tier: confidenceTier(Math.abs(spreadEdge), proj.usedSP, league),
        sub: 'model has it '+(proj.spread>0?nameA:nameB)+' by '+Math.abs(tieSafeLine(proj.spread))
      });
      }
    }
    if(market.total!==null && market.total!==undefined){
      const totalEdge = proj.total - market.total;
      if(Math.abs(totalEdge)>=MIN_BET_EDGE) teamBets.push({
        label: (totalEdge>0?'Over':'Under')+' '+market.total,
        edge: Math.abs(totalEdge),
        tier: confidenceTier(Math.abs(totalEdge), proj.usedSP, league),
        sub: 'model projects '+tieSafeLine(proj.total)+' total points'
      });
    }
  }
  teamBets.sort(function(a,b){ return b.edge - a.edge; });

  const playerBets = [];
  [[nameA,nameB],[nameB,nameA]].forEach(function(pair){
    const teamName = pair[0], oppName = pair[1];
    Object.keys(playersCache).forEach(function(pname){
      const p = playersCache[pname];
      if(!p || p.league!==league) return;
      if(!p.team || !teamNamesMatch(p.team, teamName)) return;
      if(league==='NFL' && p.team && p.teamYear==null) return; // not on a confirmed current roster
      const games = p.games || [];
      if(games.length===0) return;
      if(games.length<2) return; // a single game is too thin a sample to recommend a bet on -- see computeTopPlayerBets for the full reasoning
      let mainStat = 'passYds';
      if(p.pos==='RB') mainStat='rushYds';
      if(p.pos==='WR'||p.pos==='TE') mainStat='recYds';
      const defKey = defCategoryForStat(mainStat);
      if(!defKey || !teamsCache[oppName] || !teamsCache[oppName][defKey]) return;
      const avgVal = leagueAvgDefStat(league, defKey);
      if(!avgVal) return;
      const last5 = games.slice(-5);
      const l5avg = median(last5.map(function(g){ return g[mainStat]||0; }));
      if(!meetsVolumeThreshold(mainStat, l5avg)) return; // filters out fullbacks/deep bench players with a token stat line
      const ratio = clampDefenseRatio(shrunkTeamStat(teamsCache[oppName], defKey, league) / avgVal);
      const modelProjection = roundToHalf(l5avg * ratio); // simple matchup-adjusted projection -- see note in renderGameBets
      const realProp = getRealPropLine(pname, mainStat);
      const projected = realProp ? realProp.line : modelProjection;
      const direction = realProp ? (modelProjection > realProp.line ? 'over' : 'under') : (ratio>=1 ? 'favorable' : 'tough');
      playerBets.push({ name: pname, pos: p.pos, team: teamName, opp: oppName, ratio, l5avg, projected, modelProjection, statLabel: statLabel(mainStat), direction, usedRealLine: !!realProp, _recencyKey: mostRecentGameKey(p) });
    });
  });
  const dedupedPlayerBets = capPlayersPerTeamByPosition(playerBets);
  dedupedPlayerBets.sort(function(a,b){ return Math.abs(b.ratio-1) - Math.abs(a.ratio-1); });

  const teamSlice = teamBets.slice(0, 5);
  const playerSlice = dedupedPlayerBets.slice(0, Math.max(0, 5 - teamSlice.length));
  return { teamBets: teamSlice, playerBets: playerSlice };
}
function renderGameBets(nameA, nameB){
  const { teamBets, playerBets } = computeGameBets(nameA, nameB);
  if(teamBets.length===0 && playerBets.length===0){
    return '<div class="card"><h2>Top bets for this game</h2><div class="empty">Not enough data loaded yet — needs team stats plus a market line and/or player game logs for these two teams.</div></div>';
  }
  let rows = '';
  teamBets.forEach(function(b,i){
    rows += '<div class="team-row"><div><div class="team-name">'+(i+1)+'. '+b.label+' <span class="pill" style="background:rgba(240,185,61,0.15);">'+b.tier.label+'</span></div><div class="team-meta">'+b.sub+'</div></div><div class="pill">edge '+fmt(b.edge)+'</div></div>';
  });
  playerBets.forEach(function(b,i){
    const idx = teamBets.length + i + 1;
    const pct = Math.round((b.ratio-1)*100);
    const dirLabel = (b.direction==='favorable' ? 'Over ' : 'Under ')+b.statLabel+' · '+(b.direction==='favorable' ? '+'+pct+'% easier than average' : pct+'% tougher than average');
    const cls = b.direction==='favorable' ? 'over' : 'under';
    rows += '<div class="team-row"><div><div class="team-name">'+idx+'. '+b.name+' <span class="pill">'+b.pos+'</span></div><div class="team-meta">'+b.team+' vs '+b.opp+' · L5 avg '+fmt(b.l5avg)+' '+b.statLabel+' · <b>projected '+fmt(b.projected)+'</b></div></div><div class="glog-val '+cls+'">'+dirLabel+'</div></div>';
  });
  return '<div class="card"><h2>Top bets for this game</h2>'+rows+'<div class="note">Team rows compare the model\'s projection to the market line, same math as the main Top Bets tab. Player rows show the best matchup mismatches for either team\'s roster this game — "projected" is each player\'s last-5-game average scaled by how this opponent\'s defense compares to league average, a simple heuristic (not a sportsbook line) meant to give you a number to weigh your own line against.</div></div>';
}

// A completed game shouldn't show a hypothetical projection as if it were
// still upcoming -- this looks up the real result from this week's
// schedule data (now carries awayScore/homeScore once nflverse/CFBD report
// them) so runMatchupFor can show what actually happened instead.
function findFinalScoreForMatchup(league, nameA, nameB){
  const games = league==='NFL' ? NFL_WEEK_GAMES : CFB_WEEK_GAMES;
  const na = normalizeTeamName(nameA), nb = normalizeTeamName(nameB);
  for(const g of (games||[])){
    const ga = normalizeTeamName(g.a), gb = normalizeTeamName(g.b);
    const matches = (ga===na && gb===nb) || (ga===nb && gb===na);
    if(matches && g.awayScore!=null && g.homeScore!=null){
      return { away: g.a, home: g.b, awayScore: g.awayScore, homeScore: g.homeScore };
    }
  }
  return null;
}
function runMatchupFor(nameA, nameB, outId){
  const out = document.getElementById(outId);
  if(!nameA || !nameB || !teamsCache[nameA] || !teamsCache[nameB] || nameA===nameB){
    out.innerHTML = '<div class="card"><div class="empty">Both teams need stats saved first — add them in Teams.</div></div>';
    return;
  }
  const league = teamsCache[nameA].league;
  const lg = league.toLowerCase();
  const backBtnId = 'mu-back-'+lg;
  const backBtnHtml = '<button class="secondary" id="'+backBtnId+'" style="margin-bottom:10px;">&larr; Back to This Week</button>';
  function wireBackButton(){
    const btn = document.getElementById(backBtnId);
    if(btn) btn.addEventListener('click', function(){ activateSubTab(lg+'-week'); window.scrollTo({top:0, behavior:'smooth'}); });
  }
  const muMarket = findMarketLine(nameA, nameB);
  const proj = computeProjection(nameA, nameB, league, muMarket && muMarket.date);
  const A = teamsCache[nameA], B = teamsCache[nameB];

  const finalResult = findFinalScoreForMatchup(league, nameA, nameB);
  if(finalResult){
    const aScore = finalResult.away===nameA ? finalResult.awayScore : finalResult.homeScore;
    const bScore = finalResult.away===nameA ? finalResult.homeScore : finalResult.awayScore;
    out.innerHTML = backBtnHtml + '<div class="card"><h2>'+nameA+' vs '+nameB+' <span class="pill" style="background:rgba(51,211,153,0.18);color:#5eead4;">FINAL</span></h2>'
      + '<div class="proj-score"><div><div class="num" style="'+(aScore>bScore?'':'opacity:0.55;')+'">'+fmt(aScore)+'</div><div class="lbl">'+nameA+'</div></div><div><div class="num" style="'+(bScore>aScore?'':'opacity:0.55;')+'">'+fmt(bScore)+'</div><div class="lbl">'+nameB+'</div></div></div>'
      + '<div class="note">This game has already been played, so this is the real final score, not a projection. For reference, the model (using stats as of right now, which already include this game) would project '+nameA+' '+proj.aScore+' – '+nameB+' '+proj.bScore+' if it were still upcoming — early in a season, a single game can swing a team\'s averages a lot, so that comparison number can look strange right after a result like this.</div>'
      + '</div>';
    wireBackButton();
    return;
  }

  const total = proj.total;
  const spreadVal = proj.aScore - proj.bScore;
  const totalLine = tieSafeLine(total);
  const spreadLine = tieSafeLine(spreadVal);
  const spreadLabel = spreadLine===0 ? (nameA+' PK') : (spreadLine>0 ? (nameA+' -'+spreadLine) : (nameB+' -'+Math.abs(spreadLine)));
  const methodNote = proj.marketAnchored
    ? 'Box-score averaging alone can\'t judge an FBS-vs-FCS talent gap (each team\'s stats only reflect their own division), and FCS teams never get an SP+ rating to correct for it -- confirmed live, that combination once produced a 35-point error. For this matchup, the projection leans heavily on the actual market spread as the talent-gap signal instead, with a smaller weight for our own box-score read.'
    : proj.usedSP
    ? 'Blends offense-vs-defense yardage averaging with CFBD\'s opponent-adjusted SP+ ratings, plus home-field advantage (~'+HOME_ADV[league]+' pts to '+nameB+', assumed home) and each team\'s own turnover margin.'
    : 'Offense-vs-defense yardage averaging, plus home-field advantage (~'+HOME_ADV[league]+' pts to '+nameB+', assumed home) and each team\'s own turnover margin. Not a sportsbook line.';

  const addSpreadId = 'mu-add-spread-'+lg;
  const addTotalId = 'mu-add-total-'+lg;

  out.innerHTML = backBtnHtml + '<div class="card"><h2>'+nameA+' vs '+nameB+'</h2><div class="proj-score"><div><div class="num">'+proj.aScore+'</div><div class="lbl">'+nameA+' proj.</div></div><div><div class="num">'+proj.bScore+'</div><div class="lbl">'+nameB+' proj.</div></div></div><div class="matchup-result">'+edgeRow('Proj. pass yds', proj.aPassProj, proj.bPassProj)+edgeRow('Proj. rush yds', proj.aRushProj, proj.bRushProj)+edgeRow('Turnover margin', A.to, B.to)+'</div><div style="display:flex;gap:8px;margin-top:12px;"><button class="secondary" id="'+addSpreadId+'">Add "'+spreadLabel+'" to parlay</button><button class="secondary" id="'+addTotalId+'">Add "Total '+totalLine+'" to parlay</button></div><div class="note">'+methodNote+'</div></div>'+renderGameBets(nameA, nameB);
  wireBackButton();
  let muSpreadProb = null, muTotalProb = null;
  if(muMarket){
    const muAIsEntryA = teamNamesMatch(muMarket.aTeam, nameA);
    const muMarketFavA = (muMarket.aSpread===null||muMarket.aSpread===undefined) ? null : (muAIsEntryA ? -muMarket.aSpread : muMarket.aSpread);
    if(muMarketFavA!==null) muSpreadProb = pickProbability(Math.abs(proj.spread-muMarketFavA), proj.usedSP, league, spreadLine<0);
    if(muMarket.total!==null && muMarket.total!==undefined) muTotalProb = pickProbability(Math.abs(proj.total-muMarket.total), proj.usedSP, league, false);
  }
  document.getElementById(addSpreadId).addEventListener('click', ()=> addLeg(spreadLabel+' (model proj.)', -110, muSpreadProb));
  document.getElementById(addTotalId).addEventListener('click', ()=> addLeg('Total '+totalLine+' (model proj.)', -110, muTotalProb));
}
document.getElementById('run-matchup-nfl').addEventListener('click', ()=>{
  runMatchupFor(document.getElementById('m-teamA-nfl').value, document.getElementById('m-teamB-nfl').value, 'matchup-output-nfl');
});
document.getElementById('run-matchup-cfb').addEventListener('click', ()=>{
  runMatchupFor(document.getElementById('m-teamA-cfb').value, document.getElementById('m-teamB-cfb').value, 'matchup-output-cfb');
});

let CURRENT_NFL_WEEK = null;
let NFL_WEEK_GAMES = [];
let CFB_WEEK_GAMES = [];
// Pulls best-price ML/spread for a specific schedule game out of a market
// object, resolving which side (a/b) is which by name -- NOT by assuming
// the odds source's team order matches the schedule's, which is exactly
// the assumption that caused the CFB spread-sign bug above.
function oddsForGame(market, g){
  if(!market) return null;
  const aMatchesGA = teamNamesMatch(market.aTeam, g.a);
  return {
    aML: aMatchesGA ? market.aML : market.bML,
    aSpread: aMatchesGA ? market.aSpread : market.bSpread,
    aSpreadOdds: aMatchesGA ? market.aSpreadOdds : market.bSpreadOdds,
    bML: aMatchesGA ? market.bML : market.aML,
    bSpread: aMatchesGA ? market.bSpread : market.aSpread,
    bSpreadOdds: aMatchesGA ? market.bSpreadOdds : market.aSpreadOdds,
  };
}
function fmtOddsNum(n){ return (n===null || n===undefined) ? '—' : (n>0?'+':'')+n; }
function scheduleOddsLine(nameA, nameB){
  const market = findMarketLine(nameA, nameB);
  if(!market) return '<div class="team-meta" style="margin-top:4px;">No odds loaded for this game yet.</div>';
  const o = oddsForGame(market, {a:nameA, b:nameB});
  return '<div class="team-meta" style="margin-top:4px;">'
    + nameA+' ML '+fmtOddsNum(o.aML)+' · '+fmtOddsNum(o.aSpread)+' ('+fmtOddsNum(o.aSpreadOdds)+')'
    + ' &nbsp;|&nbsp; '
    + nameB+' ML '+fmtOddsNum(o.bML)+' · '+fmtOddsNum(o.bSpread)+' ('+fmtOddsNum(o.bSpreadOdds)+')'
    + '</div>';
}
// A game that's already been played shows its real result instead of odds
// (odds are moot once a game is over, and showing them alongside a real
// score is confusing). Falls back to the normal odds line otherwise.
function gameStatusLine(g){
  if(g.awayScore!=null && g.homeScore!=null){
    const aWon = g.awayScore>g.homeScore, bWon = g.homeScore>g.awayScore;
    return '<div class="team-meta" style="margin-top:4px;"><span class="pill" style="background:rgba(51,211,153,0.16);color:#5eead4;">FINAL</span> '
      + '<span style="'+(aWon?'font-weight:700;color:var(--ink);':'')+'">'+g.a+' '+fmt(g.awayScore)+'</span>'
      + ' — '
      + '<span style="'+(bWon?'font-weight:700;color:var(--ink);':'')+'">'+g.b+' '+fmt(g.homeScore)+'</span>'
      + '</div>';
  }
  return scheduleOddsLine(g.a, g.b);
}

async function renderSchedule(){
  await loadAllOdds();
  const live = await fetchJSON('./data/nfl-schedule.json');
  const games = (live && live.games && live.games.length) ? live.games : NFL_WEEK1;
  NFL_WEEK_GAMES = games;
  CURRENT_NFL_WEEK = live ? live.week : 1;
  const list = document.getElementById('nfl-schedule-list');
  const heading = document.getElementById('nfl-week-heading');
  if(heading) heading.textContent = 'NFL Week ' + CURRENT_NFL_WEEK + ' · 2026 season';
  list.innerHTML = games.map(function(g,i){
    return '<div class="game-row" data-idx="'+i+'" style="flex-direction:column;align-items:stretch;">'
      + '<div style="display:flex;justify-content:space-between;width:100%;"><div>'+g.a+' @ '+g.b+'</div><div class="game-date">'+g.date+'</div></div>'
      + gameStatusLine(g)
      + '</div>';
  }).join('');
  list.querySelectorAll('.game-row').forEach(function(row){
    row.addEventListener('click', function(){
      const g = games[row.dataset.idx];
      const a = resolveTeamName(g.a), b = resolveTeamName(g.b);
      activateTopTab('nfl');
      activateSubTab('nfl-matchup');
      document.getElementById('m-teamA-nfl').value = a;
      document.getElementById('m-teamB-nfl').value = b;
      runMatchupFor(a, b, 'matchup-output-nfl');
    });
  });
}
async function renderCfbSchedule(){
  await loadAllOdds();
  const live = await fetchJSON('./data/cfb-schedule.json');
  const games = (live && live.length) ? live : CFB_WEEK;
  CFB_WEEK_GAMES = games;
  const list = document.getElementById('cfb-schedule-list');
  list.innerHTML = games.map(function(g,i){
    return '<div class="game-row" data-idx="'+i+'" style="flex-direction:column;align-items:stretch;">'
      + '<div style="display:flex;justify-content:space-between;width:100%;"><div>'+g.a+' vs '+g.b+'</div><div class="game-date">'+g.date+'</div></div>'
      + gameStatusLine(g)
      + '</div>';
  }).join('');
  list.querySelectorAll('.game-row').forEach(function(row){
    row.addEventListener('click', function(){
      const g = games[row.dataset.idx];
      const a = resolveTeamName(g.a), b = resolveTeamName(g.b);
      activateTopTab('cfb');
      activateSubTab('cfb-matchup');
      document.getElementById('m-teamA-cfb').value = a;
      document.getElementById('m-teamB-cfb').value = b;
      runMatchupFor(a, b, 'matchup-output-cfb');
    });
  });
}
async function renderRankings(){
  const liveRankings = await fetchJSON('./data/cfb-rankings.json');
  const ranks = (liveRankings && liveRankings.length) ? liveRankings : CFB_TOP25;
  const list = document.getElementById('cfb-rankings-list');
  list.innerHTML = ranks.map(function(r){
    return '<div class="rank-row"><div class="rank-num">'+r.rank+'</div><div>'+r.team+'</div><div class="rank-record">'+(r.record||'')+'</div><div class="rank-next">'+(r.next||'')+'</div></div>';
  }).join('');
  const othersEl = document.getElementById('cfb-others-list');
  if(!liveRankings) othersEl.textContent = CFB_OTHERS;
  else othersEl.textContent = '';
}
async function renderInjuries(){
  const data = await fetchJSON('./data/nfl-injuries.json');
  const weekEl = document.getElementById('nfl-injury-week');
  const list = document.getElementById('nfl-injuries-list');
  const entries = (data && data.entries) ? data.entries : [];
  if(weekEl) weekEl.textContent = data && data.week ? ('Week '+data.week) : '';
  if(entries.length===0){
    list.innerHTML = '<div class="empty">No injury report loaded yet.</div>';
    return;
  }
  const order = ['Out', 'Doubtful', 'Questionable'];
  const statusColor = { Out: '#f28b7d', Doubtful: 'var(--accent)', Questionable: '#5eead4' };
  list.innerHTML = order.map(function(status){
    const rows = entries.filter(function(e){ return e.status===status; }).sort(function(a,b){ return (a.team||'').localeCompare(b.team||''); });
    if(rows.length===0) return '';
    const heading = '<div style="font-weight:800;font-size:0.82rem;color:'+statusColor[status]+';margin:16px 0 4px;padding-bottom:4px;border-bottom:2px solid '+statusColor[status]+';">'+status+' ('+rows.length+')</div>';
    const body = rows.map(function(e){
      return '<div class="team-row"><div><div class="team-name">'+e.name+' <span class="pill">'+e.pos+'</span></div><div class="team-meta">'+e.team+' · '+e.injury+'</div></div></div>';
    }).join('');
    return heading + body;
  }).join('');
}


// ==================== top bets ====================
function projectMatchup(nameA, nameB, gameDate){
  const A = teamsCache[nameA], B = teamsCache[nameB];
  if(!A || !B) return null;
  return computeProjection(nameA, nameB, A.league, gameDate); // same model as the Matchup tab -- see computeProjection
}
function teamNamesMatch(a, b){
  if(!a || !b) return false;
  if(a===b) return true;
  const na = a.toLowerCase().trim(), nb = b.toLowerCase().trim();
  if(na===nb) return true;
  // Bridges naming differences between sources -- e.g. CFBD's "Ohio State"
  // vs an odds provider's "Ohio State Buckeyes" -- but only on WHOLE WORDS.
  // A plain prefix check made "Indiana" match "Indianapolis Colts", so the
  // Colts' NFL line showed up as Indiana's CFB line.
  return na.indexOf(nb+' ')===0 || nb.indexOf(na+' ')===0;
}
function nameMatchScore(a, b){
  if(!a || !b) return 0;
  if(a===b || a.toLowerCase().trim()===b.toLowerCase().trim()) return 2;
  return teamNamesMatch(a,b) ? 1 : 0;
}
function findMarketLine(nameA, nameB){
  // Best match wins (exact names beat prefix matches), and entries from the
  // other league are ignored when we know which league these teams are in.
  let lg = null;
  try{
    const ta = (typeof teamsCache!=='undefined') && (teamsCache[nameA] || teamsCache[nameB]);
    if(ta && ta.league) lg = ta.league;
  }catch(e){}
  let best = null, bestScore = 0;
  ALL_ODDS.forEach(function(o){
    if(lg && o.league && o.league!==lg) return;
    const f1 = nameMatchScore(o.aTeam,nameA), f2 = nameMatchScore(o.bTeam,nameB);
    const r1 = nameMatchScore(o.aTeam,nameB), r2 = nameMatchScore(o.bTeam,nameA);
    const sc = Math.max((f1&&f2)?f1+f2:0, (r1&&r2)?r1+r2:0);
    if(sc>bestScore){ best=o; bestScore=sc; }
  });
  return best || undefined;
}
let MODEL_CALIBRATION = null; // loaded at startup from data/calibration.json -- null until enough graded picks exist to calibrate from (see calibrate_model.py). Keyed by league (NFL/CFB calibrate independently -- see that script's docstring for why)
let MODEL_WEIGHTS = null; // loaded at startup from data/model_weights.json -- null (or .trained===false) until enough graded team bets exist for train_model.py to trust a fit (see that script's docstring)
let INJURIES_CACHE = {}; // loaded at startup from data/nfl-injuries.json -- keyed by team name -> list of {name, pos, injury, status}. Used by detectBackupQB(); see that function's comment for the honest limitations (this lags breaking news by a few days, since it only reflects official team-released reports)
let WEATHER_CACHE = {}; // loaded at startup from data/weather.json -- keyed by HOME team name -> {dome:true} or {windMph, tempF, shortForecast, severe}. NFL-only, see fetch_weather.py's docstring for the scope reasoning
let TRACK_RECORD_PICKS = []; // loaded at startup from data/track-record.json -- used by computeTeamBettingStats() to show a team's own real betting track record (spread/total/props) on its detail page
let PLAYER_PROPS_ODDS = {}; // loaded at startup from data/player-props-odds.json -- real sportsbook player-prop lines (see fetch_player_props_odds.py). Keyed by player name -> stat -> {line, books}; empty object (not null) when unavailable so lookups can always safely use {} fallback
// Applies the logistic regression trained in train_model.py to a single
// candidate pick, mirroring that script's sigmoid(bias + w.edge*edge +
// w.is_favorite*isFavorite + w.league_is_cfb*isCfb) exactly, including
// standardizing edge the same way training did (edge_mean/edge_std are
// written into model_weights.json specifically so this side can replay
// the same transform). Returns null if the model isn't trained yet --
// callers must treat null as "no opinion," not "predicts a miss."
function predictHitProbability(edge, isFavorite, isCfb){
  if(!MODEL_WEIGHTS || !MODEL_WEIGHTS.trained) return null;
  const w = MODEL_WEIGHTS.weights;
  const scaledEdge = (edge - MODEL_WEIGHTS.edge_mean) / MODEL_WEIGHTS.edge_std;
  const z = MODEL_WEIGHTS.bias + w[0]*scaledEdge + w[1]*(isFavorite?1:0) + w[2]*(isCfb?1:0);
  return 1/(1+Math.exp(-z));
}
function confidenceTier(edge, usedSP, league){
  // Confidence reflects both edge size and data quality -- a CFB pick
  // backed by SP+ (opponent-adjusted) is more trustworthy than one from
  // box-score stats alone, which are noisy early season before teams
  // have played a representative slate of opponents.
  //
  // Thresholds are calibrated from this app's own accumulated track
  // record when enough graded picks exist (see calibrate_model.py) --
  // real self-improvement grounded in actual hit/miss history, not a
  // static guess held forever. Falls back to the original defaults
  // (7 / 3.5) until there's a real sample to calibrate from. Each league
  // calibrates independently -- CFB struggling doesn't get diluted by
  // pooling with NFL's numbers, or vice versa.
  const leagueCal = MODEL_CALIBRATION && MODEL_CALIBRATION[league];
  const strongThreshold = (leagueCal && leagueCal.calibrated) ? leagueCal.strong_threshold : 7;
  const moderateThreshold = (leagueCal && leagueCal.calibrated) ? leagueCal.moderate_threshold : 3.5;
  const dataOk = league!=='CFB' || usedSP;
  if(edge>=strongThreshold && dataOk) return {label:'Strong', cls:'high'};
  if(edge>=strongThreshold) return {label:'Strong*', cls:'mid'}; // starred: box-score only, treat with extra caution
  if(edge>=moderateThreshold) return {label:'Moderate', cls:'mid'};
  return {label:'Lean', cls:'low'};
}
// Mirrors track_predictions.py's simplify_tier() -- collapses the 4-way
// tier label into the 3 user-facing strength buckets. See that
// function's comment for the full reasoning (Strong* still counts as
// Strong here; the asterisk distinction stays visible elsewhere via the
// full tier label, just not in this simplified bucketing).
function simplifyTier(tierLabel){
  if(tierLabel==='Strong' || tierLabel==='Strong*') return 'Strong';
  if(tierLabel==='Moderate') return 'Medium';
  return 'Low';
}
const MIN_BET_EDGE = 1.0; // a team bet needs at least this many points of edge vs the market line; anything smaller is a pass, not a pick (mirrors track_predictions.py)
function computeAllBetCandidates(games, league){
  const candidates = [];
  const MIN_LEARNED_PROB = 0.55; // modest bar above a coinflip -- once the model is trained, a pick clearing the edge threshold but predicted below this gets filtered out rather than shown anyway
  games.forEach(function(g){
    if(g.awayScore!=null && g.homeScore!=null) return; // game's already been played -- nothing left to bet on
    const proj = projectMatchup(g.a, g.b, g.date);
    if(!proj) return;
    const market = findMarketLine(g.a, g.b);
    if(!market) return;
    const gameKey = g.a+' vs '+g.b;
    const isCfb = league==='CFB';
    const aIsEntryA = teamNamesMatch(market.aTeam, g.a);
    const marketFavA = (market.aSpread===null || market.aSpread===undefined) ? null : (aIsEntryA ? -market.aSpread : market.aSpread);
    if(marketFavA!==null){
      const spreadEdge = proj.spread - marketFavA;
      const favoredTeam = spreadEdge>0 ? g.a : g.b;
      const favoredLine = aIsEntryA ? (spreadEdge>0 ? market.aSpread : market.bSpread) : (spreadEdge>0 ? market.bSpread : market.aSpread);
      const favoredOdds = aIsEntryA ? (spreadEdge>0 ? market.aSpreadOdds : market.bSpreadOdds) : (spreadEdge>0 ? market.bSpreadOdds : market.aSpreadOdds);
      // Real learning, not just a threshold nudge: once train_model.py has
      // enough graded history to trust a fit, this is an actual second
      // opinion from a model fit on real outcomes -- a pick that clears
      // the edge bar but that the learned model doesn't like gets held
      // back here, rather than shown anyway just because the edge alone
      // looked big. Falls through untouched (learnedProb stays null) if
      // the model isn't trained yet -- see predictHitProbability's comment.
      const learnedProb = predictHitProbability(Math.abs(spreadEdge), favoredLine<0, isCfb);
      if(Math.abs(spreadEdge)>=MIN_BET_EDGE && (learnedProb===null || learnedProb>=MIN_LEARNED_PROB)){
        candidates.push({
          edge: Math.abs(spreadEdge),
          label: favoredTeam+' '+(favoredLine>0?'+':'')+favoredLine,
          sub: g.a+' vs '+g.b+' · model has it '+(proj.spread>0?g.a:g.b)+' by '+Math.abs(tieSafeLine(proj.spread)),
          tier: confidenceTier(Math.abs(spreadEdge), proj.usedSP, league),
          gameKey: gameKey, oddsPrice: (favoredOdds===null||favoredOdds===undefined) ? null : favoredOdds,
          learnedProb: learnedProb, league: league, usedSP: proj.usedSP, isFavorite: favoredLine<0,
          meta: {league: league, type: 'spread', team: favoredTeam, opp: (favoredTeam===g.a ? g.b : g.a), line: favoredLine},
        });
      }
    }
    if(market.total!==null && market.total!==undefined){
      const totalEdge = proj.total - market.total;
      const totalOdds = totalEdge>0 ? market.overOdds : market.underOdds;
      // Totals don't have a clean "favorite" side the way spreads do, so
      // is_favorite is passed as false (the model was trained without a
      // meaningful signal either way for totals -- this is a reasonable
      // default, not a claim that totals and dog-side spreads behave the
      // same).
      const learnedProb = predictHitProbability(Math.abs(totalEdge), false, isCfb);
      if(Math.abs(totalEdge)>=MIN_BET_EDGE && (learnedProb===null || learnedProb>=MIN_LEARNED_PROB)){
        candidates.push({
          edge: Math.abs(totalEdge),
          label: (totalEdge>0?'Over':'Under')+' '+market.total,
          sub: g.a+' vs '+g.b+' · model projects '+tieSafeLine(proj.total)+' total points',
          tier: confidenceTier(Math.abs(totalEdge), proj.usedSP, league),
          gameKey: gameKey, oddsPrice: (totalOdds===null||totalOdds===undefined) ? null : totalOdds,
          learnedProb: learnedProb, league: league, usedSP: proj.usedSP, isFavorite: false,
          meta: {league: league, type: 'total', dir: (totalEdge>0?'over':'under'), team: g.a, opp: g.b, line: market.total},
        });
      }
    }
  });
  candidates.sort(function(a,b){ return b.edge - a.edge; });
  return candidates;
}
function computeTopBets(games, league){
  return computeAllBetCandidates(games, league).slice(0, 10);
}
// Builds 3 parlay options at increasing leg-count/risk from the same
// underlying best-edge picks -- Safest (2 legs), Balanced (up to 4),
// Value (up to 6, biggest payout, lowest probability all legs hit).
// Only one leg is ever taken per game (spread+total from the same game
// are correlated outcomes, not independent bets, so combining them would
// overstate a parlay's real odds).
function buildTopParlays(games, league){
  const all = computeAllBetCandidates(games, league).filter(function(c){ return c.oddsPrice!==null && c.oddsPrice!==undefined; });
  const bestPerGame = {};
  all.forEach(function(c){
    if(!bestPerGame[c.gameKey] || c.edge > bestPerGame[c.gameKey].edge) bestPerGame[c.gameKey] = c;
  });
  const deduped = Object.values(bestPerGame).sort(function(a,b){ return b.edge - a.edge; });

  function buildOne(legs, name, description){
    if(legs.length < 2) return null;
    const decimalOdds = legs.reduce(function(acc,l){ return acc*americanToDecimal(l.oddsPrice); }, 1);
    return { name: name, description: description, legs: legs, combinedAmerican: decimalToAmerican(decimalOdds) };
  }

  const strongOnly = deduped.filter(function(c){ return c.tier.label.indexOf('Strong')===0; });
  const parlays = [];
  const safeLegs = (strongOnly.length>=2 ? strongOnly : deduped).slice(0,2);
  const p1 = buildOne(safeLegs, 'Safest', 'Fewest legs, highest-confidence picks only');
  if(p1) parlays.push(p1);
  const balancedLegs = deduped.slice(0, Math.min(4, deduped.length));
  if(balancedLegs.length > safeLegs.length){
    const p2 = buildOne(balancedLegs, 'Balanced', balancedLegs.length+'-leg mix of the week\'s best edges');
    if(p2) parlays.push(p2);
  }
  const valueLegs = deduped.slice(0, Math.min(6, deduped.length));
  if(valueLegs.length > balancedLegs.length){
    const p3 = buildOne(valueLegs, 'Value', valueLegs.length+' legs — bigger payout, lower odds all of them hit');
    if(p3) parlays.push(p3);
  }
  return parlays.slice(0, 3);
}
function renderParlaysList(elId, parlays){
  const el = document.getElementById(elId);
  if(!el) return;
  if(parlays.length===0){
    el.innerHTML = '<div class="empty">Not enough games with both a market line and priced odds this week to build a parlay.</div>';
    return;
  }
  el.innerHTML = parlays.map(function(p){
    const legRows = p.legs.map(function(l){
      return '<div class="history-item"><span><span style="display:block;">'+l.label+'</span><span class="team-meta" style="font-weight:400;">'+(l.gameKey||'')+'</span></span><span>'+(l.oddsPrice>0?'+':'')+l.oddsPrice+'</span></div>';
    }).join('');
    return '<div class="card" style="background:var(--card-2);margin-bottom:10px;">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;"><h2 style="margin:0;">'+p.name+' <span class="pill">'+p.legs.length+' legs</span></h2><div style="font-weight:800;color:var(--accent);">'+(p.combinedAmerican.startsWith('-')?'':'')+p.combinedAmerican+'</div></div>'
      + '<div class="note" style="margin:4px 0 8px;">'+p.description+'</div>'
      + legRows
      + '<button class="secondary" data-add-parlay style="margin-top:8px;">Add all '+p.legs.length+' legs to Calculator</button>'
      + '</div>';
  }).join('');
  el.querySelectorAll('[data-add-parlay]').forEach(function(btn, i){
    btn.addEventListener('click', function(){
      parlays[i].legs.forEach(function(l){ addLeg(l.label+' ('+l.gameKey+')', l.oddsPrice, pickProbability(l.edge, l.usedSP, l.league, l.isFavorite, l.learnedProb), l.meta); });
      activateTopTab('parlay');
      activateSubTab('parlay-calc');
    });
  });
}
// Groups every candidate this week (not just a top-10 cut) into Strong /
// Medium / Low sections, so the whole week's picks can be scanned by
// confidence without clicking into each individual game -- confirmed
// live this was a real gap: the only way to see a pick's tier before
// this was opening its specific matchup one at a time.
function renderBetsByStrength(elId, games, league){
  const el = document.getElementById(elId);
  const all = computeAllBetCandidates(games, league);
  if(all.length===0){
    el.innerHTML = '<div class="empty">No matchups with both team stats and a market line loaded yet this week.</div>';
    return;
  }
  const groups = {Strong: [], Medium: [], Low: []};
  all.forEach(function(b){ groups[simplifyTier(b.tier.label)].push(b); });
  ['Strong','Medium','Low'].forEach(function(bucket){ groups[bucket].sort(function(a,b){ return b.edge-a.edge; }); });
  const bucketStyle = {
    Strong: 'background:rgba(51,211,153,0.18);color:#5eead4;',
    Medium: 'background:rgba(240,185,61,0.18);',
    Low: 'background:rgba(136,146,176,0.18);',
  };
  el.innerHTML = ['Strong','Medium','Low'].map(function(bucket){
    const items = groups[bucket];
    const header = '<div style="display:flex;align-items:center;gap:8px;margin:14px 0 8px;"><span class="pill" style="'+bucketStyle[bucket]+'">'+bucket+'</span><span class="team-meta">'+items.length+' pick'+(items.length===1?'':'s')+'</span></div>';
    const body = items.length
      ? items.map(function(b){
          return '<div class="team-row"><div><div class="team-name">'+b.label+'</div><div class="team-meta">'+b.sub+'</div></div><div class="pill">edge '+fmt(b.edge)+'</div></div>';
        }).join('')
      : '<div class="empty" style="padding:10px 0;">None this week</div>';
    return header + body;
  }).join('');
}
function renderTopBetsList(elId, bets){
  const el = document.getElementById(elId);
  if(bets.length===0){
    el.innerHTML = '<div class="empty">No matchups with both team stats and a market line loaded yet this week.</div>';
    return;
  }
  el.innerHTML = bets.map(function(b,i){
    return '<div class="team-row"><div><div class="team-name">'+(i+1)+'. '+b.label+' <span class="pill" style="background:rgba(240,185,61,0.15);">'+b.tier.label+'</span></div><div class="team-meta">'+b.sub+'</div></div><div class="pill">edge '+fmt(b.edge)+'</div></div>';
  }).join('');
}

// ---- Player prop matchup targets: same defense-adjustment math as the
// hit rate checker, but scanning every loaded player instead of one at a
// time, ranked by how favorable/unfavorable this week's matchup is. Not
// tied to a specific sportsbook line since none is set for most players.
function computeTopPlayerBets(league){
  const candidates = [];
  Object.keys(playersCache).forEach(function(name){
    const p = playersCache[name];
    if(p.league!==league) return;
    if(league==='NFL' && p.team && p.teamYear==null) return; // not on a confirmed current roster -- team/opponent would be unreliable
    const games = p.games || [];
    if(games.length===0) return;
    if(games.length<2) return; // a single game is too thin a sample to recommend a bet on -- confirmed live: a 1-game rookie/backup sample cleared the flat volume threshold easily despite not being an established, ongoing role
    const opp = findOpponentThisWeek(league, p.team);
    if(!opp || !teamsCache[opp]) return;
    if(findFinalScoreForMatchup(league, p.team, opp)) return; // that game's already been played -- nothing left to project
    let mainStat = 'passYds';
    if(p.pos==='RB') mainStat='rushYds';
    if(p.pos==='WR'||p.pos==='TE') mainStat='recYds';
    const defKey = defCategoryForStat(mainStat);
    if(!defKey || !teamsCache[opp][defKey]) return;
    const avgVal = leagueAvgDefStat(league, defKey);
    if(!avgVal) return;
    const ratio = clampDefenseRatio(shrunkTeamStat(teamsCache[opp], defKey, league) / avgVal);
    const last5 = games.slice(-5);
    const l5avg = median(last5.map(function(g){ return g[mainStat]||0; }));
    if(!meetsVolumeThreshold(mainStat, l5avg)) return; // filters out fullbacks/deep bench players with a token stat line
    const modelProjection = roundToHalf(l5avg * ratio); // simple matchup-adjusted projection -- see note in renderPlayerBetsList
    const realProp = getRealPropLine(name, mainStat);
    const projected = realProp ? realProp.line : modelProjection;
    const direction = realProp ? (modelProjection > realProp.line ? 'over' : 'under') : (ratio>=1 ? 'favorable' : 'tough');
    const edge = realProp ? Math.abs(modelProjection - realProp.line) : null;
    candidates.push({
      name, pos: p.pos, team: p.team, opp, ratio, l5avg, projected, modelProjection, statLabel: statLabel(mainStat),
      direction, usedRealLine: !!realProp, edge, _recencyKey: mostRecentGameKey(p)
    });
  });
  const deduped = capPlayersPerTeamByPosition(candidates);
  deduped.sort(function(a,b){ return Math.abs(b.ratio-1) - Math.abs(a.ratio-1); });
  return deduped.slice(0, 10);
}
function renderPlayerBetsList(elId, bets){
  const el = document.getElementById(elId);
  if(bets.length===0){
    el.innerHTML = '<div class="empty">No players with logged games and a resolvable opponent this week yet.</div>';
    return;
  }
  el.innerHTML = bets.map(function(b,i){
    const pct = Math.round((b.ratio-1)*100);
    const dirLabel = (b.direction==='favorable' ? 'Over ' : 'Under ')+b.statLabel+' · '+(b.direction==='favorable' ? '+'+pct+'% easier than average' : pct+'% tougher than average');
    const cls = b.direction==='favorable' ? 'over' : 'under';
    return '<div class="team-row"><div><div class="team-name">'+(i+1)+'. '+b.name+' <span class="pill">'+b.pos+'</span></div><div class="team-meta">'+b.team+' vs '+b.opp+' · L5 avg '+fmt(b.l5avg)+' '+b.statLabel+' · <b>projected '+fmt(b.projected)+'</b></div></div><div class="glog-val '+cls+'">'+dirLabel+'</div></div>';
  }).join('');
}


// ---------- Best bet per game (one team bet + one prop for every game) ----------
function impliedFromAmerican(odds){ return 1/americanToDecimal(odds); }
function bestTeamBetForGame(g, league){
  const proj = projectMatchup(g.a, g.b, g.date);
  const market = findMarketLine(g.a, g.b);
  if(!proj || !market) return null;
  const aIsEntryA = teamNamesMatch(market.aTeam, g.a);
  const marginSd = league==='CFB' ? 16 : 13.5;
  const gameKey = g.a+' vs '+g.b;
  const opts = [];
  const marketFavA = (market.aSpread===null || market.aSpread===undefined) ? null : (aIsEntryA ? -market.aSpread : market.aSpread);
  if(marketFavA!==null){
    const edge = proj.spread - marketFavA;
    const team = edge>0 ? g.a : g.b, opp = edge>0 ? g.b : g.a;
    const line = aIsEntryA ? (edge>0 ? market.aSpread : market.bSpread) : (edge>0 ? market.bSpread : market.aSpread);
    const odds = aIsEntryA ? (edge>0 ? market.aSpreadOdds : market.bSpreadOdds) : (edge>0 ? market.bSpreadOdds : market.aSpreadOdds);
    const price = (odds===null||odds===undefined) ? -110 : odds;
    const prob = signedBetProbability(Math.abs(edge), proj.usedSP, league);
    opts.push({kind:'Spread', label: team+' '+fmtLine(line), prob:prob, odds:price, hasOdds: odds!==null&&odds!==undefined, edge:Math.abs(edge), bigGap: Math.abs(edge)>=7 || (marketFavA!==0 && proj.spread!==0 && (marketFavA>0)!==(proj.spread>0)), value: prob-impliedFromAmerican(price),
      sub:'model has it '+(proj.spread>0?g.a:g.b)+' by '+Math.abs(tieSafeLine(proj.spread)),
      meta:{league:league,type:'spread',team:team,opp:opp,line:line}});
  }
  if(market.total!==null && market.total!==undefined){
    const edge = proj.total - market.total;
    const over = edge>0;
    const odds = over ? market.overOdds : market.underOdds;
    const price = (odds===null||odds===undefined) ? -110 : odds;
    const prob = signedBetProbability(Math.abs(edge), proj.usedSP, league);
    opts.push({kind:'Total', label:(over?'Over ':'Under ')+market.total, prob:prob, odds:price, hasOdds: odds!==null&&odds!==undefined, edge:Math.abs(edge), bigGap: Math.abs(edge)>=7, value: prob-impliedFromAmerican(price),
      sub:'model projects '+tieSafeLine(proj.total)+' total points',
      meta:{league:league,type:'total',dir:over?'over':'under',team:g.a,opp:g.b,line:market.total}});
  }
  // Moneyline: only the side the model has winning outright, and only when its
  // win chance beats the price (win chance from a normal curve on the projected margin).
  [[g.a, g.b, proj.spread, aIsEntryA ? market.aML : market.bML],[g.b, g.a, -proj.spread, aIsEntryA ? market.bML : market.aML]].forEach(function(t){
    const team=t[0], opp=t[1], margin=t[2], ml=t[3];
    if(ml===null || ml===undefined) return;
    // Market-anchored win chance (see mlWinProb). Only list a moneyline when the
    // team is still more likely than not to win -- an underdog moneyline is a
    // long shot, and the same view is better expressed as the spread.
    const mm = marketMarginFor(team, opp);
    const prob = mlWinProb(league, margin, mm);
    if(prob<0.5) return;
    opts.push({kind:'Moneyline', label: team+' ML', prob:prob, odds:ml, hasOdds:true, edge:margin, value: prob-impliedFromAmerican(ml),
      sub:(mm!==null ? 'market has '+team+' '+(mm>=0?'favored by ':'as a ')+(mm>=0?fmt(mm):'dog')+' · model margin '+fmt(margin) : 'model has '+team+' winning by '+fmt(margin)),
      meta:{league:league,type:'ml',team:team,opp:opp,line:0}});
  });
  if(opts.length===0) return null;
  opts.sort(function(a,b){ return b.value-a.value; });
  const best = opts[0]; best.gameKey = gameKey; return best;
}
function bestPropForGame(g){
  let bets;
  try{ bets = computeGameBets(g.a, g.b).playerBets || []; }catch(e){ return null; }
  if(bets.length===0) return null;
  const real = bets.filter(function(b){ return b.usedRealLine; }).sort(function(a,b){ return Math.abs(b.modelProjection-b.projected)-Math.abs(a.modelProjection-a.projected); });
  if(real.length){ return {real:true, b:real[0]}; }
  return {real:false, b:bets[0]}; // already sorted by biggest matchup mismatch
}
function renderBestPerGame(elId, games, league){
  const el = document.getElementById(elId);
  if(!el) return;
  const rows = [];
  (games||[]).forEach(function(g){
    if(g.awayScore!=null && g.homeScore!=null) return; // already played
    const team = bestTeamBetForGame(g, league);
    const prop = bestPropForGame(g);
    if(!team && !prop) return;
    rows.push({g:g, team:team, prop:prop});
  });
  if(rows.length===0){ el.innerHTML = '<div class="empty">No upcoming games with a market line loaded yet.</div>'; return; }
  rows.sort(function(a,b){ return (b.team?b.team.value:-9)-(a.team?a.team.value:-9); });
  const ACTIONS = [];
  el.innerHTML = rows.map(function(r,i){
    let teamHtml = '<div class="team-meta">No market line loaded for this game yet.</div>';
    if(r.team){
      const t = r.team, cat = probabilityCategory(t.prob);
      const thin = (t.prob<0.55 ? ' <span class="team-meta">(thin edge &mdash; lean only)</span>' : '') + (t.bigGap ? ' <span class="team-meta" style="color:#f28b7d;">(model and market disagree a lot &mdash; double-check injuries/news)</span>' : '');
      const idx = ACTIONS.push(t)-1;
      teamHtml = '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;"><div><div class="team-name">'+t.label+' <span class="pill" style="'+cat.style+'">'+Math.round(t.prob*100)+'% · '+cat.label+'</span></div><div class="team-meta">'+t.kind+' · '+t.sub+' · '+fmtLine(t.odds)+thin+'</div></div><button class="secondary" data-bgadd="'+idx+'" style="margin:0;padding:6px 10px;font-size:0.76rem;">+ Slip</button></div>';
    }
    let propHtml = '<div class="team-meta">No player prop data for this game.</div>';
    if(r.prop){
      const b = r.prop.b;
      if(r.prop.real){
        const over = b.modelProjection>b.projected;
        propHtml = '<div class="team-name">'+b.name+' <span class="pill">'+b.pos+'</span> '+(over?'Over ':'Under ')+b.projected+' '+b.statLabel+' <span class="pill" style="background:rgba(51,211,153,0.15);color:#5eead4;">real line</span></div><div class="team-meta">'+b.team+' vs '+b.opp+' · model projects '+fmt(b.modelProjection)+' · L5 avg '+fmt(b.l5avg)+'</div>';
      } else {
        const over = b.modelProjection>=b.l5avg;
        propHtml = '<div class="team-name">'+b.name+' <span class="pill">'+b.pos+'</span> '+b.statLabel+' <span class="pill" style="background:rgba(136,146,176,0.18);">no sportsbook line</span></div><div class="team-meta">'+b.team+' vs '+b.opp+' · model projects '+fmt(b.modelProjection)+' (L5 avg '+fmt(b.l5avg)+') · lean '+(over?'Over':'Under')+' if your book\'s line is '+(over?'below':'above')+' '+fmt(b.modelProjection)+'</div>';
      }
    }
    return '<div style="border-bottom:1px solid var(--line);padding:12px 0;"><div style="font-weight:800;font-size:0.86rem;margin-bottom:6px;">'+r.g.a+' @ '+r.g.b+' <span class="game-date">'+(r.g.date||'')+'</span></div>'
      + '<div style="margin-bottom:8px;"><div class="team-meta" style="text-transform:uppercase;letter-spacing:0.04em;font-size:0.66rem;">Top team bet</div>'+teamHtml+'</div>'
      + '<div><div class="team-meta" style="text-transform:uppercase;letter-spacing:0.04em;font-size:0.66rem;">Top prop</div>'+propHtml+'</div></div>';
  }).join('');
  el.querySelectorAll('[data-bgadd]').forEach(function(btn){
    btn.addEventListener('click', function(){
      const t = ACTIONS[Number(btn.dataset.bgadd)];
      addLeg(t.label+' ('+t.gameKey+')', t.odds, t.prob, t.meta);
      btn.textContent = 'Added ✓';
    });
  });
}
async function renderTopBets(){
  await loadAllOdds();
  renderBestPerGame('nfl-bygame', NFL_WEEK_GAMES, 'NFL');
  renderBestPerGame('cfb-bygame', CFB_WEEK_GAMES, 'CFB');
  renderBetsByStrength('nfl-bets-by-strength', NFL_WEEK_GAMES, 'NFL');
  renderBetsByStrength('cfb-bets-by-strength', CFB_WEEK_GAMES, 'CFB');
  renderTopBetsList('nfl-topbets-list', computeTopBets(NFL_WEEK_GAMES, 'NFL'));
  renderTopBetsList('cfb-topbets-list', computeTopBets(CFB_WEEK_GAMES, 'CFB'));
  renderParlaysList('nfl-topparlays-list', buildTopParlays(NFL_WEEK_GAMES, 'NFL'));
  renderParlaysList('cfb-topparlays-list', buildTopParlays(CFB_WEEK_GAMES, 'CFB'));
  renderPlayerBetsList('nfl-playerbets-list', computeTopPlayerBets('NFL'));
  renderPlayerBetsList('cfb-playerbets-list', computeTopPlayerBets('CFB'));
}

// ---- Track record ----
let trackFilter = 'ALL';
let trackTypeFilter = 'ALL';
let trackStrengthFilter = 'ALL';
let trackStatusFilter = 'FINISHED'; // defaults to Finished -- with hundreds of new pending picks logged every week, "All" sorted by date_logged buries every finished bet under the current week's fresh pending ones
let trackSeasonFilter = 'MAIN'; // MAIN = everything after the test-week cutoff (the "real" record); TEST = the first TEST_WEEKS_CUTOFF weeks only

// Confirmed-anchored to this season's real Week 1 kickoff (the New
// England @ Seattle game on 2026-09-09, the earliest real game seen in
// this app's own data). Used only to bucket CFB picks into a week number
// comparable to NFL's native week field, since CFB has no equivalent
// stored anywhere in this pipeline (see track_predictions.py's cfb week
// labeling for the full story on why CFB uses a date-based label at
// all). If a future season's real Week 1 start date differs, update this.
const SEASON_START_DATE = '2026-09-05';
const TEST_WEEKS_CUTOFF = 3; // picks in weeks 1-3 (either league) are quarantined into "Test Weeks" -- the model is still calibrating on a tiny sample that early (see calibrate_model.py's own 30-pick minimum), so folding those results into the "real" all-time record would let early noise permanently drag down a number meant to reflect the calibrated system
function pickWeekNumber(p){
  if(p.league==='NFL'){
    const m = /NFL-Week(\d+)/.exec(p.week||'');
    return m ? parseInt(m[1],10) : null;
  }
  const m = /CFB-(\d{4}-\d{2}-\d{2})/.exec(p.week||'');
  if(!m) return null;
  const gameDate = new Date(m[1]+'T00:00:00Z');
  const start = new Date(SEASON_START_DATE+'T00:00:00Z');
  const days = Math.floor((gameDate-start)/(1000*60*60*24));
  return days>=0 ? Math.floor(days/7)+1 : null;
}
function isTestWeekPick(p){
  const wk = pickWeekNumber(p);
  return wk!==null && wk>=1 && wk<=TEST_WEEKS_CUTOFF;
}
function summarizePicks(picks){
  const graded = picks.filter(function(p){ return p.status==='hit' || p.status==='miss' || p.status==='push'; });
  const hits = graded.filter(function(p){ return p.status==='hit'; }).length;
  const pushes = graded.filter(function(p){ return p.status==='push'; }).length;
  const misses = graded.filter(function(p){ return p.status==='miss'; }).length;
  const pct = (hits+misses) > 0 ? Math.round(hits/(hits+misses)*100) : null;
  return { graded: graded.length, hits, misses, pushes, pct };
}
function summaryLine(s){
  if(s.graded===0) return 'no graded picks yet';
  return s.hits+'-'+s.misses+(s.pushes?'-'+s.pushes+' push':'')+(s.pct!==null?' ('+s.pct+'%)':'');
}
// Closing-line value: positive means the line you were given beat the
// last line seen before the game (the best early sign of a real edge).
function pickClv(p){
  if(p.last_line===undefined || p.last_line===null || p.line===undefined || p.line===null || p.backfilled) return null;
  if(p.type==='total') return p.direction==='over' ? p.last_line - p.line : p.line - p.last_line;
  if(p.type==='spread') return p.line - p.last_line;
  return null;
}
function clvRowHtml(picks){
  const vals = picks.map(pickClv).filter(function(v){ return v!==null; });
  if(vals.length<5) return '<div class="history-item"><span>Closing-line value</span><span class="team-meta">collecting (needs 5+ picks)</span></div>';
  const avg = vals.reduce(function(a,b){ return a+b; },0)/vals.length;
  const beat = vals.filter(function(v){ return v>0; }).length, lost = vals.filter(function(v){ return v<0; }).length;
  return '<div class="history-item"><span>Closing-line value</span><span>'+(avg>=0?'+':'')+avg.toFixed(2)+' pts avg · beat close '+beat+', lost to it '+lost+' (of '+vals.length+')</span></div>';
}
async function renderTrackRecord(){
  const data = await fetchJSON('./data/track-record.json');
  const rawPicks = (data && data.picks) ? data.picks : [];
  const allPicks = rawPicks.filter(function(p){ return trackSeasonFilter==='TEST' ? isTestWeekPick(p) : !isTestWeekPick(p); });

  const seasonNote = document.getElementById('track-season-note');
  if(seasonNote){
    seasonNote.textContent = trackSeasonFilter==='TEST'
      ? 'Weeks 1-'+TEST_WEEKS_CUTOFF+' only, kept separate from the main record below. Confidence thresholds are still calibrating this early (needs 30+ graded picks per league -- see the note on Top Bets), so these results shouldn\'t count against -- or for -- the "real" number yet.'
      : 'Weeks '+(TEST_WEEKS_CUTOFF+1)+'+ only -- once the model has enough real results to calibrate from. Check the Test Weeks tab above to see how the first '+TEST_WEEKS_CUTOFF+' weeks went while it was still finding its footing.';
  }

  const leagueFiltered = trackFilter==='ALL' ? allPicks : allPicks.filter(function(p){ return p.league===trackFilter; });
  const typeFiltered = trackTypeFilter==='ALL' ? leagueFiltered : leagueFiltered.filter(function(p){
    if(trackTypeFilter==='PLAYER') return p.type==='player_prop';
    if(trackTypeFilter==='SPREAD') return p.type==='spread';
    if(trackTypeFilter==='TOTAL') return p.type==='total';
    return true;
  });
  const strengthFiltered = trackStrengthFilter==='ALL' ? typeFiltered : typeFiltered.filter(function(p){ return p.strength===trackStrengthFilter; });
  const filtered = trackStatusFilter==='ALL' ? strengthFiltered : strengthFiltered.filter(function(p){
    return trackStatusFilter==='PENDING' ? p.status==='pending' : p.status!=='pending';
  });

  // Overall summary -- spread, total, and player props each have
  // different expected baselines and behave differently (confirmed live:
  // splitting spread/total together as one "team bets" number masked
  // real differences between how each is actually performing), so each
  // gets its own line instead of being folded together.
  const spreadPicks = leagueFiltered.filter(function(p){ return p.type==='spread'; });
  const totalPicks = leagueFiltered.filter(function(p){ return p.type==='total'; });
  const propPicks = leagueFiltered.filter(function(p){ return p.type==='player_prop'; });
  const summaryEl = document.getElementById('track-record-summary');
  if(summaryEl){
    summaryEl.textContent = summaryLine(summarizePicks(leagueFiltered));
  }
  const splitEl = document.getElementById('track-record-split');
  if(splitEl){
    splitEl.innerHTML = '<div class="history-item"><span>Spread / ML</span><span>'+summaryLine(summarizePicks(spreadPicks))+'</span></div>'+
      '<div class="history-item"><span>Over / Under</span><span>'+summaryLine(summarizePicks(totalPicks))+'</span></div>'+
      '<div class="history-item"><span>Player props (real sportsbook line)</span><span>'+summaryLine(summarizePicks(propPicks.filter(function(p){ return p.used_real_line; })))+'</span></div>'+
      '<div class="history-item"><span>Player props (model-only line)</span><span>'+summaryLine(summarizePicks(propPicks.filter(function(p){ return !p.used_real_line; })))+'</span></div>'+
      clvRowHtml(leagueFiltered);
  }

  // By strength -- confirmed live this was a real, separate ask from the
  // live "this week by strength" view: seeing how each confidence tier
  // has actually graded historically, not just this week's upcoming
  // picks. Older picks logged before the tier/strength fields existed
  // (and anything track_predictions.py's backfill hasn't reached yet)
  // show in their own "Not yet labeled" bucket rather than being
  // silently dropped or miscounted into one of the real tiers.
  const strengthEl = document.getElementById('track-record-by-strength');
  if(strengthEl){
    const strongPicks = leagueFiltered.filter(function(p){ return p.strength==='Strong'; });
    const mediumPicks = leagueFiltered.filter(function(p){ return p.strength==='Medium'; });
    const lowPicks = leagueFiltered.filter(function(p){ return p.strength==='Low'; });
    const unlabeledPicks = leagueFiltered.filter(function(p){ return !p.strength; });
    strengthEl.innerHTML = '<div class="history-item"><span>Strong</span><span>'+summaryLine(summarizePicks(strongPicks))+'</span></div>'+
      '<div class="history-item"><span>Medium</span><span>'+summaryLine(summarizePicks(mediumPicks))+'</span></div>'+
      '<div class="history-item"><span>Low</span><span>'+summaryLine(summarizePicks(lowPicks))+'</span></div>'+
      (unlabeledPicks.length ? '<div class="history-item"><span>Not yet labeled</span><span>'+summaryLine(summarizePicks(unlabeledPicks))+'</span></div>' : '');
  }

  // Weekly breakdown -- grouped by the week label already stored on each
  // pick, sorted most-recent-first using each week's latest date_logged
  // as a stand-in for chronological order (week labels aren't a uniform
  // sortable format between NFL "NFL-WeekN" and CFB's date-based labels).
  const weeklyEl = document.getElementById('track-record-weekly');
  if(weeklyEl){
    const byWeek = {};
    leagueFiltered.forEach(function(p){
      const wk = p.week || 'Unknown';
      if(!byWeek[wk]) byWeek[wk] = { picks: [], maxDate: '' };
      byWeek[wk].picks.push(p);
      if((p.date_logged||'') > byWeek[wk].maxDate) byWeek[wk].maxDate = p.date_logged || '';
    });
    const weeks = Object.keys(byWeek).sort(function(a,b){ return byWeek[b].maxDate.localeCompare(byWeek[a].maxDate); });
    if(weeks.length===0){
      weeklyEl.innerHTML = '<div class="empty">No weeks logged yet.</div>';
    } else {
      weeklyEl.innerHTML = weeks.map(function(wk){
        const wkPicks = byWeek[wk].picks;
        const wkSpread = wkPicks.filter(function(p){ return p.type==='spread'; });
        const wkTotal = wkPicks.filter(function(p){ return p.type==='total'; });
        const wkProp = wkPicks.filter(function(p){ return p.type==='player_prop'; });
        return '<div class="history-item"><span>'+wk+'</span><span>Spread: '+summaryLine(summarizePicks(wkSpread))+' · O/U: '+summaryLine(summarizePicks(wkTotal))+' · Props: '+summaryLine(summarizePicks(wkProp))+'</span></div>';
      }).join('');
    }
  }

  const list = document.getElementById('track-record-list');
  if(filtered.length===0){
    list.innerHTML = '<div class="empty">'+(trackStatusFilter==='FINISHED' ? 'No finished picks yet — check back once this week\'s games are played.' : 'No picks logged yet — these get added automatically each week.')+'</div>';
    return;
  }
  // Sorting by date_logged alone buries finished bets: hundreds of new
  // pending picks get logged every week, so a plain "most recent" sort is
  // almost entirely this week's fresh pending picks -- confirmed by the
  // user noticing finished bets had effectively disappeared from the list
  // even though the summary stats above still counted them correctly.
  // When specifically viewing Finished, sort by graded_date (when a
  // result actually came in) instead, so the most recently DECIDED bets
  // show up first regardless of how many new pending ones got logged since.
  const sortKey = trackStatusFilter==='FINISHED' ? 'graded_date' : 'date_logged';
  const sorted = filtered.slice().sort(function(a,b){ return (b[sortKey]||'').localeCompare(a[sortKey]||''); });
  const RENDER_CAP = 150; // full-season volume (1000+ picks/week between team bets and player props) would be a heavy DOM render on mobile -- this caps the raw list to the most recent picks; the weekly/all-time summaries above still reflect every pick, capped or not
  const capped = sorted.slice(0, RENDER_CAP);
  const capNote = sorted.length > RENDER_CAP ? '<div class="note">Showing the '+RENDER_CAP+' most recently '+(trackStatusFilter==='FINISHED'?'graded':'logged')+' of '+sorted.length+' picks — the summaries above include all of them.</div>' : '';
  list.innerHTML = capNote + capped.map(function(p){
    const statusColor = p.status==='hit' ? '#5eead4' : (p.status==='miss' ? '#f28b7d' : (p.status==='push' ? 'var(--muted)' : 'var(--accent)'));
    const statusLabel = p.status==='pending' ? 'Pending' : p.status.charAt(0).toUpperCase()+p.status.slice(1);
    const dateInfo = p.status==='pending' ? 'logged '+p.date_logged : 'graded '+(p.graded_date||'—');
    const detail = p.type==='player_prop' ? p.matchup+' · '+p.week+' · '+dateInfo : p.matchup+' · '+p.week+' · edge '+fmt(p.edge)+' · '+dateInfo;
    return '<div class="team-row"><div><div class="team-name">'+p.label+' <span class="pill">'+p.league+'</span></div><div class="team-meta">'+detail+'</div></div><div style="color:'+statusColor+';font-weight:700;font-size:0.85rem;">'+statusLabel+'</div></div>';
  }).join('');
}

// ---- Weekly Top Bets tracker (separate record from the main Track Record) ----
let weeklyFilter = 'ALL';
async function renderWeeklyTracker(){
  const data = await fetchJSON('./data/best-per-game.json');
  const all = (data && data.picks) ? data.picks : [];
  const picks = weeklyFilter==='ALL' ? all : all.filter(function(p){ return p.league===weeklyFilter; });
  const sumEl = document.getElementById('weekly-summary');
  const weekEl = document.getElementById('weekly-by-week');
  const listEl = document.getElementById('weekly-list');
  if(!sumEl) return;
  if(!all.length){
    sumEl.className='empty'; sumEl.textContent='No picks logged yet. They start appearing after the next data update, and grade after the games finish.';
    weekEl.className='empty'; weekEl.textContent='Nothing yet.';
    listEl.className='empty'; listEl.textContent='Nothing yet.';
    return;
  }
  function rec(list){
    const done = list.filter(function(p){ return p.status==='hit' || p.status==='miss'; });
    const hits = done.filter(function(p){ return p.status==='hit'; }).length;
    const pushes = list.filter(function(p){ return p.status==='push'; }).length;
    const pending = list.filter(function(p){ return p.status==='pending'; }).length;
    return {hits:hits, misses:done.length-hits, pushes:pushes, pending:pending, n:done.length, pct: done.length ? Math.round(hits/done.length*100) : null};
  }
  function recHtml(label, r){
    const color = r.pct===null ? 'var(--muted,#888)' : (r.pct>=55 ? '#2e9e5b' : (r.pct>=50 ? '#c98a00' : '#d64545'));
    return '<div class="team-row"><div><div class="team-name">'+label+'</div><div class="team-meta">'+r.hits+'-'+r.misses+(r.pushes?'-'+r.pushes+' push':'')+' · '+r.pending+' pending</div></div><div style="color:'+color+';font-weight:700;">'+(r.pct===null?'—':r.pct+'%')+'</div></div>';
  }
  const kinds = [['Spread','Spread'],['Moneyline','Moneyline'],['Total','Total'],['Player prop','Player props']];
  const parts = [recHtml('Overall', rec(picks))];
  const teamOnly = picks.filter(function(p){ return p.type!=='player_prop'; });
  parts.push(recHtml('All team bets', rec(teamOnly)));
  kinds.forEach(function(k){
    const sub = picks.filter(function(p){ return p.kind===k[0]; });
    if(sub.length) parts.push(recHtml(k[1], rec(sub)));
  });
  if(weeklyFilter==='ALL'){
    ['NFL','CFB'].forEach(function(lg){
      const sub = all.filter(function(p){ return p.league===lg; });
      if(sub.length) parts.push(recHtml(lg==='CFB'?'College':'NFL', rec(sub)));
    });
  }
  const graded = rec(picks).n;
  sumEl.className='';
  sumEl.innerHTML = parts.join('') + (graded<30 ? '<div class="note">Only '+graded+' graded so far, so these percentages can swing a lot. Treat them as a trend, not a verdict, until there are 30+.</div>' : '');

  const byWeek = {};
  picks.forEach(function(p){ (byWeek[p.week] = byWeek[p.week] || []).push(p); });
  const weeks = Object.keys(byWeek).sort(function(a,b){
    const da = byWeek[a].reduce(function(m,p){ return p.date>m?p.date:m; },'');
    const db = byWeek[b].reduce(function(m,p){ return p.date>m?p.date:m; },'');
    return da<db?1:-1;
  });
  weekEl.className='';
  weekEl.innerHTML = weeks.map(function(w){ return recHtml(w, rec(byWeek[w])); }).join('');

  const sorted = picks.slice().sort(function(a,b){ return a.date<b.date?1:(a.date>b.date?-1:0); });
  listEl.className='';
  listEl.innerHTML = sorted.map(function(p){
    const color = p.status==='hit' ? '#2e9e5b' : (p.status==='miss' ? '#d64545' : (p.status==='push' ? '#c98a00' : 'var(--muted,#888)'));
    const label = p.status.charAt(0).toUpperCase()+p.status.slice(1);
    const extra = p.prob ? ' · '+Math.round(p.prob*100)+'% est' : '';
    return '<div class="team-row"><div><div class="team-name">'+p.label+' <span class="pill">'+p.league+'</span> <span class="pill">'+p.kind+'</span></div><div class="team-meta">'+p.matchup+' · '+p.week+extra+'</div></div><div style="color:'+color+';font-weight:700;font-size:0.85rem;">'+label+'</div></div>';
  }).join('');
}
document.querySelectorAll('#weekly-filter [data-weeklyfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    weeklyFilter = btn.dataset.weeklyfilter;
    document.querySelectorAll('#weekly-filter [data-weeklyfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderWeeklyTracker();
  });
});
document.querySelectorAll('[data-subtab="track-weekly"]').forEach(function(t){ t.addEventListener('click', renderWeeklyTracker); });
document.querySelectorAll('#track-filter [data-trackfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    trackFilter = btn.dataset.trackfilter;
    document.querySelectorAll('#track-filter [data-trackfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderTrackRecord();
  });
});
document.querySelectorAll('#track-season-filter [data-trackseasonfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    trackSeasonFilter = btn.dataset.trackseasonfilter;
    document.querySelectorAll('#track-season-filter [data-trackseasonfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderTrackRecord();
  });
});
document.querySelectorAll('#track-type-filter [data-tracktypefilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    trackTypeFilter = btn.dataset.tracktypefilter;
    document.querySelectorAll('#track-type-filter [data-tracktypefilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderTrackRecord();
  });
});
document.querySelectorAll('#track-strength-filter [data-trackstrengthfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    trackStrengthFilter = btn.dataset.trackstrengthfilter;
    document.querySelectorAll('#track-strength-filter [data-trackstrengthfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderTrackRecord();
  });
});
document.querySelectorAll('#track-status-filter [data-trackstatusfilter]').forEach(function(btn){
  btn.addEventListener('click', function(){
    trackStatusFilter = btn.dataset.trackstatusfilter;
    document.querySelectorAll('#track-status-filter [data-trackstatusfilter]').forEach(function(b){ b.classList.toggle('active', b===btn); });
    renderTrackRecord();
  });
});