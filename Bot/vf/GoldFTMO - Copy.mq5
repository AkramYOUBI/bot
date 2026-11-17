//+------------------------------------------------------------------+
//| GoldFTMO.mq5  v6 — comportement trader pro                       |
//| Entree : meme cassure 20j achat (fond qui a paye).               |
//| Gestion humaine :                                                |
//|  - TP sur le prochain niveau D1 (sinon 2R mini)                  |
//|  - a +1R : prend 50 %, stop a l'entree                           |
//|  - a +2R ou +X $ flottant : stop serre, laisse courir le reste   |
//|  - stop monte chaque jour sous le plus bas recent                |
//|  - graphe : seulement les 3-4 niveaux qui comptent               |
//| Plafonds : -5 % jour, -10 % total. Pas d'arret sur le gain.      |
//+------------------------------------------------------------------+
#property copyright "Gold FTMO"
#property version   "6.00"
#property strict

#include <Trade/Trade.mqh>

#define ENTRY_N  20
#define EXIT_N   10
#define ATR_N    20
#define SL_ATR   2.0
#define WING     2

input group "=== Compte ==="
input double InpCapital    = 100000.0; // Capital
input double InpRiskPct    = 1.0;       // Risque par trade %
input int    InpDayOffset  = 0;         // Decalage minuit FTMO

input group "=== Gestion humaine ==="
input double InpPartialR   = 1.0;       // Prise partielle a x R
input double InpPartialPct = 50.0;      // % ferme a la partielle
input double InpLockR      = 2.0;       // Des x R : stop serre
input double InpLockUSD    = 800.0;     // Ou des +X $ flottants (0=off)
input double InpMinRR      = 2.0;       // TP mini = x R si niveau trop loin/proche
input int    InpMaxDays    = 15;        // Sortie temps (0=off)
input int    InpFridayHour = 20;

input group "=== Filtre ==="
input double InpMaxAtrMult = 2.2;
input int    InpAtrAvgBars = 50;

input group "=== Affichage ==="
input bool   InpDraw       = true;      // Niveaux utiles seulement

input group "=== Technique ==="
input long   InpMagic      = 26111706;
input int    InpDeviation  = 30;
input bool   InpResetHalt  = false;

#define CLR_BREAK  clrYellow
#define CLR_EXIT   clrSilver
#define CLR_TARGET clrOrange
#define CLR_ENTRY   clrLimeGreen
#define CLR_RISK   C'40,20,20'

CTrade trade;
int hATR = INVALID_HANDLE;
int hATRavg = INVALID_HANDLE;

string gvDay, gvDayBal, gvHaltDay, gvHaltAll;
string gvDist, gvPeak, gvEntry, gvPartial, gvR;

string g_status = "ATTENTE";
string g_why    = "-";
double g_break = 0.0, g_exitLv = 0.0, g_target = 0.0, g_atr = 0.0;
int    g_mark = 0;

//+------------------------------------------------------------------+
int OnInit()
  {
   if(InpCapital <= 0.0 || InpRiskPct <= 0.0 || InpRiskPct >= 5.0)
      return INIT_PARAMETERS_INCORRECT;
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
     {
      Print("Or seulement. Symbole : ", _Symbol);
      return INIT_FAILED;
     }

   hATR = iATR(_Symbol, PERIOD_D1, ATR_N);
   if(hATR == INVALID_HANDLE)
      return INIT_FAILED;
   if(InpMaxAtrMult > 0.0 && InpAtrAvgBars > 1)
     {
      hATRavg = iMA(_Symbol, PERIOD_D1, InpAtrAvgBars, 0, MODE_SMA, hATR);
      if(hATRavg == INVALID_HANDLE)
         return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviation);
   trade.SetTypeFillingBySymbol(_Symbol);

   string id = "GF6_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))
               + "_" + IntegerToString(InpMagic) + "_";
   gvDay     = id + "DAY";
   gvDayBal  = id + "BAL";
   gvHaltDay = id + "HDAY";
   gvHaltAll = id + "HALL";
   gvDist    = id + "DIST";
   gvPeak    = id + "PEAK";
   gvEntry   = id + "ENTRY";
   gvPartial = id + "PART";
   gvR       = id + "R";

   if(InpResetHalt)
     {
      GlobalVariableSet(gvHaltAll, 0.0);
      GlobalVariableSet(gvHaltDay, 0.0);
      Print("Arret efface. Remets InpResetHalt a false.");
     }

   PrintFormat("GoldFTMO v6 | gestion humaine | capital %.0f | risque %.0f | partielle %.0f%% a +%.1fR",
               InpCapital, InpCapital * InpRiskPct / 100.0, InpPartialPct, InpPartialR);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hATRavg != INVALID_HANDLE) IndicatorRelease(hATRavg);
   ObjectsDeleteAll(0, "GF6_");
   Comment("");
  }

