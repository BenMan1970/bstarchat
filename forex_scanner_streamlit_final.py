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
OUTPUT_SIZE = 50  # Réduit pour éviter les limites API

# --- INTERFACE POUR CLE API ---
st.sidebar.header("🔑 Configuration API")
API_KEY = st.sidebar.text_input("Clé API Twelve Data", type="password", help="Entrez votre clé API Twelve Data")

if not API_KEY:
    st.warning("⚠️ Veuillez entrer votre clé API Twelve Data dans la barre latérale pour commencer.")
    st.info("💡 Vous pouvez obtenir une clé API gratuite sur https://twelvedata.com/")
    st.stop()

# --- FETCH DATA ---
def get_data(symbol, api_key):
    """Récupère les données avec diagnostic détaillé"""
    try:
        params = {
            "symbol": symbol,
            "interval": INTERVAL,
            "outputsize": OUTPUT_SIZE,
            "apikey": api_key,
            "timezone": "UTC"
        }
        
        st.write(f"🔍 Requête pour {symbol}...")
        r = requests.get(TWELVE_DATA_API_URL, params=params, timeout=15)
        
        st.write(f"📡 Status: {r.status_code}")
        
        if r.status_code != 200:
            st.error(f"❌ Erreur HTTP {r.status_code} pour {symbol}")
            return None
            
        j = r.json()
        st.write(f"📋 Réponse API: {list(j.keys())}")
        
        # Diagnostics détaillés
        if "status" in j and j["status"] == "error":
            st.error(f"❌ Erreur API pour {symbol}: {j.get('message', 'Erreur inconnue')}")
            return None
            
        if "code" in j and j["code"] != 200:
            st.error(f"❌ Code erreur {j['code']} pour {symbol}: {j.get('message', 'Erreur inconnue')}")
            return None
            
        if "values" not in j:
            st.warning(f"⚠️ Pas de données 'values' pour {symbol}. Clés disponibles: {list(j.keys())}")
            if "note" in j:
                st.info(f"ℹ️ Note API: {j['note']}")
            return None
            
        if not j["values"] or len(j["values"]) == 0:
            st.warning(f"⚠️ Données vides pour {symbol}")
            return None
            
        df = pd.DataFrame(j["values"])
        st.write(f"📊 Données reçues: {len(df)} lignes, colonnes: {list(df.columns)}")
        
        # Vérification des colonnes essentielles
        required_cols = ['datetime', 'open', 'high', 'low', 'close']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            st.error(f"❌ Colonnes manquantes pour {symbol}: {missing_cols}")
            return None
        
        df['datetime'] = pd.to_datetime(df['datetime'])
        df.set_index('datetime', inplace=True)
        df = df.sort_index()
        
        # Conversion en float avec diagnostic
        for col in ['open', 'high', 'low', 'close']:
            original_type = df[col].dtype
            df[col] = pd.to_numeric(df[col], errors='coerce')
            null_count = df[col].isnull().sum()
            if null_count > 0:
                st.warning(f"⚠️ {null_count} valeurs nulles dans {col} pour {symbol}")
            
        df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close"}, inplace=True)
        
        # Vérification finale
        clean_df = df[['Open','High','Low','Close']].dropna()
        st.write(f"✅ Données nettoyées: {len(clean_df)} lignes valides")
        
        if len(clean_df) < 30:
            st.warning(f"⚠️ Pas assez de données pour {symbol} ({len(clean_df)} lignes)")
            return None
            
        return clean_df
        
    except requests.exceptions.Timeout:
        st.error(f"⏱️ Timeout pour {symbol}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"🌐 Erreur réseau pour {symbol}: {e}")
        return None
    except Exception as e:
        st.error(f"💥 Erreur inattendue pour {symbol}: {e}")
        return None

# --- PAIRS SIMPLIFIEES POUR TEST ---
FOREX_PAIRS_TD = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD"
]

