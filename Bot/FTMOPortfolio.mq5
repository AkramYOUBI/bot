//+------------------------------------------------------------------+
//| FTMOPortfolio.mq5  v2.0                                          |
//| Portefeuille multi-marches pour challenge FTMO 100k 2-Step       |
//|  - Tendance  : cassure 20j (logique GoldFTMO) sur Or, WTI, Brent |
//|  - Crypto    : cassure 20j long, TP 3R sur BTC, ETH              |
//|  - Retour moyenne indices : IBS, RSI(2), Double-7 (US/GER)       |
//|  - Double-7 sur l'or                                             |
//| Un seul graphique suffit (n'importe quel symbole, ex XAUUSD H1). |
//| Signaux sur bougie D1 cloturee, execution apres InpEntryHour.    |
//| Regles FTMO : -5 %/jour (garde-fou 3.5 %), -10 % total, objectif |
//| Phase 1 +10 % / Phase 2 +5 % puis arret automatique.            |
//| Valide sur Dukascopy H1 bid/ask 2020-2026 (ftmo_lab/).           |
//+------------------------------------------------------------------+
#property copyright "FTMO Portfolio"
#property version   "2.00"
#property strict

#include <Trade/Trade.mqh>

enum EMode
  {
   MODE_PHASE1 = 0,   // Challenge Phase 1 (objectif +10 %)
   MODE_PHASE2 = 1,   // Challenge Phase 2 (objectif +5 %)
   MODE_FUNDED = 2    // Compte finance (pas d'objectif, risque reduit)
  };

enum EUniverse
  {
   UNIV_ADAPT = 0,    // Or adaptatif achat+vente selon regime (XAUUSD) - 3 briques
   UNIV_GOLD  = 1,    // Or achat seul v2.0 (XAUUSD) - 4 briques
   UNIV_MULTI = 2     // Multi-marches - 13 briques
  };

input group "=== Mode ==="
input EUniverse InpUniverse   = UNIV_ADAPT;   // Univers (or seul / multi-marches)
input EMode  InpMode          = MODE_PHASE1; // Mode
input double InpCapital       = 100000.0;    // Capital initial du compte
input double InpKChallenge    = 3.0;         // Multiplicateur risque Phase 1/2 (adaptatif 3.0 | or 2.0 | multi 2.5)
input double InpKFunded       = 1.25;        // Multiplicateur risque finance (adaptatif 1.25 | or 1.0 | multi 0.75)
input double InpTarget1Pct    = 10.0;        // Objectif Phase 1 %
input double InpTarget2Pct    = 5.0;         // Objectif Phase 2 %
input int    InpMinDays       = 4;           // Jours de trading minimum FTMO
input bool   InpStopAtTarget  = true;        // Tout fermer et arreter a l'objectif

input group "=== Protection FTMO ==="
input double InpDailyGuardPct = 3.5;         // Garde-fou jour % (FTMO = 5)
input double InpMaxLossPct    = 10.0;        // Perte max totale FTMO %
input double InpMaxOpenPct    = 4.0;         // Risque ouvert max cumule % (adaptatif 4 | or 5 | multi 8)
input double InpDDScalePct    = 6.0;         // Risque reduit lineairement en DD % (or 6 | multi 10)
input int    InpPragueOffset  = 1;           // Heure serveur - heure Prague (FTMO = 1)

input group "=== Execution ==="
input int    InpEntryHour     = 2;           // Heure serveur mini pour agir (evite reouverture)
input int    InpDeviation     = 50;          // Glissement max (points)
input long   InpMagicBase     = 26111800;    // Magic de base (+id composant)
input bool   InpResetHalt     = false;       // Effacer un arret (objectif/plafond)

input group "=== Symboles (noms FTMO) ==="
input string InpGold  = "XAUUSD";
input string InpWTI   = "USOIL.cash";
input string InpBrent = "UKOIL.cash";
input string InpBTC   = "BTCUSD";
input string InpETH   = "ETHUSD";
input string InpUS30  = "US30.cash";
input string InpUS100 = "US100.cash";
input string InpUS500 = "US500.cash";
input string InpGER40 = "GER40.cash";

input group "=== Briques actives ==="
input bool InpUseBRK  = true;   // Cassure 20j Or/Petrole
input bool InpUseCRY  = true;   // Cassure crypto
input bool InpUseD7   = true;   // Double-7
input bool InpUseIBS  = true;   // IBS indices
input bool InpUseRSI2 = true;   // RSI(2) indices

//--- types de strategies
#define T_BRK  0
#define T_CRY  1
#define T_D7   2
#define T_IBS  3
#define T_RSI2 4
#define T_MOM  5
#define T_RBRK 6   // cassure dans le sens du regime (achat ou vente)
#define T_RMOM 7   // momentum hebdo dans le sens du regime (achat ou vente)

