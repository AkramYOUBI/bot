//+------------------------------------------------------------------+
//| FTMOPortfolio.mq5  v1.0                                          |
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
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

enum EMode
  {
   MODE_PHASE1 = 0,   // Challenge Phase 1 (objectif +10 %)
   MODE_PHASE2 = 1,   // Challenge Phase 2 (objectif +5 %)
   MODE_FUNDED = 2    // Compte finance (pas d'objectif, risque reduit)
  };

input group "=== Mode ==="
input EMode  InpMode          = MODE_PHASE1; // Mode
input double InpCapital       = 100000.0;    // Capital initial du compte
input double InpKChallenge    = 2.5;         // Multiplicateur de risque Phase 1/2
input double InpKFunded       = 0.75;        // Multiplicateur de risque finance
input double InpTarget1Pct    = 10.0;        // Objectif Phase 1 %
input double InpTarget2Pct    = 5.0;         // Objectif Phase 2 %
input int    InpMinDays       = 4;           // Jours de trading minimum FTMO
input bool   InpStopAtTarget  = true;        // Tout fermer et arreter a l'objectif

input group "=== Protection FTMO ==="
input double InpDailyGuardPct = 3.5;         // Garde-fou jour % (FTMO = 5)
input double InpMaxLossPct    = 10.0;        // Perte max totale FTMO %
input double InpMaxOpenPct    = 8.0;         // Risque ouvert max cumule %
input double InpDDScalePct    = 10.0;        // Risque reduit lineairement en DD (0=off)
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
   long     magic;
   bool     on;
   datetime doneBar;  // derniere bougie D1 traitee
  };

Comp   C[];
CTrade trade;
string gvPrefix;
string g_log = "";

#define NBARS 320

//+------------------------------------------------------------------+
void AddComp(const string name, const string sym, const int type, const double w,
             const double slAtr, const double tpR, const double th, const int maxd, const bool use)
  {
   int n = ArraySize(C);
   ArrayResize(C, n + 1);
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
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpCapital <= 0.0)
      return INIT_PARAMETERS_INCORRECT;
   ArrayResize(C, 0);
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

   for(int i = 0; i < ArraySize(C); i++)
     {
      if(!C[i].on)
         continue;
      if(!SymbolSelect(C[i].sym, true))
        {
         PrintFormat("Symbole %s introuvable -> brique %s desactivee (verifie le nom chez ton broker).",
                     C[i].sym, C[i].name);
         C[i].on = false;
        }
     }

   gvPrefix = "FP1_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "_" +
              IntegerToString(InpMagicBase) + "_";
   if(InpResetHalt)
     {
      GlobalVariableSet(gvPrefix + "HALL", 0.0);
      GlobalVariableSet(gvPrefix + "HDAY", 0.0);
      GlobalVariableSet(gvPrefix + "DONE", 0.0);
      Print("Arrets effaces. Remets InpResetHalt=false.");
     }
   trade.SetDeviationInPoints(InpDeviation);
   EventSetTimer(30);
   PrintFormat("FTMOPortfolio v1.0 | mode %s | K %.2f | capital %.0f | %d briques",
               EnumToString(InpMode), K(), InpCapital, ArraySize(C));
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
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
   if((int)GV("DAY") != day)
     {
      GVSet("DAY", day);
      GVSet("DAYBAL", AccountInfoDouble(ACCOUNT_BALANCE));   // regle FTMO : solde debut de jour
      GVSet("HDAY", 0.0);
     }
   if(GV("HALL") > 0.5 || GV("DONE") > 0.5)
      return false;

   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double dayFloor = GV("DAYBAL") - InpCapital * InpDailyGuardPct / 100.0;
   double maxFloor = InpCapital * (1.0 - InpMaxLossPct / 100.0) + InpCapital * 0.002;

   if(eq <= maxFloor)
     {
      CloseAll("ARRET TOTAL : proche du plafond -10 %.");
      GVSet("HALL", 1.0);
      return false;
     }
   if(eq <= dayFloor)
     {
      if(GV("HDAY") < 0.5)
         CloseAll(StringFormat("JOURNEE COUPEE : garde-fou -%.1f %% atteint.", InpDailyGuardPct));
      GVSet("HDAY", 1.0);
      return false;
     }
   if(GV("HDAY") > 0.5)
      return false;

   double tgt = TargetPct();
   if(InpStopAtTarget && tgt > 0.0 && eq >= InpCapital * (1.0 + tgt / 100.0) && GV("TDAYS") >= InpMinDays)
     {
      CloseAll(StringFormat("OBJECTIF +%.0f %% ATTEINT (%.0f jours de trading). Robot arrete.", tgt, GV("TDAYS")));
      GVSet("DONE", 1.0);
      return false;
     }
   return true;
  }

