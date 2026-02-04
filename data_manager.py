import json
import os

def save_data(broker, watchlists, trade_log, bot_config, username="default"):
    """
    Saves user data to JSON file.
    """
    filename = f"user_{username}.json"
    data = {
        "balance": broker.balance,
        "inventory": broker.inventory,
        "transaction_history": broker.transaction_history,
        "watchlists": watchlists,
        "trade_log": trade_log,
        "bot_config": bot_config
    }
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

def load_data(username="default"):
    """
    Loads user data from JSON file.
    Returns: dict or None
    """
    filename = f"user_{username}.json"
    if not os.path.exists(filename):
        return None
        
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        # If error (e.g. empty file), backup and return None
        print(f"Error loading data: {e}")
        return None