struct Comp
  {
   string   name;
   string   sym;
   int      type;
   double   w;        // risque de base en % (multiplie par K)
   double   slAtr;
   double   tpR;      // 0 = pas de TP
   double   th;       // seuil (RSI)
   int      maxd;     // jours max
   int      en;       // cassure : N barres entree | momentum : recul N jours
   int      ex;       // cassure : N barres sortie
   double   be;       // stop ramene a l'entree (+0.1R) des +be R (0 = off)
   long     magic;
   bool     on;
   datetime doneBar;  // derniere bougie D1 traitee
   datetime nextCheck;// prochaine verification (evite le travail a chaque tick)
   bool     warnHist;
   int      nSig, nTrade, nRisk, nLot, nRefus, nHist, nLive; // bilan (journal en fin de test)
  };

Comp   C[];
CTrade trade;
string gvPrefix;
string g_log = "";

#define NBARS   1000   // EMA200 : il faut un long historique pour converger
#define MINBARS 300

//--- etat en memoire (GlobalVariables ecrites seulement quand ca change)
int    s_day = 0, s_lastTd = 0;
double s_dayBal = 0.0, s_tdays = 0.0;
bool   s_hday = false, s_hall = false, s_done = false;
bool   g_tester = false;

//+------------------------------------------------------------------+
void AddComp(const string name, const string sym, const int type, const double w,
             const double slAtr, const double tpR, const double th, const int maxd, const bool use,
             const int en = 20, const int ex = 10)
  {
   int n = ArraySize(C);
   ArrayResize(C, n + 1);
   C[n].en = en;
   C[n].ex = ex;
   C[n].be = 0.0;
   C[n].name = name;
   C[n].sym = sym;
   C[n].type = type;
   C[n].w = w;
   C[n].slAtr = slAtr;
   C[n].tpR = tpR;
   C[n].th = th;
   C[n].maxd = maxd;
   C[n].magic = InpMagicBase + n;
   C[n].on = use;
   C[n].doneBar = 0;
   C[n].nextCheck = 0;
   C[n].warnHist = false;
   C[n].nSig = 0; C[n].nTrade = 0; C[n].nRisk = 0; C[n].nLot = 0;
   C[n].nRefus = 0; C[n].nHist = 0; C[n].nLive = 0;
  }

//+------------------------------------------------------------------+
//| Trouve le nom du symbole chez le broker (FTMO ou autre)          |
//+------------------------------------------------------------------+
bool TrySym(const string name, string &out)
  {
   bool custom = false;
   if(name == "" || !SymbolExist(name, custom))
      return false;
   if(!SymbolSelect(name, true))
      return false;
   out = name;
   return true;
  }

