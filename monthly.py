"""
InvestoBot — Analisi mensile
Eseguito da GitHub Actions il primo di ogni mese.
Analizza mercati reali, considera il portafoglio attuale,
e manda un consiglio su come distribuire i 20€ mensili.
"""
import os, time, requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_IDS = [
    os.environ.get("CHAT_ID", "43443426"),
    "495866880",
]
BUDGET = 20.0

# ── PORTAFOGLIO ATTUALE (aggiorna questi dati quando cambia) ──────────────────
PORTAFOGLIO = [
    {"ticker": "EUNL.L", "display": "EUNL", "nome": "iShares MSCI World Acc",       "investito": 19.59},
    {"ticker": "VUSA.L", "display": "VUSA", "nome": "Vanguard S&P 500 Dist",         "investito": 10.33},
    {"ticker": "JEDI.L", "display": "JEDI", "nome": "VanEck Space Innovators",       "investito": 7.60},
    {"ticker": "NVDA",   "display": "NVDA", "nome": "Nvidia",                        "investito": 6.69},
    {"ticker": "VUAA.L", "display": "VUAA", "nome": "Vanguard S&P 500 Acc",          "investito": 5.18},
    {"ticker": "V80A.L", "display": "V80A", "nome": "Vanguard LifeStrategy 80%",     "investito": 4.87},
    {"ticker": "DFEN.L", "display": "DFEN", "nome": "VanEck Defense ETF",            "investito": 4.61},
    {"ticker": "CPRX",   "display": "CPRX", "nome": "Catalyst Pharmaceuticals",      "investito": 1.57},
]

# ── CANDIDATI ETF/OBBLIGAZIONI per nuovi acquisti (basso rischio) ─────────────
CANDIDATI = [
    {"ticker": "VUSA.L", "display": "VUSA", "nome": "Vanguard S&P 500 Dist",         "cat": "etf",  "note": "Già in portafoglio — accumula"},
    {"ticker": "EUNL.L", "display": "EUNL", "nome": "iShares MSCI World Acc",        "cat": "etf",  "note": "Già in portafoglio — il più diversificato"},
    {"ticker": "VUAA.L", "display": "VUAA", "nome": "Vanguard S&P 500 Acc",          "cat": "etf",  "note": "Già in portafoglio — accumula dividendi"},
    {"ticker": "VWRL.L", "display": "VWRL", "nome": "Vanguard FTSE All-World",       "cat": "etf",  "note": "Nuovo — include emergenti"},
    {"ticker": "AGGG.L", "display": "AGGG", "nome": "iShares Core Global Agg Bond",  "cat": "bond", "note": "Nuovo — obbligazioni globali, rifugio"},
    {"ticker": "IGLO.L", "display": "IGLO", "nome": "iShares Global Govt Bond",      "cat": "bond", "note": "Nuovo — titoli stato globali, basso rischio"},
    {"ticker": "SGLD.L", "display": "SGLD", "nome": "Invesco Physical Gold ETC",     "cat": "gold", "note": "Nuovo — oro fisico, rifugio in crisi"},
]

