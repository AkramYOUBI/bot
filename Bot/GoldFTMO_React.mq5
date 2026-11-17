//+------------------------------------------------------------------+
//| GoldFTMO_React.mq5  v1.1  ATTENTION EXPERIMENTAL                 |
//| Buy+Sell H1 : la simu Python v1 etait TROP OPTIMISTE.            |
//| Sur MT5 reel 2020+ : brule ~-9k / halt FTMO (voir notes).        |
//| Pour FTMO fiable : utiliser GoldFTMO.mq5 en D1 ACHAT SEUL.       |
//+------------------------------------------------------------------+
#property copyright "Gold FTMO React"
#property version   "1.10"
#property strict

#include <Trade/Trade.mqh>

input group "=== Compte FTMO ==="
input double InpCapital   = 100000.0; // Capital initial (plafonds)
input double InpRiskPct   = 1.0;      // Risque par trade %
input double InpDailyPct  = 5.0;      // Plafond perte jour %
input double InpMaxPct    = 10.0;     // Plafond perte totale %
input int    InpDayOffset = 0;        // Decalage minuit FTMO (h)

input group "=== Signal (buy + sell) ==="
input ENUM_TIMEFRAMES InpTF = PERIOD_H1; // TF signal
input int    InpLookback  = 12;       // Cassure haut/bas N barres
input double InpTP_USD    = 30.0;     // Take profit en $ prix (~30 points)
input double InpSL_ATR    = 1.8;      // Stop = x ATR
input int    InpAtrPeriod = 14;       // Periode ATR
input bool   InpBuyOn     = true;     // Autoriser BUY
input bool   InpSellOn    = true;     // Autoriser SELL
input bool   InpUseEma    = false;    // Filtre EMA (plus safe, moins de trades)
input int    InpEmaPeriod = 50;       // Periode EMA

input group "=== Gestion ==="
input bool   InpBE_1R     = true;     // Stop a l'entree des +1R
input int    InpMaxBars   = 48;       // Sortie temps (barres TF)
input int    InpMaxDayTrades = 2;     // Max trades / jour
input int    InpPauseLoss = 2;        // Pause apres N pertes
input int    InpPauseHours = 24;      // Duree pause (heures)
input int    InpFridayHour = 20;      // Pas d'entree vendredi apres

input group "=== Affichage ==="
input bool   InpDraw = true;

input group "=== Technique ==="
input long   InpMagic = 26111730;
input int    InpDeviation = 30;
input bool   InpResetHalt = false;

CTrade trade;
int hATR = INVALID_HANDLE;
int hEMA = INVALID_HANDLE;

string gvDay, gvDayBal, gvHaltDay, gvHaltAll;
string gvR, gvBE, gvStreak, gvPauseUntil, gvDayTrades, gvDayTradesD;
string g_why = "-";

ENUM_TIMEFRAMES SigTF() { return InpTF; }

int OnInit()
  {
   if(InpCapital <= 0 || InpRiskPct <= 0 || InpLookback < 3 || InpTP_USD <= 0 || InpSL_ATR <= 0)
      return INIT_PARAMETERS_INCORRECT;
   if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
     {
      Print("Or seulement");
      return INIT_FAILED;
     }

   hATR = iATR(_Symbol, SigTF(), InpAtrPeriod);
   if(hATR == INVALID_HANDLE)
      return INIT_FAILED;
   if(InpUseEma)
     {
      hEMA = iMA(_Symbol, SigTF(), InpEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
      if(hEMA == INVALID_HANDLE)
         return INIT_FAILED;
     }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviation);
   trade.SetTypeFillingBySymbol(_Symbol);

   string id = "GFR_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))
               + "_" + IntegerToString(InpMagic) + "_";
   gvDay = id + "DAY";
   gvDayBal = id + "BAL";
   gvHaltDay = id + "HDAY";
   gvHaltAll = id + "HALL";
   gvR = id + "R";
   gvBE = id + "BE";
   gvStreak = id + "STR";
   gvPauseUntil = id + "PAUSE";
   gvDayTrades = id + "NDAY";
   gvDayTradesD = id + "DDAY";

   if(InpResetHalt)
     {
      GlobalVariableSet(gvHaltAll, 0);
      GlobalVariableSet(gvHaltDay, 0);
     }

   Print("ATTENTION: GoldFTMO_React H1 buy+sell a ECHOUE le test MT5 2020+ (compte ~-9%).");
   Print("Pour FTMO: prefere GoldFTMO.mq5 D1 achat seul (logique prouvee).");
   PrintFormat("GoldFTMO_React v1.1 | TF %s | lb %d | TP %.0f | SL %.1f ATR | risk %.1f%%",
               EnumToString(InpTF), InpLookback, InpTP_USD, InpSL_ATR, InpRiskPct);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(hATR != INVALID_HANDLE) IndicatorRelease(hATR);
   if(hEMA != INVALID_HANDLE) IndicatorRelease(hEMA);
   ObjectsDeleteAll(0, "GFR_");
  }