string ResolveSym(const string wanted)
  {
   string out = "";
   if(TrySym(wanted, out))
      return out;
   string alt = "";
   if(wanted == InpGold)  alt = "XAUUSD,GOLD,XAUUSD.,XAUUSDm,XAUUSD.a";
   if(wanted == InpWTI)   alt = "USOIL.cash,USOIL,WTI,XTIUSD,USOUSD,CL-OIL,WTI.cash,OILUSD";
   if(wanted == InpBrent) alt = "UKOIL.cash,UKOIL,BRENT,XBRUSD,UKOUSD,BRENT.cash";
   if(wanted == InpBTC)   alt = "BTCUSD,BTCUSD.,BTCUSDm,BITCOIN,XBTUSD";
   if(wanted == InpETH)   alt = "ETHUSD,ETHUSD.,ETHUSDm,ETHEREUM";
   if(wanted == InpUS30)  alt = "US30.cash,US30,DJ30,WS30,US30Cash,DOW30,USA30";
   if(wanted == InpUS100) alt = "US100.cash,US100,NAS100,USTEC,NDX100,US100Cash,USTECH";
   if(wanted == InpUS500) alt = "US500.cash,US500,SPX500,SP500,US500Cash,USA500";
   if(wanted == InpGER40) alt = "GER40.cash,GER40,DE40,DAX40,GER30,DE30,GER40Cash";
   string parts[];
   int k = StringSplit(alt, ',', parts);
   for(int j = 0; j < k; j++)
      if(TrySym(parts[j], out))
         return out;
   return "";
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpCapital <= 0.0)
      return INIT_PARAMETERS_INCORRECT;
   ArrayResize(C, 0);
   if(InpUniverse == UNIV_ADAPT)
     {
      //       nom         symbole  type    poids SL   TP  seuil maxj actif      en  ex
      AddComp("RBRK20_OR", InpGold, T_RBRK, 1.00, 1.8, 3.0, 0, 15, InpUseBRK, 20, 10);
      C[ArraySize(C) - 1].be = 1.0;
      AddComp("RBRK55_OR", InpGold, T_RBRK, 0.70, 1.8, 2.0, 0, 30, InpUseBRK, 55, 20);
      C[ArraySize(C) - 1].be = 1.0;
      AddComp("RMOM_OR",   InpGold, T_RMOM, 0.60, 3.0, 0.0, 0,  4, true,      60,  0);
     }
   else if(InpUniverse == UNIV_GOLD)
     {
      //       nom        symbole  type   poids SL   TP  seuil maxj actif      en  ex
      AddComp("BRK20_OR", InpGold, T_BRK, 1.00, 1.8, 3.0, 0, 15, InpUseBRK, 20, 10);
      AddComp("BRK55_OR", InpGold, T_BRK, 0.70, 1.8, 2.0, 0, 30, InpUseBRK, 55, 20);
      AddComp("D7_OR",    InpGold, T_D7,  0.80, 3.0, 0.0, 0, 10, InpUseD7);
      AddComp("MOM_OR",   InpGold, T_MOM, 0.60, 3.0, 0.0, 0,  4, true,      60,  0);
     }
   else
     {
   //       nom          symbole   type    poids  SL   TP  seuil maxj  actif
   AddComp("BRK_OR",    InpGold,  T_BRK,  1.00, 1.8, 2.0,  0, 15, InpUseBRK);
   AddComp("BRK_WTI",   InpWTI,   T_BRK,  0.70, 1.8, 2.0,  0, 15, InpUseBRK);
   AddComp("BRK_BRENT", InpBrent, T_BRK,  0.30, 1.8, 2.0,  0, 15, InpUseBRK);
   AddComp("CRY_BTC",   InpBTC,   T_CRY,  0.40, 2.0, 3.0,  0, 60, InpUseCRY);
   AddComp("CRY_ETH",   InpETH,   T_CRY,  0.40, 2.0, 3.0,  0, 60, InpUseCRY);
   AddComp("D7_OR",     InpGold,  T_D7,   0.50, 3.0, 0.0,  0, 10, InpUseD7);
   AddComp("D7_US30",   InpUS30,  T_D7,   0.40, 3.0, 0.0,  0, 10, InpUseD7);
   AddComp("IBS_US100", InpUS100, T_IBS,  0.40, 3.0, 0.0,  0,  5, InpUseIBS);
   AddComp("IBS_US500", InpUS500, T_IBS,  0.40, 3.0, 0.0,  0,  5, InpUseIBS);
   AddComp("IBS_US30",  InpUS30,  T_IBS,  0.40, 3.0, 0.0,  0,  5, InpUseIBS);
   AddComp("IBS_GER40", InpGER40, T_IBS,  0.40, 3.0, 0.0,  0,  5, InpUseIBS);
   AddComp("RSI2_US500",InpUS500, T_RSI2, 0.60, 2.0, 0.0, 10, 10, InpUseRSI2);
   AddComp("RSI2_US100",InpUS100, T_RSI2, 0.60, 2.0, 0.0, 20, 10, InpUseRSI2);
     }

   for(int i = 0; i < ArraySize(C); i++)
     {
      if(!C[i].on)
         continue;
      string found = ResolveSym(C[i].sym);
      if(found == "")
        {
         PrintFormat("!! Symbole %s introuvable -> brique %s DESACTIVEE (mets le bon nom dans les parametres).",
                     C[i].sym, C[i].name);
         C[i].on = false;
         continue;
        }
      if(found != C[i].sym)
         PrintFormat("Symbole %s remplace par %s pour %s.", C[i].sym, found, C[i].name);
      C[i].sym = found;
      PrintFormat("Brique %-11s -> %-12s | lot min %.2f | pas %.2f", C[i].name, C[i].sym,
                  SymbolInfoDouble(C[i].sym, SYMBOL_VOLUME_MIN), SymbolInfoDouble(C[i].sym, SYMBOL_VOLUME_STEP));
     }

   gvPrefix = "FP1_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "_" +
              IntegerToString(InpMagicBase) + "_";
   if(InpResetHalt)
     {
      GlobalVariableSet(gvPrefix + "HALL", 0.0);
      GlobalVariableSet(gvPrefix + "HDAY", 0.0);
      GlobalVariableSet(gvPrefix + "DONE", 0.0);
      s_hall = false; s_hday = false; s_done = false;
      Print("Arrets effaces. Remets InpResetHalt=false.");
     }
   if(MQLInfoInteger(MQL_TESTER))
      GlobalVariablesDeleteAll(gvPrefix);      // chaque backtest repart d'un etat propre
   s_day    = (int)GV("DAY");
   s_dayBal = GV("DAYBAL");
   s_hday   = GV("HDAY") > 0.5;
   s_hall   = GV("HALL") > 0.5;
   s_done   = GV("DONE") > 0.5;
   s_tdays  = GV("TDAYS");
   s_lastTd = (int)GV("LASTTD");
   g_tester = (bool)MQLInfoInteger(MQL_TESTER) && !(bool)MQLInfoInteger(MQL_VISUAL_MODE);
   trade.SetDeviationInPoints(InpDeviation);
   EventSetTimer(60);   // crypto le week-end : pas de tick sur l'or, le timer prend le relais
   PrintFormat("FTMOPortfolio v2.0 | mode %s | K %.2f | capital %.0f | %d briques",
               EnumToString(InpMode), K(), InpCapital, ArraySize(C));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   Print("===== BILAN PAR BRIQUE (signaux / trades / refus risque / lot trop petit / refus broker / historique KO / marche ferme) =====");
   for(int i = 0; i < ArraySize(C); i++)
      PrintFormat("%-11s %-12s %s | sig %d | trades %d | risque %d | lot %d | refus %d | hist %d | ferme %d",
                  C[i].name, C[i].sym, C[i].on ? "ON " : "OFF", C[i].nSig, C[i].nTrade, C[i].nRisk,
                  C[i].nLot, C[i].nRefus, C[i].nHist, C[i].nLive);
   EventKillTimer();
   Comment("");
  }

