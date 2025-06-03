import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
import requests

# --- CONFIG ---
st.set_page_config(page_title="Forex Scanner", page_icon="📈", layout="wide")

# --- CONFIG API TWELVE DATA ---
TWELVE_DATA_API_URL = "https://api.twelvedata.com/time_series"
INTERVAL = "1h"
OUTPUT_SIZE = 100

# --- INTERFACE POUR CLE API ---
st.sidebar.header("🔑 Configuration API")
API_KEY = st.sidebar.text_input("Clé API Twelve Data", type="password", help="Entrez votre clé API Twelve Data")

if not API_KEY:
    st.warning("⚠️ Veuillez entrer votre clé API Twelve Data dans la barre latérale pour commencer.")
    st.info("💡 Vous pouvez obtenir une clé API gratuite sur https://twelvedata.com/")
    st.stop()

# --- FETCH DATA ---
@st.cache_data(ttl=900)
def get_data(symbol, api_key):
    try:
        r = requests.get(TWELVE_DATA_API_URL, params={
            "symbol": symbol,
            "interval": INTERVAL,
            "outputsize": OUTPUT_SIZE,
            "apikey": api_key,
            "timezone": "UTC"
        }, timeout=10)
        
        if r.status_code != 200:
            st.error(f"Erreur HTTP {r.status_code} pour {symbol}")
            return None
            
        j = r.json()
        
        # Vérification des erreurs API
        if "code" in j and j["code"] != 200:
            st.error(f"Erreur API pour {symbol}: {j.get('message', 'Erreur inconnue')}")
            return None
            
        if "values" not in j or not j["values"]:
            st.warning(f"Aucune donnée disponible pour {symbol}")
            return None
            
        df = pd.DataFrame(j["values"])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        
        # Conversion en float avec gestion d'erreurs
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close"}, inplace=True)
        
        # Vérification des données valides
        if df[['Open','High','Low','Close']].isnull().all().all():
            st.warning(f"Données invalides pour {symbol}")
            return None
            
        return df[['Open','High','Low','Close']].dropna()
        
    except requests.exceptions.Timeout:
        st.error(f"Timeout lors de la récupération des données pour {symbol}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur de connexion pour {symbol}: {e}")
        return None
    except Exception as e:
        st.error(f"Erreur lors de la récupération des données pour {symbol}: {e}")
        return None

# --- PAIRS ---
FOREX_PAIRS_TD = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD", "NZD/USD",
    "EUR/JPY", "GBP/JPY", "EUR/GBP",
    "XAU/USD", "US30/USD", "NAS100/USD", "SPX/USD"
]

# --- INDICATEURS ---
def ema(s, p): 
    return s.ewm(span=p, adjust=False).mean()

def rma(s, p): 
    return s.ewm(alpha=1/p, adjust=False).mean()

def rsi(src, p):
    try:
        d = src.diff()
        g = d.where(d > 0, 0.0)
        l = -d.where(d < 0, 0.0)
        rs = rma(g, p) / rma(l, p).replace(0, 1e-9)
        return 100 - 100 / (1 + rs)
    except:
        return pd.Series([50] * len(src), index=src.index)

def adx(h, l, c, p):
    try:
        tr = pd.concat([h-l, abs(h-c.shift()), abs(l-c.shift())], axis=1).max(axis=1)
        atr = rma(tr, p)
        up = h.diff()
        down = l.shift() - l
        plus = np.where((up > down) & (up > 0), up, 0.0)
        minus = np.where((down > up) & (down > 0), down, 0.0)
        pdi = 100 * rma(pd.Series(plus, index=h.index), p) / atr.replace(0, 1e-9)
        mdi = 100 * rma(pd.Series(minus, index=h.index), p) / atr.replace(0, 1e-9)
        dx = 100 * abs(pdi - mdi) / (pdi + mdi).replace(0, 1e-9)
        return rma(dx, p)
    except:
        return pd.Series([20] * len(h), index=h.index)

# --- SIGNALS ---
def confluence_stars(val):
    stars_map = {6: "⭐⭐⭐⭐⭐⭐", 5: "⭐⭐⭐⭐⭐", 4: "⭐⭐⭐⭐", 
                 3: "⭐⭐⭐", 2: "⭐⭐", 1: "⭐"}
    return stars_map.get(val, "WAIT")

