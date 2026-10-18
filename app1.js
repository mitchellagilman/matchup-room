
const STORAGE_KEY = 'teams-db';
const SEED_FLAG_KEY = 'seeded-v6';
const PLAYERS_SEED_FLAG_KEY = 'players-seeded-v2';

function fmt(n){ return (Math.round(n*10)/10).toFixed(1); }
// The model's own projected spread/total (unlike a real market line, which
// almost never lands on a whole number for exactly this reason) is built
// from two whole-number score predictions, so it can land on an exact
// integer -- e.g. a projected 24-21 game is a flat "-3" spread. Displaying
// that as-is risks looking like a real bettable line that could push. This
// nudges by half a point ONLY for display -- it never touches proj.spread/
// proj.total themselves, so edge calculations and confidence tiers against
// the real market line are completely unaffected. A true pick'em (0) is
// left alone -- there's no real favorite to nudge toward.
function tieSafeLine(n){
  if(n===0) return 0;
  if(Number.isInteger(n)) return n>0 ? n+0.5 : n-0.5;
  return n;
}

const NFL_SEED = {
"Los Angeles Rams": {league:"NFL", ppg:30.5, pa:20.4, passOff:268.1, rushOff:126.6, passDef:216.7, rushDef:110.8, to:0.65, ats:""},
"Dallas Cowboys": {league:"NFL", ppg:27.7, pa:30.1, passOff:266.3, rushOff:125.6, passDef:251.5, rushDef:125.5, to:-0.53, ats:""},
"New England Patriots": {league:"NFL", ppg:28.8, pa:18.8, passOff:250.5, rushOff:128.9, passDef:193.5, rushDef:101.7, to:0.18, ats:""},
"Buffalo Bills": {league:"NFL", ppg:28.3, pa:21.5, passOff:216.6, rushOff:159.6, passDef:156.9, rushDef:136.2, to:0.06, ats:""},
"Detroit Lions": {league:"NFL", ppg:28.3, pa:24.3, passOff:253.1, rushOff:120.1, passDef:217.4, rushDef:114.5, to:0.24, ats:""},
"Chicago Bears": {league:"NFL", ppg:25.9, pa:24.4, passOff:225.1, rushOff:144.2, passDef:227.2, rushDef:134.5, to:1.29, ats:""},
"San Francisco 49ers": {league:"NFL", ppg:25.7, pa:21.8, passOff:244.5, rushOff:106.9, passDef:232.4, rushDef:107.8, to:-0.35, ats:""},
"Seattle Seahawks": {league:"NFL", ppg:28.4, pa:17.2, passOff:228.1, rushOff:123.3, passDef:193.9, rushDef:91.9, to:-0.18, ats:""},
"Indianapolis Colts": {league:"NFL", ppg:27.4, pa:24.2, passOff:227.8, rushOff:118.1, passDef:247.9, rushDef:101.9, to:-0.12, ats:""},
"Denver Broncos": {league:"NFL", ppg:23.6, pa:18.3, passOff:223.9, rushOff:118.7, passDef:187.2, rushDef:91.1, to:-0.18, ats:""},
"Jacksonville Jaguars": {league:"NFL", ppg:27.9, pa:19.8, passOff:222.3, rushOff:115.1, passDef:218.1, rushDef:85.6, to:0.76, ats:""},
"Los Angeles Chargers": {league:"NFL", ppg:21.6, pa:20.0, passOff:212.2, rushOff:121.6, passDef:179.9, rushDef:105.4, to:0.12, ats:""},
"New York Giants": {league:"NFL", ppg:22.4, pa:25.8, passOff:204.4, rushOff:129.1, passDef:214.2, rushDef:145.3, to:-0.12, ats:""},
"Atlanta Falcons": {league:"NFL", ppg:20.8, pa:23.6, passOff:207.2, rushOff:125.8, passDef:200.4, rushDef:126.2, to:0.29, ats:""},
"Green Bay Packers": {league:"NFL", ppg:23.0, pa:21.2, passOff:212.8, rushOff:119.8, passDef:194.1, rushDef:117.7, to:0.06, ats:""},
"Baltimore Ravens": {league:"NFL", ppg:24.9, pa:23.4, passOff:175.6, rushOff:156.6, passDef:247.9, rushDef:106.6, to:-0.18, ats:""},
"Cincinnati Bengals": {league:"NFL", ppg:24.4, pa:28.9, passOff:235.6, rushOff:93.6, passDef:233.8, rushDef:147.1, to:-0.18, ats:""},
"Houston Texans": {league:"NFL", ppg:23.8, pa:17.4, passOff:218.1, rushOff:108.9, passDef:183.5, rushDef:93.7, to:1.00, ats:""},
"Arizona Cardinals": {league:"NFL", ppg:20.9, pa:28.7, passOff:232.6, rushOff:93.1, passDef:230.8, rushDef:126.9, to:-0.12, ats:""},
"Kansas City Chiefs": {league:"NFL", ppg:21.3, pa:19.3, passOff:214.1, rushOff:106.6, passDef:195.8, rushDef:105.7, to:-0.06, ats:""},
"Tampa Bay Buccaneers": {league:"NFL", ppg:22.4, pa:24.2, passOff:205.9, rushOff:114.5, passDef:238.2, rushDef:99.1, to:0.41, ats:""},
"Washington Commanders": {league:"NFL", ppg:20.9, pa:26.5, passOff:184.1, rushOff:134.7, passDef:242.5, rushDef:141.5, to:-0.76, ats:""},
"New Orleans Saints": {league:"NFL", ppg:18.0, pa:22.5, passOff:219.3, rushOff:94.3, passDef:179.2, rushDef:120.6, to:-0.24, ats:""},
"Philadelphia Eagles": {league:"NFL", ppg:22.3, pa:19.1, passOff:194.3, rushOff:116.9, passDef:189.8, rushDef:124.4, to:0.35, ats:""},
"Pittsburgh Steelers": {league:"NFL", ppg:23.4, pa:22.8, passOff:202.4, rushOff:103.3, passDef:243.9, rushDef:113.1, to:0.71, ats:""},
"Miami Dolphins": {league:"NFL", ppg:20.4, pa:24.9, passOff:180.5, rushOff:120.2, passDef:216.4, rushDef:132.4, to:-0.24, ats:""},
"Carolina Panthers": {league:"NFL", ppg:18.3, pa:22.4, passOff:179.3, rushOff:116.3, passDef:203.9, rushDef:123.3, to:-0.12, ats:""},
"Minnesota Vikings": {league:"NFL", ppg:20.2, pa:19.6, passOff:166.7, rushOff:108.3, passDef:158.5, rushDef:124.1, to:-0.53, ats:""},
"New York Jets": {league:"NFL", ppg:17.6, pa:29.6, passOff:140.3, rushOff:123.3, passDef:216.1, rushDef:139.5, to:-1.12, ats:""},
"Cleveland Browns": {league:"NFL", ppg:16.4, pa:22.3, passOff:165.1, rushOff:97.0, passDef:167.2, rushDef:116.4, to:-0.41, ats:""},
"Tennessee Titans": {league:"NFL", ppg:16.7, pa:28.1, passOff:166.1, rushOff:93.5, passDef:230.5, rushDef:114.6, to:-0.29, ats:""},
"Las Vegas Raiders": {league:"NFL", ppg:14.2, pa:25.4, passOff:167.7, rushOff:77.5, passDef:201.0, rushDef:116.8, to:-0.41, ats:""}
};