//+------------------------------------------------------------------+
double GV(const string k)       { return GlobalVariableCheck(gvPrefix + k) ? GlobalVariableGet(gvPrefix + k) : 0.0; }
void   GVSet(const string k, const double v) { GlobalVariableSet(gvPrefix + k, v); }
double K()                       { return InpMode == MODE_FUNDED ? InpKFunded : InpKChallenge; }
double TargetPct()
  {
   if(InpMode == MODE_PHASE1) return InpTarget1Pct;
   if(InpMode == MODE_PHASE2) return InpTarget2Pct;
   return 0.0;
  }

// Jour FTMO (minuit Prague) a partir de l'heure serveur
int FtmoDay()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent() - (datetime)(InpPragueOffset * 3600), dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
  }

//+------------------------------------------------------------------+
bool SelectComp(const int i, ulong &ticket)
  {
   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      ulong t = PositionGetTicket(p);
      if(t == 0)
         continue;
      if(PositionGetInteger(POSITION_MAGIC) == C[i].magic && PositionGetString(POSITION_SYMBOL) == C[i].sym)
        {
         ticket = t;
         return true;
        }
     }
   ticket = 0;
   return false;
  }

bool IsMine(const long magic)
  {
   return magic >= InpMagicBase && magic < InpMagicBase + ArraySize(C);
  }

void CloseAll(const string why)
  {
   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      ulong t = PositionGetTicket(p);
      if(t == 0 || !IsMine(PositionGetInteger(POSITION_MAGIC)))
         continue;
      trade.SetExpertMagicNumber((ulong)PositionGetInteger(POSITION_MAGIC));
      trade.SetTypeFillingBySymbol(PositionGetString(POSITION_SYMBOL));
      trade.PositionClose(t);
     }
   Print(why);
  }

// Perte en $ si le stop de la position est touche (0 si stop au-dela de l'entree)
double PosRisk()
  {
   double profit = 0.0;
   string sym = PositionGetString(POSITION_SYMBOL);
   double vol = PositionGetDouble(POSITION_VOLUME);
   double op  = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl  = PositionGetDouble(POSITION_SL);
   long   typ = PositionGetInteger(POSITION_TYPE);
   if(sl <= 0.0)
      return InpCapital * 0.03;
   ENUM_ORDER_TYPE ot = (typ == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(ot, sym, vol, op, sl, profit))
      return InpCapital * 0.03;
   return MathMax(0.0, -profit);
  }

double OpenRisk()
  {
   double tot = 0.0;
   for(int p = PositionsTotal() - 1; p >= 0; p--)
     {
      ulong t = PositionGetTicket(p);
      if(t == 0 || !IsMine(PositionGetInteger(POSITION_MAGIC)))
         continue;
      tot += PosRisk();
     }
   return tot;
  }

//+------------------------------------------------------------------+
//| Plafonds FTMO : renvoie false si on ne doit pas ouvrir           |
//+------------------------------------------------------------------+
bool Guard()
  {
   int day = FtmoDay();
   if(s_day != day)
     {
      s_day = day;
      s_dayBal = AccountInfoDouble(ACCOUNT_BALANCE);   // regle FTMO : solde debut de jour
      s_hday = false;
      GVSet("DAY", day);
      GVSet("DAYBAL", s_dayBal);
      GVSet("HDAY", 0.0);
     }
   if(s_hall || s_done)
      return false;

   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dayFloor = s_dayBal - InpCapital * InpDailyGuardPct / 100.0;
   double maxFloor = InpCapital * (1.0 - InpMaxLossPct / 100.0) + InpCapital * 0.002;

   if(eq <= maxFloor)
     {
      CloseAll("ARRET TOTAL : proche du plafond -10 %.");
      s_hall = true;
      GVSet("HALL", 1.0);
      return false;
     }
   if(s_hday)
      return false;
   if(eq <= dayFloor)
     {
      CloseAll(StringFormat("JOURNEE COUPEE : garde-fou -%.1f %% atteint.", InpDailyGuardPct));
      s_hday = true;
      GVSet("HDAY", 1.0);
      return false;
     }

   double tgt = TargetPct();
   if(InpStopAtTarget && tgt > 0.0 && eq >= InpCapital * (1.0 + tgt / 100.0) && s_tdays >= InpMinDays)
     {
      CloseAll(StringFormat("OBJECTIF +%.0f %% ATTEINT (%.0f jours de trading). Robot arrete.", tgt, s_tdays));
      s_done = true;
      GVSet("DONE", 1.0);
      return false;
     }
   return true;
  }

