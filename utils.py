import pandas as pd
import requests
import yfinance as yf
import datetime
import streamlit as st

@st.cache_data(ttl=60)
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
        # Use history(1d) as it is most reliable for Close, even if slightly delayed vs fast_info
        # fast_info often returns -1 or stale data after hours
        
        curr_price = 0.0
        time_str = "N/A"
        
        # Try fetching 1 minute data for today first
        df_m = get_stock_data(ticker, period="1d", interval="1m")
        
        if not df_m.empty:
            curr_price = float(df_m['Close'].iloc[-1])
            time_str = df_m.index[-1].strftime("%Y-%m-%d %H:%M")
        else:
            # Fallback to Daily history (reliable 5d)
            if not df_d.empty:
                curr_price = float(df_d['Close'].iloc[-1])
                time_str = df_d.index[-1].strftime("%Y-%m-%d (已收盤)")
                
        # Double check against fast_info ONLY if we have no valid price yet or it seems wild
        # But actually history() is usually better.
        # If curr_price is 0, try fast_info
        if curr_price == 0:
             fi = t.fast_info.get('last_price', -1)
             if fi > 0: 
                 curr_price = fi
                 time_str = "Realtime (FastInfo)"
        
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

@st.cache_data(ttl=3600)
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
            pivot = raw_df.pivot_table(index='date', columns='name', values='net', aggfunc='sum').fillna(0)
            
            # Rename approximate columns
            rename_map = {}
            for col in pivot.columns:
                if 'Foreign' in col: rename_map[col] = 'Foreign_Net'
                elif 'Trust' in col: rename_map[col] = 'Trust_Net'
                elif 'Dealer' in col: rename_map[col] = 'Dealer_Net'
            
            pivot = pivot.rename(columns=rename_map)
            
            # Merge duplicate columns (e.g. Foreign_Net appearing twice)
            pivot = pivot.groupby(level=0, axis=1).sum()

            return pivot
            
    except Exception as e:
        print(f"Inst Data Error: {e}")
        
    return pd.DataFrame()


# --- Analysis Tools ---