double GV(const string name)
  {
   return GlobalVariableCheck(name) ? GlobalVariableGet(name) : 0.0;
  }

double Buf(const int handle, const int shift)
  {
   double b[];
   if(CopyBuffer(handle, 0, shift, 1, b) != 1)
      return 0.0;
   return b[0];
  }

bool Mine()
  {
   return PositionGetInteger(POSITION_MAGIC) == InpMagic &&
          PositionGetString(POSITION_SYMBOL) == _Symbol;
  }

bool SelectMine(ulong &ticket)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t != 0 && Mine())
        {
         ticket = t;
         return true;
        }
     }
   ticket = 0;
   return false;
  }

void CloseMine(const string why)
  {
   ulong ticket;
   if(SelectMine(ticket) && trade.PositionClose(ticket))
      Print(why);
  }

int FtmoDay()
  {
   datetime t = TimeCurrent() - (datetime)(InpDayOffset * 3600);
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return dt.year * 10000 + dt.mon * 100 + dt.day;
  }

void RollDay()
  {
   double day = (double)FtmoDay();
   if(GV(gvDay) == day)
      return;
   GlobalVariableSet(gvDay, day);
   GlobalVariableSet(gvDayBal, AccountInfoDouble(ACCOUNT_BALANCE));
   GlobalVariableSet(gvHaltDay, 0.0);
  }

double DayFloor() { return GV(gvDayBal) - InpCapital * 0.05; }
double MaxFloor() { return InpCapital * 0.90; }

bool Alive()
  {
   RollDay();
   if(GV(gvHaltAll) > 0.5)
      return false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= MaxFloor())
     {
      CloseMine("ARRET TOTAL : -10 %.");
      GlobalVariableSet(gvHaltAll, 1.0);
      return false;
     }
   if(eq <= DayFloor())
     {
      CloseMine("JOURNEE COUPEE : -5 %.");
      GlobalVariableSet(gvHaltDay, 1.0);
      return false;
     }
   if(GV(gvHaltDay) > 0.5)
      return false;
   return true;
  }

double Extreme(const bool highs, const int shift, const int count)
  {
   double a[];
   int got = highs ? CopyHigh(_Symbol, PERIOD_D1, shift, count, a)
                   : CopyLow(_Symbol, PERIOD_D1, shift, count, a);
   if(got != count)
      return 0.0;
   return highs ? a[ArrayMaximum(a)] : a[ArrayMinimum(a)];
  }

// Prochain pivot D1 AU-DESSUS du prix = cible naturelle
double NextResistance(const double above)
  {
   double best = 0.0;
   int last = MathMin(80, Bars(_Symbol, PERIOD_D1) - WING - 3);
   for(int s = WING + 1; s <= last; s++)
     {
      double p = iHigh(_Symbol, PERIOD_D1, s);
      if(p <= above)
         continue;
      bool ok = true;
      for(int k = 1; k <= WING && ok; k++)
        {
         if(p <= iHigh(_Symbol, PERIOD_D1, s - k) || p <= iHigh(_Symbol, PERIOD_D1, s + k))
            ok = false;
        }
      if(!ok)
         continue;
      if(best == 0.0 || p < best)
         best = p;
     }
   return best;
  }

