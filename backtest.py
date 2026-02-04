import pandas as pd
import numpy as np
from strategy import calculate_indicators, get_signal

class BacktestEngine:
    def __init__(self, initial_capital=1000000.0):
        self.initial_capital = initial_capital
    
    def run_backtest(self, df, strategy_type="MA_Cross"):
        """
        df: Raw DataFrame (OHLCV).
        strategy_type: Name of strategy to test.
        """
        # 1. Calc Indicators
        df = calculate_indicators(df.copy())
        
        cash = self.initial_capital
        inventory = 0
        
        equity_curve = []
        trade_log = []
        
        # Ensure data sorted
        df = df.sort_index()
        
        # Start iteration
        # Need at least 30 rows for indicators to stabilize (MA20, MACD26+9)
        start_idx = 30
        if len(df) < start_idx:
            return pd.Series(), pd.DataFrame()
            
        for i in range(start_idx, len(df)):
            curr_idx = df.index[i]
            
            curr_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            close_price = curr_row['Close']
            
            # --- Get Signal ---
            signal = get_signal(curr_row, prev_row, strategy_type)
            
            # --- Execution ---
            # Simplified Execution: Buy Max / Sell All
            # This logic should mimic the Bot's logic later
            
            action = None
            qty_traded = 0
            pnl = 0
            fee = 0
            tax = 0
            
            if signal == 1: # Buy
                if inventory == 0:
                    # Buy Max (leave buffer/fee)
                    max_mv = cash * 0.99
                    if close_price > 0:
                        shares = int(max_mv // close_price // 1000) * 1000
                        
                        if shares > 0:
                            cost = shares * close_price
                            fee = int(cost * 0.001425)
                            fee = max(fee, 20)
                            total_cost = cost + fee
                            
                            if cash >= total_cost:
                                cash -= total_cost
                                inventory += shares
                                action = "BUY"
                                qty_traded = shares
                            
            elif signal == -1: # Sell
                if inventory > 0:
                    # Sell All
                    revenue = inventory * close_price
                    fee = int(revenue * 0.001425)
                    fee = max(fee, 20)
                    tax = int(revenue * 0.003)
                    net_revenue = revenue - fee - tax
                    
                    cash += net_revenue
                    
                    # Log Trade
                    action = "SELL"
                    qty_traded = inventory
                    inventory = 0
            
            # Record Equity
            market_value = inventory * close_price
            total_equity = cash + market_value
            equity_curve.append({"Date": curr_idx, "Equity": total_equity})
            
            if action:
                trade_log.append({
                    "Date": curr_idx,
                    "Action": action,
                    "Price": close_price,
                    "Qty": qty_traded,
                    "Fee": fee,
                    "Tax": tax,
                    "Cash": cash,
                    "Equity": total_equity
                })
        
        equity_df = pd.DataFrame(equity_curve).set_index("Date")
        trade_df = pd.DataFrame(trade_log)
        
        return equity_df, trade_df

    def calculate_kpis(self, equity_df, trade_df):
        if equity_df.empty:
            return {
                "Total Return": 0, "MDD": 0, "Win Rate": 0, "Sharpe Ratio": 0, "Total Trades": 0
            }
            
        start_eq = equity_df['Equity'].iloc[0]
        end_eq = equity_df['Equity'].iloc[-1]
        
        # 1. Total Return
        total_return = (end_eq - start_eq) / start_eq * 100
        
        # 2. Max Drawdown (MDD)
        roll_max = equity_df['Equity'].cummax()
        drawdown = (equity_df['Equity'] - roll_max) / roll_max
        mdd = drawdown.min() * 100 # %
        
        # 3. Win Rate
        win_rate = 0
        completed_trades = 0
        wins = 0
        
        if not trade_df.empty:
            # Pair trades roughly for P&L tracking
            # Since we iterate sequentially, we can track internal "entry_price"
            entry_price = 0
            entry_fee = 0
            
            current_trade_pnl = []
            
            for idx, row in trade_df.iterrows():
                if row['Action'] == 'BUY':
                    entry_price = row['Price']
                    entry_fee = row['Fee']
                elif row['Action'] == 'SELL' and entry_price > 0:
                    exit_price = row['Price']
                    qty = row['Qty']
                    exit_fee = row['Fee']
                    tax = row['Tax']
                    
                    gross_pnl = (exit_price - entry_price) * qty
                    net_pnl = gross_pnl - entry_fee - exit_fee - tax
                    
                    if net_pnl > 0: wins += 1
                    completed_trades += 1
                    entry_price = 0 # reset
            
            win_rate = (wins / completed_trades * 100) if completed_trades > 0 else 0
            
        # 4. Sharpe Ratio
        equity_df['Daily_Ret'] = equity_df['Equity'].pct_change()
        mean_ret = equity_df['Daily_Ret'].mean()
        std_ret = equity_df['Daily_Ret'].std()
        
        if std_ret == 0 or pd.isna(std_ret):
            sharpe = 0
        else:
            sharpe = (mean_ret / std_ret) * np.sqrt(252)
            
        return {
            "Total Return": total_return,
            "MDD": mdd,
            "Win Rate": win_rate,
            "Sharpe Ratio": sharpe,
            "Total Trades": completed_trades
        }