def calculate_signals(df):
    if df is None or len(df) < 60:
        return None
        
    try:
        ohlc4 = df[['Open','High','Low','Close']].mean(axis=1)
        signals = {}
        bull = bear = 0

        # HMA approximation
        hma = df['Close'].rolling(9).mean()
        if len(hma) >= 2 and not pd.isna(hma.iloc[-1]) and not pd.isna(hma.iloc[-2]):
            if hma.iloc[-1] > hma.iloc[-2]: 
                bull += 1
                signals['HMA'] = "▲"
            elif hma.iloc[-1] < hma.iloc[-2]: 
                bear += 1
                signals['HMA'] = "▼"
            else:
                signals['HMA'] = "—"
        else:
            signals['HMA'] = "—"

        # RSI
        rsi_series = rsi(ohlc4, 10)
        if len(rsi_series) > 0 and not pd.isna(rsi_series.iloc[-1]):
            rsi_val = rsi_series.iloc[-1]
            signals['RSI'] = f"{int(rsi_val)}"
            if rsi_val > 50: 
                bull += 1
            elif rsi_val < 50: 
                bear += 1
        else:
            signals['RSI'] = "50"

        # ADX
        adx_series = adx(df['High'], df['Low'], df['Close'], 14)
        if len(adx_series) > 0 and not pd.isna(adx_series.iloc[-1]):
            adx_val = adx_series.iloc[-1]
            signals['ADX'] = f"{int(adx_val)}"
            if adx_val >= 20: 
                bull += 1
                bear += 1
        else:
            signals['ADX'] = "20"

        # Heikin Ashi
        try:
            ha_open = (df['Open'].shift(1) + df['Close'].shift(1)) / 2
            ha_close = (df[['Open','High','Low','Close']].sum(axis=1)) / 4
            if not pd.isna(ha_close.iloc[-1]) and not pd.isna(ha_open.iloc[-1]):
                if ha_close.iloc[-1] > ha_open.iloc[-1]: 
                    bull += 1
                    signals['HA'] = "▲"
                elif ha_close.iloc[-1] < ha_open.iloc[-1]: 
                    bear += 1
                    signals['HA'] = "▼"
                else:
                    signals['HA'] = "—"
            else:
                signals['HA'] = "—"
        except:
            signals['HA'] = "—"

        # SHA (Smoothed Heikin Ashi)
        try:
            sha = df['Close'].ewm(span=10).mean()
            sha_open = df['Open'].ewm(span=10).mean()
            if not pd.isna(sha.iloc[-1]) and not pd.isna(sha_open.iloc[-1]):
                if sha.iloc[-1] > sha_open.iloc[-1]: 
                    bull += 1
                    signals['SHA'] = "▲"
                elif sha.iloc[-1] < sha_open.iloc[-1]: 
                    bear += 1
                    signals['SHA'] = "▼"
                else:
                    signals['SHA'] = "—"
            else:
                signals['SHA'] = "—"
        except:
            signals['SHA'] = "—"

        # Ichimoku simplifié
        try:
            tenkan = (df['High'].rolling(9).max() + df['Low'].rolling(9).min()) / 2
            kijun = (df['High'].rolling(26).max() + df['Low'].rolling(26).min()) / 2
            senkou_a = (tenkan + kijun) / 2
            senkou_b = (df['High'].rolling(52).max() + df['Low'].rolling(52).min()) / 2
            price = df['Close'].iloc[-1]
            
            if (not pd.isna(senkou_a.iloc[-1]) and not pd.isna(senkou_b.iloc[-1]) and 
                not pd.isna(price)):
                cloud_top = max(senkou_a.iloc[-1], senkou_b.iloc[-1])
                cloud_bottom = min(senkou_a.iloc[-1], senkou_b.iloc[-1])
                
                if price > cloud_top: 
                    bull += 1
                    signals['Ichimoku'] = "▲"
                elif price < cloud_bottom: 
                    bear += 1
                    signals['Ichimoku'] = "▼"
                else: 
                    signals['Ichimoku'] = "—"
            else:
                signals['Ichimoku'] = "—"
        except:
            signals['Ichimoku'] = "—"

        confluence = max(bull, bear)
        direction = "HAUSSIER" if bull > bear else "BAISSIER" if bear > bull else "NEUTRE"
        stars = confluence_stars(confluence)

        return {"confluence": confluence, "direction": direction, "stars": stars, "signals": signals}
        
    except Exception as e:
        st.error(f"Erreur dans le calcul des signaux: {e}")
        return None