double LossAt(const double lots, const double price, const double sl)
  {
   double profit = 0.0;
   if(OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, lots, price, sl, profit))
      return -profit;
   double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tv <= 0.0 || ts <= 0.0)
      return -1.0;
   return MathAbs(price - sl) / ts * tv * lots;
  }

double NormLot(double lots)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0)
      return 0.0;
   lots = MathFloor(lots / step + 1e-8) * step;
   if(lots + 1e-8 < minL || lots > maxL)
      return 0.0;
   int d = (int)MathRound(-MathLog10(step));
   if(d < 0)
      d = 0;
   return NormalizeDouble(lots, d);
  }

double LotsFor(const double price, const double sl, const double riskMoney)
  {
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double per  = LossAt(1.0, price, sl);
   if(per <= 0.0 || step <= 0.0 || riskMoney <= 0.0)
      return 0.0;
   double lots = NormLot(MathMin(riskMoney / per, maxL));
   int guard = 0;
   while(lots >= minL && LossAt(lots, price, sl) > riskMoney * 1.02 && guard++ < 2000)
      lots = NormLot(lots - step);
   if(lots < minL)
      return 0.0;
   double margin = 0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, lots, price, margin) &&
      margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.80)
      return 0.0;
   return lots;
  }

void SetHLine(const string name, const double price, const color clr,
              const int style, const int width, const string tip)
  {
   if(price <= 0.0)
     {
      if(ObjectFind(0, name) >= 0)
         ObjectDelete(0, name);
      return;
     }
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_HLINE, 0, 0, price);
   ObjectSetDouble(0, name, OBJPROP_PRICE, price);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_STYLE, style);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, width);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetString(0, name, OBJPROP_TOOLTIP, tip);
  }

void SetZone(const string name, const datetime t1, const double p1,
             const datetime t2, const double p2, const color clr)
  {
   if(ObjectFind(0, name) < 0)
      ObjectCreate(0, name, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, name, OBJPROP_TIME, 0, t1);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 0, p1);
   ObjectSetInteger(0, name, OBJPROP_TIME, 1, t2);
   ObjectSetDouble(0, name, OBJPROP_PRICE, 1, p2);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, name, OBJPROP_FILL, true);
   ObjectSetInteger(0, name, OBJPROP_BACK, true);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void SetLabel(const string name, const int x, const int y, const string text, const color clr)
  {
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
      ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
     }
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
  }

void MarkEntry(const double price, const double sl, const double tp, const double breakLv, const string reason)
  {
   g_mark++;
   string tag = IntegerToString(g_mark);
   datetime t = TimeCurrent();

   string arr = "GF6_ARR_" + tag;
   if(ObjectFind(0, arr) < 0)
      ObjectCreate(0, arr, OBJ_ARROW_BUY, 0, t, price);
   ObjectSetInteger(0, arr, OBJPROP_COLOR, CLR_ENTRY);
   ObjectSetInteger(0, arr, OBJPROP_WIDTH, 2);

   string txt = "GF6_TXT_" + tag;
   if(ObjectFind(0, txt) < 0)
      ObjectCreate(0, txt, OBJ_TEXT, 0, t, price);
   ObjectSetString(0, txt, OBJPROP_TEXT,
                   StringFormat("ACHAT | %s | TP %.0f", reason, tp));
   ObjectSetInteger(0, txt, OBJPROP_COLOR, CLR_ENTRY);
   ObjectSetInteger(0, txt, OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, txt, OBJPROP_ANCHOR, ANCHOR_LEFT_LOWER);

   SetZone("GF6_RISK_" + tag, t - 86400, price, t + 3 * 86400, sl, CLR_RISK);
   SetHLine("GF6_BROKE_" + tag, breakLv, CLR_BREAK, STYLE_DASH, 2, "Niveau casse");
  }