# ── ANALISI DATI REALI ────────────────────────────────────────────────────────
def scarica(ticker: str, periodo="3mo") -> pd.DataFrame | None:
    try:
        df = yf.download(ticker, period=periodo, interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 20:
            return None
        return df.dropna()
    except:
        return None

def rsi(close: pd.Series, n=14) -> float:
    d = close.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    rs = g / l.replace(0, np.nan)
    v  = float((100 - 100/(1+rs)).iloc[-1])
    return round(v, 1) if not np.isnan(v) else 50.0

def trend(close: pd.Series) -> str:
    if len(close) < 20: return "neutro"
    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    pr    = float(close.iloc[-1])
    chg1m = (pr - float(close.iloc[-22])) / float(close.iloc[-22]) * 100 if len(close) >= 22 else 0
    if pr > ema20 and chg1m > 2:  return "rialzista"
    if pr < ema20 and chg1m < -2: return "ribassista"
    return "laterale"

def analizza_asset(ticker: str) -> dict:
    df = scarica(ticker)
    if df is None:
        return {"ok": False, "rsi": 50, "trend": "n/d", "chg": 0, "prezzo": 0}
    close  = df["Close"].squeeze()
    pr     = round(float(close.iloc[-1]), 2)
    pr_ieri= round(float(close.iloc[-2]), 2)
    chg    = round((pr - pr_ieri) / pr_ieri * 100, 2) if pr_ieri else 0
    chg_1m = round((pr - float(close.iloc[-22])) / float(close.iloc[-22]) * 100, 2) if len(close)>=22 else 0
    return {
        "ok": True, "prezzo": pr, "chg": chg, "chg_1m": chg_1m,
        "rsi": rsi(close), "trend": trend(close),
    }

# ── CONTESTO GEOPOLITICO (aggiornato manualmente ogni mese nel codice) ─────────
# In GitHub Actions non c'è accesso al web in modo affidabile,
# quindi il contesto è scritto qui e va aggiornato quando si fa push.
CONTESTO_GEO = """
• Crisi energetica Iran: petrolio Brent ~$93, gas GNL sotto pressione. 
  Favorisce oro e difesa, pesa sui mercati azionari nel breve.
• Inflazione EU in calo ma ancora sopra target BCE (2,4%). 
  Tassi potrebbero scendere nel Q3 2026 → positivo per obbligazioni.
• S&P 500 in zona massimi storici (7.500+ punti). 
  Mercato USA caro ma sostenuto da utili tech solidi.
• ETF difesa (DFEN) e spazio (JEDI) volatili dopo forti rialzi YTD.
"""

# ── LOGICA CONSIGLIO ──────────────────────────────────────────────────────────
def genera_consiglio(analisi_port: list, analisi_cand: list) -> list:
    """
    Restituisce una lista di consigli di acquisto con importi.
    Logica: favorisce asset con RSI basso, trend positivo, già in portafoglio.
    """
    consigli = []

    # Punteggio per ogni candidato
    scored = []
    for c, a in zip(CANDIDATI, analisi_cand):
        if not a["ok"]: continue
        score = 0
        # RSI basso = possibile sconto
        if a["rsi"] < 35:   score += 40
        elif a["rsi"] < 45: score += 20
        elif a["rsi"] < 55: score += 10
        # Trend
        if a["trend"] == "rialzista": score += 20
        elif a["trend"] == "laterale": score += 10
        # Calo ultimo mese = possibile sconto (DCA)
        if a["chg_1m"] < -5:  score += 20
        elif a["chg_1m"] < 0: score += 10
        # Bonus se già in portafoglio (familiarità, DCA)
        in_port = any(p["display"] == c["display"] for p in PORTAFOGLIO)
        if in_port: score += 15
        # Bonus obbligazioni/oro in contesto di crisi
        if c["cat"] in ("bond", "gold"): score += 10
        scored.append({**c, **a, "score": score, "in_port": in_port})

    # Top 3 per score
    top = sorted(scored, key=lambda x: x["score"], reverse=True)[:3]
    if not top: return []

    # Distribuisce 20€ in base al punteggio relativo
    tot_score = sum(t["score"] for t in top) or 1
    budget_rimasto = BUDGET
    for i, t in enumerate(top):
        quota = round(BUDGET * t["score"] / tot_score, 2)
        quota = max(3.0, min(quota, 12.0))
        if budget_rimasto < 3: break
        quota = min(quota, budget_rimasto)
        budget_rimasto -= quota
        consigli.append({**t, "importo": quota})

    # Se rimangono spiccioli, aggiungili al primo consiglio
    if budget_rimasto > 0.5 and consigli:
        consigli[0]["importo"] = round(consigli[0]["importo"] + budget_rimasto, 2)

    return consigli

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send(text: str, cid: str):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=15
        )
        r.raise_for_status()
        print(f"✅ Inviato a {cid}")
    except Exception as e:
        print(f"❌ Errore invio a {cid}: {e}")