# --- INTERFACE UTILISATEUR ---
st.title("📈 Forex Scanner")
st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    st.header("⚙️ Paramètres")
    min_conf = st.slider("Confluence minimale", 0, 6, 3)
    show_all = st.checkbox("Afficher toutes les paires", value=False)
    
    scan_button = st.button("🚀 Lancer le scan", type="primary")

with col2:
    if scan_button and API_KEY:
        st.header("📊 Résultats du scan")
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        
        for i, symbol in enumerate(FOREX_PAIRS_TD):
            progress = (i + 1) / len(FOREX_PAIRS_TD)
            progress_bar.progress(progress)
            status_text.text(f"Analyse de {symbol} ({i+1}/{len(FOREX_PAIRS_TD)})")
            
            df = get_data(symbol, API_KEY)
            
            if df is not None:
                res = calculate_signals(df)
                if res:
                    if show_all or res['confluence'] >= min_conf:
                        color = ('green' if res['direction'] == 'HAUSSIER' 
                               else 'red' if res['direction'] == 'BAISSIER' 
                               else 'gray')
                        
                        row = {
                            "Paire": symbol.replace("/", ""),
                            "Confluences": res['stars'],
                            "Direction": f"<span style='color:{color}'>{res['direction']}</span>",
                        }
                        row.update(res['signals'])
                        results.append(row)
            
            # Délai pour éviter de surcharger l'API
            time.sleep(0.5)
        
        progress_bar.empty()
        status_text.empty()
        
        if results:
            df_res = pd.DataFrame(results)
            # Tri par nombre d'étoiles (plus complexe car ce sont des strings)
            df_res['sort_key'] = df_res['Confluences'].apply(lambda x: x.count('⭐'))
            df_res = df_res.sort_values(by="sort_key", ascending=False).drop('sort_key', axis=1)
            
            st.markdown("### 🎯 Opportunités détectées")
            st.markdown(df_res.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            # Bouton de téléchargement
            csv_data = df_res.copy()
            csv_data['Direction'] = csv_data['Direction'].str.replace('<[^<]+?>', '', regex=True)
            
            st.download_button(
                "📂 Exporter en CSV", 
                data=csv_data.to_csv(index=False).encode('utf-8'), 
                file_name=f"forex_confluences_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", 
                mime="text/csv"
            )
            
            # Statistiques
            st.markdown("### 📈 Statistiques")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Pairs analysées", len(FOREX_PAIRS_TD))
            with col2:
                st.metric("Opportunités trouvées", len(results))
            with col3:
                haussier = sum(1 for r in results if 'HAUSSIER' in r['Direction'])
                st.metric("Signaux haussiers", haussier)
                
        else:
            st.warning("⚠️ Aucun résultat correspondant aux critères.")
            st.info("💡 Essayez de réduire la confluence minimale ou d'activer 'Afficher toutes les paires'")

# Footer
st.markdown("---")
col1, col2 = st.columns([2, 1])
with col1:
    st.caption(f"🕒 Dernière mise à jour : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
with col2:
    st.caption("💡 Données fournies par Twelve Data")

# Aide
with st.expander("ℹ️ Aide et informations"):
    st.markdown("""
    **Comment utiliser ce scanner :**
    1. Entrez votre clé API Twelve Data (gratuite sur twelvedata.com)
    2. Ajustez la confluence minimale (nombre d'indicateurs en accord)
    3. Lancez le scan pour analyser toutes les paires
    
    **Indicateurs utilisés :**
    - **HMA** : Hull Moving Average (approximation)
    - **RSI** : Relative Strength Index
    - **ADX** : Average Directional Index  
    - **HA** : Heikin Ashi
    - **SHA** : Smoothed Heikin Ashi
    - **Ichimoku** : Nuage d'Ichimoku (simplifié)
    
    **Symboles :**
    - ▲ : Signal haussier
    - ▼ : Signal baissier  
    - — : Signal neutre
    """)