void DrawAnalysis()
  {
   if(!InpDraw)
      return;

   g_break  = Extreme(true, 2, ENTRY_N);
   g_exitLv = Extreme(false, 2, EXIT_N);
   g_atr    = Buf(hATR, 1);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   g_target = NextResistance(MathMax(ask, g_break));

   // Seulement ce qui compte pour ce trade
   SetHLine("GF6_BREAK", g_break, CLR_BREAK, STYLE_SOLID, 3, "Entree si cloture D1 > ce niveau (20j)");
   SetHLine("GF6_EXIT", g_exitLv, CLR_EXIT, STYLE_DASH, 2, "Sortie structure (plus bas 10j)");
   SetHLine("GF6_TARGET", g_target, CLR_TARGET, STYLE_SOLID, 2, "Prochain niveau D1 = TP");

   ulong ticket;
   if(SelectMine(ticket))
     {
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      double sl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      SetHLine("GF6_SL", sl, clrRed, STYLE_DOT, 2, "Stop actuel");
      SetHLine("GF6_TP", tp, clrLime, STYLE_DOT, 2, "Objectif");
      SetHLine("GF6_EN", entry, clrDodgerBlue, STYLE_DOT, 1, "Entree");
     }
   else
     {
      if(ObjectFind(0, "GF6_SL") >= 0) ObjectDelete(0, "GF6_SL");
      if(ObjectFind(0, "GF6_TP") >= 0) ObjectDelete(0, "GF6_TP");
      if(ObjectFind(0, "GF6_EN") >= 0) ObjectDelete(0, "GF6_EN");
     }

   if(ObjectFind(0, "GF6_BG") < 0)
     {
      ObjectCreate(0, "GF6_BG", OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_XDISTANCE, 8);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_YDISTANCE, 18);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_XSIZE, 480);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_YSIZE, 200);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_BGCOLOR, clrBlack);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_COLOR, clrDimGray);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_BACK, false);
      ObjectSetInteger(0, "GF6_BG", OBJPROP_SELECTABLE, false);
     }

   double c1 = iClose(_Symbol, PERIOD_D1, 1);
   double c2 = iClose(_Symbol, PERIOD_D1, 2);
   bool edge = (g_break > 0.0 && c1 > g_break && c2 <= Extreme(true, 3, ENTRY_N));

   if(GV(gvHaltAll) > 0.5) g_status = "ARRET TOTAL";
   else if(GV(gvHaltDay) > 0.5) g_status = "JOURNEE FINIE";
   else if(SelectMine(ticket)) g_status = "EN POSITION — gestion active";
   else if(edge) g_status = "SIGNAL ACHAT";
   else g_status = "ATTENTE sous le haut 20j";

   string panel = StringFormat(
      "GoldFTMO v6 | trader pro\n"
      "Statut : %s\n"
      "%s\n"
      "------------------------------------\n"
      "JAUNE  = cassure 20j (entree)\n"
      "ORANGE = prochain niveau (TP)\n"
      "GRIS   = plus bas 10j (sortie)\n"
      "Gestion : +%.1fR = -%.0f%% + BE | +%.1fR ou +%.0f$ = stop serre\n"
      "Equity %.0f | jour %.0f | total %.0f",
      g_status, g_why,
      InpPartialR, InpPartialPct, InpLockR, InpLockUSD,
      AccountInfoDouble(ACCOUNT_EQUITY), DayFloor(), MaxFloor());
   SetLabel("GF6_PANEL", 16, 24, panel, clrWhite);
   ChartRedraw(0);
  }