def send_photo(url: str, caption: str, cid: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": cid, "photo": url, "caption": caption, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
        print(f"✅ Foto inviata a {cid}")
    except Exception as e:
        print(f"❌ Errore foto a {cid}: {e}")

def get_cat() -> str | None:
    try:
        r = requests.get("https://api.thecatapi.com/v1/images/search", timeout=10)
        return r.json()[0]["url"]
    except:
        return None

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    now    = datetime.now()
    mesi   = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
               "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    mese   = mesi[now.month - 1]
    anno   = now.year

    print(f"🚀 InvestoBot analisi mensile — {now.strftime('%d/%m/%Y %H:%M')}")
    print("Scarico dati portafoglio...")

    # Analisi portafoglio attuale
    analisi_port = []
    for p in PORTAFOGLIO:
        print(f"  → {p['display']}...")
        a = analizza_asset(p["ticker"])
        analisi_port.append({**p, **a})
        time.sleep(1.5)

    print("Scarico dati candidati...")
    analisi_cand = []
    for c in CANDIDATI:
        print(f"  → {c['display']}...")
        a = analizza_asset(c["ticker"])
        analisi_cand.append(a)
        time.sleep(1.5)

    # Genera consigli
    consigli = genera_consiglio(analisi_port, analisi_cand)

    # ── COSTRUISCE IL MESSAGGIO ───────────────────────────────────────────────
    msg = (
        f"📅 <b>InvestoBot — Consiglio {mese} {anno}</b>\n"
        f"🐱 Fred puzza e pure Dod\n\n"
    )

    # Stato portafoglio
    msg += "💼 <b>Il tuo portafoglio questo mese:</b>\n"
    tot_inv = tot_att = 0.0
    for a in analisi_port:
        if not a["ok"]: continue
        pnl     = round(a["prezzo"] - a["investito"] / max(a["investito"],1), 2) if a["investito"] else 0
        chg_s   = f"+{a['chg']}%" if a["chg"] >= 0 else f"{a['chg']}%"
        emoji   = "🟢" if a["chg"] >= 0 else "🔴"
        msg += f"  {emoji} {a['display']}: €{a['prezzo']:.2f} ({chg_s}) · RSI {a['rsi']}\n"
    msg += "\n"

    # Contesto geopolitico
    msg += "🌍 <b>Contesto mercati:</b>\n"
    for riga in CONTESTO_GEO.strip().split("\n"):
        if riga.strip():
            msg += f"{riga.strip()}\n"
    msg += "\n"

    # Consigli di acquisto
    msg += f"💰 <b>Come investire i tuoi €{BUDGET:.0f} questo mese:</b>\n\n"
    if consigli:
        for i, c in enumerate(consigli, 1):
            in_p  = "✅ già in portafoglio" if c["in_port"] else "🆕 nuovo"
            trend_e = "📈" if c["trend"] == "rialzista" else "📉" if c["trend"] == "ribassista" else "➡️"
            msg += (
                f"<b>{i}. {c['nome']} ({c['display']})</b>\n"
                f"   💶 <b>Investi: €{c['importo']:.2f}</b> su Revolut\n"
                f"   {in_p} · {c['cat'].upper()}\n"
                f"   {trend_e} Trend: {c['trend']} · RSI: {c['rsi']} · Prezzo: €{c['prezzo']:.2f}\n"
                f"   📌 {c['note']}\n\n"
            )
        tot_consigliato = sum(c["importo"] for c in consigli)
        msg += f"Totale consigliato: <b>€{tot_consigliato:.2f}</b> / €{BUDGET:.0f}\n\n"
    else:
        msg += "Dati non disponibili questa settimana. Riprova con /analisi.\n\n"

    msg += (
        "📝 Dopo ogni acquisto scrivi su Telegram:\n"
        "<code>/comprato TICKER IMPORTO</code>\n\n"
        "⚠️ <i>Non è consulenza finanziaria. Investi con consapevolezza.</i>"
    )

    # Invia a tutti gli utenti
    cat_url = get_cat()
    for cid in CHAT_IDS:
        if cat_url:
            send_photo(cat_url, f"🐱 Buon {mese} {anno}! Il consiglio mensile è qui sotto 👇", cid)
            time.sleep(1)
        send(msg, cid)
        time.sleep(1)

    print("✅ Analisi mensile completata e inviata!")

if __name__ == "__main__":
    main()