# --- INDICATEURS SIMPLIFIES ---
def calculate_simple_signals(df):
    """Version simplifiée des signaux pour debug"""
    if df is None or len(df) < 20:
        return None
        
    try:
        signals = {}
        bull = bear = 0
        
        # 1. Simple Moving Average
        sma_short = df['Close'].rolling(5).mean()
        sma_long = df['Close'].rolling(10).mean()
        
        if len(sma_short) >= 2 and len(sma_long) >= 2:
            if sma_short.iloc[-1] > sma_long.iloc[-1]:
                bull += 1
                signals['SMA'] = "▲"
            else:
                bear += 1
                signals['SMA'] = "▼"
        else:
            signals['SMA'] = "—"
        
        # 2. Price vs Moving Average
        sma_20 = df['Close'].rolling(20).mean()
        current_price = df['Close'].iloc[-1]
        
        if not pd.isna(sma_20.iloc[-1]):
            if current_price > sma_20.iloc[-1]:
                bull += 1
                signals['Price_vs_MA'] = "▲"
            else:
                bear += 1
                signals['Price_vs_MA'] = "▼"
        else:
            signals['Price_vs_MA'] = "—"
        
        # 3. Volume (si disponible) ou momentum simple
        if len(df) >= 3:
            momentum = df['Close'].iloc[-1] - df['Close'].iloc[-3]
            if momentum > 0:
                bull += 1
                signals['Momentum'] = "▲"
            else:
                bear += 1
                signals['Momentum'] = "▼"
        else:
            signals['Momentum'] = "—"
        
        # 4. High/Low position
        high_20 = df['High'].rolling(20).max()
        low_20 = df['Low'].rolling(20).min()
        
        if not pd.isna(high_20.iloc[-1]) and not pd.isna(low_20.iloc[-1]):
            range_20 = high_20.iloc[-1] - low_20.iloc[-1]
            position = (current_price - low_20.iloc[-1]) / range_20 if range_20 > 0 else 0.5
            
            if position > 0.7:
                bull += 1
                signals['Position'] = "▲"
            elif position < 0.3:
                bear += 1
                signals['Position'] = "▼"
            else:
                signals['Position'] = "—"
        else:
            signals['Position'] = "—"
        
        confluence = max(bull, bear)
        direction = "HAUSSIER" if bull > bear else "BAISSIER" if bear > bull else "NEUTRE"
        
        # Système d'étoiles simplifié
        stars_map = {4: "⭐⭐⭐⭐", 3: "⭐⭐⭐", 2: "⭐⭐", 1: "⭐"}
        stars = stars_map.get(confluence, "WAIT")
        
        return {
            "confluence": confluence, 
            "direction": direction, 
            "stars": stars, 
            "signals": signals,
            "price": f"{current_price:.4f}"
        }
        
    except Exception as e:
        st.error(f"💥 Erreur calcul signaux: {e}")
        return None

# --- INTERFACE UTILISATEUR ---
st.title("📈 Forex Scanner (Mode Debug)")
st.markdown("---")

col1, col2 = st.columns([1, 3])

with col1:
    st.header("⚙️ Paramètres")
    min_conf = st.slider("Confluence minimale", 0, 4, 1)  # Réduit à 4 max
    show_all = st.checkbox("Afficher toutes les paires", value=True)  # Par défaut True
    debug_mode = st.checkbox("Mode debug détaillé", value=True)
    
    scan_button = st.button("🚀 Lancer le scan", type="primary")

