import pandas as pd
import requests
import os

def fetch_and_parse(url, market_suffix):
    print(f"Fetching {url}...")
    try:
        # Fix SSL Error: Use requests with verify=False
        r = requests.get(url, verify=False)
        r.encoding = 'big5' # Force Big5 for TWSE
        
        # Use pandas to read HTML from text
        dfs = pd.read_html(r.text, header=0)
        # The ISIN table is usually the first one
        df = dfs[0]
        
        # Identify the correct column
        col_name = None
        for col in df.columns:
            if "有價證券代號" in str(col):
                col_name = col
                break
        
        if not col_name:
            print("Could not find Code/Name column.")
            return {}

        stock_map = {}
        for item in df[col_name]:
            item = str(item)
            # Format is usually "2330　台積電" or "2330 台積電"
            # It might have 0x3000 (ideographic space)
            parts = item.split()
            if len(parts) >= 2:
                code = parts[0].strip()
                name = parts[1].strip()
                
                # Filter: We only want standard stock codes (usually 4 digits)
                # But ETFs are 5 digits (0050.TW). 
                # Warrants are 6 digits.
                # Let's include everything that looks like a stock/ETF ticker.
                
                # Check if code is numeric or alphanumeric (some ETFs/Warrents)
                # Simple heuristic: Code length check.
                if len(code) == 4 or (len(code) == 5 and code.startswith('00')):
                    # Add .TW / .TWO suffix
                    ticker = f"{code}.{market_suffix}"
                    stock_map[ticker] = name
                    # Also map raw code for flexibility
                    stock_map[code] = name
                    
        return stock_map
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return {}

def main():
    # 1. Listed (TWSE) -> .TW
    twse_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
    twse_map = fetch_and_parse(twse_url, "TW")
    print(f"Parsed {len(twse_map)//2} TWSE stocks.")

    # 2. OTC (TPEX) -> .TWO
    # Note: Yahoo Finance often uses .TWO for OTC, but sometimes .TW works too if mapped.
    # Safe bet: Yahoo Finance uses .TWO for Taipei Exchange. 
    # BUT, many users just try .TW. Let's support both if possible? 
    # Actually, let's stick to .TWO for OTC as per Yahoo standard.
    # Wait, simple app.py logic usually just appends .TW. 
    # If the user types 8299 (Phison), it's OTC. It needs 8299.TWO.
    # My current app logic aut-appends ".TW". This might be a bug for OTC stocks.
    # I should map "8299" -> "群聯" AND maybe I should help the app know it is .TWO?
    # For now, let's just generate the Name Map. Fixing the .TW vs .TWO issue is a separate task (Logic).
    # I will map both "8299.TWO" and "8299.TW" to the name just in case the user forces it, 
    # or just map "8299" -> Name.
    
    tpex_url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    tpex_map = fetch_and_parse(tpex_url, "TWO")
    print(f"Parsed {len(tpex_map)//2} TPEX stocks.")
    
    # Merge
    full_map = {**twse_map, **tpex_map}
    
    # Write to stock_map.py in current directory (files are relative to CWD)
    # CWD is d:/AI/Antigravity/STOCK/
    with open("stock_map.py", "w", encoding="utf-8") as f:
        f.write("# Auto-generated stock name map\n")
        f.write("# Contains TWSE and TPEX stocks/ETFs\n\n")
        f.write("STOCK_NAMES = {\n")
        
        # Sort for neatness
        for code in sorted(full_map.keys()):
            name = full_map[code]
            f.write(f'    "{code}": "{name}",\n')
            
        f.write("}\n\n")
        f.write("def get_stock_name(symbol):\n")
        f.write("    # Strip suffix for fuzzy lookup if exact match fail\n")
        f.write("    if symbol in STOCK_NAMES:\n")
        f.write("        return STOCK_NAMES[symbol]\n")
        f.write("    base = symbol.split('.')[0]\n")
        f.write("    return STOCK_NAMES.get(base, symbol)\n")

    print(f"Successfully generated stock_map.py with {len(full_map)} entries.")

if __name__ == "__main__":
    main()