void ManageHuman()
  {
   ulong ticket;
   if(!SelectMine(ticket))
     {
      GlobalVariableSet(gvPartial, 0.0);
      return;
     }

   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl    = PositionGetDouble(POSITION_SL);
   double tp    = PositionGetDouble(POSITION_TP);
   double vol   = PositionGetDouble(POSITION_VOLUME);
   double bid   = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double r     = GV(gvR);
   if(r <= 0.0)
      r = MathAbs(entry - sl);
   if(r <= 0.0)
      return;

   double gain = bid - entry;
   double gainR = gain / r;
   double floatUsd = 0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, vol, entry, bid, floatUsd))
      floatUsd = vol * gain * 100.0;

   datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
   int daysOpen = (int)((TimeCurrent() - opened) / 86400);

   // 1) Structure morte : cloture sous le plus bas 10j
   double c1 = iClose(_Symbol, PERIOD_D1, 1);
   double exitLow = Extreme(false, 2, EXIT_N);
   if(exitLow > 0.0 && c1 > 0.0 && c1 < exitLow)
     {
      CloseMine("Sortie humaine : structure cassee (bas 10j).");
      return;
     }

   // 2) Temps max
   if(InpMaxDays > 0 && daysOpen >= InpMaxDays)
     {
      CloseMine(StringFormat("Sortie humaine : %d jours max.", InpMaxDays));
      return;
     }

   double gap = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   // 3) Partielle a +1R : encaisser, stop a l'entree
   if(InpPartialR > 0.0 && GV(gvPartial) < 0.5 && gainR >= InpPartialR)
     {
      double closeVol = NormLot(vol * InpPartialPct / 100.0);
      if(closeVol >= minL && vol - closeVol >= minL - 1e-8)
        {
         if(trade.PositionClosePartial(ticket, closeVol))
           {
            GlobalVariableSet(gvPartial, 1.0);
            PrintFormat("Partielle : -%.2f lot a +%.2fR (%.0f $).", closeVol, gainR, floatUsd);
            if(SelectMine(ticket))
              {
               double be = NormalizeDouble(entry, _Digits);
               if(be > sl && be < bid - gap)
                  trade.PositionModify(ticket, be, tp);
              }
            g_why = StringFormat("Partielle prise a +%.1fR — stop a l'entree", gainR);
            return;
           }
        }
      else
        {
         // Volume trop petit pour partielle : au moins BE
         double be = NormalizeDouble(entry, _Digits);
         if(be > sl && be < bid - gap)
           {
            trade.PositionModify(ticket, be, tp);
            GlobalVariableSet(gvPartial, 1.0);
           }
        }
     }

   // 4) Lock : +2R ou +X $ — stop sous le plus bas recent / 1 ATR
   bool lock = (InpLockR > 0.0 && gainR >= InpLockR) ||
               (InpLockUSD > 0.0 && floatUsd >= InpLockUSD);
   if(lock)
     {
      double atr = Buf(hATR, 1);
      double swing = Extreme(false, 1, 5);
      double nsl = bid - atr * 1.0;
      if(swing > 0.0)
         nsl = MathMax(nsl, swing - atr * 0.1);
      nsl = MathMax(nsl, entry); // ne jamais redescendre sous BE une fois lock
      nsl = NormalizeDouble(nsl, _Digits);
      if(nsl > sl && nsl < bid - gap)
        {
         if(trade.PositionModify(ticket, nsl, tp))
            g_why = StringFormat("Stop serre (lock) a %.0f | flottant %.0f $", nsl, floatUsd);
        }
     }
   else
     {
      // 5) Trail classique : pic - 2 ATR (comme avant), mais jamais sous BE apres partielle
      double peak = MathMax(GV(gvPeak), iHigh(_Symbol, PERIOD_D1, 1));
      GlobalVariableSet(gvPeak, peak);
      double dist = GV(gvDist);
      if(dist > 0.0)
        {
         double nsl = NormalizeDouble(peak - dist, _Digits);
         if(GV(gvPartial) > 0.5)
            nsl = MathMax(nsl, entry);
         if(nsl > sl && nsl < bid - gap)
            trade.PositionModify(ticket, nsl, tp);
        }
     }

   // Recaler TP si un niveau plus proche est apparu et qu'on n'a pas encore partiel
   if(GV(gvPartial) < 0.5 && g_target > entry && (tp <= 0.0 || g_target < tp))
     {
      double room = g_target - entry;
      if(room >= r * InpMinRR * 0.9)
        {
         double ntp = NormalizeDouble(g_target, _Digits);
         if(ntp > bid + gap)
            trade.PositionModify(ticket, sl, ntp);
        }
     }
  }