@st.cache_data(ttl=300)
def get_top_movers_batch(top_n=10):
    """
    Fetches data for a broad list of key TWSE stocks to determine Top Gainers/Losers.
    Returns: (gainers_df, losers_df, volume_df)
    """
    # Sample List of Key Stocks (Top ~100 by weight/popularity approx)
    # Includes Tech, Finance, FPC, Steel, Transport, ETFs
    targets = [
        "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2303.TW", "2881.TW", "2882.TW", "2891.TW", "2886.TW", "2884.TW",
        "1301.TW", "1303.TW", "1326.TW", "6505.TW", "2002.TW", "2912.TW", "713.TW", "5871.TW", "5876.TW", "2890.TW",
        "2892.TW", "2883.TW", "2885.TW", "2880.TW", "2887.TW", "2382.TW", "2357.TW", "3231.TW", "2356.TW", "2327.TW",
        "3008.TW", "3045.TW", "2412.TW", "3034.TW", "2603.TW", "2609.TW", "2615.TW", "2379.TW", "3037.TW", "2345.TW",
        "5880.TW", "2395.TW", "4938.TW", "2377.TW", "2376.TW", "2408.TW", "2344.TW", "3711.TW", "3661.TW", "2383.TW",
        "3017.TW", "2368.TW", "2312.TW", "3443.TW", "6669.TW", "3035.TW", "3006.TW", "6415.TW", "5269.TW", "8046.TWO",
        "3293.TWO", "3529.TWO", "3131.TWO", "8299.TWO", "6274.TWO", "8069.TWO", "5347.TWO", "6147.TWO", "3227.TWO",
        "1101.TW", "1102.TW", "1216.TW", "1402.TW", "1476.TW", "1504.TW", "1590.TW", "1605.TW", "2207.TW", "2105.TW",
        "2353.TW", "2324.TW", "2409.TW", "3481.TW", "2618.TW", "2610.TW", "2915.TW", "8454.TW", "9910.TW", "9904.TW",
        "0050.TW", "0056.TW", "00878.TW", "00929.TW", "00919.TW", "00940.TW", "00939.TW", "006208.TW"
    ]
    
    try:
        # Batch Download (Much faster)
        df = yf.download(targets, period="5d", progress=False)
        
        # Handle MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            # Extract Close and Volume
            # df['Close'] gives a DataFrame with tickers as columns
            closes = df['Close']
            volumes = df['Volume']
        else:
            # Single ticker case (unlikely given list), or Flat index
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # Calculate Change % (Last close vs Prev Close)
        # Using .iloc[-1] and .iloc[-2]
        if len(closes) < 2:
             return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
             
        latest = closes.iloc[-1]
        prev = closes.iloc[-2]
        
        # Series: Pct Change
        pct_change = ((latest - prev) / prev) * 100
        
        # create summary df
        summary = pd.DataFrame({
            "Price": latest,
            "ChangePct": pct_change,
            "Volume": volumes.iloc[-1]
        })
        
        # Filter NaNs
        summary = summary.dropna()
        
        # Sort
        gainers = summary.sort_values("ChangePct", ascending=False).head(top_n)
        losers = summary.sort_values("ChangePct", ascending=True).head(top_n)
        active = summary.sort_values("Volume", ascending=False).head(top_n)
        
        # Add Name Column (Optional, if we import STOCK_NAMES)
        # For now return Ticker index
        
        return gainers, losers, active

    except Exception as e:
        print(f"Batch Mover Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=300)
def get_sector_performance():
    """
    Approximates sector performance using key ETFs or Index Representatives.
    """
    sectors = {
        "半導體": "2330.TW",
        "金融": "2881.TW",
        "航運": "2603.TW",
        "鋼鐵": "2002.TW",
        "塑膠": "1301.TW",
        "水泥": "1101.TW",
        "食品": "1216.TW",
        "電子": "2317.TW",
        "高股息": "0056.TW",
    }
    
    data = []
    try:
        df = yf.download(list(sectors.values()), period="5d", progress=False)['Close']
        if len(df) >= 2:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            pct = ((latest - prev) / prev) * 100
            
            for name, ticker in sectors.items():
                if ticker in pct:
                    data.append({"Sector": name, "Change": pct[ticker], "Proxy": ticker})
                    
        return pd.DataFrame(data).sort_values("Change", ascending=False)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fundamental_data(ticker):
    """
    Fetches basic fundamentals (EPS, ROE, PE, PB) from yfinance.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        
        # Extract key metrics with fallbacks
        data = {
            "EPS (Trailing)": info.get('trailingEps', 'N/A'),
            "EPS (Forward)": info.get('forwardEps', 'N/A'),
            "P/E Ratio": info.get('trailingPE', 'N/A'),
            "ROE": info.get('returnOnEquity', 'N/A'),
            "P/B Ratio": info.get('priceToBook', 'N/A'),
            "Dividend Yield": info.get('dividendYield', 'N/A'),
            "Market Cap": info.get('marketCap', 'N/A')
        }
        
        # Formatting
        if isinstance(data['ROE'], (float, int)): data['ROE'] = f"{data['ROE']*100:.2f}%"
        if isinstance(data['Dividend Yield'], (float, int)): data['Dividend Yield'] = f"{data['Dividend Yield']:.2f}%"
        if isinstance(data['P/E Ratio'], (float, int)): data['P/E Ratio'] = f"{data['P/E Ratio']:.2f}"
        if isinstance(data['Market Cap'], (float, int)): data['Market Cap'] = f"{data['Market Cap']/100000000:.2f} 億"
        
        return data
    except Exception as e:
        print(f"Fund Error: {e}")
        return {}

@st.cache_data(ttl=86400)
def fetch_shareholding_data(stock_id):
    """
    Fetches weekly shareholding distribution (Large shareholders) from FinMind.
    Looking for 'TaiwanStockShareholding'.
    Focus on > 400 or > 1000 lots (Big Hands).
    """
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockShareholding",
            "data_id": stock_id,
            "start_date": (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d"),
            "end_date": datetime.date.today().strftime("%Y-%m-%d")
        }
        r = requests.get(url, params=params)
        j = r.json()
        
        if j['msg'] == 'success':
            df = pd.DataFrame(j['data'])
            if df.empty: return pd.DataFrame()
            
            # Filter for "Total" or specific buckets?
            # FinMind returns breakdown by level (1-999, 1000-5000...).
            # We want "HoldingPercentage" of the top levels (e.g., Level 15 = >1000 lots which is usually huge, 
            # or just look for 'ForeignInvestmentShares' etc if available? No, Shareholding is by holding ranges)
            # FinMind levels: 15=1000+ lots (check docs)
            # Actually FinMind returns columns: date, stock_id, mixture, HoldingProportion, HoldingShares, level
            # level 15 is max (>1000 lots usually)
            
            df['date'] = pd.to_datetime(df['date'])
            
            # Get > 400 lots (Common definition of 'Big Hand' in TW)
            # or > 1000 lots
            # We will sum up holding proportion for levels > 10 (approx > 400/600/800/1000)
            # FinMind levels map: 
            # 14: 600-800, 15: 800-1000, 16: >1000 (Check latest schema, assuming >1000 is level 15 in some versions or 17)
            # To be safe, let's just grab the highest level available.
            
            # Let's pivot to inspect
            # We want to trend "Big Hands Holding %"
            
            # Simplified: Filter level == 15 (if that's max)
            # Actually, let's filter for the specific "Total" or combine high levels.
            # Let's assume Level 15 (1000張以上) for now.
            
            big_hands = df[df['HoldingGradation'] == 15] # 15 is often >1000 lots code in TWSE
            if big_hands.empty:
                 # Try 14 or Max
                 max_level = df['HoldingGradation'].max()
                 big_hands = df[df['HoldingGradation'] == max_level]
            
            return big_hands[['date', 'HoldingProportion', 'HoldingShares']]
            
    except Exception as e:
        print(f"Shareholding Error: {e}")
        
    return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_financial_statement(ticker):
    """
    Fetches condensed Income Statement and Balance Sheet.
    Returns: (income_df, balance_df)
    """
    try:
        t = yf.Ticker(ticker)
        # Quarterly Financials preferred for recency
        inc = t.quarterly_financials
        bal = t.quarterly_balance_sheet
        return inc, bal
    except:
        return pd.DataFrame(), pd.DataFrame()

@st.cache_data(ttl=86400)
def get_dividend_history(ticker):
    """
    Fetches dividend history.
    """
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs.empty: return pd.DataFrame()
        
        # Convert Series to DataFrame
        df = divs.to_frame(name="Dividend").sort_index(ascending=False)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_recent_news(ticker):
    """
    Fetches recent news headlines.
    Parsed for new yfinance structure.
    """
    try:
        t = yf.Ticker(ticker)
        raw_news = t.news
        
        parsed_news = []
        for n in raw_news:
            # --- 1. Title ---
            # Try 'title' direct, or inside 'content'
            title = n.get('title')
            if not title and 'content' in n:
                title = n['content'].get('title', 'No Title')
            if not title: title = 'No Title'
            
            # --- 2. Publisher ---
            publisher = 'Unknown'
            # Try provider.displayName
            if 'provider' in n and isinstance(n['provider'], dict):
                publisher = n['provider'].get('displayName', publisher)
            # Try content.provider.displayName
            elif 'content' in n and 'provider' in n['content']:
                publisher = n['content']['provider'].get('displayName', publisher)
                
            # --- 3. Link ---
            link = '#'
            # Try clickThroughUrl.url
            if 'clickThroughUrl' in n and isinstance(n['clickThroughUrl'], dict):
                 link = n['clickThroughUrl'].get('url', link)
            # Try content.clickThroughUrl.url
            elif 'content' in n and 'clickThroughUrl' in n['content']:
                 link = n['content']['clickThroughUrl'].get('url', link)
            # Try link direct
            elif 'link' in n:
                 link = n.get('link', link)
                
            parsed_news.append({
                "title": title,
                "publisher": publisher,
                "link": link,
                "providerPublishTime": n.get('providerPublishTime', 0)
            })
            
        return parsed_news
    except:
        return []
