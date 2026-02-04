import pandas as pd
import requests
import yfinance as yf
import datetime

def get_stock_data(ticker, period="1y", interval="1d"):
    """
    Robust wrapper for yfinance download.
    Handles MultiIndex columns (ticker levels) and ensures clean OHLCV format.
    """
    try:
        # Download
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        
        if df.empty:
            return df
            
        # Handle MultiIndex Columns (feature of yf 0.2+)
        # If columns are (Price, Ticker), drop the Ticker level
        if isinstance(df.columns, pd.MultiIndex):
            # Attempt to flatten or drop level
            # Check if levels > 1
            if df.columns.nlevels > 1:
                df.columns = df.columns.droplevel(1) # Drop Ticker level
        
        # Ensure standard columns exist
        needed = ['Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in df.columns for col in needed):
            pass
            
        # Ensure numeric
        for col in needed:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df = df.dropna()
        
        # --- TIMEZONE FIX ---
        # yfinance returns UTC. Convert to Asia/Taipei
        if df.index.tz is None:
             # Assume UTC if naive, or localize? yfinance usually returns tz-aware UTC
             try:
                 df.index = df.index.tz_localize('UTC')
             except:
                 pass # Already aware?
                 
        try:
             df.index = df.index.tz_convert('Asia/Taipei')
        except:
             pass 

        return df
        
    except Exception as e:
        print(f"Data Fetch Error {ticker}: {e}")
        return pd.DataFrame()

def get_latest_price(ticker):
    """
    Returns the latest Close price as a scalar float.
    Safe against Series/DataFrame returns.
    """
    try:
        # Try Intraday first for freshness (1m)
        df = get_stock_data(ticker, period="1d", interval="1m")
        if df.empty:
             # Fallback to Daily
             df = get_stock_data(ticker, period="5d", interval="1d")
             
        if df.empty:
            return 0.0
            
        price_val = df['Close'].iloc[-1]
        
        # Force Scalar
        if isinstance(price_val, pd.Series):
             return float(price_val.values[0])
        elif isinstance(price_val, (pd.DataFrame, list, pd.api.extensions.ExtensionArray)): 
             try: return float(price_val.iloc[0])
             except: return float(price_val)
        return float(price_val)
    except:
        return 0.0

def get_realtime_quote(ticker):
    """
    Returns a dict with: 'price', 'change', 'pct', 'time_str'
    Uses 1m data for latest price, and Daily data for Previous Close.
    """
    try:
        # 1. Get History (Daily) - Primary
        df_d = get_stock_data(ticker, period="1mo", interval="1d")
        
        # 2. Get History (Hourly) - Fallback for recent gaps (common in yfinance)
        df_h = get_stock_data(ticker, period="5d", interval="60m")
        
        # Setup Timezone & Dates
        try:
             now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
             today_date = now.date()
        except:
             today_date = datetime.date.today()

        def get_last_close_before_today(df, scan_date):
            if df.empty: return None, None
            # Check TZ
            if df.index.tz is None: 
                try: df.index = df.index.tz_localize('UTC').tz_convert('Asia/Taipei')
                except: pass
            else:
                try: df.index = df.index.tz_convert('Asia/Taipei')
                except: pass
                
            mask = df.index.date < scan_date
            df_past = df[mask]
            
            if not df_past.empty:
                return df_past.index[-1].date(), float(df_past['Close'].iloc[-1])
            return None, None

        # Candidate 1: Daily
        d_date, d_price = get_last_close_before_today(df_d, today_date)
        
        # Candidate 2: Hourly
        h_date, h_price = get_last_close_before_today(df_h, today_date)
        
        # DECISION: Pick the most recent one
        prev_close = 0.0
        
        if d_date and h_date:
            if h_date > d_date:
                prev_close = h_price # Hourly is newer (Daily gap)
            else:
                prev_close = d_price # Daily is same or newer (prefer Daily for accuracy)
        elif d_date:
            prev_close = d_price
        elif h_date:
            prev_close = h_price
        else:
            # No past data? Fallback to Open
            if not df_d.empty: prev_close = float(df_d['Open'].iloc[0])

        # 2. Get Intraday (for Current Price & Time)
        df_m = get_stock_data(ticker, period="1d", interval="1m")
        
        curr_price = 0.0
        time_str = "N/A"
        
        is_intraday = False
        
        if not df_m.empty:
            curr_price = float(df_m['Close'].iloc[-1])
            # Formatted Date + Time
            time_str = df_m.index[-1].strftime("%Y-%m-%d %H:%M")
            is_intraday = True
        else:
            # Fallback to Daily last row
            if not df_d.empty:
                curr_price = float(df_d['Close'].iloc[-1])
                time_str = df_d.index[-1].strftime("%Y-%m-%d (已收盤)")
        
        # 3. Calculate Change
        if prev_close > 0:
            chg = curr_price - prev_close
            pct = (chg / prev_close) * 100
        else:
            chg = 0; pct = 0
            
        return {
            "price": curr_price,
            "change": chg,
            "pct": pct,
            "time": time_str,
            "prev_close": prev_close
        }
    except Exception as e:
        print(f"Quote Error: {e}")
        return {"price": 0, "change": 0, "pct": 0, "time": "Error"}


def fetch_twse_institutional_data(stock_id, days=30):
    """
    Scrapes TWSE institutional data (unchanged but robust).
    """
    data = []
    try:
        url = f"https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
            "data_id": stock_id,
            "start_date": (datetime.date.today() - datetime.timedelta(days=days+10)).strftime("%Y-%m-%d"),
            "end_date": datetime.date.today().strftime("%Y-%m-%d")
        }
        r = requests.get(url, params=params)
        j = r.json()
        
        if j['msg'] == 'success':
            raw_df = pd.DataFrame(j['data'])
            if raw_df.empty: return pd.DataFrame()
            
            raw_df['date'] = pd.to_datetime(raw_df['date'])
            raw_df['buy'] = raw_df['buy'].astype(float)
            raw_df['sell'] = raw_df['sell'].astype(float)
            raw_df['net'] = raw_df['buy'] - raw_df['sell']
            
            # Pivot by Name
            # We want columns: Foreign_Net, Trust_Net, Dealer_Net
            # Name mapping might vary.
            # Typical names: "Foreign Dealers", "Investment Trust", "Dealers"
            
            pivot = raw_df.pivot_table(index='date', columns='name', values='net', aggfunc='sum').fillna(0)
            
            # Rename approximate columns
            rename_map = {}
            for col in pivot.columns:
                if 'Foreign' in col: rename_map[col] = 'Foreign_Net'
                elif 'Trust' in col: rename_map[col] = 'Trust_Net'
                elif 'Dealer' in col: rename_map[col] = 'Dealer_Net'
            
            pivot = pivot.rename(columns=rename_map)
            return pivot
            
    except Exception as e:
        print(f"Inst Data Error: {e}")
        
    return pd.DataFrame()