void CountTradingDay()
  {
   int day = FtmoDay();
   if(s_lastTd != day)
     {
      s_lastTd = day;
      s_tdays += 1.0;
      GVSet("LASTTD", day);
      GVSet("TDAYS", s_tdays);
     }
  }

//+------------------------------------------------------------------+
//| Indicateurs calcules a la main sur D1 (identiques au labo)       |
//| r[0..n-1] : plus ancien -> bougie d'hier (r[n-1])                |
//+------------------------------------------------------------------+
double HiMax(const MqlRates &r[], const int from, const int to)
  {
   double m = -DBL_MAX;
   for(int j = from; j <= to; j++) m = MathMax(m, r[j].high);
   return m;
  }
double LoMin(const MqlRates &r[], const int from, const int to)
  {
   double m = DBL_MAX;
   for(int j = from; j <= to; j++) m = MathMin(m, r[j].low);
   return m;
  }
double ClMax(const MqlRates &r[], const int from, const int to)
  {
   double m = -DBL_MAX;
   for(int j = from; j <= to; j++) m = MathMax(m, r[j].close);
   return m;
  }
double ClMin(const MqlRates &r[], const int from, const int to)
  {
   double m = DBL_MAX;
   for(int j = from; j <= to; j++) m = MathMin(m, r[j].close);
   return m;
  }
double SmaClose(const MqlRates &r[], const int idx, const int n)
  {
   double s = 0.0;
   for(int j = idx - n + 1; j <= idx; j++) s += r[j].close;
   return s / n;
  }
// ATR = moyenne simple du True Range (comme iATR MT5)
void AtrArr(const MqlRates &r[], const int n, const int per, double &a[])
  {
   ArrayResize(a, n);
   ArrayInitialize(a, 0.0);
   double tr[];
   ArrayResize(tr, n);
   tr[0] = r[0].high - r[0].low;
   for(int j = 1; j < n; j++)
      tr[j] = MathMax(r[j].high - r[j].low, MathMax(MathAbs(r[j].high - r[j - 1].close), MathAbs(r[j].low - r[j - 1].close)));
   double s = 0.0;
   for(int j = 0; j < n; j++)
     {
      s += tr[j];
      if(j >= per) s -= tr[j - per];
      if(j >= per - 1) a[j] = s / per;
     }
  }
void EmaArr(const MqlRates &r[], const int n, const int per, double &e[])
  {
   ArrayResize(e, n);
   double k = 2.0 / (per + 1.0);
   e[0] = r[0].close;
   for(int j = 1; j < n; j++) e[j] = k * r[j].close + (1.0 - k) * e[j - 1];
  }
double Rsi(const MqlRates &r[], const int n, const int per)
  {
   double up = 0.0, dn = 0.0, a = 1.0 / per;
   for(int j = 1; j < n; j++)
     {
      double d = r[j].close - r[j - 1].close;
      up = a * MathMax(d, 0.0) + (1.0 - a) * up;
      dn = a * MathMax(-d, 0.0) + (1.0 - a) * dn;
     }
   if(dn <= 0.0) return 100.0;
   return 100.0 - 100.0 / (1.0 + up / dn);
  }

//+------------------------------------------------------------------+
//| Sortie journaliere (bougie d'hier cloturee)                      |
//+------------------------------------------------------------------+
//+------------------------------------------------------------------+
//| Regime D1 : +1 haussier, -1 baissier, 0 neutre                    |
//| haussier = cloture > EMA200, EMA50 > EMA200, EMA50 monte sur 10j  |
//+------------------------------------------------------------------+
int Regime(const MqlRates &r[], const int n)
  {
   int d = n - 1;
   double e50[], e200[];
   EmaArr(r, n, 50, e50);
   EmaArr(r, n, 200, e200);
   double c1 = r[d].close;
   double slope = e50[d] - e50[d - 10];
   if(c1 > e200[d] && e50[d] > e200[d] && slope > 0.0) return 1;
   if(c1 < e200[d] && e50[d] < e200[d] && slope < 0.0) return -1;
   return 0;
  }

