
import pandas as pd
import numpy as np
import streamlit as st
from utils import get_stock_data
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import xgboost as xgb

# ==========================================
# 1. Feature Engineering
# ==========================================
# ==========================================
# 1. Feature Engineering
# ==========================================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['Close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['Close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line, macd - signal_line # MACD_Hist

def calculate_kd(df, period=9):
    low_min = df['Low'].rolling(window=period).min()
    high_max = df['High'].rolling(window=period).max()
    rsv = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return k, d

def calculate_bollinger(df, period=20, std_dev=2):
    ma = df['Close'].rolling(window=period).mean()
    std = df['Close'].rolling(window=period).std()
    upper = ma + (std * std_dev)
    lower = ma - (std * std_dev)
    return upper, lower

def prepare_data(ticker, period="2y"):
    """
    Fetches data and generates technical features.
    Target: Next Day's Close Price.
    """
    df = get_stock_data(ticker, period=period)
    if df.empty: return pd.DataFrame(), pd.DataFrame()
    
    # Ensure correct sorting
    df = df.sort_index()

    # Features
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['RSI'] = calculate_rsi(df['Close'])
    
    # MACD
    df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = calculate_macd(df)
    
    # KD
    df['K'], df['D'] = calculate_kd(df)
    
    # Bollinger
    df['UpperB'], df['LowerB'] = calculate_bollinger(df)
    
    df['PctChange'] = df['Close'].pct_change()
    df['VolChange'] = df['Volume'].pct_change()
    
    # --- ADD VIX DATA ---
    try:
        vix = get_stock_data("^VIX", period=period) 
        if not vix.empty:
            vix = vix[['Close']].rename(columns={'Close': 'VIX'})
            df = df.join(vix, how='left')
            df['VIX'] = df['VIX'].ffill()
    except Exception as e:
        print(f"VIX Fetch Error: {e}")
        df['VIX'] = 0 
    
    # Handle infinite values & NaNs
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df.dropna()
    
    # Valid Features Check
    if 'VIX' not in df.columns: df['VIX'] = 0
    
    return df

# ==========================================
# 2. XGBoost Model
# ==========================================
def train_xgboost(df, horizon=1, features=['Close', 'MA5', 'MA20', 'RSI', 'MACD', 'MACD_Hist', 'K', 'D', 'UpperB', 'LowerB', 'PctChange', 'VolChange', 'VIX']):
    """
    Trains XGBoost Regressor for a specific prediction horizon.
    horizon=1 -> Predict next day
    horizon=5 -> Predict 5 days later
    """
    data = df.copy()
    
    # Create Target: Future Close Price shifted by 'horizon'
    # if horizon=1, Target[t] = Close[t+1]
    data['Target'] = data['Close'].shift(-horizon)
    
    # For training, we need valid Target. 
    # The last 'horizon' rows will have NaN Target. These are our "Predict X" input rows.
    train_valid = data.dropna(subset=['Target'])
    
    if train_valid.empty:
         return None, pd.DataFrame(), 0, 0, 0, {}
    
    X = train_valid[features]
    y = train_valid['Target']
    
    # Split
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    
    # Model
    model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    # Evaluate
    preds = model.predict(X_test)
    # Validating metrics on Test Set (Split 80/20)
    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    
    # Calculate MAPE
    diff = np.abs((y_test - preds) / y_test)
    diff.replace([np.inf, -np.inf], np.nan, inplace=True)
    mape = diff.mean()
    
    results = pd.DataFrame({
        "Actual": y_test,
        "Predicted": preds
    }, index=y_test.index)
    
    # --- IMPORTANT ---
    # Re-train model on FULL dataset for future prediction
    # If we don't do this, the model is stale (missing last 20% data)
    final_model = xgb.XGBRegressor(
        objective='reg:squarederror',
        n_estimators=100,
        learning_rate=0.1,
        max_depth=5,
        random_state=42
    )
    final_model.fit(X, y)
    
    # Feature Importance
    f_importance = dict(zip(features, final_model.feature_importances_))
    
    return final_model, results, mae, rmse, mape, f_importance