const CFB_SEED = {
"Alabama": {league:"CFB", conf:"SEC", ppg:48, pa:14, passOff:263.5, rushOff:104.1, passDef:169.9, rushDef:126.9, to:0, ats:"", wk1:true},
"Arkansas": {league:"CFB", conf:"SEC", ppg:32.9, pa:33.8, passOff:262.9, rushOff:191.9, passDef:239.2, rushDef:185.9, to:0, ats:""},
"Auburn": {league:"CFB", conf:"SEC", ppg:26.8, pa:20.7, passOff:197.1, rushOff:176.8, passDef:229.8, rushDef:99.3, to:0, ats:""},
"Florida": {league:"CFB", conf:"SEC", ppg:21.6, pa:24.0, passOff:204.6, rushOff:139.0, passDef:222.9, rushDef:153.9, to:0, ats:""},
"Georgia": {league:"CFB", conf:"SEC", ppg:63, pa:3, passOff:220.2, rushOff:182.1, passDef:216.5, rushDef:81.5, to:0, ats:"", wk1:true},
"Kentucky": {league:"CFB", conf:"SEC", ppg:23.0, pa:26.4, passOff:201.9, rushOff:139.2, passDef:239.9, rushDef:134.2, to:0, ats:""},
"LSU": {league:"CFB", conf:"SEC", ppg:51, pa:10, passOff:229.5, rushOff:104.0, passDef:204.6, rushDef:124.1, to:0, ats:"", wk1:true},
"Mississippi State": {league:"CFB", conf:"SEC", ppg:30.4, pa:30.2, passOff:241.2, rushOff:158.0, passDef:223.0, rushDef:186.3, to:0, ats:""},
"Missouri": {league:"CFB", conf:"SEC", ppg:30.2, pa:18.9, passOff:188.0, rushOff:228.3, passDef:173.5, rushDef:103.8, to:0, ats:""},
"Oklahoma": {league:"CFB", conf:"SEC", ppg:51, pa:0, passOff:235.8, rushOff:118.5, passDef:195.2, rushDef:77.3, to:0, ats:"", wk1:true},
"Ole Miss": {league:"CFB", conf:"SEC", ppg:37.6, pa:20.4, passOff:335.7, rushOff:188.9, passDef:213.1, rushDef:159.7, to:0, ats:""},
"South Carolina": {league:"CFB", conf:"SEC", ppg:22.7, pa:22.1, passOff:225.2, rushOff:111.1, passDef:216.3, rushDef:136.7, to:0, ats:""},
"Tennessee": {league:"CFB", conf:"SEC", ppg:56, pa:9, passOff:292.8, rushOff:173.5, passDef:244.8, rushDef:152.4, to:0, ats:"", wk1:true},
"Texas": {league:"CFB", conf:"SEC", ppg:59, pa:7, passOff:250.7, rushOff:137.8, passDef:234.9, rushDef:103.9, to:0, ats:"", wk1:true},
"Texas A&M": {league:"CFB", conf:"SEC", ppg:50, pa:0, passOff:259.8, rushOff:184.7, passDef:176.6, rushDef:130.8, to:0, ats:"", wk1:true},
"Vanderbilt": {league:"CFB", conf:"SEC", ppg:38.5, pa:22.8, passOff:287.5, rushOff:175.5, passDef:249.4, rushDef:108.2, to:0, ats:""},
"Illinois": {league:"CFB", conf:"Big Ten", ppg:29.4, pa:23.6, passOff:235.8, rushOff:138.1, passDef:218.4, rushDef:126.7, to:0, ats:""},
"Indiana": {league:"CFB", conf:"Big Ten", ppg:52, pa:16, passOff:239.1, rushOff:212.9, passDef:188.8, rushDef:77.2, to:0, ats:"", wk1:true},
"Iowa": {league:"CFB", conf:"Big Ten", ppg:29.3, pa:16.1, passOff:143.2, rushOff:176.9, passDef:172.7, rushDef:107.7, to:0, ats:""},
"Maryland": {league:"CFB", conf:"Big Ten", ppg:23.5, pa:26.5, passOff:255.7, rushOff:104.3, passDef:226.5, rushDef:175.6, to:0, ats:""},
"Michigan": {league:"CFB", conf:"Big Ten", ppg:13, pa:12, passOff:186.8, rushOff:210.2, passDef:211.4, rushDef:111.9, to:0, ats:"", wk1:true},
"Michigan State": {league:"CFB", conf:"Big Ten", ppg:24.6, pa:29.9, passOff:222.7, rushOff:122.8, passDef:231.3, rushDef:147.3, to:0, ats:""},
"Minnesota": {league:"CFB", conf:"Big Ten", ppg:23.0, pa:22.9, passOff:189.9, rushOff:103.2, passDef:210.5, rushDef:121.1, to:0, ats:""},
"Nebraska": {league:"CFB", conf:"Big Ten", ppg:28.7, pa:24.6, passOff:224.6, rushOff:145.9, passDef:154.1, rushDef:175.4, to:0, ats:""},
"Northwestern": {league:"CFB", conf:"Big Ten", ppg:23.4, pa:19.8, passOff:185.9, rushOff:160.2, passDef:193.5, rushDef:136.2, to:0, ats:""},
"Ohio State": {league:"CFB", conf:"Big Ten", ppg:56, pa:3, passOff:268.2, rushOff:154.4, passDef:129.7, rushDef:89.4, to:0, ats:"", wk1:true},
"Oregon": {league:"CFB", conf:"Big Ten", ppg:34, pa:27, passOff:253.6, rushOff:198.6, passDef:157.9, rushDef:115.7, to:0, ats:"", wk1:true},
"Penn State": {league:"CFB", conf:"Big Ten", ppg:45, pa:0, passOff:187.6, rushOff:174.4, passDef:184.2, rushDef:142.5, to:0, ats:"", wk1:true},
"Purdue": {league:"CFB", conf:"Big Ten", ppg:18.8, pa:31.8, passOff:217.2, rushOff:126.4, passDef:241.7, rushDef:181.8, to:0, ats:""},
"Rutgers": {league:"CFB", conf:"Big Ten", ppg:28.7, pa:31.8, passOff:266.1, rushOff:141.0, passDef:222.9, rushDef:209.9, to:0, ats:""},
"UCLA": {league:"CFB", conf:"Big Ten", ppg:18.2, pa:33.4, passOff:180.2, rushOff:139.7, passDef:196.6, rushDef:190.4, to:0, ats:""},
"USC": {league:"CFB", conf:"Big Ten", ppg:39, pa:0, passOff:296.0, rushOff:169.5, passDef:207.5, rushDef:143.2, to:0, ats:"", wk1:true},
"Washington": {league:"CFB", conf:"Big Ten", ppg:34.1, pa:18.7, passOff:244.5, rushOff:165.5, passDef:211.3, rushDef:100.1, to:0, ats:""},
"Wisconsin": {league:"CFB", conf:"Big Ten", ppg:12.8, pa:21.6, passOff:136.4, rushOff:116.7, passDef:218.2, rushDef:105.2, to:0, ats:""},
"Arizona": {league:"CFB", conf:"Big 12", ppg:31.5, pa:19.3, passOff:255.2, rushOff:152.4, passDef:165.3, rushDef:143.2, to:0, ats:""},
"Arizona State": {league:"CFB", conf:"Big 12", ppg:25.8, pa:24.5, passOff:223.7, rushOff:193.6, passDef:233.5, rushDef:124.0, to:0, ats:""},
"Baylor": {league:"CFB", conf:"Big 12", ppg:31.1, pa:32.6, passOff:309.6, rushOff:141.5, passDef:194.9, rushDef:197.2, to:0, ats:""},
"BYU": {league:"CFB", conf:"Big 12", ppg:31.4, pa:19.1, passOff:221.4, rushOff:178.1, passDef:209.7, rushDef:122.7, to:0, ats:""},
"Cincinnati": {league:"CFB", conf:"Big 12", ppg:30.3, pa:25.6, passOff:231.2, rushOff:176.1, passDef:220.5, rushDef:178.8, to:0, ats:""},
"Colorado": {league:"CFB", conf:"Big 12", ppg:20.9, pa:30.5, passOff:202.8, rushOff:125.6, passDef:203.2, rushDef:222.5, to:0, ats:""},
"Houston": {league:"CFB", conf:"Big 12", ppg:29.1, pa:22.8, passOff:216.4, rushOff:178.1, passDef:218.8, rushDef:129.0, to:0, ats:""},
"Iowa State": {league:"CFB", conf:"Big 12", ppg:27.4, pa:20.2, passOff:221.4, rushOff:174.7, passDef:218.5, rushDef:138.0, to:0, ats:""},
"Kansas": {league:"CFB", conf:"Big 12", ppg:28.1, pa:26.8, passOff:222.2, rushOff:168.2, passDef:214.1, rushDef:173.1, to:0, ats:""},
"Kansas State": {league:"CFB", conf:"Big 12", ppg:29.4, pa:26.7, passOff:198.8, rushOff:171.3, passDef:222.4, rushDef:163.8, to:0, ats:""},
"Oklahoma State": {league:"CFB", conf:"Big 12", ppg:14.2, pa:33.3, passOff:174.1, rushOff:118.3, passDef:252.4, rushDef:165.9, to:0, ats:""},
"TCU": {league:"CFB", conf:"Big 12", ppg:30.7, pa:25.3, passOff:290.1, rushOff:131.4, passDef:245.6, rushDef:133.1, to:0, ats:""},
"Texas Tech": {league:"CFB", conf:"Big 12", ppg:33, pa:10, passOff:278.5, rushOff:182.9, passDef:190.1, rushDef:68.1, to:0, ats:"", wk1:true},
"UCF": {league:"CFB", conf:"Big 12", ppg:24.3, pa:23.6, passOff:220.8, rushOff:158.0, passDef:185.1, rushDef:150.7, to:0, ats:""},
"Utah": {league:"CFB", conf:"Big 12", ppg:41.3, pa:18.9, passOff:216.6, rushOff:266.3, passDef:177.8, rushDef:181.2, to:0, ats:""},
"West Virginia": {league:"CFB", conf:"Big 12", ppg:21.8, pa:30.8, passOff:188.9, rushOff:160.6, passDef:265.4, rushDef:143.8, to:0, ats:""},
"Boston College": {league:"CFB", conf:"ACC", ppg:25.4, pa:32.8, passOff:280.2, rushOff:103.9, passDef:255.7, rushDef:177.6, to:0, ats:""},
"California": {league:"CFB", conf:"ACC", ppg:25.3, pa:27.2, passOff:276.4, rushOff:81.8, passDef:205.2, rushDef:156.6, to:0, ats:""},
"Clemson": {league:"CFB", conf:"ACC", ppg:27.2, pa:20.5, passOff:267.8, rushOff:124.5, passDef:251.6, rushDef:105.5, to:0, ats:""},
"Duke": {league:"CFB", conf:"ACC", ppg:34.6, pa:29.4, passOff:285.4, rushOff:138.1, passDef:276.8, rushDef:147.4, to:0, ats:""},
"Florida State": {league:"CFB", conf:"ACC", ppg:33.0, pa:22.0, passOff:253.4, rushOff:218.7, passDef:190.8, rushDef:138.1, to:0, ats:""},
"Georgia Tech": {league:"CFB", conf:"ACC", ppg:32.2, pa:25.0, passOff:262.5, rushOff:197.5, passDef:235.2, rushDef:164.0, to:0, ats:""},
"Louisville": {league:"CFB", conf:"ACC", ppg:29.9, pa:21.2, passOff:220.6, rushOff:163.9, passDef:188.8, rushDef:114.3, to:0, ats:""},
"Miami": {league:"CFB", conf:"ACC", ppg:30.9, pa:14.8, passOff:253.2, rushOff:151.8, passDef:204.9, rushDef:89.2, to:0, ats:""},
"NC State": {league:"CFB", conf:"ACC", ppg:30.2, pa:27.2, passOff:245.7, rushOff:145.5, passDef:273.2, rushDef:138.8, to:0, ats:""},
"North Carolina": {league:"CFB", conf:"ACC", ppg:19.2, pa:24.5, passOff:183.9, rushOff:105.2, passDef:211.2, rushDef:125.7, to:0, ats:""},
"Pittsburgh": {league:"CFB", conf:"ACC", ppg:33.7, pa:24.8, passOff:273.3, rushOff:117.2, passDef:235.3, rushDef:95.1, to:0, ats:""},
"SMU": {league:"CFB", conf:"ACC", ppg:32.2, pa:20.5, passOff:283.1, rushOff:133.9, passDef:283.2, rushDef:111.9, to:0, ats:""},
"Stanford": {league:"CFB", conf:"ACC", ppg:18.8, pa:29.2, passOff:222.0, rushOff:84.5, passDef:288.9, rushDef:119.2, to:0, ats:""},
"Syracuse": {league:"CFB", conf:"ACC", ppg:20.2, pa:34.9, passOff:217.2, rushOff:123.2, passDef:252.8, rushDef:175.0, to:0, ats:""},
"Virginia": {league:"CFB", conf:"ACC", ppg:30.8, pa:19.6, passOff:239.1, rushOff:178.7, passDef:195.6, rushDef:114.5, to:0, ats:""},
"Virginia Tech": {league:"CFB", conf:"ACC", ppg:21.4, pa:30.2, passOff:166.3, rushOff:182.4, passDef:224.8, rushDef:153.2, to:0, ats:""},
"Wake Forest": {league:"CFB", conf:"ACC", ppg:28.1, pa:22.1, passOff:237.7, rushOff:156.2, passDef:206.9, rushDef:121.6, to:0, ats:""},
"Notre Dame": {league:"CFB", conf:"Independent", ppg:42.0, pa:17.6, passOff:255.1, rushOff:203.4, passDef:213.4, rushDef:100.1, to:0, ats:""}
};