double GV(const string n) { return GlobalVariableCheck(n) ? GlobalVariableGet(n) : 0.0; }

double Buf(const int h, const int sh)
  {
   double b[];
   if(CopyBuffer(h, 0, sh, 1, b) != 1) return 0;
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
      if(t != 0 && Mine()) { ticket = t; return true; }
     }
   ticket = 0;
   return false;
  }

void CloseMine(const string why)
  {
   ulong t;
   if(SelectMine(t) && trade.PositionClose(t))
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
   if(GV(gvDay) == day) return;
   GlobalVariableSet(gvDay, day);
   GlobalVariableSet(gvDayBal, AccountInfoDouble(ACCOUNT_BALANCE));
   GlobalVariableSet(gvHaltDay, 0);
   GlobalVariableSet(gvDayTrades, 0);
   GlobalVariableSet(gvDayTradesD, day);
  }

double DayFloor() { return GV(gvDayBal) - InpCapital * InpDailyPct / 100.0; }
double MaxFloor() { return InpCapital * (1.0 - InpMaxPct / 100.0); }

bool Alive()
  {
   RollDay();
   if(GV(gvHaltAll) > 0.5) return false;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq <= MaxFloor())
     {
      CloseMine("ARRET TOTAL FTMO -10%");
      GlobalVariableSet(gvHaltAll, 1);
      return false;
     }
   if(eq <= DayFloor())
     {
      CloseMine("JOURNEE COUPEE FTMO -5%");
      GlobalVariableSet(gvHaltDay, 1);
      return false;
     }
   if(GV(gvHaltDay) > 0.5) return false;
   return true;
  }

double Extreme(const bool highs, const int shift, const int count)
  {
   double a[];
   int got = highs ? CopyHigh(_Symbol, SigTF(), shift, count, a)
                   : CopyLow(_Symbol, SigTF(), shift, count, a);
   if(got != count) return 0;
   return highs ? a[ArrayMaximum(a)] : a[ArrayMinimum(a)];
  }

double NormLot(double lots)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots / step) * step;
   if(lots < minL) lots = 0;
   if(lots > maxL) lots = maxL;
   return NormalizeDouble(lots, 2);
  }

double LotsFor(const double price, const double sl, const double riskMoney)
  {
   double loss = 0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, _Symbol, 1.0, price, sl, loss))
      return 0;
   loss = MathAbs(loss);
   if(loss <= 0) return 0;
   return NormLot(riskMoney / loss);
  }

void DetectClose()
  {
   static ulong last_id = 0;
   ulong ticket;
   if(SelectMine(ticket))
     {
      last_id = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      return;
     }
   if(last_id == 0) return;
   // result via history
   if(!HistorySelect(TimeCurrent() - 7 * 86400, TimeCurrent() + 60))
     {
      last_id = 0;
      return;
     }
   double profit = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
     {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_POSITION_ID) != last_id) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT ||
         HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_OUT_BY ||
         HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_INOUT)
         profit += HistoryDealGetDouble(d, DEAL_PROFIT)
                   + HistoryDealGetDouble(d, DEAL_SWAP)
                   + HistoryDealGetDouble(d, DEAL_COMMISSION);
     }
   last_id = 0;
   if(profit < 0)
     {
      double st = GV(gvStreak) + 1;
      GlobalVariableSet(gvStreak, st);
      if(InpPauseLoss > 0 && st >= InpPauseLoss)
        {
         GlobalVariableSet(gvPauseUntil, (double)(TimeCurrent() + InpPauseHours * 3600));
         GlobalVariableSet(gvStreak, 0);
         g_why = "Pause apres pertes";
        }
     }
   else
      GlobalVariableSet(gvStreak, 0);
  }

void Manage()
  {
   ulong ticket;
   if(!SelectMine(ticket)) return;

   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   long type = PositionGetInteger(POSITION_TYPE);
   datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
   int barsOpen = iBarShift(_Symbol, SigTF(), opened, true);
   if(barsOpen < 0) barsOpen = 0;

   if(InpMaxBars > 0 && barsOpen >= InpMaxBars)
     {
      CloseMine("Sortie temps max barres");
      return;
     }

   if(!InpBE_1R || GV(gvBE) > 0.5) return;
   double r = GV(gvR);
   if(r <= 0) return;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double fav = (type == POSITION_TYPE_BUY) ? (bid - entry) : (entry - ask);
   if(fav < r) return;

   double be = NormalizeDouble(entry, _Digits);
   double gap = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   bool ok = false;
   if(type == POSITION_TYPE_BUY && be > sl && be < bid - gap) ok = true;
   if(type == POSITION_TYPE_SELL && (sl == 0 || be < sl) && be > ask + gap) ok = true;
   if(ok && trade.PositionModify(ticket, be, tp))
     {
      GlobalVariableSet(gvBE, 1);
      g_why = "BE a +1R";
     }
  }