with col2:
    if scan_button and API_KEY:
        st.header("📊 Résultats du scan")
        
        if debug_mode:
            st.info("🔧 Mode debug activé - vous verrez tous les détails du processus")
        
        results = []
        errors = []
        
        for i, symbol in enumerate(FOREX_PAIRS_TD):
            st.markdown(f"### 🔍 Analyse de {symbol} ({i+1}/{len(FOREX_PAIRS_TD)})")
            
            with st.expander(f"Détails pour {symbol}", expanded=debug_mode):
                df = get_data(symbol, API_KEY)
                
                if df is not None:
                    st.success(f"✅ Données récupérées pour {symbol}")
                    
                    res = calculate_simple_signals(df)
                    if res:
                        st.write(f"🎯 Signaux calculés: {res}")
                        
                        if show_all or res['confluence'] >= min_conf:
                            color = ('green' if res['direction'] == 'HAUSSIER' 
                                   else 'red' if res['direction'] == 'BAISSIER' 
                                   else 'gray')
                            
                            row = {
                                "Paire": symbol.replace("/", ""),
                                "Prix": res['price'],
                                "Confluences": res['stars'],
                                "Direction": f"<span style='color:{color}'>{res['direction']}</span>",
                            }
                            row.update(res['signals'])
                            results.append(row)
                            st.success(f"✅ {symbol} ajouté aux résultats")
                        else:
                            st.info(f"ℹ️ {symbol} filtré (confluence {res['confluence']} < {min_conf})")
                    else:
                        st.error(f"❌ Échec calcul signaux pour {symbol}")
                        errors.append(f"{symbol}: Échec calcul signaux")
                else:
                    st.error(f"❌ Pas de données pour {symbol}")
                    errors.append(f"{symbol}: Pas de données")
            
            # Délai pour éviter de surcharger l'API
            if i < len(FOREX_PAIRS_TD) - 1:  # Pas de délai après le dernier
                time.sleep(2)  # Augmenté à 2 secondes
        
        # Résultats finaux
        st.markdown("---")
        st.markdown("## 📋 Résumé final")
        
        if results:
            st.success(f"✅ {len(results)} opportunités trouvées sur {len(FOREX_PAIRS_TD)} paires analysées")
            
            df_res = pd.DataFrame(results)
            df_res['sort_key'] = df_res['Confluences'].apply(lambda x: x.count('⭐'))
            df_res = df_res.sort_values(by="sort_key", ascending=False).drop('sort_key', axis=1)
            
            st.markdown("### 🎯 Opportunités détectées")
            st.markdown(df_res.to_html(escape=False, index=False), unsafe_allow_html=True)
            
        else:
            st.warning("⚠️ Aucun résultat trouvé")
            st.info("💡 Vérifiez votre clé API ou réduisez la confluence minimale")
        
        if errors:
            st.markdown("### ❌ Erreurs rencontrées")
            for error in errors:
                st.text(f"• {error}")

# Footer
st.markdown("---")
st.caption(f"🕒 Dernière mise à jour : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

# Guide de diagnostic
with st.expander("🔧 Guide de diagnostic"):
    st.markdown("""
    **Si aucun résultat n'apparaît :**
    
    1. **Clé API invalide** : Vérifiez votre clé sur twelvedata.com
    2. **Limites API atteintes** : Attendez ou upgradez votre plan
    3. **Symboles invalides** : Certains symboles peuvent ne pas être disponibles
    4. **Confluence trop élevée** : Réduisez la confluence minimale à 1
    5. **Données insuffisantes** : Certaines paires peuvent manquer de données historiques
    
    **En mode debug, vous devriez voir :**
    - Les requêtes API pour chaque paire
    - Le status code de chaque réponse
    - Le nombre de lignes de données reçues
    - Les erreurs spécifiques
    
    **API Twelve Data - Plans gratuits :**
    - 800 appels par jour
    - 8 appels par minute
    - Données différées
    """)

# Test rapide de l'API
if st.button("🧪 Test rapide API"):
    st.write("Test de connexion avec EUR/USD...")
    test_result = get_data("EUR/USD", API_KEY)
    if test_result is not None:
        st.success("✅ API fonctionne !")
        st.write(f"Exemple de données reçues: {len(test_result)} lignes")
        st.write(test_result.head())
    else:
        st.error("❌ Problème avec l'API")