const NFL_WEEK1 = [
  {a:"New England Patriots", b:"Seattle Seahawks", date:"Wed Sep 9"},
  {a:"San Francisco 49ers", b:"Los Angeles Rams", date:"Thu Sep 10 (Melbourne)"},
  {a:"Chicago Bears", b:"Carolina Panthers", date:"Sun Sep 13"},
  {a:"Tampa Bay Buccaneers", b:"Cincinnati Bengals", date:"Sun Sep 13"},
  {a:"New Orleans Saints", b:"Detroit Lions", date:"Sun Sep 13"},
  {a:"Buffalo Bills", b:"Houston Texans", date:"Sun Sep 13"},
  {a:"Baltimore Ravens", b:"Indianapolis Colts", date:"Sun Sep 13"},
  {a:"Cleveland Browns", b:"Jacksonville Jaguars", date:"Sun Sep 13"},
  {a:"Atlanta Falcons", b:"Pittsburgh Steelers", date:"Sun Sep 13"},
  {a:"New York Jets", b:"Tennessee Titans", date:"Sun Sep 13"},
  {a:"Arizona Cardinals", b:"Los Angeles Chargers", date:"Sun Sep 13"},
  {a:"Miami Dolphins", b:"Las Vegas Raiders", date:"Sun Sep 13"},
  {a:"Green Bay Packers", b:"Minnesota Vikings", date:"Sun Sep 13"},
  {a:"Washington Commanders", b:"Philadelphia Eagles", date:"Sun Sep 13"},
  {a:"Dallas Cowboys", b:"New York Giants", date:"Sun Sep 13 (SNF)"},
  {a:"Denver Broncos", b:"Kansas City Chiefs", date:"Mon Sep 14 (MNF)"}
];

const CFB_TOP25 = [
  {rank:1, team:"Ohio State", record:"1-0", next:"@ Texas (Sep 12)"},
  {rank:2, team:"Oregon", record:"1-0", next:"@ Oklahoma State (Sep 12)"},
  {rank:3, team:"Georgia", record:"1-0", next:"vs Western Kentucky (Sep 12)"},
  {rank:4, team:"Notre Dame", record:"0-0", next:"vs Wisconsin (Sep 6)"},
  {rank:5, team:"Texas", record:"1-0", next:"vs Ohio State (Sep 12)"},
  {rank:6, team:"Indiana", record:"1-0", next:"vs Howard (Sep 12)"},
  {rank:7, team:"Miami", record:"1-0", next:"vs Florida A&M (Sep 10)"},
  {rank:8, team:"Texas A&M", record:"1-0", next:"vs Arizona State (Sep 12)"},
  {rank:9, team:"Ole Miss", record:"0-0", next:"vs Louisville (Sep 6)"},
  {rank:10, team:"Oklahoma", record:"1-0", next:"@ Michigan (Sep 12)"},
  {rank:11, team:"LSU", record:"1-0", next:"vs Louisiana Tech (Sep 12)"},
  {rank:12, team:"Texas Tech", record:"1-0", next:"@ Oregon State (Sep 12)"},
  {rank:13, team:"Alabama", record:"1-0", next:"@ Kentucky (Sep 12)"},
  {rank:14, team:"BYU", record:"1-0", next:"vs Arizona (Sep 12)"},
  {rank:14, team:"USC", record:"2-0", next:"vs Louisiana (Sep 12)"},
  {rank:16, team:"Michigan", record:"1-0", next:"vs Oklahoma (Sep 12)"},
  {rank:17, team:"Washington", record:"0-0", next:"vs Washington State (Sep 6)"},
  {rank:18, team:"Penn State", record:"1-0", next:"@ Temple (Sep 12)"},
  {rank:19, team:"SMU", record:"0-0", next:"@ Florida State (Sep 7)"},
  {rank:20, team:"Tennessee", record:"1-0", next:"@ Georgia Tech (Sep 12)"},
  {rank:21, team:"Utah", record:"1-0", next:"vs Arkansas (Sep 12)"},
  {rank:22, team:"Iowa", record:"1-0", next:"vs Iowa State (Sep 12)"},
  {rank:23, team:"Houston", record:"1-0", next:"vs Southern U. (Sep 12)"},
  {rank:24, team:"Louisville", record:"0-0", next:"@ Ole Miss (Sep 6)"},
  {rank:25, team:"Missouri", record:"1-0", next:"@ Kansas (Sep 11)"}
];
const CFB_OTHERS = "Clemson (0-1), Florida (1-0), Boise State (0-1), Arizona (1-0), TCU (0-1), Navy (1-0), South Carolina (1-0), Illinois (1-0), Vanderbilt (1-0), Oklahoma State (0-1), Pittsburgh (1-0), Virginia Tech (1-0), Minnesota (1-0), Louisiana (1-0), Georgia Tech (0-1), UNLV (1-1), New Mexico (1-0), Auburn (1-0), James Madison (1-0), Memphis (2-0), California (0-1), Liberty (0-1), Tulane (0-1), Virginia (1-0), Western Michigan (0-1)";

const CFB_WEEK = [
  {a:"Ohio State", b:"Texas", date:"Sat Sep 12"},
  {a:"Oregon", b:"Oklahoma State", date:"Sat Sep 12"},
  {a:"Georgia", b:"Western Kentucky", date:"Sat Sep 12"},
  {a:"Notre Dame", b:"Wisconsin", date:"Sun Sep 6"},
  {a:"Indiana", b:"Howard", date:"Sat Sep 12"},
  {a:"Miami", b:"Florida A&M", date:"Thu Sep 10"},
  {a:"Texas A&M", b:"Arizona State", date:"Sat Sep 12"},
  {a:"Ole Miss", b:"Louisville", date:"Sun Sep 6"},
  {a:"LSU", b:"Louisiana Tech", date:"Sat Sep 12"},
  {a:"Texas Tech", b:"Oregon State", date:"Sat Sep 12"},
  {a:"Alabama", b:"Kentucky", date:"Sat Sep 12"},
  {a:"BYU", b:"Arizona", date:"Sat Sep 12"},
  {a:"USC", b:"Louisiana", date:"Sat Sep 12"},
  {a:"Oklahoma", b:"Michigan", date:"Sat Sep 12"},
  {a:"Washington", b:"Washington State", date:"Sun Sep 6"},
  {a:"Penn State", b:"Temple", date:"Sat Sep 12"},
  {a:"SMU", b:"Florida State", date:"Mon Sep 7"},
  {a:"Tennessee", b:"Georgia Tech", date:"Sat Sep 12"},
  {a:"Utah", b:"Arkansas", date:"Sat Sep 12"},
  {a:"Iowa", b:"Iowa State", date:"Sat Sep 12"},
  {a:"Houston", b:"Southern U.", date:"Sat Sep 12"},
  {a:"Missouri", b:"Kansas", date:"Fri Sep 11"}
];

const PLAYERS_SEED = {
"Jayden Maiava": {pos:"QB", team:"USC", league:"CFB", games:[{date:"2026-09-05", opp:"vs Missouri State", passYds:635, rushYds:0, receptions:0, recYds:0, tds:5}]},
"Nate Sheppard": {pos:"RB", team:"Duke", league:"CFB", games:[{date:"2026-09-05", opp:"Week 1", passYds:0, rushYds:227, receptions:0, recYds:0, tds:2}]},
"Malachi Toney": {pos:"WR", team:"Miami", league:"CFB", games:[{date:"2026-09-05", opp:"vs Florida A&M", passYds:0, rushYds:0, receptions:0, recYds:234, tds:2}]}
};