# ==========================================
# 3. LSTM Model (Deep Learning)
# ==========================================
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping

def create_sequences(data, seq_length):
    xs, ys = [], []
    for i in range(len(data) - seq_length):
        x = data[i:(i + seq_length)]
        y = data[i + seq_length]
        xs.append(x)
        ys.append(y)
    return np.array(xs), np.array(ys)

@st.cache_resource(show_spinner="Training LSTM Model... this may take a minute.")
def train_lstm_model(ticker_data_json, seq_length=60, epochs=20):
    """
    Wrapper to train LSTM. 
    Cached by streamlit to avoid re-training if data hasn't changed.
    Input `ticker_data_json` is just for hashing (can be the df.to_json()).
    Actually passing DF to cache is tricky. Better to not cache here or use hash_funcs.
    For simplicity, we might skip cache first or cache the heavy lifting.
    Let's just implement standard training first.
    """
    pass 

def train_lstm(df, forecast_days=1, seq_length=60, epochs=10, features=['Close', 'MA5', 'MA20', 'RSI', 'PctChange', 'VolChange', 'VIX']):
    
    # 1. Scale Data
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(df[features])
    
    target_idx = features.index('Close')
    
    X, y = [], []
    # Train for Horizon = 1 (Predict Next Day)
    for i in range(seq_length, len(scaled_data)):
        X.append(scaled_data[i-seq_length:i]) 
        y.append(scaled_data[i, target_idx])
        
    X, y = np.array(X), np.array(y)
    
    if len(X) == 0: return None, pd.DataFrame(), 0, 0, 0, [], None

    # 2. Split Data (OLD: Train on 90% only -> Causes Lag)
    # NEW: Train on 100% Data for Production Prediction
    # We still need x_train, y_train for syntax, but we use ALL data.
    
    # Check if we have enough data
    if len(X) < 10:
        return None, pd.DataFrame(), 0, 0, 0, [], None

    X_train = np.array(X)
    y_train = np.array(y)
    
    # 3. Build LSTM Model
    model = Sequential()
    model.add(LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])))
    model.add(Dropout(0.2))
    model.add(LSTM(units=30, return_sequences=False))
    model.add(Dropout(0.2))
    model.add(Dense(units=1))
    
    model.compile(optimizer='adam', loss='mean_squared_error')
    
    # 4. Train
    # Use validation_split=0.1 to just show some validation metrics, 
    # BUT this creates the same problem (last 10% not used for training).
    # For Production: Train on everything. 
    # We can rely on 'loss' (Training Loss) for convergence check.
    history = model.fit(X_train, y_train, epochs=epochs, batch_size=32, verbose=0)
    
    # 5. Evaluate (Self-Check on recent data)
    # We can't really calculate "Test MAE" accurately without a holdout, 
    # but we can calc "Training MAE" to return something.
    train_preds = model.predict(X_train)
    
    # Inverse Transform
    # We need to inverse transform (y is only 1 column, but scaler was fit on N features)
    # Hack: scaler expects N features.
    # We need a helper to inverse just the target column.
    
    # Create dummy array for inverse transform
    def inverse_target(preds_array):
        # preds_array: (N, 1)
        # We need (N, features)
        dummy = np.zeros((len(preds_array), len(features)))
        # Target (Close) is at target_idx
        dummy[:, target_idx] = preds_array.flatten()
        inv = scaler.inverse_transform(dummy)
        return inv[:, target_idx]

    y_train_inv = inverse_target(y_train)
    train_preds_inv = inverse_target(train_preds)
    
    mae = mean_absolute_error(y_train_inv, train_preds_inv)
    rmse = np.sqrt(mean_squared_error(y_train_inv, train_preds_inv))
    mape = np.mean(np.abs((y_train_inv - train_preds_inv) / y_train_inv))
    
    results = pd.DataFrame({
        "Actual": y_train_inv,
        "Predicted": train_preds_inv
    }, index=df.index[seq_length:])

    # RECURSIVE FUTURE PREDICTION
    future_prices = []
    
    # Start with the last known sequence
    current_seq = scaled_data[-seq_length:].copy() # shape (60, features)
    
    for _ in range(forecast_days):
        # Predict Next Step using current sequence
        # Reshape to (1, 60, features)
        input_seq = current_seq.reshape(1, seq_length, len(features))
        pred_scaled = model.predict(input_seq)[0][0] # Scalar
        
        # Inverse to get real price for this step
        dummy_f = np.zeros((1, len(features)))
        dummy_f[:, target_idx] = pred_scaled
        pred_price = scaler.inverse_transform(dummy_f)[0, target_idx]
        future_prices.append(pred_price)
        
        # Update Sequence for Next Step
        # Shift everything left, append new prediction?
        # PROBLEM: We only predicted "Close" price, but we need ALL features (MA, RSI, etc) for the next step.
        # Strategy:
        # 1. "Naive" strategy: Assume other features stay constant? (Bad)
        # 2. "Feature Estimation": Re-calculate indicators based on new Close? (Complex)
        # 3. "Self-Correction": Just assume other features drift or use last known?
        
        # Better approach for simplified recursion:
        # Create a dummy row for the new step. 
        # Update 'Close' with predicted close.
        # For other columns, copy the last value (Naive persistence).
        # This is not perfect but valid for short horizon (5 days).
        
        new_row = current_seq[-1].copy() # Copy last row of features
        new_row[target_idx] = pred_scaled # Update Close
        
        # Append new row, remove first row
        current_seq = np.vstack([current_seq[1:], new_row])
    
    return model, results, mae, rmse, mape, future_prices, history

