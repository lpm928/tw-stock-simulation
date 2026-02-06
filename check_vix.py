
import yfinance as yf
import pandas as pd

print("Checking ^VIXTWN (Taiwan VIX)...")
try:
    vix = yf.Ticker("^VIXTWN")
    hist = vix.history(period="1mo")
    if not hist.empty:
        print("Success! Found ^VIXTWN data:")
        print(hist.tail())
    else:
        print("Failed: ^VIXTWN history is empty.")
except Exception as e:
    print(f"Error checking ^VIXTWN: {e}")

print("\nChecking ^VIX (US VIX) as fallback/comparison...")
try:
    vix = yf.Ticker("^VIX")
    hist = vix.history(period="1mo")
    if not hist.empty:
        print("Success! Found ^VIX data:")
        print(hist.tail())
    else:
        print("Failed: ^VIX history is empty.")
except Exception as e:
    print(f"Error checking ^VIX: {e}")
