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
    
    
    # Local Backup (Always good to have)
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving local data: {e}")

    # Cloud Persistence
    try:
        from gsheet_handler import gsheet_logger
        gsheet_logger.save_user_data("Stock_Bot_Log", username, data)
        return True
    except Exception as e:
        print(f"Error saving cloud data: {e}")
        return False

def load_data(username="default"):
    """
    Loads user data from JSON file.
    Returns: dict or None
    """
    # 1. Try Cloud
    try:
        from gsheet_handler import gsheet_logger
        cloud_data = gsheet_logger.fetch_user_data("Stock_Bot_Log", username)
        if cloud_data:
            print(f"Loaded data from Cloud for {username}")
            return cloud_data
    except Exception as e:
        print(f"Cloud load error: {e}")

    # 2. Local Fallback
    filename = f"user_{username}.json"
    if not os.path.exists(filename):
        return None
        
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"Loaded data from Local for {username}")
            return data
    except Exception as e:
        print(f"Error loading local data: {e}")
        return None