bool ExitSignal(const int i, const MqlRates &r[], const int n, const int side)
  {
   int d = n - 1;
   double c1 = r[d].close;
   switch(C[i].type)
     {
      case T_RBRK:
         if(side > 0) return c1 < LoMin(r, d - C[i].ex, d - 1);
         return c1 > HiMax(r, d - C[i].ex, d - 1);
      case T_RMOM:
         return false;                                  // sortie par le temps (4 jours)
      case T_BRK:
      case T_CRY:
         return c1 < LoMin(r, d - C[i].ex, d - 1);     // cloture sous le plus bas N jours
      case T_MOM:
         return false;                                  // sortie par le temps (4 jours)
      case T_D7:
         return c1 >= ClMax(r, d - 6, d);               // cloture au plus haut 7j
      case T_IBS:
         return c1 > r[d - 1].high;                     // cloture au-dessus du haut de la veille
      case T_RSI2:
         return c1 > SmaClose(r, d, 5);                 // cloture au-dessus de la MM5
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Entree journaliere : renvoie true si achat + distance du stop    |
//+------------------------------------------------------------------+
bool EntrySignal(const int i, const MqlRates &r[], const int n, double &slDist, string &why, int &side)
  {
   int d = n - 1;
   side = 1;
   double atr[];
   AtrArr(r, n, 20, atr);
   double A = atr[d];
   if(A <= 0.0)
      return false;
   double c1 = r[d].close, c2 = r[d - 1].close;
   slDist = A * C[i].slAtr;

   switch(C[i].type)
     {
      case T_RBRK:
        {
         int rg = Regime(r, n);
         if(rg > 0 && c1 > HiMax(r, d - C[i].en, d - 1) && c2 <= HiMax(r, d - C[i].en - 1, d - 2))
            side = 1;
         else if(rg < 0 && c1 < LoMin(r, d - C[i].en, d - 1) && c2 >= LoMin(r, d - C[i].en - 1, d - 2))
            side = -1;
         else
            return false;
         why = StringFormat("regime %s : cassure %dj %s", rg > 0 ? "HAUSSIER" : "BAISSIER", C[i].en,
                            side > 0 ? "du plus haut" : "du plus bas");
         return true;
        }
      case T_RMOM:
        {
         MqlDateTime bt;
         TimeToStruct(r[d].time, bt);
         if(bt.day_of_week != 5)
            return false;                               // signal a la cloture du vendredi
         int rg = Regime(r, n);
         double past = r[d - C[i].en].close;
         if(rg > 0 && c1 > past)
            side = 1;
         else if(rg < 0 && c1 < past)
            side = -1;
         else
            return false;
         why = StringFormat("regime %s : momentum %dj %.2f vs %.2f", rg > 0 ? "HAUSSIER" : "BAISSIER", C[i].en, c1, past);
         return true;
        }
      case T_BRK:
        {
         double avg = 0.0;
         for(int j = d - 49; j <= d; j++) avg += atr[j];
         avg /= 50.0;
         if(avg > 0.0 && A > 2.2 * avg)
            return false;                                       // volatilite extreme
         double h1 = HiMax(r, d - C[i].en, d - 1), h2 = HiMax(r, d - C[i].en - 1, d - 2);
         if(!(c1 > h1 && c2 <= h2))
            return false;
         double ema[];
         EmaArr(r, n, 50, ema);
         if(!(c1 > ema[d] && ema[d] > ema[d - 3]))
            return false;
         why = StringFormat("cassure %dj %.2f > %.2f", C[i].en, c1, h1);
         return true;
        }
      case T_MOM:
        {
         MqlDateTime bt;
         TimeToStruct(r[d].time, bt);
         if(bt.day_of_week != 5 || !(c1 > r[d - C[i].en].close))
            return false;                               // signal a la cloture du vendredi
         why = StringFormat("momentum %dj : %.2f > %.2f", C[i].en, c1, r[d - C[i].en].close);
         return true;
        }
      case T_CRY:
        {
         double h1 = HiMax(r, d - C[i].en, d - 1);
         if(!(c1 > h1))
            return false;
         why = StringFormat("cassure crypto %.0f > %.0f", c1, h1);
         return true;
        }
      case T_D7:
        {
         double t = SmaClose(r, d, 200);
         if(!(c1 > t && c1 <= ClMin(r, d - 6, d)))
            return false;
         why = "double-7 (plus bas 7j en tendance)";
         return true;
        }
      case T_IBS:
        {
         double t = SmaClose(r, d, 200);
         double rg = MathMax(r[d].high - r[d].low, 1e-12);
         double ibs = (c1 - r[d].low) / rg;
         if(!(c1 >= t && ibs < 0.2))
            return false;
         why = StringFormat("IBS %.2f < 0.2", ibs);
         return true;
        }
      case T_RSI2:
        {
         double t = SmaClose(r, d, 200);
         double rs = Rsi(r, n, 2);
         if(!(c1 > t && rs < C[i].th))
            return false;
         why = StringFormat("RSI2 %.1f < %.0f", rs, C[i].th);
         return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
double LotsFor(const string sym, const ENUM_ORDER_TYPE ot, const double price, const double sl, const double riskMoney)
  {
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double per = 0.0;
   if(!OrderCalcProfit(ot, sym, 1.0, price, sl, per) || per >= 0.0 || step <= 0.0)
      return 0.0;
   double lots = MathFloor(riskMoney / (-per) / step + 1e-9) * step;
   lots = MathMin(lots, maxL);
   if(lots + 1e-9 < minL)
      return 0.0;
   double margin = 0.0;
   if(OrderCalcMargin(ot, sym, lots, price, margin) &&
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.5)
     {
      lots = MathFloor(lots * AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.5 / margin / step) * step;
      if(lots + 1e-9 < minL)
         return 0.0;
     }
   int dg = (int)MathMax(0.0, MathRound(-MathLog10(step)));
   return NormalizeDouble(lots, dg);
  }

bool MarketLive(const string sym)
  {
   MqlTick tk;
   if(!SymbolInfoTick(sym, tk))
      return false;
   return (TimeCurrent() - tk.time) < 300 && tk.ask > 0.0 && tk.bid > 0.0;
  }

//+------------------------------------------------------------------+
//| Traitement journalier d'une brique                               |
//+------------------------------------------------------------------+
void Process(const int i, const bool canOpen)
  {
   if(!C[i].on)
      return;
   datetime now = TimeCurrent();
   if(now < C[i].nextCheck)
      return;                                              // rien a faire avant cette heure
   datetime bar = iTime(C[i].sym, PERIOD_D1, 0);
   if(bar == 0)
     {
      C[i].nextCheck = now + 3600;
      return;
     }
   datetime act = bar + InpEntryHour * 3600;               // heure d'action du jour
   if(bar == C[i].doneBar)
     {
      // deja traite : on revient a l'heure d'action de la prochaine bougie D1
      datetime nxt = bar + 86400 + InpEntryHour * 3600;
      C[i].nextCheck = (nxt > now) ? nxt : now + 3600;    // week-end / jour ferie : toutes les heures
      return;
     }
   if(now < act)
     {
      C[i].nextCheck = act;
      return;
     }
   if(!MarketLive(C[i].sym))
     {
      C[i].nLive++;
      C[i].nextCheck = now + 600;
      return;
     }

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(C[i].sym, PERIOD_D1, 1, NBARS, r);   // r[n-1] = bougie d'hier
   if(n < MINBARS)
     {
      C[i].nHist++;
      if(!C[i].warnHist)
        {
         PrintFormat("%s : historique D1 insuffisant (%d < %d barres) - nouvel essai chaque jour.",
                     C[i].name, n, MINBARS);
         C[i].warnHist = true;
        }
      C[i].doneBar = bar;                                  // re-essai a la prochaine bougie D1
      return;
     }

   trade.SetExpertMagicNumber((ulong)C[i].magic);
   trade.SetTypeFillingBySymbol(C[i].sym);

   ulong ticket;
   if(SelectComp(i, ticket))
     {
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      int held = iBarShift(C[i].sym, PERIOD_D1, opened, false);
      int pside = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      if(ExitSignal(i, r, n, pside))
        {
         if(trade.PositionClose(ticket))
            PrintFormat("%s : sortie signal journalier.", C[i].name);
        }
      else if(held >= C[i].maxd)
        {
         if(trade.PositionClose(ticket))
            PrintFormat("%s : sortie temps (%d jours).", C[i].name, held);
        }
      C[i].doneBar = bar;          // pas de re-entree le jour d'une sortie (comme le labo)
      return;
     }

   C[i].doneBar = bar;
   if(!canOpen)
      return;

   double slDist = 0.0;
   string why = "";
   int side = 1;
   if(!EntrySignal(i, r, n, slDist, why, side))
      return;
   C[i].nSig++;

   double price = (side > 0) ? SymbolInfoDouble(C[i].sym, SYMBOL_ASK) : SymbolInfoDouble(C[i].sym, SYMBOL_BID);
   int    dg  = (int)SymbolInfoInteger(C[i].sym, SYMBOL_DIGITS);
   double pt  = SymbolInfoDouble(C[i].sym, SYMBOL_POINT);
   double stopLv = SymbolInfoInteger(C[i].sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   if(slDist <= stopLv || price <= 0.0)
      return;
   double sl = NormalizeDouble(price - side * slDist, dg);
   double tp = C[i].tpR > 0.0 ? NormalizeDouble(price + side * slDist * C[i].tpR, dg) : 0.0;
   ENUM_ORDER_TYPE ot = (side > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   // risque : % du capital initial x K, reduit en drawdown
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double sc = 1.0;
   if(InpDDScalePct > 0.0 && eq < InpCapital)
      sc = MathMax(0.3, 1.0 - (InpCapital - eq) / InpCapital / (InpDDScalePct / 100.0));
   double riskMoney = InpCapital * C[i].w * K() / 100.0 * sc;

   double open = OpenRisk();
   double dayFloor = s_dayBal - InpCapital * InpDailyGuardPct / 100.0;
   double maxFloor = InpCapital * (1.0 - InpMaxLossPct / 100.0) + InpCapital * 0.003;
   if(open + riskMoney > InpCapital * InpMaxOpenPct / 100.0 ||
      eq - open - riskMoney <= maxFloor || eq - open - riskMoney <= dayFloor)
     {
      C[i].nRisk++;
      PrintFormat("%s : signal ignore (plafond de risque). ouvert %.0f + %.0f", C[i].name, open, riskMoney);
      return;
     }

   double lots = LotsFor(C[i].sym, ot, price, sl, riskMoney);
   if(lots <= 0.0)
     {
      C[i].nLot++;
      PrintFormat("%s : lot trop petit/marge insuffisante pour risque %.0f$.", C[i].name, riskMoney);
      return;
     }
   bool ok = (side > 0) ? trade.Buy(lots, C[i].sym, 0.0, sl, tp, C[i].name)
                        : trade.Sell(lots, C[i].sym, 0.0, sl, tp, C[i].name);
   if(ok)
     {
      CountTradingDay();
      C[i].nTrade++;
      PrintFormat("%s %s %s %.2f lots | SL %s | TP %s | risque %.0f$ | %s", side > 0 ? "ACHAT" : "VENTE",
                  C[i].name, C[i].sym, lots, DoubleToString(sl, dg), DoubleToString(tp, dg), riskMoney, why);
     }
   else
     {
      C[i].nRefus++;
      PrintFormat("%s : ordre refuse %s", C[i].name, trade.ResultRetcodeDescription());
     }
  }

//+------------------------------------------------------------------+
//| Stop ramene a l'entree (+0.1R) des que le gain atteint be x R     |
//+------------------------------------------------------------------+
void ManageBE()
  {
   for(int i = 0; i < ArraySize(C); i++)
     {
      if(!C[i].on || C[i].be <= 0.0)
         continue;
      ulong t;
      if(!SelectComp(i, t))
         continue;
      double op = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      if(sl <= 0.0)
         continue;
      bool isBuy = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY;
      int  dg = (int)SymbolInfoInteger(C[i].sym, SYMBOL_DIGITS);
      double gap = SymbolInfoInteger(C[i].sym, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(C[i].sym, SYMBOL_POINT);
      if(isBuy)
        {
         if(sl >= op) continue;                         // deja protege
         double R = op - sl;
         double bid = SymbolInfoDouble(C[i].sym, SYMBOL_BID);
         if(bid - op < C[i].be * R) continue;
         double nsl = NormalizeDouble(op + 0.1 * R, dg);
         if(nsl < bid - gap)
           {
            trade.SetExpertMagicNumber((ulong)C[i].magic);
            if(trade.PositionModify(t, nsl, tp))
               PrintFormat("%s : stop a l'entree (+0.1R) a %s", C[i].name, DoubleToString(nsl, dg));
           }
        }
      else
        {
         if(sl <= op) continue;
         double R = sl - op;
         double ask = SymbolInfoDouble(C[i].sym, SYMBOL_ASK);
         if(op - ask < C[i].be * R) continue;
         double nsl = NormalizeDouble(op - 0.1 * R, dg);
         if(nsl > ask + gap)
           {
            trade.SetExpertMagicNumber((ulong)C[i].magic);
            if(trade.PositionModify(t, nsl, tp))
               PrintFormat("%s : stop a l'entree (-0.1R) a %s", C[i].name, DoubleToString(nsl, dg));
           }
        }
     }
  }

//+------------------------------------------------------------------+
void Panel()
  {
   if(g_tester)
      return;                                  // pas de panneau en test non visuel (vitesse)
   static uint lastMs = 0;
   uint ms = GetTickCount();
   if(ms - lastMs < 2000)
      return;
   lastMs = ms;
   string s = StringFormat("FTMOPortfolio v2.0 | %s | K %.2f\n", EnumToString(InpMode), K());
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   s += StringFormat("Equity %.0f (%.2f %%) | jour ref %.0f | jours trading %.0f\n",
                     eq, (eq / InpCapital - 1.0) * 100.0, s_dayBal, s_tdays);
   string stat = "ACTIF";
   if(s_hday) stat = "JOURNEE COUPEE";
   if(s_hall) stat = "ARRET TOTAL";
   if(s_done) stat = "OBJECTIF ATTEINT";
   s += StringFormat("Risque ouvert %.0f $ | Statut: %s\n", OpenRisk(), stat);
   for(int i = 0; i < ArraySize(C); i++)
     {
      ulong t;
      string st = "off";
      if(C[i].on)
        {
         st = "attente";
         if(SelectComp(i, t))
            st = StringFormat("%s %.0f$", PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? "ACHAT" : "VENTE",
                              PositionGetDouble(POSITION_PROFIT));
        }
      s += StringFormat("  %-11s %-11s %s\n", C[i].name, C[i].sym, st);
     }
   Comment(s);
  }

void Run()
  {
   bool ok = Guard();
   if(s_done || s_hall)
     {
      Panel();
      return;
     }
   ManageBE();
   for(int i = 0; i < ArraySize(C); i++)
      Process(i, ok);
   Panel();
  }

void OnTick()  { Run(); }
void OnTimer() { Run(); }
//+------------------------------------------------------------------+
