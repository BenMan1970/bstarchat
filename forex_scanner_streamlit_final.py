import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
import requests

# --- CONFIGURATION DES SECRETS ---
API_KEY = st.secrets.get("API_KEY", "")
TWELVE_DATA_API_URL = st.secrets.get("TWELVE_DATA_API_URL", "https://api.twelvedata.com/time_series")
INTERVAL = st.secrets.get("INTERVAL", "1min")
OUTPUT_SIZE = st.secrets.get("OUTPUT_SIZE", "60")

# --- FETCH DATA ---
@st.cache_data(ttl=900)
def get_data(symbol):
    try:
        r = requests.get(TWELVE_DATA_API_URL, params={
            "symbol": symbol,
            "interval": INTERVAL,
            "outputsize": OUTPUT_SIZE,
            "apikey": API_KEY,
            "timezone": "UTC"
        })
        r.raise_for_status()  # Lève une exception pour les erreurs HTTP
        j = r.json()
        if "values" not in j:
            st.error(f"Erreur pour {symbol}: 'values' absent dans la réponse API: {j}")
            return None
        df = pd.DataFrame(j["values"])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        df = df.astype(float)
        df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close"}, inplace=True)
        return df[['Open','High','Low','Close']]
    except requests.exceptions.HTTPError as e:
        if r.status_code == 429:
            st.warning(f"Limite de requêtes dépassée pour {symbol}. Attente avant réessai...")
            time.sleep(60)  # Attendre 60 secondes avant de réessayer
            return get_data(symbol)  # Réessayer
        st.error(f"Erreur HTTP pour {symbol}: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Erreur générale pour {symbol}: {str(e)}")
        return None

# --- PAIRS ---
FOREX_PAIRS_TD = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/JPY", "GBP/JPY", "EUR/GBP"
]

# --- INDICATEURS ---
def ema(s, p): return s.ewm(span=p, adjust=False).mean()
def rma(s, p): return s.ewm(alpha=1/p, adjust=False).mean()

# --- SIGNALS ---
def confluence_stars(val):
    if val == 6: return "⭐⭐⭐⭐⭐⭐"
    elif val == 5: return "⭐⭐⭐⭐⭐"
    elif val == 4: return "⭐⭐⭐⭐"
    elif val == 3: return "⭐⭐⭐"
    elif val == 2: return "⭐⭐"
    elif val == 1: return "⭐"
    else: return "WAIT"

def calculate_signals(df):
    if df is None or len(df) < 60:
        return None
    ohlc4 = df[['Open','High','Low','Close']].mean(axis=1)
    signals = {}
    bull = bear = 0

    hma = df['Close'].rolling(9).mean()  # approximation de HMA
    if hma.iloc[-1] > hma.iloc[-2]: bull += 1; signals['HMA'] = "▲"
    elif hma.iloc[-1] < hma.iloc[-2]: bear += 1; signals['HMA'] = "▼"

    rsi_val = rsi(ohlc4, 10).iloc[-1]
    signals['RSI'] = f"{int(rsi_val)}"
    if rsi_val > 50: bull += 1
    elif rsi_val < 50: bear += 1

    adx_val = adx(df['High'], df['Low'], df['Close'], 14).iloc[-1]
    signals['ADX'] = f"{int(adx_val)}"
    if adx_val >= 20: bull += 1; bear += 1

    ha_open = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
    ha_close = (df[['Open','High','Low','Close']].sum(axis=1)) / 4
    if ha_close.iloc[-1] > ha_open.iloc[-1]: bull += 1; signals['HA'] = "▲"
    elif ha_close.iloc[-1] < ha_open.iloc[-1]: bear += 1; signals['HA'] = "▼"

    sha = df['Close'].ewm(span=10).mean()
    sha_open = df['Open'].ewm(span=10).mean()
    if sha.iloc[-1] > sha_open.iloc[-1]: bull += 1; signals['SHA'] = "▲"
    elif sha.iloc[-1] < sha_open.iloc[-1]: bear += 1; signals['SHA'] = "▼"

    # Ichimoku simplifié
    tenkan = (df['High'].rolling(9).max() + df['Low'].rolling(9).min()) / 2
    kijun = (df['High'].rolling(26).max() + df['Low'].rolling(26).min()) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (df['High'].rolling(52).max() + df['Low'].rolling(52).min()) / 2
    price = df['Close'].iloc[-1]
    ichi_signal = 1 if price > max(senkou_a.iloc[-1], senkou_b.iloc[-1]) else -1 if price < min(senkou_a.iloc[-1], senkou_b.iloc[-1]) else 0
    if ichi_signal == 1: bull += 1; signals['Ichimoku'] = "▲"
    elif ichi_signal == -1: bear += 1; signals['Ichimoku'] = "▼"
    else: signals['Ichimoku'] = "—"

    confluence = max(bull, bear)
    direction = "HAUSSIER" if bull > bear else "BAISSIER" if bear > bull else "NEUTRE"
    stars = confluence_stars(confluence)

    return {"confluence": confluence, "direction": direction, "stars": stars, "signals": signals}

def rsi(src, p):
    d = src.diff(); g = d.where(d > 0, 0.0); l = -d.where(d < 0, 0.0)
    rs = rma(g, p) / rma(l, p).replace(0, 1e-9)
    return 100 - 100 / (1 + rs)

def adx(h, l, c, p):
    tr = pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)
    atr = rma(tr, p)
    up = h.diff(); down = l.shift() - l
    plus = np.where((up > down) & (up > 0), up, 0.0)
    minus = np.where((down > up) & (down > 0), down, 0.0)
    pdi = 100 * rma(pd.Series(plus, index=h.index), p) / atr.replace(0, 1e-9)
    mdi = 100 * rma(pd.Series(minus, index=h.index), p) / atr.replace(0, 1e-9)
    dx = 100 * abs(pdi - mdi) / (pdi + mdi).replace(0, 1e-9)
    return rma(dx, p)

# --- INTERFACE UTILISATEUR ---
st.sidebar.header("Paramètres")
min_conf = st.sidebar.slider("Confluence minimale", 0, 6, 3)
show_all = st.sidebar.checkbox("Afficher toutes les paires", value=False)

if st.sidebar.button("Lancer le scan"):
    if not API_KEY:
        st.error("Clé API non configurée. Vérifiez les secrets dans Streamlit.")
    else:
        results = []
        for i, symbol in enumerate(FOREX_PAIRS_TD):
            st.sidebar.text(f"Analyse de {symbol} ({i+1}/{len(FOREX_PAIRS_TD)})")
            df = get_data(symbol)
            time.sleep(1.0)
            res = calculate_signals(df)
            if res:
                if show_all or res['confluence'] >= min_conf:
                    color = 'green' if res['direction'] == 'HAUSSIER' else 'red' if res['direction'] == 'BAISSIER' else 'gray'
                    row = {
                        "Paire": symbol.replace("/", ""),
                        "Confluences": res['stars'],
                        "Direction": f"<span style='color:{color}'>{res['direction']}</span>",
                    }
                    row.update(res['signals'])
                    results.append(row)

        if results:
            df_res = pd.DataFrame(results).sort_values(by="Confluences", ascending=False)
            st.markdown(df_res.to_html(escape=False, index=False), unsafe_allow_html=True)
            st.download_button("📂 Exporter CSV", data=df_res.to_csv(index=False).encode('utf-8'), file_name="confluences.csv", mime="text/csv")
        else:
            st.warning("Aucun résultat correspondant aux critères.")

st.caption(f"Dernière mise à jour : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
