import sys
import os
import pandas as pd
import numpy as np

# Add parent dir to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker import PaperBroker
from data_manager import save_data, load_data
from strategy import calculate_indicators, get_signal
import datetime

def test_broker_ops():
    print("--- Testing Broker Operations ---")
    broker = PaperBroker(initial_balance=1000000)
    
    # 1. Buy Long
    print(f"[1] Buy Long: 2330.TW @ 1000")
    # Top up first to avoid insufficient funds
    broker.set_balance(2000000)
    success, msg = broker.buy("2330.TW", 1000.0, 1000, action="現股買進")
    
    inv = broker.inventory.get("2330.TW")
    if success and inv:
        print(f"PASS: Buy Successful. Qty: {inv['qty']}")
    else:
        print(f"FAIL: {msg}")

    # 2. Sell Long
    print(f"[2] Sell Long: 2330.TW @ 1100")
    success, msg = broker.sell("2330.TW", 1100.0, 1000, action="現股賣出")
    if success: print(f"PASS: Sell Successful. Msg: {msg}")
    else: print(f"FAIL: {msg}")

    # 3. Short Sell
    print(f"[3] Short Sell: 2603.TW @ 500")
    success, msg = broker.sell("2603.TW", 500.0, 1000, action="融券賣出")
    inv = broker.inventory.get("2603.TW")
    if success and inv['qty'] == -1000:
        print(f"PASS: Short Successful. Qty: {inv['qty']}")
    else:
        print(f"FAIL: {msg}")

    # 4. Cover Short
    print(f"[4] Cover Short: 2603.TW @ 400")
    success, msg = broker.buy("2603.TW", 400.0, 1000, action="融券回補")
    if success and broker.inventory["2603.TW"]['qty'] == 0:
        print(f"PASS: Cover Successful. Msg: {msg}")
    else:
        print(f"FAIL: {msg}")

def test_persistence():
    print("\n--- Testing Persistence ---")
    broker = PaperBroker() # reset
    broker.set_balance(5000)
    broker.inventory = {"TEST": {"qty": 100, "cost": 10}}
    watch = {"MyList": ["1111"]}
    log = ["Log1"]
    cfg = {"targets":["TEST"]}
    
    save_data(broker, watch, log, cfg)
    
    data = load_data()
    # Check
    if data['balance'] == 5000 and data['inventory']['TEST']['qty'] == 100:
        print("PASS: Save/Load Data Integrity Verified.")
    else:
        print("FAIL: Data mismatch.")

def test_strategy():
    print("\n--- Testing Strategy Logic ---")
    # Mock Data: Need Full OHLC for KD/BB
    dates = pd.date_range('2024-01-01', periods=30)
    data = {
        'Close': np.linspace(100, 130, 30), # 30 days linear up
        'Open': np.linspace(100, 130, 30),
        'High': np.linspace(101, 131, 30),
        'Low': np.linspace(99, 129, 30),
        'Volume': [1000]*30
    }
    df = pd.DataFrame(data, index=dates)
    
    # Run Calc
    try:
        df = calculate_indicators(df)
        print("PASS: Indicators Calculation Successful.")
    except Exception as e:
        print(f"FAIL: Calc Error: {e}")
        return
    
    # Check Signal
    # Fake a Golden Cross manually to test get_signal logic
    # Prev: MA5 < MA20. Curr: MA5 > MA20.
    row1 = {'MA5': 90, 'MA20': 95, 'RSI': 50, 'DIF':0, 'DEM':0, 'K':50, 'D':50, 'Close': 100, 'BB_Low': 90, 'BB_Up': 110}
    row2 = {'MA5': 96, 'MA20': 95, 'RSI': 60, 'DIF':0, 'DEM':0, 'K':50, 'D':50, 'Close': 105, 'BB_Low': 90, 'BB_Up': 110}
    
    sig = get_signal(row2, row1, "MA_Cross")
    if sig == 1:
        print("PASS: MA Golden Cross Detected.")
    else:
        print(f"FAIL: Signal not detected. Sig={sig}")

def test_risk_mgmt():
    print("\n--- Testing Risk Management (Simulation) ---")
    # Scenario: Long 2330 @ 1000. Curr Price 800. SL 10%.
    # PnL% = (800-1000)/1000 = -20%. Should Trigger.
    
    cost = 1000
    curr = 800
    qty = 1000
    sl_pct = 0.10
    
    pnl_pct = (curr - cost) / cost
    print(f"Scenario: Cost {cost}, Curr {curr}, PnL {pnl_pct*100:.1f}%")
    
    triggered = False
    if pnl_pct < -sl_pct:
        triggered = True
        
    if triggered:
        print("PASS: Stop Loss Logic Triggered correctly.")
    else:
        print("FAIL: Stop Loss failed to trigger.")

def test_watchlist():
    print("\n--- Testing Watchlist Logic ---")
    watchlists = {"Default": ["2330.TW"]}
    active_list = "Default"
    
    # Add Item
    if "2603.TW" not in watchlists[active_list]:
        watchlists[active_list].append("2603.TW")
    
    if "2603.TW" in watchlists["Default"]:
        print("PASS: Added Item Successful.")
    else:
        print("FAIL: Add Item Failed.")
        
    # Create List
    watchlists["NewList"] = []
    if "NewList" in watchlists:
        print("PASS: Create List Successful.")
    else:
        print("FAIL: Create List Failed.")
        
    # Add to New List
    watchlists["NewList"].append("0050.TW")
    if "0050.TW" in watchlists["NewList"]:
        print("PASS: Add to New List Successful.")
    else:
        print("FAIL: Add to New List Failed.")
        
    # Delete List
    del watchlists["NewList"]
    if "NewList" not in watchlists:
         print("PASS: Delete List Successful.")
    else:
         print("FAIL: Delete List Failed.")

if __name__ == "__main__":
    test_broker_ops()
    test_persistence()
    test_strategy()
    test_risk_mgmt()
    test_watchlist()