const ODDS_SEED = [
  {game:"Dallas Cowboys @ New York Giants", league:"NFL", date:"Sep 13",
   aTeam:"Dallas Cowboys", aML:-148, aSpread:-2.5, aSpreadOdds:-110,
   bTeam:"New York Giants", bML:124, bSpread:2.5, bSpreadOdds:-110,
   total:48.5, overOdds:-110, underOdds:-110},
  {game:"Denver Broncos @ Kansas City Chiefs", league:"NFL", date:"Sep 14 (MNF)",
   aTeam:"Denver Broncos", aML:124, aSpread:2.5, aSpreadOdds:-110,
   bTeam:"Kansas City Chiefs", bML:-144, bSpread:-2.5, bSpreadOdds:-110,
   total:42.5, overOdds:-110, underOdds:-110},
  {game:"Ohio State @ Texas", league:"CFB", date:"Sep 12",
   aTeam:"Ohio State", aML:-104, aSpread:1.5, aSpreadOdds:-110,
   bTeam:"Texas", bML:-115, bSpread:-1.5, bSpreadOdds:-110,
   total:47.5, overOdds:-110, underOdds:-110}
];

const hasStorage = (typeof window.storage !== 'undefined' && window.storage !== null);
let memTeams = {}, memHistory = {}, memPlayers = {};
let storageWarned = false;

function warnNoStorage(){
  if(storageWarned) return;
  storageWarned = true;
  const banner = document.createElement('div');
  banner.className = 'note';
  banner.style.cssText = 'background:rgba(240,185,61,0.12);padding:8px 10px;border-radius:4px;margin-bottom:14px;';
  banner.textContent = "Note: your edits won't be saved between visits in this view — everything still works for now, pre-loaded with real stats.";
  document.querySelector('.wrap').insertBefore(banner, document.querySelector('.app-header').nextSibling);
}

async function fetchJSON(path){
  try{
    const res = await fetch(path, {cache:'no-store'});
    if(!res.ok) return null;
    return await res.json();
  }catch(e){ return null; }
}

async function loadTeams(){
  if(!hasStorage){ warnNoStorage(); return memTeams; }
  try{ const res = await window.storage.get(STORAGE_KEY, false); return res ? JSON.parse(res.value) : {}; }catch(e){ return {}; }
}
async function saveTeams(teams){
  if(!hasStorage){ memTeams = teams; return; }
  try{ await window.storage.set(STORAGE_KEY, JSON.stringify(teams), false); }catch(e){ memTeams = teams; }
}
async function loadHistory(name){
  if(!hasStorage){ return memHistory[name] || []; }
  try{ const res = await window.storage.get('history:'+name, false); return res ? JSON.parse(res.value) : []; }catch(e){ return []; }
}
async function appendHistory(name, entry){
  const hist = await loadHistory(name);
  hist.push(entry);
  if(!hasStorage){ memHistory[name] = hist; return; }
  try{ await window.storage.set('history:'+name, JSON.stringify(hist), false); }catch(e){ memHistory[name] = hist; }
}
async function loadPlayers(){
  if(!hasStorage){ return memPlayers; }
  try{ const res = await window.storage.get('players-db', false); return res ? JSON.parse(res.value) : {}; }catch(e){ return {}; }
}
async function savePlayers(players){
  if(!hasStorage){ memPlayers = players; return; }
  try{ await window.storage.set('players-db', JSON.stringify(players), false); }catch(e){ memPlayers = players; }
}

let teamsCache = {};
let playersCache = {};

async function ensureSeeded(){
  try{
    teamsCache = await loadTeams();
    let changed = false;
    const liveNfl = await fetchJSON('./data/nfl-teams.json');
    const liveCfb = await fetchJSON('./data/cfb-teams.json');
    const nflData = liveNfl || NFL_SEED;
    const cfbData = liveCfb || CFB_SEED;
    const today = new Date().toISOString().slice(0,10);
    // Always re-sync every team to whatever's currently live (or the fallback
    // constants) -- not just on first load. This is what makes Trends
    // actually accumulate: a history entry is logged whenever the incoming
    // numbers differ from what's already stored, which happens naturally
    // whenever the weekly Action pushes fresh stats.
    async function syncTeam(name, incoming){
      const existing = teamsCache[name];
      if(!existing || JSON.stringify(existing) !== JSON.stringify(incoming)){
        teamsCache[name] = Object.assign({}, incoming);
        changed = true;
        await appendHistory(name, Object.assign({date: today}, incoming));
      }
    }
    for(const name in nflData){ await syncTeam(name, nflData[name]); }
    for(const name in cfbData){ await syncTeam(name, cfbData[name]); }
    if(changed) await saveTeams(teamsCache);
  }catch(e){
    teamsCache = Object.assign({}, NFL_SEED, CFB_SEED);
  }
}

// NFL and CFB players share one flat dictionary keyed by plain name, with
// no league-scoping -- confirmed live: "Caleb Williams" is both the
// Bears' real starting QB (NFL) and a CFB running back at New Haven, and
// since CFB data merges in after NFL, the CFB entry was silently
// overwriting the NFL one. The Bears' actual QB vanished from every
// NFL-only view (the Hit Rate Checker's player list, in particular)
// because his own name pointed at someone else's data entirely. This
// detects a cross-league name collision at merge time and disambiguates
// with a league suffix instead of letting one clobber the other, rather
// than re-keying the whole app (playersCache[name] lookups are used in
// many places -- this fixes the merge without touching all of them).
function mergePlayerEntry(cache, name, incoming){
  const existing = cache[name];
  const key = (existing && existing.league && existing.league!==incoming.league) ? (name+' ('+incoming.league+')') : name;
  if(JSON.stringify(cache[key]) !== JSON.stringify(incoming)){
    cache[key] = Object.assign({}, incoming);
    return true;
  }
  return false;
}
async function ensurePlayersSeeded(){
  try{
    playersCache = await loadPlayers();
    let changed = false;
    const liveNflP = await fetchJSON('./data/nfl-players.json');
    const liveCfbP = await fetchJSON('./data/cfb-players.json');
    for(const name in PLAYERS_SEED){
      if(!playersCache[name]){ playersCache[name] = JSON.parse(JSON.stringify(PLAYERS_SEED[name])); changed = true; }
    }
    // Always re-sync from live data on every load, same as teams -- picks
    // up new games/players each week instead of only on first visit.
    // NFL merges first, so it always keeps the plain name; a CFB player
    // who collides with an existing NFL name gets the "(CFB)" suffix --
    // see mergePlayerEntry's comment above for why this exists at all.
    if(liveNflP){ for(const name in liveNflP){
      if(mergePlayerEntry(playersCache, name, liveNflP[name])) changed = true;
    } }
    if(liveCfbP){ for(const name in liveCfbP){
      if(mergePlayerEntry(playersCache, name, liveCfbP[name])) changed = true;
    } }
    if(changed) await savePlayers(playersCache);
  }catch(e){
    playersCache = JSON.parse(JSON.stringify(PLAYERS_SEED));
  }
}

function activateTopTab(tabName){
  document.querySelectorAll('.bottom-nav-item[data-tab]').forEach(t=>t.classList.toggle('active', t.dataset.tab===tabName));
  document.querySelectorAll('.leaguepanel').forEach(p=>p.classList.toggle('active', p.id==='panel-'+tabName));
}
function activateSubTab(subName){
  const el = document.querySelector('[data-subtab="'+subName+'"]');
  if(!el) return;
  const parent = el.closest('.leaguepanel');
  parent.querySelectorAll('.subtab').forEach(t=>t.classList.toggle('active', t.dataset.subtab===subName));
  parent.querySelectorAll('.subpanel').forEach(p=>p.classList.toggle('active', p.id==='subpanel-'+subName));
}
document.querySelectorAll('.bottom-nav-item[data-tab]').forEach(tab=>{
  tab.addEventListener('click', ()=> activateTopTab(tab.dataset.tab));
});
document.querySelectorAll('.subtab[data-subtab]').forEach(tab=>{
  tab.addEventListener('click', ()=> activateSubTab(tab.dataset.subtab));
});

