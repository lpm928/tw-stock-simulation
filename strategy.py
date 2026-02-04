import pandas as pd
import numpy as np

def calculate_indicators(df):
    """
    Calculates all technical indicators needed for strategies.
    Modifies df in-place.
    """
    # MA
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD (12, 26, 9)
    exp12 = df['Close'].ewm(span=12, adjust=False).mean()
    exp26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = exp12 - exp26
    df['DEM'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['MACD_Bar'] = df['DIF'] - df['DEM']
    
    # Bollinger Bands (20, 2)
    df['BB_Mid'] = df['Close'].rolling(window=20).mean()
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Up'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BB_Low'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # KD (Stochastic Oscillator) (9, 3, 3)
    low_min = df['Low'].rolling(window=9).min()
    high_max = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    
    # Calculate K and D recursively (Loop for accuracy)
    k_list = []
    d_list = []
    k = 50
    d = 50
    
    # To improve speed, if df is large, this loop is slow.
    # But for 1y daily data (~250 rows), it's negligible.
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_list.append(50)
            d_list.append(50)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_list.append(k)
            d_list.append(d)
            
    df['K'] = k_list
    df['D'] = d_list

    return df

def get_signal(row, prev_row, strategy_name):
    """
    Returns generic signal: 1 (Buy), -1 (Sell), 0 (Hold).
    """
    signal = 0
    
    if strategy_name == "MA_Cross":
        if prev_row['MA5'] < prev_row['MA20'] and row['MA5'] > row['MA20']:
            signal = 1
        elif prev_row['MA5'] > prev_row['MA20'] and row['MA5'] < row['MA20']:
            signal = -1
            
    elif strategy_name == "RSI_Strategy":
        if prev_row['RSI'] < 30 and row['RSI'] >= 30:
            signal = 1
        elif prev_row['RSI'] > 70 and row['RSI'] <= 70:
            signal = -1
            
    elif strategy_name == "MACD_Strategy":
        if prev_row['DIF'] < prev_row['DEM'] and row['DIF'] > row['DEM']:
            signal = 1
        elif prev_row['DIF'] > prev_row['DEM'] and row['DIF'] < row['DEM']:
            signal = -1
            
    elif strategy_name == "Bollinger_Strategy":
        if row['Close'] <= row['BB_Low']:
            signal = 1
        elif row['Close'] >= row['BB_Up']:
            signal = -1
            
    elif strategy_name == "KD_Strategy":
        if prev_row['K'] < 20 and prev_row['K'] < prev_row['D'] and row['K'] > row['D']:
            signal = 1
        elif prev_row['K'] > 80 and prev_row['K'] > prev_row['D'] and row['K'] < row['D']:
            signal = -1
            
    return signal

def get_strategy_status(df, strategy_name):
    """
    Returns a string describing strategy status.
    e.g. "MA5: 120 > MA20: 115"
    """
    if df.empty: return "無數據"
    row = df.iloc[-1]
    
    try:
        if strategy_name == "MA_Cross":
            ma5 = row['MA5']
            ma20 = row['MA20']
            dist = (ma5 - ma20) / ma20 * 100
            trend = "多頭排列" if ma5 > ma20 else "空頭排列"
            return f"MA5: {ma5:.1f} | MA20: {ma20:.1f} ({trend} {dist:+.1f}%)"
            
        elif strategy_name == "RSI_Strategy":
            rsi = row['RSI']
            return f"RSI: {rsi:.1f} (超買>70, 超賣<30)"
            
        elif strategy_name == "MACD_Strategy":
            dif = row['DIF']
            dem = row['DEM']
            bar = row['MACD_Bar']
            return f"DIF: {dif:.2f} | DEM: {dem:.2f} | Bar: {bar:.2f}"
            
        elif strategy_name == "Bollinger_Strategy":
            up = row['BB_Up']
            low = row['BB_Low']
            close = row['Close']
            return f"現價: {close:.1f} | 上軌: {up:.1f} | 下軌: {low:.1f}"
            
        elif strategy_name == "KD_Strategy":
            k = row['K']
            d = row['D']
            return f"K: {k:.1f} | D: {d:.1f}"
    except:
        return "計算錯誤"
        
    return "N/A"

def check_strategy(df, ticker, broker, strategy_name="MA_Cross"):
    """
    Legacy wrapper.
    """
    if 'MACD_Bar' not in df.columns or 'K' not in df.columns:
        df = calculate_indicators(df)
        
    if len(df) < 2:
        return False, ""
        
    curr_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    signal = get_signal(curr_row, prev_row, strategy_name)
    
    qty = broker.inventory.get(ticker, {}).get('qty', 0)
    current_price = curr_row['Close']
    
    msg = ""
    executed = False
    
    if signal == 1:
        if qty == 0: 
             success, m = broker.buy(ticker, current_price, 1000, action="現股買進")
             if success:
                 msg = f"🚀 {strategy_name} 買進訊號! {m}"
                 executed = True
             else:
                 msg = f"⚠️ {strategy_name} 買進訊號但失敗: {m}"
    elif signal == -1:
        if qty > 0:
            success, m = broker.sell(ticker, current_price, qty, action="現股賣出")
            if success:
                msg = f"📉 {strategy_name} 賣出訊號! {m}"
                executed = True
            else:
                 msg = f"⚠️ {strategy_name} 賣出訊號但失敗: {m}"
                 
    return executed, msg