void TryEntry()
  {
   if(!Alive()) return;
   ulong ticket;
   if(SelectMine(ticket)) return;

   if(InpPauseLoss > 0 && GV(gvPauseUntil) > (double)TimeCurrent())
     {
      g_why = "Pause active";
      return;
     }

   RollDay();
   if(GV(gvDayTradesD) != (double)FtmoDay())
     {
      GlobalVariableSet(gvDayTradesD, (double)FtmoDay());
      GlobalVariableSet(gvDayTrades, 0);
     }
   if(GV(gvDayTrades) >= InpMaxDayTrades)
     {
      g_why = "Max trades du jour";
      return;
     }

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   if(dt.day_of_week == 5 && dt.hour >= InpFridayHour) return;

   double atr = Buf(hATR, 1);
   if(atr <= 0) return;

   double hh = Extreme(true, 2, InpLookback);
   double hhP = Extreme(true, 3, InpLookback);
   double ll = Extreme(false, 2, InpLookback);
   double llP = Extreme(false, 3, InpLookback);
   double c1 = iClose(_Symbol, SigTF(), 1);
   double c2 = iClose(_Symbol, SigTF(), 2);
   if(hh <= 0 || ll <= 0 || c1 <= 0) return;

   int side = 0; // 1 buy -1 sell
   if(InpBuyOn && c1 > hh && c2 <= hhP) side = 1;
   if(InpSellOn && c1 < ll && c2 >= llP) side = -1;
   if(side == 0) return;

   if(InpUseEma && hEMA != INVALID_HANDLE)
     {
      double e1 = Buf(hEMA, 1);
      if(e1 <= 0) return;
      if(side == 1 && c1 < e1) return;
      if(side == -1 && c1 > e1) return;
     }

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double entry = (side > 0) ? ask : bid;
   double dist = atr * InpSL_ATR;
   if(dist < InpTP_USD * 0.4) dist = InpTP_USD * 0.6;

   double sl = NormalizeDouble(entry - side * dist, _Digits);
   double tp = NormalizeDouble(entry + side * InpTP_USD, _Digits);

   double riskMoney = InpCapital * InpRiskPct / 100.0;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq - riskMoney <= DayFloor() || eq - riskMoney <= MaxFloor())
     {
      g_why = "Plafond: pas d'entree";
      return;
     }

   double lots = LotsFor(entry, sl, riskMoney);
   if(lots <= 0) return;

   bool ok = false;
   if(side > 0)
      ok = trade.Buy(lots, _Symbol, 0, sl, tp, "GFR_BUY");
   else
      ok = trade.Sell(lots, _Symbol, 0, sl, tp, "GFR_SELL");

   if(!ok)
     {
      Print("Ordre refuse: ", trade.ResultRetcodeDescription());
      return;
     }

   GlobalVariableSet(gvR, dist);
   GlobalVariableSet(gvBE, 0);
   GlobalVariableSet(gvDayTrades, GV(gvDayTrades) + 1);
   g_why = StringFormat("%s cassure %d | SL %.1f ATR | TP %.0f$",
                        side > 0 ? "BUY" : "SELL", InpLookback, InpSL_ATR, InpTP_USD);
   Print(g_why, " lots=", lots);
  }

void DrawPanel()
  {
   if(!InpDraw) return;
   double hh = Extreme(true, 2, InpLookback);
   double ll = Extreme(false, 2, InpLookback);
   if(ObjectFind(0, "GFR_HH") < 0) ObjectCreate(0, "GFR_HH", OBJ_HLINE, 0, 0, hh);
   ObjectSetDouble(0, "GFR_HH", OBJPROP_PRICE, hh);
   ObjectSetInteger(0, "GFR_HH", OBJPROP_COLOR, clrDodgerBlue);
   if(ObjectFind(0, "GFR_LL") < 0) ObjectCreate(0, "GFR_LL", OBJ_HLINE, 0, 0, ll);
   ObjectSetDouble(0, "GFR_LL", OBJPROP_PRICE, ll);
   ObjectSetInteger(0, "GFR_LL", OBJPROP_COLOR, clrOrangeRed);

   string s = StringFormat(
      "GoldFTMO_React v1 | %s\n"
      "%s\n"
      "BUY si cloture > bleu | SELL si cloture < rouge\n"
      "TP %.0f$ | SL %.1f ATR | risk %.1f%% | FTMO -%.0f/-%.0f",
      EnumToString(InpTF), g_why, InpTP_USD, InpSL_ATR, InpRiskPct, InpDailyPct, InpMaxPct);
   Comment(s);
  }

void OnTick()
  {
   if(Bars(_Symbol, SigTF()) < InpLookback + InpAtrPeriod + 10) return;
   bool live = Alive();
   DetectClose();
   Manage();

   datetime bar = iTime(_Symbol, SigTF(), 0);
   static datetime last = 0;
   if(bar != 0 && bar != last)
     {
      last = bar;
      if(live) TryEntry();
      DrawPanel();
     }
  }
//+------------------------------------------------------------------+
