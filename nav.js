/* nav.js -- navigation, search and "find things fast" layer.
   Loaded last (after app1/app2/app3). It only wraps/overrides the small
   navigation + search functions; the betting logic is untouched.
   Adds: Games tab with NFL/College switch, search across everything,
   "filter this page" bar, remembered position + back button, collapsible
   explainer cards, back-to-top button. */
(function(){
'use strict';

// ---------- styles ----------
var css = ''
+ '.tabs{flex-wrap:wrap;overflow:visible;}'
+ '.league-switch{display:flex;gap:6px;margin-bottom:10px;}'
+ '.league-switch span{flex:1;text-align:center;padding:9px 6px;border-radius:10px;background:var(--card);border:1px solid var(--line);color:var(--muted);font-weight:700;font-size:0.88rem;cursor:pointer;}'
+ '.league-switch span.active{background:var(--card-2);color:var(--accent);border-color:var(--accent);}'
+ '.pagefilter{margin:0 0 12px;}'
+ '.pagefilter-row{position:relative;}'
+ '.pagefilter input{width:100%;padding:9px 34px 9px 12px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:0.85rem;}'
+ '.pagefilter .pf-clear{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:transparent;color:var(--muted);border:none;font-size:1.1rem;padding:4px 8px;margin:0;display:none;}'
+ '.pagefilter.has-text .pf-clear{display:block;}'
+ '.pf-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;}'
+ '.pf-chip{padding:5px 11px;border-radius:999px;background:var(--card);border:1px solid var(--line);color:var(--muted);font-size:0.74rem;font-weight:600;cursor:pointer;}'
+ '.pf-chip.on{background:var(--accent);color:var(--accent-ink);border-color:var(--accent);}'
+ '.pf-count{color:var(--muted);font-size:0.72rem;margin-top:6px;}'
+ '.pf-hidden{display:none !important;}'
+ '.collapse-h{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px;}'
+ '.collapse-h::after{content:"\\25B8  info";font-size:0.7rem;font-weight:600;color:var(--muted);}'
+ '.collapse-h.open::after{content:"\\25BE  hide";}'
+ '.collapse-body{display:none;margin-top:10px;}'
+ '.collapse-body.open{display:block;}'
+ '#to-top{position:fixed;right:14px;bottom:calc(var(--nav-h,70px) + 76px);z-index:70;width:42px;height:42px;border-radius:50%;background:var(--card-2);color:var(--ink);border:1px solid var(--line);font-size:1.1rem;display:none;align-items:center;justify-content:center;margin:0;padding:0;box-shadow:0 6px 18px rgba(0,0,0,.45);}'
+ '#to-top.show{display:flex;}'
+ '.search-results{max-height:68vh;}'
+ '.search-group{padding:7px 12px 3px;font-size:0.68rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:var(--card-2);position:sticky;top:0;}'
+ '.search-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);background:transparent;color:var(--muted);border:none;font-size:1.2rem;padding:4px 8px;margin:0;display:none;}'
+ '.search-wrap.has-text .search-clear{display:block;}'
+ '.search-input{padding-right:36px;}'
+ '@media (max-width:767px){.pf-chip{font-size:0.85rem;padding:8px 14px;}.pagefilter input{font-size:1rem;padding:12px 36px 12px 14px;}.league-switch span{font-size:1.05rem;padding:14px 6px;}.tabs .subtab{font-size:0.95rem;padding:10px 15px;}.search-input{font-size:1rem;}}';
var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

function $(s, r){ return (r||document).querySelector(s); }
function $$(s, r){ return Array.prototype.slice.call((r||document).querySelectorAll(s)); }
function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
function store(k, v){ try{ if(v===undefined) return localStorage.getItem(k); localStorage.setItem(k, v); }catch(e){ return null; } }

// ---------- bottom nav: merge NFL + CFB into one "Games" tab ----------
var nflItem = $('.bottom-nav-item[data-tab="nfl"]'), cfbItem = $('.bottom-nav-item[data-tab="cfb"]');
if(nflItem && cfbItem){
  nflItem.setAttribute('data-tab', 'games');
  var lbl = nflItem.querySelectorAll('span'); if(lbl[1]) lbl[1].textContent = 'Games';
  cfbItem.parentNode.removeChild(cfbItem);
}
var lastLeague = store('mr_last_league') === 'cfb' ? 'cfb' : 'nfl';
var LEAGUE_PANELS = {nfl:1, cfb:1};

// ---------- league switch inside the NFL / CFB panels ----------
['nfl','cfb'].forEach(function(lg){
  var panel = $('#panel-'+lg); if(!panel) return;
  var sw = document.createElement('div'); sw.className = 'league-switch'; sw.setAttribute('data-league-switch', lg);
  sw.innerHTML = '<span data-league="nfl">🏈 NFL</span><span data-league="cfb">🎓 College</span>';
  panel.insertBefore(sw, panel.firstChild);
  $$('span', sw).forEach(function(sp){
    sp.addEventListener('click', function(){
      var target = sp.dataset.league;
      if(target === currentLeagueOfPanel()) return;
      var cur = currentSub();
      var suffix = cur ? cur.replace(/^(nfl|cfb)-/, '') : 'week';
      window.activateTopTab(target);
      if($('[data-subtab="'+target+'-'+suffix+'"]')) window.activateSubTab(target+'-'+suffix);
    });
  });
});
function currentLeagueOfPanel(){ return $('#panel-nfl.active') ? 'nfl' : ($('#panel-cfb.active') ? 'cfb' : null); }
function activePanel(){ return $('.leaguepanel.active'); }
function currentTab(){ var p = activePanel(); return p ? p.id.replace('panel-','') : 'home'; }
function currentSub(){
  var p = activePanel(); if(!p) return null;
  var sp = $('.subpanel.active', p); return sp ? sp.id.replace('subpanel-','') : null;
}

// ---------- wrap the core nav functions ----------
var origTop = window.activateTopTab, origSub = window.activateSubTab;
var applyingHash = false;
window.activateTopTab = function(name){
  if(name === 'games') name = lastLeague;
  if(LEAGUE_PANELS[name]){ lastLeague = name; store('mr_last_league', name); }
  origTop(name);
  var navKey = LEAGUE_PANELS[name] ? 'games' : name;
  $$('.bottom-nav-item[data-tab]').forEach(function(t){ t.classList.toggle('active', t.dataset.tab === navKey); });
  afterNav(true);
};
window.activateSubTab = function(name){
  origSub(name);
  afterNav(true);
};
function afterNav(resetFilter){
  $$('.league-switch').forEach(function(sw){
    var lg = currentLeagueOfPanel();
    $$('span', sw).forEach(function(sp){ sp.classList.toggle('active', sp.dataset.league === lg); });
  });
  if(resetFilter) clearPageFilter(true);
  updateFilterBars();
  if(!applyingHash){
    var h = '#'+currentTab()+(currentSub()?'/'+currentSub():'');
    if(location.hash !== h){ try{ history.pushState(null, '', h); }catch(e){} }
    window.scrollTo(0, 0);
  }
}
function applyHash(){
  var m = /^#([a-z]+)(?:\/([a-z0-9-]+))?$/.exec(location.hash || '');
  if(!m || !$('#panel-'+m[1])) return;
  applyingHash = true;
  try{
    window.activateTopTab(m[1]);
    if(m[2] && $('[data-subtab="'+m[2]+'"]')) window.activateSubTab(m[2]);
  } finally { applyingHash = false; }
}
window.addEventListener('popstate', applyHash);

// ---------- "filter this page" bar ----------
var NO_FILTER_SUBS = {'nfl-matchup':1,'cfb-matchup':1,'parlay-calc':1,'nfl-trends':1,'cfb-trends':1};
var pfText = '';
var CHIPS = {topbets:['Strong','Over','Under','ML','Real line'], track:['Hit','Miss','Pending'], nfl:[], cfb:[], parlay:[]};
$$('.leaguepanel').forEach(function(panel){
  var key = panel.id.replace('panel-','');
  if(key === 'home') return;
  var tabs = $('.tabs', panel); if(!tabs) return;
  var bar = document.createElement('div'); bar.className = 'pagefilter'; bar.setAttribute('data-pf', key);
  var chips = (CHIPS[key]||[]).map(function(c){ return '<span class="pf-chip" data-chip="'+esc(c)+'">'+esc(c)+'</span>'; }).join('');
  bar.innerHTML = '<div class="pagefilter-row"><input type="text" placeholder="Filter this page (team, player, bet...)" autocomplete="off"><button class="pf-clear" aria-label="Clear filter">×</button></div>'
    + (chips ? '<div class="pf-chips">'+chips+'</div>' : '') + '<div class="pf-count"></div>';
  tabs.parentNode.insertBefore(bar, tabs.nextSibling);
  var input = $('input', bar);
  input.addEventListener('input', function(){ pfText = input.value; applyPageFilter(); });
  $('.pf-clear', bar).addEventListener('click', function(){ clearPageFilter(false); input.focus(); });
  $$('.pf-chip', bar).forEach(function(ch){
    ch.addEventListener('click', function(){ setPageFilter(pfText.toLowerCase() === ch.dataset.chip.toLowerCase() ? '' : ch.dataset.chip); });
  });
});
function updateFilterBars(){
  var sub = currentSub();
  $$('.pagefilter').forEach(function(b){
    var panel = b.closest('.leaguepanel');
    b.style.display = (panel && panel.classList.contains('active') && !NO_FILTER_SUBS[sub]) ? '' : 'none';
  });
}
function filterBarInput(){ var b = $('.leaguepanel.active .pagefilter'); return b ? $('input', b) : null; }
function setPageFilter(text){
  pfText = text || '';
  var inp = filterBarInput(); if(inp) inp.value = pfText;
  applyPageFilter();
}
function clearPageFilter(silent){
  pfText = '';
  $$('.pagefilter input').forEach(function(i){ i.value = ''; });
  applyPageFilter();
}
var ITEM_SEL = '.team-row, .game-row, .rank-row, .history-item, [data-filter-item]';
function applyPageFilter(){
  var panel = activePanel(); if(!panel) return;
  var sub = $('.subpanel.active', panel) || panel;
  var q = pfText.trim().toLowerCase();
  var tokens = q ? q.split(/\s+/) : [];
  $$('.pagefilter', panel).forEach(function(b){ b.classList.toggle('has-text', !!q); });
  $$('.pf-chip', panel).forEach(function(c){ c.classList.toggle('on', !!q && c.dataset.chip.toLowerCase() === q); });
  // reset everything first
  $$('.pf-hidden', sub).forEach(function(e){ e.classList.remove('pf-hidden'); });
  var count = $('.pf-count', panel);
  if(!q || NO_FILTER_SUBS[currentSub()]){ if(count) count.textContent = ''; return; }
  var items = $$(ITEM_SEL, sub).filter(function(el){
    // rows inside an atomic filter item (like a parlay card) are not filtered on their own
    var host = el.parentElement && el.parentElement.closest('[data-filter-item]');
    return !host || !sub.contains(host);
  });
  var shown = 0;
  items.forEach(function(el){
    var txt = (el.textContent || '').toLowerCase();
    var ok = tokens.every(function(t){ return txt.indexOf(t) !== -1; });
    if(ok) shown++; else el.classList.add('pf-hidden');
  });
  // hide cards whose rows are all filtered out
  $$('.card', sub).forEach(function(card){
    if(card.hasAttribute('data-filter-item')) return;
    var rows = $$(ITEM_SEL, card);
    if(rows.length && rows.every(function(r){ return r.classList.contains('pf-hidden') || (r.closest('.pf-hidden') !== null); })){
      card.classList.add('pf-hidden');
    }
  });
  if(count) count.textContent = shown ? ('Showing '+shown+' of '+items.length+' matching “'+pfText.trim()+'”') : ('No matches for “'+pfText.trim()+'” on this page');
}
var pfTimer = null, pfBusy = false;
new MutationObserver(function(){
  if(pfBusy || !pfText) return;
  clearTimeout(pfTimer);
  pfTimer = setTimeout(function(){ pfBusy = true; try{ applyPageFilter(); } finally { setTimeout(function(){ pfBusy = false; }, 0); } }, 200);
}).observe($('.wrap'), {childList:true, subtree:true});

// ---------- collapsible explainer cards ----------
var HOW = /^(How this|Recommended parlays|Weekly Top Bets record|Recommended parlay record)/;
function collapseExplainers(){
  $$('.card > h2').forEach(function(h){
    if(h.dataset.collapsible || !HOW.test(h.textContent.trim())) return;
    var card = h.parentElement; if(card.querySelector('input,select,button,table')) return;
    h.dataset.collapsible = '1';
    var body = document.createElement('div'); body.className = 'collapse-body';
    while(h.nextSibling){ body.appendChild(h.nextSibling); }
    card.appendChild(body);
    h.classList.add('collapse-h');
    var key = 'mr_open_' + h.textContent.trim().slice(0, 40);
    if(store(key) === '1'){ h.classList.add('open'); body.classList.add('open'); }
    h.addEventListener('click', function(){
      var open = !body.classList.contains('open');
      body.classList.toggle('open', open); h.classList.toggle('open', open); store(key, open ? '1' : '0');
    });
    card.style.paddingBottom = '12px';
  });
}
collapseExplainers();

// ---------- back to top ----------
var topBtn = document.createElement('button'); topBtn.id = 'to-top'; topBtn.setAttribute('aria-label', 'Back to top'); topBtn.textContent = '↑';
document.body.appendChild(topBtn);
topBtn.addEventListener('click', function(){ window.scrollTo({top:0, behavior:'smooth'}); });
window.addEventListener('scroll', function(){ topBtn.classList.toggle('show', window.scrollY > 700); }, {passive:true});

// ---------- universal search ----------
var PAGES = [
  {t:'Home', k:'home start overview', tab:'home'},
  {t:'NFL – This Week (schedule)', k:'nfl schedule games week odds lines', tab:'nfl', sub:'nfl-week'},
  {t:'NFL – Teams', k:'nfl teams standings record rankings', tab:'nfl', sub:'nfl-teams'},
  {t:'NFL – Matchup analyzer', k:'nfl matchup compare projection analyze', tab:'nfl', sub:'nfl-matchup'},
  {t:'NFL – Players & hit rate checker', k:'nfl players hit rate prop stats roster checker line', tab:'nfl', sub:'nfl-players'},
  {t:'NFL – Trends', k:'nfl trends history', tab:'nfl', sub:'nfl-trends'},
  {t:'NFL – Injury report', k:'nfl injuries injury report out questionable doubtful', tab:'nfl', sub:'nfl-injuries'},
  {t:'College – This Week (schedule)', k:'cfb college ncaa schedule games week odds lines', tab:'cfb', sub:'cfb-week'},
  {t:'College – Rankings (AP poll)', k:'cfb college ncaa rankings ap poll top 25', tab:'cfb', sub:'cfb-rankings'},
  {t:'College – Teams', k:'cfb college ncaa teams record', tab:'cfb', sub:'cfb-teams'},
  {t:'College – Matchup analyzer', k:'cfb college ncaa matchup compare projection analyze', tab:'cfb', sub:'cfb-matchup'},
  {t:'College – Players & hit rate checker', k:'cfb college ncaa players hit rate prop stats roster', tab:'cfb', sub:'cfb-players'},
  {t:'College – Trends', k:'cfb college ncaa trends history', tab:'cfb', sub:'cfb-trends'},
  {t:'College – Injuries', k:'cfb college ncaa injuries', tab:'cfb', sub:'cfb-injuries'},
  {t:'Top Bets – Team bets (by strength, top 10)', k:'top bets picks recommended spread total moneyline strength strong edge', tab:'topbets', sub:'topbets-team'},
  {t:'Top Bets – Best per game', k:'best per game top pick each game', tab:'topbets', sub:'topbets-bygame'},
  {t:'Top Bets – Player props', k:'player props prop bets yards touchdowns', tab:'topbets', sub:'topbets-player'},
  {t:'Top Bets – Recommended parlays', k:'recommended parlays parlay picks weekly', tab:'topbets', sub:'topbets-parlays'},
  {t:'Parlay – Odds board', k:'odds board lines sportsbook books compare', tab:'parlay', sub:'odds-board'},
  {t:'Parlay – Calculator & check a bet', k:'parlay calculator slip check a bet alt lines payout analyzer probability', tab:'parlay', sub:'parlay-calc'},
  {t:'Parlay – My Bets (placed bets)', k:'my bets placed bets tracker history profit', tab:'parlay', sub:'my-bets'},
  {t:'Track – All picks record', k:'track record accuracy hit rate history graded picks', tab:'track', sub:'track-all'},
  {t:'Track – Weekly top bets record', k:'track weekly top bets best per game record', tab:'track', sub:'track-weekly'},
  {t:'Track – Parlay record', k:'track parlay record units profit', tab:'track', sub:'track-parlays'}
].filter(function(p){ return p.tab === 'home' || !p.sub || $('[data-subtab="'+p.sub+'"]'); });

var betCache = {t:0, bets:[]};
function topBetsCached(){
  if(Date.now() - betCache.t < 60000) return betCache.bets;
  var bets = [];
  try{
    if(typeof computeTopBets === 'function'){
      computeTopBets(NFL_WEEK_GAMES, 'NFL').forEach(function(b){ bets.push({b:b, lg:'NFL'}); });
      computeTopBets(CFB_WEEK_GAMES, 'CFB').forEach(function(b){ bets.push({b:b, lg:'CFB'}); });
    }
  }catch(e){}
  betCache = {t: Date.now(), bets: bets};
  return bets;
}
function tokensMatch(text, tokens){ var t = text.toLowerCase(); return tokens.every(function(x){ return t.indexOf(x) !== -1; }); }
function wordPrefixMatch(text, tokens){ var words = text.toLowerCase().split(/[^a-z0-9]+/); return tokens.every(function(x){ return words.some(function(w){ return w.indexOf(x) === 0; }); }); }
function rankByStart(list, tokens){
  return list.sort(function(a, b){
    var q = tokens.join(' ');
    var sa = a.name.toLowerCase() === q ? 0 : (wordPrefixMatch(a.name, tokens) ? 1 : 2), sb = b.name.toLowerCase() === q ? 0 : (wordPrefixMatch(b.name, tokens) ? 1 : 2);
    return sa - sb;
  });
}
function quickLinks(){
  return [PAGES[3], PAGES[14], PAGES[21], PAGES[19], PAGES[6], PAGES[22]].filter(Boolean).map(function(p){ return {type:'page', name:p.t, meta:'Jump to', tab:p.tab, sub:p.sub}; });
}
window.performGlobalSearch = function(query){
  var q = (query||'').trim().toLowerCase();
  if(q.length < 2) return [];
  var tokens = q.split(/\s+/), out = [];
  // pages
  PAGES.forEach(function(p){ if(wordPrefixMatch(p.t+' '+p.k, tokens)) out.push({type:'page', name:p.t, meta:'Jump to this section', tab:p.tab, sub:p.sub}); });
  var pages = out.slice(0, 4); out = [];
  // games this week
  var games = [];
  [['NFL', typeof NFL_WEEK_GAMES !== 'undefined' ? NFL_WEEK_GAMES : []], ['CFB', typeof CFB_WEEK_GAMES !== 'undefined' ? CFB_WEEK_GAMES : []]].forEach(function(pair){
    (pair[1]||[]).forEach(function(g){
      if(tokensMatch(g.a+' vs '+g.b, tokens)) games.push({type:'game', league:pair[0], name:g.a+' vs '+g.b, meta:pair[0]+' · '+(g.date||'')+(g.awayScore!=null?' · final '+g.awayScore+'-'+g.homeScore:''), g:g});
    });
  });
  // teams / players
  var teams = [], players = [];
  Object.keys(teamsCache||{}).forEach(function(name){
    if(tokensMatch(name, tokens)){ var t = teamsCache[name]; teams.push({type:'team', league:t.league, name:name, meta:t.league+(t.conf?' · '+t.conf:'')+(t.record?' · '+t.record:'')}); }
  });
  Object.keys(playersCache||{}).forEach(function(name){
    if(tokensMatch(name, tokens)){ var p = playersCache[name]; players.push({type:'player', league:p.league, name:name, meta:p.league+' · '+p.pos+(p.team?' · '+p.team:'')}); }
  });
  // this week's bets
  var bets = [];
  topBetsCached().forEach(function(x){
    var txt = x.b.label+' '+(x.b.sub||'');
    if(tokensMatch(txt, tokens)) bets.push({type:'bet', league:x.lg, name:x.b.label, meta:x.lg+' · '+(x.b.tier?x.b.tier.label+' · ':'')+'edge '+(typeof fmt==='function'?fmt(x.b.edge):x.b.edge), q:q});
  });
  // tracked picks (newest first)
  var picks = [];
  (typeof TRACK_RECORD_PICKS !== 'undefined' ? TRACK_RECORD_PICKS : []).slice().reverse().forEach(function(p){
    if(picks.length >= 5) return;
    if(tokensMatch((p.label||'')+' '+(p.matchup||''), tokens)) picks.push({type:'pick', league:p.league, name:p.label, meta:'Tracked · '+(p.matchup||'')+' · '+(p.status||'pending'), q:q});
  });
  return [].concat(pages, rankByStart(games, tokens).slice(0,4), rankByStart(teams, tokens).slice(0,5), rankByStart(players, tokens).slice(0,6), bets.slice(0,5), picks);
};
var TYPE_LABEL = {page:'Go to', game:'Games', team:'Teams', player:'Players', bet:'This week’s bets', pick:'Tracked picks'};
var lastResults = [];
window.renderSearchResults = function(results, emptyMode){
  var el = $('#global-search-results'); if(!el) return;
  lastResults = results;
  var wrap = $('.search-wrap');
  var inp = $('#global-search');
  if(wrap) wrap.classList.toggle('has-text', !!(inp && inp.value));
  if(!results.length){
    if(inp && inp.value.trim().length >= 2){ el.innerHTML = '<div class="search-result-row" style="cursor:default;"><div class="search-result-meta">No matches. Try a team, player, or a section like “injuries”.</div></div>'; el.classList.add('open'); }
    else { el.classList.remove('open'); el.innerHTML = ''; }
    return;
  }
  var html = '', lastType = null;
  results.forEach(function(r, i){
    var head = emptyMode ? (r.type === 'recent' ? 'Recent' : 'Quick links') : TYPE_LABEL[r.type];
    var gt = emptyMode ? head : r.type;
    if(gt !== lastType){ html += '<div class="search-group">'+esc(head)+'</div>'; lastType = gt; }
    html += '<div class="search-result-row" data-result-idx="'+i+'"><div><div class="search-result-name">'+esc(r.name)+'</div><div class="search-result-meta">'+esc(r.meta||'')+'</div></div></div>';
  });
  el.innerHTML = html; el.classList.add('open');
  $$('[data-result-idx]', el).forEach(function(row){
    row.addEventListener('click', function(){ window.goToSearchResult(results[Number(row.dataset.resultIdx)]); });
  });
};
function remember(r){
  if(r.type === 'page' && !r.sub && r.tab === 'home') return;
  try{
    var list = JSON.parse(store('mr_recent_search_v1') || '[]').filter(function(x){ return !(x.name === r.name && x.type === r.type); });
    list.unshift({type:r.type, name:r.name, meta:r.meta, league:r.league, tab:r.tab, sub:r.sub, q:r.q, g:r.g});
    store('mr_recent_search_v1', JSON.stringify(list.slice(0, 5)));
  }catch(e){}
}
window.goToSearchResult = function(r){
  var resultsEl = $('#global-search-results'); if(resultsEl) resultsEl.classList.remove('open');
  var inputEl = $('#global-search'); if(inputEl){ inputEl.value = ''; inputEl.blur(); }
  var wrap = $('.search-wrap'); if(wrap) wrap.classList.remove('has-text');
  remember(r);
  var lg = (r.league||'').toLowerCase();
  if(r.type === 'page'){
    window.activateTopTab(r.tab); if(r.sub) window.activateSubTab(r.sub);
  } else if(r.type === 'team'){
    window.activateTopTab(lg); window.activateSubTab(lg+'-teams'); renderTeamDetail(lg, r.name);
    var d = $('#'+lg+'-team-detail'); if(d) setTimeout(function(){ d.scrollIntoView({behavior:'smooth', block:'start'}); }, 50);
  } else if(r.type === 'player'){
    window.activateTopTab(lg); window.activateSubTab(lg+'-players'); renderPlayerDetail(lg, r.name);
    var d2 = $('#'+lg+'-player-detail'); if(d2) setTimeout(function(){ d2.scrollIntoView({behavior:'smooth', block:'start'}); }, 50);
  } else if(r.type === 'game' && r.g){
    var a = resolveTeamName(r.g.a), b = resolveTeamName(r.g.b);
    window.activateTopTab(lg); window.activateSubTab(lg+'-matchup');
    var sa = $('#m-teamA-'+lg), sb = $('#m-teamB-'+lg);
    if(sa && sb){ sa.value = a; sb.value = b; runMatchupFor(a, b, 'matchup-output-'+lg); }
  } else if(r.type === 'bet'){
    window.activateTopTab('topbets'); window.activateSubTab('topbets-team'); setPageFilter(r.name);
  } else if(r.type === 'pick'){
    window.activateTopTab('track'); window.activateSubTab('track-all'); setPageFilter(r.name);
  }
};
(function wireSearch(){
  var inp = $('#global-search'); if(!inp) return;
  inp.placeholder = 'Search teams, players, games, bets, sections...';
  var wrap = $('.search-wrap');
  var x = document.createElement('button'); x.className = 'search-clear'; x.setAttribute('aria-label', 'Clear search'); x.textContent = '×';
  wrap.appendChild(x);
  x.addEventListener('click', function(){ inp.value = ''; wrap.classList.remove('has-text'); showIdle(); inp.focus(); });
  function showIdle(){
    var recents = [];
    try{ recents = JSON.parse(store('mr_recent_search_v1') || '[]'); }catch(e){}
    var items = recents.map(function(r){ return Object.assign({}, r, {type: r.type, _recent:true}); });
    var rows = items.concat(quickLinks());
    // reuse the grouped renderer with simple headings
    var el = $('#global-search-results');
    var html = '';
    if(items.length){ html += '<div class="search-group">Recent</div>' + items.map(function(r,i){ return '<div class="search-result-row" data-idle="'+i+'"><div><div class="search-result-name">'+esc(r.name)+'</div><div class="search-result-meta">'+esc(r.meta||'')+'</div></div></div>'; }).join(''); }
    var ql = quickLinks();
    html += '<div class="search-group">Quick links</div>' + ql.map(function(r,i){ return '<div class="search-result-row" data-idle-q="'+i+'"><div><div class="search-result-name">'+esc(r.name)+'</div></div></div>'; }).join('');
    el.innerHTML = html; el.classList.add('open'); lastResults = [];
    $$('[data-idle]', el).forEach(function(row){ row.addEventListener('click', function(){ window.goToSearchResult(items[Number(row.dataset.idle)]); }); });
    $$('[data-idle-q]', el).forEach(function(row){ row.addEventListener('click', function(){ window.goToSearchResult(ql[Number(row.dataset.idleQ)]); }); });
  }
  inp.addEventListener('focus', function(){ if(!inp.value.trim()) showIdle(); });
  inp.addEventListener('input', function(){ if(!inp.value.trim()){ wrap.classList.remove('has-text'); showIdle(); } });
  inp.addEventListener('keydown', function(e){
    if(e.key === 'Enter' && lastResults.length){ window.goToSearchResult(lastResults[0]); }
    else if(e.key === 'Escape'){ $('#global-search-results').classList.remove('open'); inp.blur(); }
  });
  document.addEventListener('keydown', function(e){
    if(e.key === '/' && !/INPUT|SELECT|TEXTAREA/.test((document.activeElement||{}).tagName||'')){ e.preventDefault(); inp.focus(); }
  });
})();

// ---------- init ----------
applyingHash = true; afterNav(false); applyingHash = false;
applyHash();
// explainer cards created after first render (e.g. loaded lazily) get picked up too
setTimeout(collapseExplainers, 1500);
})();