# ==========================================
# 4. Prophet Model (Seasonality Expert)
# ==========================================
from prophet import Prophet
import logging

# Mute Prophet Logs
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

def train_prophet(df, forecast_days=5):
    """
    Trains FB Prophet Model.
    Returns: 
        forecast_df (full dataframe with history + future)
        future_only (list of T+1...T+N prices)
        model (object, for components plot)
        mae (float)
    """
    # 1. Prep Data (Prophet strict format: ds, y)
    prophet_df = df.reset_index()[['Date', 'Close']].copy()
    prophet_df.columns = ['ds', 'y']
    
    # Ensure ds is tz-naive for Prophet (often an issue)
    if prophet_df['ds'].dt.tz is not None:
        prophet_df['ds'] = prophet_df['ds'].dt.tz_localize(None)
        
    # 2. Build & Train
    # daily_seasonality=True because we have daily data
    # yearly_seasonality=True (if > 1 year data)
    # weekly_seasonality=True (to capture day-of-week effects)
    
    # Simple Heuristic: If < 1 year data, disable yearly
    use_yearly = len(prophet_df) > 365
    
    m = Prophet(daily_seasonality=False, weekly_seasonality=True, yearly_seasonality=use_yearly)
    m.fit(prophet_df)
    
    # 3. Predict Future
    # Prophet logic: make_future_dataframe includes history + future
    future = m.make_future_dataframe(periods=forecast_days, freq='B') # 'B' = Business Day
    forecast = m.predict(future)
    
    # 4. Extract Results
    # Return last 'forecast_days' rows
    future_preds = forecast.iloc[-forecast_days:]
    
    # Extract just the price values
    future_prices = future_preds['yhat'].values.tolist()
    
    # Metrics (Training MAE)
    # Compare 'yhat' with 'y' in history
    # Align indices (Prophet preserves order)
    history_len = len(prophet_df)
    y_true = prophet_df['y'].values
    y_pred = forecast['yhat'].iloc[:history_len].values
    
    mae = mean_absolute_error(y_true, y_pred)
    
    return forecast, future_prices, m, mae