void CountTradingDay()
  {
   int day = FtmoDay();
   if((int)GV("LASTTD") != day)
     {
      GVSet("LASTTD", day);
      GVSet("TDAYS", GV("TDAYS") + 1.0);
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
bool ExitSignal(const int i, const MqlRates &r[], const int n)
  {
   int d = n - 1;
   double c1 = r[d].close;
   switch(C[i].type)
     {
      case T_BRK:
      case T_CRY:
         return c1 < LoMin(r, d - 10, d - 1);          // cloture sous le plus bas 10j
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
bool EntrySignal(const int i, const MqlRates &r[], const int n, double &slDist, string &why)
  {
   int d = n - 1;
   double atr[];
   AtrArr(r, n, 20, atr);
   double A = atr[d];
   if(A <= 0.0)
      return false;
   double c1 = r[d].close, c2 = r[d - 1].close;
   slDist = A * C[i].slAtr;

   switch(C[i].type)
     {
      case T_BRK:
        {
         double avg = 0.0;
         for(int j = d - 49; j <= d; j++) avg += atr[j];
         avg /= 50.0;
         if(avg > 0.0 && A > 2.2 * avg)
            return false;                                       // volatilite extreme
         double h1 = HiMax(r, d - 20, d - 1), h2 = HiMax(r, d - 21, d - 2);
         if(!(c1 > h1 && c2 <= h2))
            return false;
         double ema[];
         EmaArr(r, n, 50, ema);
         if(!(c1 > ema[d] && ema[d] > ema[d - 3]))
            return false;
         why = StringFormat("cassure 20j %.2f > %.2f", c1, h1);
         return true;
        }
      case T_CRY:
        {
         double h1 = HiMax(r, d - 20, d - 1);
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
double LotsFor(const string sym, const double price, const double sl, const double riskMoney)
  {
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double per = 0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, sym, 1.0, price, sl, per) || per >= 0.0 || step <= 0.0)
      return 0.0;
   double lots = MathFloor(riskMoney / (-per) / step + 1e-9) * step;
   lots = MathMin(lots, maxL);
   if(lots + 1e-9 < minL)
      return 0.0;
   double margin = 0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, price, margin) &&
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
   datetime bar = iTime(C[i].sym, PERIOD_D1, 0);
   if(bar == 0 || bar == C[i].doneBar)
      return;
   MqlDateTime now;
   TimeToStruct(TimeCurrent(), now);
   if(now.hour < InpEntryHour || !MarketLive(C[i].sym))
      return;

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(C[i].sym, PERIOD_D1, 1, NBARS, r);   // r[n-1] = bougie d'hier
   if(n < 260)
      return;                                              // historique pas encore pret

   trade.SetExpertMagicNumber((ulong)C[i].magic);
   trade.SetTypeFillingBySymbol(C[i].sym);

   ulong ticket;
   if(SelectComp(i, ticket))
     {
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      int held = iBarShift(C[i].sym, PERIOD_D1, opened, false);
      if(ExitSignal(i, r, n))
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
   if(!EntrySignal(i, r, n, slDist, why))
      return;

   double ask = SymbolInfoDouble(C[i].sym, SYMBOL_ASK);
   int    dg  = (int)SymbolInfoInteger(C[i].sym, SYMBOL_DIGITS);
   double pt  = SymbolInfoDouble(C[i].sym, SYMBOL_POINT);
   double stopLv = SymbolInfoInteger(C[i].sym, SYMBOL_TRADE_STOPS_LEVEL) * pt;
   if(slDist <= stopLv)
      return;
   double sl = NormalizeDouble(ask - slDist, dg);
   double tp = C[i].tpR > 0.0 ? NormalizeDouble(ask + slDist * C[i].tpR, dg) : 0.0;

   // risque : % du capital initial x K, reduit en drawdown
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double sc = 1.0;
   if(InpDDScalePct > 0.0 && eq < InpCapital)
      sc = MathMax(0.3, 1.0 - (InpCapital - eq) / InpCapital / (InpDDScalePct / 100.0));
   double riskMoney = InpCapital * C[i].w * K() / 100.0 * sc;

   double open = OpenRisk();
   double dayFloor = GV("DAYBAL") - InpCapital * InpDailyGuardPct / 100.0;
   double maxFloor = InpCapital * (1.0 - InpMaxLossPct / 100.0) + InpCapital * 0.003;
   if(open + riskMoney > InpCapital * InpMaxOpenPct / 100.0 ||
      eq - open - riskMoney <= maxFloor || eq - open - riskMoney <= dayFloor)
     {
      PrintFormat("%s : signal ignore (plafond de risque). ouvert %.0f + %.0f", C[i].name, open, riskMoney);
      return;
     }

   double lots = LotsFor(C[i].sym, ask, sl, riskMoney);
   if(lots <= 0.0)
     {
      PrintFormat("%s : lot trop petit/marge insuffisante pour risque %.0f$.", C[i].name, riskMoney);
      return;
     }
   if(trade.Buy(lots, C[i].sym, 0.0, sl, tp, C[i].name))
     {
      CountTradingDay();
      PrintFormat("ACHAT %s %s %.2f lots | SL %s | TP %s | risque %.0f$ | %s",
                  C[i].name, C[i].sym, lots, DoubleToString(sl, dg), DoubleToString(tp, dg), riskMoney, why);
     }
   else
      PrintFormat("%s : achat refuse %s", C[i].name, trade.ResultRetcodeDescription());
  }

//+------------------------------------------------------------------+
void Panel()
  {
   string s = StringFormat("FTMOPortfolio v1.0 | %s | K %.2f\n", EnumToString(InpMode), K());
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   s += StringFormat("Equity %.0f (%.2f %%) | jour ref %.0f | jours trading %.0f\n",
                     eq, (eq / InpCapital - 1.0) * 100.0, GV("DAYBAL"), GV("TDAYS"));
   string stat = "ACTIF";
   if(GV("HDAY") > 0.5) stat = "JOURNEE COUPEE";
   if(GV("HALL") > 0.5) stat = "ARRET TOTAL";
   if(GV("DONE") > 0.5) stat = "OBJECTIF ATTEINT";
   s += StringFormat("Risque ouvert %.0f $ | Statut: %s\n", OpenRisk(), stat);
   for(int i = 0; i < ArraySize(C); i++)
     {
      ulong t;
      string st = "off";
      if(C[i].on)
        {
         st = "attente";
         if(SelectComp(i, t))
            st = StringFormat("EN POSITION %.0f$", PositionGetDouble(POSITION_PROFIT));
        }
      s += StringFormat("  %-11s %-11s %s\n", C[i].name, C[i].sym, st);
     }
   Comment(s);
  }

void Run()
  {
   bool ok = Guard();
   if(GV("DONE") > 0.5 || GV("HALL") > 0.5)
     {
      Panel();
      return;
     }
   for(int i = 0; i < ArraySize(C); i++)
      Process(i, ok);
   Panel();
  }

void OnTick()  { Run(); }
void OnTimer() { Run(); }
//+------------------------------------------------------------------+