// Ranks a team among every other team in its own league for a given stat.
// For passOff/rushOff/ppg, higher is better (rank 1 = most). For
// passDef/rushDef/pa, LOWER is better (rank 1 = fewest allowed) -- flip
// the sort for those.
function rankTeamStat(name, key, lowerIsBetter){
  const t = teamsCache[name];
  if(!t) return null;
  const league = t.league;
  const rows = Object.keys(teamsCache)
    .filter(n=>teamsCache[n].league===league && typeof teamsCache[n][key]==='number')
    .map(n=>({ n, v: teamsCache[n][key] }));
  if(rows.length===0 || typeof t[key]!=='number') return null;
  rows.sort(function(a,b){ return lowerIsBetter ? a.v-b.v : b.v-a.v; });
  const rank = rows.findIndex(r=>r.n===name) + 1;
  return { rank, of: rows.length };
}
function rankLabel(r){ return r ? ('#'+r.rank+' of '+r.of) : '—'; }
// Computes a team's own real betting track record (spread, total, and
// its players' props) from TRACK_RECORD_PICKS -- confirmed live this was
// a real gap: nothing anywhere in the app showed how a specific team's
// games have actually performed against the model's own picks, only
// league-wide stats. Spread/total match by the pick's own stored
// _away/_home fields (exact); player props match primarily via the
// player's CURRENT roster team (playersCache), falling back to a plain
// substring check against the pick's matchup string only if the player
// isn't found there (e.g. since left the roster) -- the roster lookup is
// preferred since it's exact, unlike matching raw text.
function computeTeamBettingStats(teamName){
  const spreadPicks = [], totalPicks = [], propPicks = [];
  TRACK_RECORD_PICKS.forEach(function(p){
    if(p.status!=='hit' && p.status!=='miss') return; // pushes and pending excluded -- a push isn't a hit or a miss, and pending has no result yet
    if(p.type==='spread' || p.type==='total'){
      if(p._away===teamName || p._home===teamName){
        (p.type==='spread' ? spreadPicks : totalPicks).push(p);
      }
    } else if(p.type==='player_prop'){
      const player = playersCache[p._player_name];
      const belongsToTeam = player ? player.team===teamName : (p.matchup||'').indexOf(teamName)>=0;
      if(belongsToTeam) propPicks.push(p);
    }
  });
  function summarize(picks){
    const hits = picks.filter(function(p){ return p.status==='hit'; }).length;
    return { hits: hits, total: picks.length, pct: picks.length ? Math.round(hits/picks.length*100) : null };
  }
  return { spread: summarize(spreadPicks), total: summarize(totalPicks), props: summarize(propPicks) };
}
function renderTeamDetail(lg, name){
  const container = document.getElementById(lg+'-team-detail');
  const t = teamsCache[name];
  if(!t){ container.innerHTML=''; return; }
  const offRank = rankTeamStat(name, 'ppg', false);
  const paRank = rankTeamStat(name, 'pa', true);
  const passOffRank = rankTeamStat(name, 'passOff', false);
  const rushOffRank = rankTeamStat(name, 'rushOff', false);
  const passDefRank = rankTeamStat(name, 'passDef', true);
  const rushDefRank = rankTeamStat(name, 'rushDef', true);
  const games = (t.games || []).slice().reverse(); // most recent first
  const gamesHtml = games.length ? games.map(function(g){
    const won = g.result==='W', lost = g.result==='L';
    return '<div class="glog-row"><span>Week '+(g.week||'?')+' '+(won?'vs':lost?'@':'vs')+' '+g.opp+'</span>'
      + '<span class="glog-val '+(won?'over':lost?'under':'')+'">'+g.result+' '+fmt(g.teamScore)+'-'+fmt(g.oppScore)+'</span></div>';
  }).join('') : '<div class="empty">No games played yet this season.</div>';
  const betStats = computeTeamBettingStats(name);
  function betLine(label, s){
    return '<div class="glog-row"><span>'+label+'</span><span class="glog-val">'+(s.total ? s.hits+'-'+(s.total-s.hits)+' ('+s.pct+'%)' : 'no graded picks yet')+'</span></div>';
  }
  container.innerHTML = '<div class="card">'
    + '<h2>'+name+(t.conf?' <span class="pill">'+t.conf+'</span>':'')+(t.division==='fcs'?' <span class="pill">FCS</span>':'')+'</h2>'
    + '<div class="team-meta">Record: <b>'+(t.record||'—')+'</b> · TO margin '+(t.to>=0?'+':'')+fmt(t.to)+'/g · ATS '+(t.ats||'—')+'</div>'
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">This app\'s betting track record</div>'
    + '<div class="note" style="margin-top:0;">How the model\'s own picks involving this team have actually graded -- not this team\'s real sportsbook ATS record, just this app\'s history.</div>'
    + betLine('Spread picks', betStats.spread)
    + betLine('Total (O/U) picks', betStats.total)
    + betLine('Player prop picks', betStats.props)
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">Offense</div>'
    + '<div class="glog-row"><span>Points/g — '+fmt(t.ppg)+'</span><span class="glog-val">'+rankLabel(offRank)+'</span></div>'
    + '<div class="glog-row"><span>Pass yds/g — '+fmt(t.passOff)+'</span><span class="glog-val">'+rankLabel(passOffRank)+'</span></div>'
    + '<div class="glog-row"><span>Rush yds/g — '+fmt(t.rushOff)+'</span><span class="glog-val">'+rankLabel(rushOffRank)+'</span></div>'
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">Defense</div>'
    + '<div class="glog-row"><span>Points allowed/g — '+fmt(t.pa)+'</span><span class="glog-val">'+rankLabel(paRank)+'</span></div>'
    + '<div class="glog-row"><span>Pass yds allowed/g — '+fmt(t.passDef)+'</span><span class="glog-val">'+rankLabel(passDefRank)+'</span></div>'
    + '<div class="glog-row"><span>Rush yds allowed/g — '+fmt(t.rushDef)+'</span><span class="glog-val">'+rankLabel(rushDefRank)+'</span></div>'
    + '<div class="note">Rankings are within '+t.league+(t.league==='CFB'?' (FBS + FCS combined)':'')+' only, based on stats currently loaded.</div>'
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">Results this season</div>'
    + gamesHtml
    + '<button class="secondary" id="'+lg+'-team-detail-close" style="margin-top:10px;">Close</button>'
    + '</div>';
  document.getElementById(lg+'-team-detail-close').addEventListener('click', function(){ container.innerHTML=''; });
}
function renderTeamList(lg){
  const league = lg.toUpperCase();
  const list = document.getElementById(lg+'-team-list');
  const names = Object.keys(teamsCache).filter(n=>teamsCache[n].league===league).sort();
  const countEl = document.getElementById(lg+'-team-count');
  if(countEl) countEl.textContent = names.length + ' loaded';
  if(names.length===0){
    list.innerHTML = '<div class="empty">No teams yet.</div>';
  } else {
    list.innerHTML = names.map(n=>{
      const t = teamsCache[n];
      return '<div class="team-row" data-team-name="'+n.replace(/"/g,'&quot;')+'" style="cursor:pointer;"><div><div class="team-name">'+n+(t.conf?' <span class="pill">'+t.conf+'</span>':'')+(t.wk1?' <span class="pill" style="background:rgba(63,122,153,0.35);color:#8fd39f;">2026 Wk1</span>':'')+'</div><div class="team-meta">'+(t.record?t.record+' · ':'')+fmt(t.ppg)+' PPG · '+fmt(t.pa)+' PA · TO '+(t.to>=0?'+':'')+fmt(t.to)+'/g · ATS '+(t.ats||'—')+'</div></div></div>';
    }).join('');
    list.querySelectorAll('.team-row').forEach(function(row){
      row.addEventListener('click', function(){
        renderTeamDetail(lg, row.dataset.teamName);
        const detailEl = document.getElementById(lg+'-team-detail');
        if(detailEl) detailEl.scrollIntoView({behavior:'smooth', block:'start'});
      });
    });
  }
}
function refreshTeamLists(){ renderTeamList('nfl'); renderTeamList('cfb'); populateSelects(); }

function populateSelects(){
  const nflNames = Object.keys(teamsCache).filter(n=>teamsCache[n].league==='NFL').sort();
  const cfbNames = Object.keys(teamsCache).filter(n=>teamsCache[n].league==='CFB').sort();
  const nflOpts = nflNames.map(n=>'<option value="'+n+'">'+n+'</option>').join('');
  const cfbOpts = cfbNames.map(n=>'<option value="'+n+'">'+n+'</option>').join('');
  ['m-teamA-nfl','m-teamB-nfl','nfl-trend-team'].forEach(id=>{
    const el = document.getElementById(id); const prev = el.value;
    el.innerHTML = nflOpts || '<option value="">No NFL teams yet</option>';
    if(nflNames.includes(prev)) el.value = prev;
  });
  ['m-teamA-cfb','m-teamB-cfb','cfb-trend-team'].forEach(id=>{
    const el = document.getElementById(id); const prev = el.value;
    el.innerHTML = cfbOpts || '<option value="">No college teams yet</option>';
    if(cfbNames.includes(prev)) el.value = prev;
  });
  populateCheckSelects();
}
function populateCheckSelects(){
  const leagueEl = document.getElementById('chk-league');
  if(!leagueEl) return;
  const league = leagueEl.value;
  const names = Object.keys(teamsCache).filter(n=>teamsCache[n].league===league).sort();
  const opts = names.map(n=>'<option value="'+n+'">'+n+'</option>').join('') || '<option value="">No teams yet</option>';
  ['chk-teamA','chk-teamB'].forEach(function(id){
    const el = document.getElementById(id); const prev = el.value;
    el.innerHTML = opts;
    if(names.includes(prev)) el.value = prev;
  });
  populateCheckSideSelect();
}
function populateCheckSideSelect(){
  const a = document.getElementById('chk-teamA').value;
  const b = document.getElementById('chk-teamB').value;
  const sideEl = document.getElementById('chk-side');
  if(!sideEl) return;
  const prev = sideEl.value;
  sideEl.innerHTML = (a?'<option value="A">'+a+'</option>':'')+(b?'<option value="B">'+b+'</option>':'');
  if(prev==='A'||prev==='B') sideEl.value = prev;
}

function wireTrend(lg){
  document.getElementById(lg+'-load-trend').addEventListener('click', async ()=>{
    const name = document.getElementById(lg+'-trend-team').value;
    const out = document.getElementById(lg+'-trend-output');
    if(!name){ out.innerHTML=''; return; }
    const hist = await loadHistory(name);
    if(hist.length===0){ out.innerHTML = '<div class="card"><div class="empty">No history logged yet for this team.</div></div>'; return; }
    const rows = hist.slice().reverse().map(h=>'<div class="history-item"><span>'+h.date+'</span><span>'+fmt(h.ppg)+' PPG / '+fmt(h.pa)+' PA</span><span>'+fmt(h.passOff)+' pass / '+fmt(h.rushOff)+' rush</span></div>').join('');
    let trendNote = '';
    if(hist.length>=2){
      const delta = hist[hist.length-1].ppg - hist[0].ppg;
      trendNote = '<div class="note">Scoring trend: '+(delta>=0?'+':'')+fmt(delta)+' PPG from first to most recent logged entry.</div>';
    }
    out.innerHTML = '<div class="card"><h2>'+name+' — logged history</h2>'+rows+trendNote+'</div>';
  });
}
wireTrend('nfl');
wireTrend('cfb');

function statLabel(stat){
  return {passYds:'passing yards', rushYds:'rushing yards', receptions:'receptions', recYds:'receiving yards', tds:'total TDs'}[stat] || stat;
}
function populatePlayerSelects(){
  const nflNames = Object.keys(playersCache).filter(n=>playersCache[n].league==='NFL').sort();
  const cfbNames = Object.keys(playersCache).filter(n=>playersCache[n].league==='CFB').sort();

  function optsFor(names, searchText){
    const q = (searchText||'').trim().toLowerCase();
    return names
      .filter(n => !q || (playersCache[n].team||'').toLowerCase().indexOf(q) !== -1)
      .map(n=>'<option value="'+n+'">'+n+' ('+playersCache[n].pos+')</option>').join('');
  }
  function fillSelect(id, names, searchText){
    const el = document.getElementById(id); if(!el) return;
    const prev = el.value;
    const opts = optsFor(names, searchText);
    el.innerHTML = opts || '<option value="">'+(names.length?'No players match that team':'No players loaded yet')+'</option>';
    if(names.includes(prev)){
      const q = (searchText||'').trim().toLowerCase();
      if(!q || (playersCache[prev].team||'').toLowerCase().indexOf(q) !== -1) el.value = prev;
    }
  }
  function fillTeamDatalist(id, names){
    const el = document.getElementById(id); if(!el) return;
    const teams = Array.from(new Set(names.map(n=>playersCache[n].team).filter(Boolean))).sort();
    el.innerHTML = teams.map(t=>'<option value="'+t+'">').join('');
  }

  fillTeamDatalist('nfl-hr-teamlist', nflNames);
  fillTeamDatalist('cfb-hr-teamlist', cfbNames);
  const nflFilter = document.getElementById('nfl-hr-teamfilter') ? document.getElementById('nfl-hr-teamfilter').value : '';
  const cfbFilter = document.getElementById('cfb-hr-teamfilter') ? document.getElementById('cfb-hr-teamfilter').value : '';
  fillSelect('nfl-hr-player', nflNames, nflFilter);
  fillSelect('cfb-hr-player', cfbNames, cfbFilter);

  const nflCountEl = document.getElementById('nfl-player-count');
  if(nflCountEl) nflCountEl.textContent = nflNames.length + ' loaded';
  const cfbCountEl = document.getElementById('cfb-player-count');
  if(cfbCountEl) cfbCountEl.textContent = cfbNames.length + ' loaded';
}
function wireHrTeamFilter(lg){
  const el = document.getElementById(lg+'-hr-teamfilter');
  if(el) el.addEventListener('input', populatePlayerSelects);
}
wireHrTeamFilter('nfl');
wireHrTeamFilter('cfb');
function computeSinglePlayerProjection(name){
  const p = playersCache[name];
  if(!p) return null;
  const league = p.league;
  const games = p.games || [];
  let mainStat = 'passYds';
  if(p.pos==='RB') mainStat='rushYds';
  if(p.pos==='WR'||p.pos==='TE') mainStat='recYds';
  if(games.length===0) return { statLabel: statLabel(mainStat), noGames: true };
  const opp = findOpponentThisWeek(league, p.team);
  if(!opp || !teamsCache[opp]) return { statLabel: statLabel(mainStat), noOpponent: true };
  const defKey = defCategoryForStat(mainStat);
  if(!defKey || !teamsCache[opp][defKey]) return { statLabel: statLabel(mainStat), opp, noData: true };
  const avgVal = leagueAvgDefStat(league, defKey);
  if(!avgVal) return { statLabel: statLabel(mainStat), opp, noData: true };
  const last5 = games.slice(-5);
  const l5avg = median(last5.map(function(g){ return g[mainStat]||0; }));
  const ratio = clampDefenseRatio(shrunkTeamStat(teamsCache[opp], defKey, league) / avgVal);
  const modelProjection = roundToHalf(l5avg * ratio);
  const realProp = getRealPropLine(name, mainStat);
  const projected = realProp ? realProp.line : modelProjection;
  const direction = realProp ? (modelProjection > realProp.line ? 'over' : 'under') : (ratio>=1 ? 'favorable' : 'tough');
  return {
    statLabel: statLabel(mainStat), opp, l5avg, ratio, projected, modelProjection,
    direction, usedRealLine: !!realProp, books: realProp ? realProp.books : null,
    meetsVolume: meetsVolumeThreshold(mainStat, l5avg),
  };
}
function renderPlayerDetail(lg, name){
  const container = document.getElementById(lg+'-player-detail');
  const p = playersCache[name];
  if(!p){ container.innerHTML=''; return; }
  const league = p.league;
  const unconfirmed = league==='NFL' && p.team && (p.teamYear==null);
  const proj = computeSinglePlayerProjection(name);

  let projBlock;
  if(!proj || proj.noGames){
    projBlock = '<div class="empty">No games logged yet for this player.</div>';
  } else if(unconfirmed){
    projBlock = '<div class="note" style="color:#f28b7d;">Not on a confirmed current active roster, so this week\'s opponent can\'t be reliably resolved.</div>';
  } else if(proj.noOpponent){
    projBlock = '<div class="empty">Could not find this team\'s game this week.</div>';
  } else if(proj.noData){
    projBlock = '<div class="empty">Not enough data to project vs '+proj.opp+' yet.</div>';
  } else {
    const pct = Math.round((proj.ratio-1)*100);
    const dirLabel = (proj.direction==='favorable' ? 'Over ' : 'Under ')+proj.statLabel+' · '+(proj.direction==='favorable' ? '+'+pct+'% easier than average' : pct+'% tougher than average');
    const badgeCls = proj.direction==='favorable' ? 'high' : 'low';
    const volNote = proj.meetsVolume ? '' : '<div class="note">Recent volume for this stat is low — treat this projection with extra caution.</div>';
    projBlock = '<div class="hitrate-badge '+badgeCls+'">'+fmt(proj.projected)+' <span style="font-size:0.9rem;font-weight:600;">'+proj.statLabel+'</span></div>'
      + '<div class="hitrate-sub">'+dirLabel+' · vs '+proj.opp+'</div>' + volNote;
  }

  const last5 = (p.games||[]).slice(-5).reverse();
  const gamesRows = last5.length ? last5.map(function(g){
    return '<div class="glog-row"><span>'+g.date+(g.opp?' · '+g.opp:'')+'</span><span class="team-meta">pass '+fmt(g.passYds)+' · rush '+fmt(g.rushYds)+' · rec '+(g.receptions||0)+'/'+fmt(g.recYds)+' · TD '+fmt(g.tds)+'</span></div>';
  }).join('') : '<div class="empty">No games logged yet.</div>';

  const teamLabel = (p.team||'—') + (unconfirmed ? ' <span class="pill" style="background:rgba(242,139,125,0.15);color:#f28b7d;">not on active roster</span>' : '');
  container.innerHTML = '<div class="card">'
    + '<h2>'+name+' <span class="pill">'+p.pos+'</span></h2>'
    + '<div class="team-meta">'+teamLabel+'</div>'
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">This week\'s top prop</div>'
    + projBlock
    + '<div style="margin-top:14px;font-weight:700;font-size:0.85rem;">Last 5 games</div>'
    + gamesRows
    + '<button class="secondary" id="'+lg+'-player-detail-close" style="margin-top:10px;">Close</button>'
    + '</div>';
  document.getElementById(lg+'-player-detail-close').addEventListener('click', function(){ container.innerHTML=''; });
}
function renderPlayersList(lg){
  const league = lg.toUpperCase();
  const list = document.getElementById(lg+'-players-list');
  const names = Object.keys(playersCache).filter(n=>playersCache[n].league===league).sort();
  if(names.length===0){
    list.innerHTML = '<div class="empty">No players yet.</div>';
  } else {
    list.innerHTML = names.map(n=>{
      const p = playersCache[n];
      const g = p.games || [];
      const last5 = g.slice(-5);
      const avg = function(key){ return median(last5.map(function(x){ return x[key]||0; })); };
      let mainStat = 'passYds';
      if(p.pos==='RB') mainStat='rushYds';
      if(p.pos==='WR'||p.pos==='TE') mainStat='recYds';
      const unconfirmed = league==='NFL' && p.team && (p.teamYear==null);
      const teamLabel = (p.team||'—') + (unconfirmed ? ' <span class="pill" style="background:rgba(242,139,125,0.15);color:#f28b7d;">not on active roster</span>' : '');
      return '<div class="team-row" data-player-name="'+n.replace(/"/g,'&quot;')+'" style="cursor:pointer;"><div><div class="team-name">'+n+' <span class="pill">'+p.pos+'</span></div><div class="team-meta">'+teamLabel+' · '+g.length+' game'+(g.length===1?'':'s')+' logged · L5 avg '+statLabel(mainStat)+': '+fmt(avg(mainStat))+'</div></div></div>';
    }).join('');
    list.querySelectorAll('.team-row').forEach(function(row){
      row.addEventListener('click', function(){
        renderPlayerDetail(lg, row.dataset.playerName);
        const detailEl = document.getElementById(lg+'-player-detail');
        if(detailEl) detailEl.scrollIntoView({behavior:'smooth', block:'start'});
      });
    });
  }
}
function refreshPlayersLists(){ renderPlayersList('nfl'); renderPlayersList('cfb'); populatePlayerSelects(); }


function defCategoryForStat(stat){
  if(stat==='passYds') return 'passDef';
  if(stat==='rushYds') return 'rushDef';
  if(stat==='receptions' || stat==='recYds') return 'passDef'; // receiving production runs against the opponent's pass defense
  return null; // 'tds' isn't tied to one specific defensive category -- skipped rather than guessed
}
// No source in this pipeline has real depth-chart data (starter vs. backup),
// so player-prop bet lists can't filter on that directly. The best proxy
// available is recent production volume: a fullback or inactive backup
// with a 1-2 yard L5 average isn't a real betting signal no matter what
// position label they carry, so bets below these thresholds are excluded
// rather than shown as noise. These are heuristic cutoffs, not official
// snap-count or depth-chart thresholds.
const MIN_VOLUME_FOR_BET = { passYds: 75, rushYds: 15, recYds: 15 };
function meetsVolumeThreshold(stat, l5avg){
  const min = MIN_VOLUME_FOR_BET[stat];
  return min===undefined || l5avg >= min;
}
// Guards against a small-sample defensive stat swinging a projection to
// an unrealistic extreme -- confirmed live: a team's rushDef after just
// ONE game (early season, before stats have any chance to stabilize)
// was so far below average it alone would have projected a real
// 106-yard/game back down to single digits. Real defenses regress toward
// league-average over a full season; this caps how much any one
// matchup's ratio can move a projection in either direction, regardless
// of why the underlying defensive stat looks extreme.
function clampDefenseRatio(ratio){
  return Math.max(0.6, Math.min(1.6, ratio));
}
// Real sportsbook player-prop lines always land on a half-point (X.5) --
// confirmed live: this app's raw l5avg*ratio math was instead producing
// numbers like "362.7" or "94.1", which don't look or feel like a line
// anyone could actually bet at a real book. Rounding to the nearest 0.5
// doesn't change what the number means, just how it's presented -- makes
// it read like a real, usable line instead of a raw statistical output.
function roundToHalf(n){
  return Math.round(n*2)/2;
}
// Real market line for a player prop, when one exists -- see
// fetch_player_props_odds.py for how this gets populated. Returns null
// (not a number) when unavailable, so callers can fall back to the
// model's own projection exactly like before this existed.
function getRealPropLine(playerName, stat){
  const entry = PLAYER_PROPS_ODDS && PLAYER_PROPS_ODDS[playerName] && PLAYER_PROPS_ODDS[playerName][stat];
  return (entry && entry.line!==null && entry.line!==undefined) ? entry : null;
}
// Median instead of mean for a player's "recent form" window -- confirmed
// live: a single extreme outlier game (a QB's real 457-yard passing game
// sitting in an otherwise-normal 5-game window) pulled the mean up to
// 301.6, well above what the player's other 4 games actually looked like
// (median: 269.0). A mean has no resistance to one freak game; a median
// of 5 values is resistant to up to 2 extreme values (the very highest
// and lowest) without needing an arbitrary trim threshold -- a standard,
// well-established technique for exactly this kind of high-variance,
// single-game-outlier-prone data, not an invented hack.
function median(nums){
  if(!nums.length) return 0;
  const sorted = nums.slice().sort(function(a,b){ return a-b; });
  const mid = Math.floor(sorted.length/2);
  return sorted.length%2 ? sorted[mid] : (sorted[mid-1]+sorted[mid])/2;
}
// QB is a true one-starter-at-a-time position (unlike RB/WR/TE, where more
// than one player legitimately splitting real touches is normal) -- but
// this pipeline has no depth-chart data to say who's QB1 right now. A
// mid-season benching (or an injury-driven change) leaves the old starter
// with real, non-trivial games logged that still clear the volume filter,
// so both players show up as if they're each starting. The best available
// proxy for "who's actually playing now" is whoever's last logged game is
// the most recent -- games are stored oldest-to-newest (see
// fetch_players_nfl.py), so the last array entry is each player's latest game.
function mostRecentGameKey(player){
  const games = (player && player.games) || [];
  if(games.length===0) return -1;
  const last = games[games.length-1];
  const m = /^(\d+)-wk(\d+)/.exec(last.date || '');
  if(!m) return -1;
  return Number(m[1])*100 + Number(m[2]); // year*100+week -- sorts correctly across week 9 -> week 10
}
// Keeps only the most-recently-played QB per team among a list of
// candidates that already carry {pos, team, _recencyKey, l5avg}. Non-QB
// rows pass through untouched -- committees are legitimate at other
// positions.
//
// TIE-BREAKER: confirmed live, two real QBs on the same team can have the
// exact same "most recent game" week (neither has played yet in a new
// season, both still showing last season's finale) -- recency alone
// doesn't distinguish them, and a real backup/insurance QB (barely-there
// production in his last few appearances) was passing the filter right
// alongside the actual starter. When recency ties, the higher L5 volume
// wins -- a real starter's rolling average should be substantially
// higher than a backup's, even across a tied "last played" week.
// Caps how many players per team, per position, are eligible to show up
// as a "top prop" -- no real depth-chart data exists anywhere in this
// pipeline, so recent volume (L5 average) is the best available stand-in
// for "how featured is this player in the offense right now." Per-user
// spec: QB and RB effectively have one real "starter" worth trusting for
// this purpose; WR rooms run deeper (top 4 game-to-game); TE even more
// concentrated at the top than WR (top 2).
//
// QB specifically also tie-breaks on recency first, then volume -- see
// the longer comment below on why (two QBs on the same team can share an
// identical "last played" week, and recency alone doesn't distinguish a
// real current starter from a backup who barely played in a brief stint).
// RB/WR/TE are ranked by volume alone, since the goal there isn't finding
// "the one true starter" the way it is for QB, just the most-featured
// players in the rotation.
const POSITION_CAPS = { QB: 1, RB: 1, WR: 4, TE: 2 };
function capPlayersPerTeamByPosition(candidates){
  const byTeamPos = {};
  candidates.forEach(function(c){
    const cap = POSITION_CAPS[c.pos];
    if(cap===undefined) return; // positions outside this app's tracked set (shouldn't occur given MIN_VOLUME_FOR_BET only covers QB/RB/WR/TE stats) pass through untouched below
    const key = (c.team||'')+'|'+c.pos;
    (byTeamPos[key] = byTeamPos[key] || []).push(c);
  });
  const keep = new Set();
  Object.keys(byTeamPos).forEach(function(key){
    const pos = key.split('|')[1];
    const group = byTeamPos[key];
    if(pos==='QB'){
      // Recency first (who actually played most recently), then volume as
      // the tie-breaker -- confirmed live: two real QBs on the same team
      // can share an identical "last played" week (neither has played yet
      // this season), and recency alone doesn't distinguish a real
      // current starter from a backup who barely played in a brief stint.
      group.sort(function(a,b){ return (b._recencyKey - a._recencyKey) || (b.l5avg - a.l5avg); });
    } else {
      group.sort(function(a,b){ return b.l5avg - a.l5avg; });
    }
    group.slice(0, POSITION_CAPS[pos]).forEach(function(c){ keep.add(c); });
  });
  return candidates.filter(function(c){ return POSITION_CAPS[c.pos]===undefined || keep.has(c); });
}
function normalizeTeamName(s){
  // Strips accents/diacritics and punctuation so e.g. CFBD's "San José State"
  // (from /teams/fbs) matches "San Jose State" (from /games) -- different
  // endpoints don't always agree on exact spelling for the same team.
  return (s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[.,']/g,'').replace(/\s+/g,' ').trim();
}
function resolveTeamName(rawName){
  if(teamsCache[rawName]) return rawName;
  const norm = normalizeTeamName(rawName);
  const match = Object.keys(teamsCache).find(k => normalizeTeamName(k)===norm);
  return match || rawName;
}
function findOpponentThisWeek(league, teamName){
  const games = league==='NFL' ? NFL_WEEK_GAMES : CFB_WEEK_GAMES;
  const norm = normalizeTeamName(teamName);
  for(const g of (games||[])){
    if(normalizeTeamName(g.a)===norm) return resolveTeamName(g.b);
    if(normalizeTeamName(g.b)===norm) return resolveTeamName(g.a);
  }
  return null;
}
function leagueAvgDefStat(league, key){
  const teams = Object.values(teamsCache).filter(t=>t.league===league && t[key]);
  if(teams.length===0) return null;
  return teams.reduce((s,t)=>s+t[key],0)/teams.length;
}
// Same small-sample problem shrinkStat fixes for ppg/pa/to, extended to
// passOff/rushOff/passDef/rushDef -- confirmed live these were still
// being read completely raw everywhere, including feeding directly into
// EVERY player prop's opponent-matchup ratio (teamsCache[opp][defKey]).
// An opponent's pass/rush defense number from just 1-2 games is exactly
// the kind of extreme-outlier-prone sample this app already treats
// carefully for ppg/pa/to; player props inherited that same risk here
// without the same protection. No team-specific previous-season prior
// exists yet for these 4 specific stats (only ppg/pa/to have that), so
// this shrinks toward league average for now -- still a large
// improvement over no shrinkage at all, and a reasonable next candidate
// for a team-specific prior later once that data's being fetched.
function shrunkTeamStat(team, statKey, league){
  if(!team) return null;
  const raw = team[statKey];
  if(raw===null || raw===undefined) return raw;
  const gamesPlayed = (team.games && team.games.length) || 0;
  const leagueAvg = leagueAvgDefStat(league, statKey);
  return shrinkStat(raw, null, leagueAvg, gamesPlayed);
}
// Detects a likely backup/emergency QB situation for a team -- confirmed
// live this was a real, meaningful gap: the model had no way to know a
// team's QB situation had changed at all, using season-wide ppg built
// mostly from games the normal starter played. Real example that
// motivated this: Bears' starter and primary backup were both hurt in
// the same week, dropping them to their 3rd-string QB -- the real market
// line swung 6 points (Bears -1.5 to Bears +4.5) purely on that news, and
// the model had zero mechanism to reflect any of it.
//
// Two independent signals, either one triggers the flag:
// 1. RECENCY MISMATCH -- the team's season-long primary QB (most games
//    played) is not the one who played most recently, meaning a backup
//    has ALREADY taken meaningful snaps this season.
// 2. INJURY REPORT -- the season-long primary QB is listed Out or
//    Doubtful on the current injury report.
//
// HONEST LIMITATION: this can detect "a backup is playing" but not WHICH
// backup, or how far down the depth chart the team has had to go. A
// third-string emergency QB (like the Bears/Keenum case, since Keenum
// has zero games logged this season and so isn't even visible to this
// detection at all) is a much bigger downgrade than a normal primary
// backup, but this applies the same flat penalty either way -- it's a
// real, useful signal, not a complete substitute for actually knowing
// this week's specific depth-chart situation.
const BACKUP_QB_PENALTY = 5; // points off the team's projected offense when flagged -- a middle estimate grounded in the real 6-point Bears/Eagles market swing, not an exact calibration
// Rest-days adjustment -- confirmed live this was a real, well-documented
// gap with zero data-source cost: everything needed (real calendar dates
// for each team's games) was already one field away in the same raw
// nflverse data fetch_nfl.py already pulls, just never carried through
// past "week number" into each team's game log. A short week (Thursday
// game after a normal Sunday game, ~4 days rest instead of the usual ~7)
// and an extra-rest week (coming off a bye, ~13-14 days) are both
// commonly-documented factors in real sports analytics -- modest,
// single-digit-point effects, not huge ones, which is why these
// adjustments are kept small and symmetric rather than dramatic.
const REST_SHORT_THRESHOLD = 5; // days -- at or below this counts as a short week
const REST_LONG_THRESHOLD = 12; // days -- at or above this counts as extra rest (bye week territory)
const REST_SHORT_PENALTY = 1.5; // points off projected offense on a short week
const REST_LONG_BONUS = 1.0; // points added to projected offense coming off extra rest
function computeRestDays(team, upcomingGameDate){
  const games = team && team.games;
  if(!games || !games.length || !upcomingGameDate) return null;
  const lastGame = games[games.length-1];
  if(!lastGame.date) return null; // older cached data without the date field yet -- gracefully skip rather than guess
  const lastDate = new Date(lastGame.date+'T00:00:00Z');
  const upcoming = new Date(upcomingGameDate+'T00:00:00Z');
  const days = Math.round((upcoming-lastDate)/(1000*60*60*24));
  return days>0 ? days : null; // negative/zero would mean bad data (upcoming date before last game) -- treat as unknown rather than apply a nonsensical adjustment
}
function restAdjustment(team, upcomingGameDate){
  const days = computeRestDays(team, upcomingGameDate);
  if(days===null) return 0;
  if(days<=REST_SHORT_THRESHOLD) return -REST_SHORT_PENALTY;
  if(days>=REST_LONG_THRESHOLD) return REST_LONG_BONUS;
  return 0;
}
// Weather adjustment -- confirmed real via fetch_weather.py using the
// National Weather Service's real public API structure. Applied to the
// TOTAL (not one team's spread specifically), since bad weather affects
// both offenses playing in the same conditions, not just one side.
// NFL-only, home-team's stadium only (the away team plays in the SAME
// conditions as the home team, so only one lookup per game is needed) --
// see fetch_weather.py's docstring for the CFB scope decision.
const WEATHER_TOTAL_PENALTY = 3; // points off the combined total when flagged severe -- a modest, commonly-cited magnitude for real bad-weather NFL games, not a dramatic one
function weatherAdjustment(homeTeamName, league){
  if(league!=='NFL') return 0;
  const w = WEATHER_CACHE[homeTeamName];
  if(!w || w.dome || !w.severe) return 0;
  return -WEATHER_TOTAL_PENALTY;
}
function detectBackupQB(teamName, league){
  if(league!=='NFL') return null; // injury report + this whole detection mechanism only covers NFL for now
  const qbs = Object.keys(playersCache).filter(function(n){
    const p = playersCache[n];
    return p.team===teamName && p.pos==='QB' && p.league===league;
  });
  if(qbs.length<2) return null; // nothing to compare against
  let primary = null, primaryGames = -1;
  qbs.forEach(function(n){
    const g = (playersCache[n].games||[]).length;
    if(g>primaryGames){ primaryGames = g; primary = n; }
  });
  if(!primary || primaryGames<2) return null; // too little data to call anyone "the primary" confidently
  let mostRecent = null, mostRecentKey = -1;
  qbs.forEach(function(n){
    const k = mostRecentGameKey(playersCache[n]);
    if(k>mostRecentKey){ mostRecentKey = k; mostRecent = n; }
  });
  const recencyMismatch = mostRecent && mostRecent!==primary;

  let injuryFlag = false;
  const teamInjuries = (INJURIES_CACHE[teamName]||[]);
  teamInjuries.forEach(function(e){
    if(e.name===primary && e.pos==='QB' && (e.status==='Out' || e.status==='Doubtful')) injuryFlag = true;
  });

  if(!recencyMismatch && !injuryFlag) return null;
  return {
    primary: primary,
    reason: injuryFlag ? (primary+' listed '+teamInjuries.find(function(e){return e.name===primary;}).status+' at QB')
                        : (primary+'\'s backup has already played more recently this season'),
  };
}

function wireHitRate(lg){
  document.getElementById(lg+'-run-hitrate').addEventListener('click', ()=>{
    const name = document.getElementById(lg+'-hr-player').value;
    const stat = document.getElementById(lg+'-hr-stat').value;
    const line = parseFloat(document.getElementById(lg+'-hr-line').value);
    const out = document.getElementById(lg+'-hitrate-output');
    if(!name || !playersCache[name]){ out.innerHTML = '<div class="empty">No games logged for this player yet.</div>'; return; }
    const player = playersCache[name];
    // Last 10 games, most-recent first -- dips into last season automatically
    // when the current season doesn't have 10 games yet (handled by the
    // fetch scripts; this slice(-10) is just a defensive cap in the UI too).
    const games = (player.games || []).slice(-10).reverse();
    if(games.length===0){ out.innerHTML = '<div class="empty">No games logged for this player yet.</div>'; return; }
    if(isNaN(line)){ out.innerHTML = '<div class="empty">Enter the line to check against.</div>'; return; }
    const overs = games.filter(g=>(g[stat]||0) > line).length;
    const pct = Math.round((overs/games.length)*100);
    const last5 = games.slice(0,5);
    const last5overs = last5.filter(g=>(g[stat]||0) > line).length;

    // Defense-adjusted estimate: scale the raw hit rate by how this week's
    // opponent's relevant defense compares to the league average. This is a
    // simple multiplicative heuristic, not a statistical model -- it's meant
    // to show direction and rough size of the matchup effect, not a precise
    // probability.
    let adjBlock = '';
    const league = lg.toUpperCase();
    const teamUnconfirmed = league==='NFL' && player.team && (player.teamYear==null);
    if(teamUnconfirmed){
      adjBlock = '<div class="note" style="margin-top:14px;color:#f28b7d;">⚠ '+name+' isn\'t on any 2026 active roster in the latest data — "'+player.team+'" is just their last known team, not confirmed current. Skipping the opponent-defense adjustment since it depends on knowing who they\'re actually playing this week.</div>';
    } else {
    const opp = findOpponentThisWeek(league, player.team);
    const defKey = defCategoryForStat(stat);
    if(opp && teamsCache[opp] && defKey && teamsCache[opp][defKey]){
      const oppVal = shrunkTeamStat(teamsCache[opp], defKey, league);
      const avgVal = leagueAvgDefStat(league, defKey);
      if(avgVal){
        const ratio = clampDefenseRatio(oppVal/avgVal); // >1 = opponent allows more than average (easier matchup)
        const adjPct = Math.max(0, Math.min(100, Math.round(pct*ratio)));
        const adjClass = adjPct>=60 ? 'high' : (adjPct>=40 ? 'mid' : 'low');
        const strength = ratio>=1.08 ? 'a below-average' : (ratio<=0.92 ? 'a tougher-than-average' : 'a roughly average');
        const defLabel = defKey==='passDef' ? 'pass' : 'rush';
        adjBlock = '<div class="note" style="margin-top:14px;margin-bottom:4px;">This week: <b>'+name+'</b> ('+player.team+') vs <b>'+opp+'</b> — '+strength+' '+defLabel+' defense ('+fmt(oppVal)+' '+defLabel+' yds/g allowed vs league avg '+fmt(avgVal)+').</div>'+
          '<div class="hitrate-badge '+adjClass+'">'+adjPct+'% <span style="font-size:0.9rem;font-weight:600;"> adjusted</span></div>'+
          '<div class="hitrate-sub">raw rate ('+pct+'%) scaled by opponent defense vs league average — a simple heuristic, not a statistical projection.</div>';
      }
    } else if(defKey){
      adjBlock = '<div class="note" style="margin-top:14px;">No opponent-defense adjustment available — '+(opp ? "couldn't find "+opp+"'s stats" : "couldn't find "+name+"'s game this week")+'.</div>';
    }
    }

    const badgeClass = pct>=60 ? 'high' : (pct>=40 ? 'mid' : 'low');
    const rows = games.map(function(g){
      const val = g[stat]||0;
      const isOver = val > line;
      return '<div class="glog-row"><span>'+g.date+(g.opp?' · '+g.opp:'')+'</span><span class="glog-val '+(isOver?'over':'under')+'">'+fmt(val)+' '+(isOver?'▲':'▼')+'</span></div>';
    }).join('');
    out.innerHTML = '<div class="hitrate-badge '+badgeClass+'">'+overs+'/'+games.length+' · '+pct+'%</div><div class="hitrate-sub">raw rate over '+line+' '+statLabel(stat)+' (last '+games.length+' games) · last 5: '+last5overs+'/'+last5.length+'</div>'+adjBlock+'<div style="margin-top:12px;">'+rows+'</div>';
  });
}
wireHitRate('nfl');
wireHitRate('cfb');