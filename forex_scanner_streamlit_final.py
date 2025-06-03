import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timezone
import requests

# --- CONFIG ---
st.set_page_config(page_title="Forex Scanner", page_icon="📈", layout="wide")

# --- VERSION ULTRA-SIMPLIFIEE POUR DEBUG ---
st.title("📈 Forex Scanner - Version Debug")
st.markdown("---")

# Variables globales pour le debug
debug_info = []

def add_debug(message):
    debug_info.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
    st.write(f"🔍 {message}")

# Test avec API gratuite alternative (exchangerate-api.com)
def test_free_api():
    """Test avec une API gratuite simple"""
    add_debug("Test avec API gratuite exchangerate-api.com")
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=10)
        add_debug(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            add_debug(f"Données reçues: {list(data.keys())}")
            return data
        else:
            add_debug(f"Erreur HTTP: {response.status_code}")
            return None
    except Exception as e:
        add_debug(f"Erreur: {e}")
        return None

# Test avec Twelve Data
def test_twelve_data(api_key):
    """Test spécifique Twelve Data"""
    add_debug("Test avec Twelve Data API")
    
    if not api_key:
        add_debug("❌ Pas de clé API fournie")
        return None
    
    try:
        # Test avec un symbole simple
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": "EURUSD",  # Sans slash
            "interval": "1day",   # Intervalle jour au lieu d'heure
            "outputsize": "10",   # Très peu de données
            "apikey": api_key
        }
        
        add_debug(f"URL: {url}")
        add_debug(f"Paramètres: {params}")
        
        response = requests.get(url, params=params, timeout=15)
        add_debug(f"Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            add_debug(f"Clés de réponse: {list(data.keys())}")
            
            # Diagnostic détaillé
            if "status" in data:
                add_debug(f"Status API: {data['status']}")
            if "message" in data:
                add_debug(f"Message API: {data['message']}")
            if "note" in data:
                add_debug(f"Note API: {data['note']}")
            if "values" in data:
                add_debug(f"Nombre de valeurs: {len(data['values']) if data['values'] else 0}")
                if data['values']:
                    add_debug(f"Première valeur: {data['values'][0]}")
            
            return data
        else:
            add_debug(f"❌ Erreur HTTP: {response.status_code}")
            add_debug(f"Réponse: {response.text[:200]}")
            return None
            
    except Exception as e:
        add_debug(f"❌ Exception: {e}")
        return None

# Générateur de données fictives pour test
def generate_fake_data():
    """Génère des données fictives pour tester la logique"""
    add_debug("Génération de données fictives")
    
    dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
    np.random.seed(42)  # Pour des résultats reproductibles
    
    # Simulation d'un prix qui évolue
    base_price = 1.1000
    price_changes = np.random.normal(0, 0.002, 50).cumsum()
    closes = base_price + price_changes
    
    # OHLC cohérent
    opens = np.roll(closes, 1)
    opens[0] = base_price
    
    highs = closes + np.random.uniform(0, 0.003, 50)
    lows = closes - np.random.uniform(0, 0.003, 50)
    
    df = pd.DataFrame({
        'Open': opens,
        'High': highs,
        'Low': lows,
        'Close': closes
    }, index=dates)
    
    add_debug(f"Données fictives générées: {len(df)} lignes")
    return df

def calculate_simple_signals(df):
    """Calcul de signaux très simples"""
    if df is None or len(df) == 0:
        add_debug("❌ Pas de données pour calculer les signaux")
        return None
    
    add_debug(f"Calcul des signaux sur {len(df)} lignes")
    
    try:
        signals = {}
        bull = bear = 0
        
        # 1. Tendance simple (prix actuel vs prix d'il y a 5 jours)
        if len(df) >= 6:
            current = df['Close'].iloc[-1]
            past = df['Close'].iloc[-6]
            if current > past:
                bull += 1
                signals['Trend_5d'] = "▲"
                add_debug(f"Tendance 5j: Haussière ({current:.4f} > {past:.4f})")
            else:
                bear += 1
                signals['Trend_5d'] = "▼"
                add_debug(f"Tendance 5j: Baissière ({current:.4f} < {past:.4f})")
        
        # 2. Moyenne mobile simple
        if len(df) >= 10:
            ma_10 = df['Close'].rolling(10).mean().iloc[-1]
            current = df['Close'].iloc[-1]
            if current > ma_10:
                bull += 1
                signals['MA_10'] = "▲"
                add_debug(f"Prix vs MA10: Haussier ({current:.4f} > {ma_10:.4f})")
            else:
                bear += 1
                signals['MA_10'] = "▼"
                add_debug(f"Prix vs MA10: Baissier ({current:.4f} < {ma_10:.4f})")
        
        # 3. Volatilité (range des 5 derniers jours)
        if len(df) >= 5:
            recent_high = df['High'].tail(5).max()
            recent_low = df['Low'].tail(5).min()
            current = df['Close'].iloc[-1]
            position = (current - recent_low) / (recent_high - recent_low) if recent_high > recent_low else 0.5
            
            if position > 0.7:
                bull += 1
                signals['Position'] = "▲"
                add_debug(f"Position dans range: Haute ({position:.2f})")
            elif position < 0.3:
                bear += 1
                signals['Position'] = "▼"
                add_debug(f"Position dans range: Basse ({position:.2f})")
            else:
                signals['Position'] = "—"
                add_debug(f"Position dans range: Neutre ({position:.2f})")
        
        confluence = max(bull, bear)
        direction = "HAUSSIER" if bull > bear else "BAISSIER" if bear > bull else "NEUTRE"
        
        stars_map = {3: "⭐⭐⭐", 2: "⭐⭐", 1: "⭐", 0: "WAIT"}
        stars = stars_map.get(confluence, "WAIT")
        
        result = {
            "confluence": confluence,
            "direction": direction,
            "stars": stars,
            "signals": signals,
            "price": f"{df['Close'].iloc[-1]:.4f}",
            "bull_count": bull,
            "bear_count": bear
        }
        
        add_debug(f"Signaux calculés: {bull} haussiers, {bear} baissiers")
        return result
        
    except Exception as e:
        add_debug(f"❌ Erreur calcul signaux: {e}")
        return None

# Interface utilisateur
col1, col2 = st.columns([1, 2])

with col1:
    st.header("🔧 Tests de Diagnostic")
    
    # Test API gratuite
    if st.button("🧪 Test API Gratuite"):
        debug_info.clear()
        st.markdown("### Test avec API gratuite")
        result = test_free_api()
        if result:
            st.success("✅ API gratuite fonctionne!")
            st.json(result)
        
    # Test Twelve Data
    api_key = st.text_input("Clé API Twelve Data", type="password")
    if st.button("🧪 Test Twelve Data") and api_key:
        debug_info.clear()
        st.markdown("### Test Twelve Data")
        result = test_twelve_data(api_key)
        if result:
            st.json(result)
    
    # Test avec données fictives
    if st.button("🧪 Test Logique (Données Fictives)"):
        debug_info.clear()
        st.markdown("### Test avec données fictives")
        fake_data = generate_fake_data()
        signals = calculate_simple_signals(fake_data)
        
        if signals:
            st.success("✅ Logique de calcul fonctionne!")
            st.json(signals)
            
            # Affichage des données
            st.line_chart(fake_data['Close'])
        else:
            st.error("❌ Problème dans la logique")

with col2:
    st.header("📋 Log de Debug")
    
    if debug_info:
        for info in debug_info:
            st.text(info)
    else:
        st.info("Cliquez sur un bouton de test pour voir les logs")

# Section d'aide
st.markdown("---")
with st.expander("🆘 Guide de Diagnostic"):
    st.markdown("""
    **Étapes de diagnostic :**
    
    1. **Test API Gratuite** : Vérifie que votre connexion internet fonctionne
    2. **Test Twelve Data** : Vérifie spécifiquement votre clé API
    3. **Test Logique** : Vérifie que le calcul des signaux fonctionne
    
    **Problèmes courants :**
    - **Clé API invalide** : Vérifiez sur twelvedata.com
    - **Quota dépassé** : Plan gratuit = 800 appels/jour
    - **Symboles incorrects** : Essayez "EURUSD" au lieu de "EUR/USD"
    - **Interval non supporté** : Essayez "1day" au lieu de "1h"
    
    **Messages d'erreur typiques :**
    - `"status": "error"` : Problème avec la requête
    - `"note": "Thank you..."` : Limite de quota atteinte
    - `HTTP 429` : Trop de requêtes par minute
    - `HTTP 401` : Clé API invalide
    """)

# Test automatique au lancement
if 'auto_test_done' not in st.session_state:
    st.session_state.auto_test_done = True
    st.info("🚀 Lancement du test automatique...")
    
    # Test de connectivité basique
    debug_info.clear()
    add_debug("Test automatique de connectivité")
    
    try:
        response = requests.get("https://httpbin.org/get", timeout=5)
        if response.status_code == 200:
            add_debug("✅ Connexion internet OK")
        else:
            add_debug("❌ Problème de connexion")
    except:
        add_debug("❌ Pas de connexion internet")
    
    # Affichage des infos système
    add_debug(f"Streamlit version: {st.__version__}")
    add_debug(f"Pandas version: {pd.__version__}")
    add_debug("Test automatique terminé")