void TryEntry()
  {
   ulong ticket;
   if(SelectMine(ticket))
      return;

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(dt.day_of_week == 5 && dt.hour >= InpFridayHour)
      return;

   double atr = Buf(hATR, 1);
   if(atr <= 0.0)
      return;

   if(InpMaxAtrMult > 0.0 && hATRavg != INVALID_HANDLE)
     {
      double avg = Buf(hATRavg, 1);
      if(avg > 0.0 && atr > avg * InpMaxAtrMult)
        {
         g_why = StringFormat("Refuse: volatilite ATR %.1f trop haute", atr);
         return;
        }
     }

   double hh  = Extreme(true, 2, ENTRY_N);
   double hhP = Extreme(true, 3, ENTRY_N);
   double c1  = iClose(_Symbol, PERIOD_D1, 1);
   double c2  = iClose(_Symbol, PERIOD_D1, 2);
   if(hh <= 0.0 || hhP <= 0.0 || c1 <= 0.0 || c2 <= 0.0)
      return;
   if(!(c1 > hh && c2 <= hhP))
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(ask <= 0.0)
      return;
   double dist = atr * SL_ATR;
   if(dist < SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point)
      return;

   double sl = NormalizeDouble(ask - dist, _Digits);

   // TP humain : prochain niveau D1, au moins MinRR
   double res = NextResistance(ask);
   double minTp = ask + dist * InpMinRR;
   double tpPrice = minTp;
   if(res > ask + dist * 0.5)
     {
      if(res >= minTp)
         tpPrice = res;
      else
         tpPrice = minTp; // niveau trop proche : on vise au moins 2R
     }
   double tp = NormalizeDouble(tpPrice, _Digits);

   double riskMoney = InpCapital * InpRiskPct / 100.0;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq - riskMoney <= DayFloor() || eq - riskMoney <= MaxFloor())
     {
      Print("Cassure laissee : plafond.");
      return;
     }

   double lots = LotsFor(ask, sl, riskMoney);
   if(lots <= 0.0)
      return;
   if(!trade.Buy(lots, _Symbol, 0.0, sl, tp, "GF6"))
     {
      Print("Achat refuse : ", trade.ResultRetcodeDescription());
      return;
     }

   GlobalVariableSet(gvDist, dist);
   GlobalVariableSet(gvPeak, ask);
   GlobalVariableSet(gvEntry, ask);
   GlobalVariableSet(gvR, dist);
   GlobalVariableSet(gvPartial, 0.0);

   string reason = StringFormat("cloture %.0f > haut20j %.0f", c1, hh);
   MarkEntry(ask, sl, tp, hh, reason);
   g_why = StringFormat("Entree | %s | SL %.0f | TP %.0f (niveau/2R)", reason, sl, tp);
   PrintFormat("ACHAT %.2f | SL %.2f | TP %.2f | risque %.0f | %s",
               lots, sl, tp, LossAt(lots, ask, sl), reason);
  }

void OnTick()
  {
   if(Bars(_Symbol, PERIOD_D1) < ENTRY_N + InpAtrAvgBars + 5)
      return;

   bool live = Alive();
   if(GV(gvHaltAll) > 0.5)
     {
      DrawAnalysis();
      return;
     }

   // Gestion tick : partielle / BE / lock (comportement humain)
   ManageHuman();

   datetime bar = iTime(_Symbol, PERIOD_D1, 0);
   static datetime lastBar = 0;
   if(bar != 0 && bar != lastBar)
     {
      lastBar = bar;
      if(live && Alive())
         TryEntry();
      DrawAnalysis();
     }
   else
     {
      static datetime lastM5 = 0;
      datetime m5 = iTime(_Symbol, PERIOD_M5, 0);
      if(m5 != 0 && m5 != lastM5)
        {
         lastM5 = m5;
         DrawAnalysis();
        }
     }
  }
//+------------------------------------------------------------------+
