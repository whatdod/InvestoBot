"""
InvestoBot — Analisi mensile investimenti
Eseguito da GitHub Actions il 1° del mese, o manualmente.
Modalità: mensile / analisi / portafoglio
"""
import os, time, json, requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_IDS = [
    os.environ.get("CHAT_ID", "43443426"),
    "495866880",
]
BUDGET   = 20.0
MODALITA = os.environ.get("MODALITA", "mensile")

# ── PORTAFOGLIO ATTUALE ───────────────────────────────────────────────────────
PORTAFOGLIO_DEFAULT = [
    {"ticker":"EUNL.L","display":"EUNL","nome":"iShares MSCI World Acc",      "investito":19.59},
    {"ticker":"VUSA.L","display":"VUSA","nome":"Vanguard S&P 500 Dist",        "investito":10.33},
    {"ticker":"JEDI.L","display":"JEDI","nome":"VanEck Space Innovators",      "investito":7.60},
    {"ticker":"NVDA",  "display":"NVDA","nome":"Nvidia",                       "investito":6.69},
    {"ticker":"VUAA.L","display":"VUAA","nome":"Vanguard S&P 500 Acc",         "investito":5.18},
    {"ticker":"V80A.L","display":"V80A","nome":"Vanguard LifeStrategy 80%",    "investito":4.87},
    {"ticker":"DFEN.L","display":"DFEN","nome":"VanEck Defense ETF",           "investito":4.61},
    {"ticker":"CPRX",  "display":"CPRX","nome":"Catalyst Pharmaceuticals",     "investito":1.57},
]

TICKER_MAP = {
    "EUNL":"EUNL.L","VUSA":"VUSA.L","JEDI":"JEDI.L","VUAA":"VUAA.L",
    "V80A":"V80A.L","DFEN":"DFEN.L","VWRL":"VWRL.L","AGGG":"AGGG.L",
    "IGLO":"IGLO.L","SGLD":"SGLD.L","NVDA":"NVDA","CPRX":"CPRX",
}

CANDIDATI = [
    {"ticker":"VUSA.L","display":"VUSA","nome":"Vanguard S&P 500 Dist",        "cat":"etf",  "note":"Già in portafoglio — accumula"},
    {"ticker":"EUNL.L","display":"EUNL","nome":"iShares MSCI World Acc",       "cat":"etf",  "note":"Già in portafoglio — il più diversificato"},
    {"ticker":"VUAA.L","display":"VUAA","nome":"Vanguard S&P 500 Acc",         "cat":"etf",  "note":"Già in portafoglio — accumula dividendi"},
    {"ticker":"VWRL.L","display":"VWRL","nome":"Vanguard FTSE All-World",      "cat":"etf",  "note":"Nuovo — include emergenti"},
    {"ticker":"AGGG.L","display":"AGGG","nome":"iShares Core Global Agg Bond", "cat":"bond", "note":"Nuovo — obbligazioni globali, rifugio"},
    {"ticker":"IGLO.L","display":"IGLO","nome":"iShares Global Govt Bond",     "cat":"bond", "note":"Nuovo — titoli stato globali"},
    {"ticker":"SGLD.L","display":"SGLD","nome":"Invesco Physical Gold ETC",    "cat":"gold", "note":"Nuovo — oro fisico, rifugio in crisi"},
]

CONTESTO_GEO = [
    "• Crisi Iran: petrolio Brent ~$93, pesa su mercati azionari nel breve.",
    "• Inflazione EU in calo → BCE potrebbe tagliare tassi Q3 2026.",
    "• S&P 500 in zona massimi storici, sostenuto da utili tech.",
    "• ETF difesa (DFEN) e spazio (JEDI) volatili dopo forti rialzi YTD.",
]

PORTFOLIO_FILE = "portafoglio.json"

def load_portafoglio():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE) as f:
                return json.load(f)
        except:
            pass
    return PORTAFOGLIO_DEFAULT

def save_portafoglio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ── ANALISI MERCATO ───────────────────────────────────────────────────────────
def scarica(ticker):
    try:
        df = yf.download(ticker, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 15:
            return None
        return df.dropna()
    except:
        return None

def calcola_rsi(close, n=14):
    d = close.diff()
    g = d.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-d).clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    rs = g / l.replace(0, np.nan)
    v  = float((100 - 100/(1+rs)).iloc[-1])
    return round(v, 1) if not np.isnan(v) else 50.0

def calcola_trend(close):
    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    pr    = float(close.iloc[-1])
    chg1m = (pr - float(close.iloc[-22])) / float(close.iloc[-22]) * 100 if len(close)>=22 else 0
    if pr > ema20 and chg1m > 2:  return "rialzista"
    if pr < ema20 and chg1m < -2: return "ribassista"
    return "laterale"

def analizza(ticker):
    df = scarica(ticker)
    if df is None:
        return {"ok":False,"prezzo":0,"chg":0,"chg_1m":0,"rsi":50,"trend":"n/d"}
    close = df["Close"].squeeze()
    pr    = round(float(close.iloc[-1]), 2)
    pr_i  = round(float(close.iloc[-2]), 2)
    chg   = round((pr-pr_i)/pr_i*100, 2) if pr_i else 0
    chg1m = round((pr-float(close.iloc[-22]))/float(close.iloc[-22])*100,2) if len(close)>=22 else 0
    return {"ok":True,"prezzo":pr,"chg":chg,"chg_1m":chg1m,
            "rsi":calcola_rsi(close),"trend":calcola_trend(close)}

def genera_consigli(portafoglio, analisi_cand):
    scored = []
    for c, a in zip(CANDIDATI, analisi_cand):
        if not a["ok"]: continue
        sc = 0
        if a["rsi"]<35: sc+=40
        elif a["rsi"]<45: sc+=20
        elif a["rsi"]<55: sc+=10
        if a["trend"]=="rialzista": sc+=20
        elif a["trend"]=="laterale": sc+=10
        if a["chg_1m"]<-5: sc+=20
        elif a["chg_1m"]<0: sc+=10
        in_port = any(p["display"]==c["display"] for p in portafoglio)
        if in_port: sc+=15
        if c["cat"] in ("bond","gold"): sc+=10
        scored.append({**c,**a,"score":sc,"in_port":in_port})
    top = sorted(scored, key=lambda x: x["score"], reverse=True)[:3]
    if not top: return []
    tot = sum(t["score"] for t in top) or 1
    rim = BUDGET
    out = []
    for t in top:
        q = max(3.0, min(round(BUDGET*t["score"]/tot, 2), 12.0, rim))
        if rim < 3: break
        rim -= q
        out.append({**t,"importo":q})
    if rim > 0.5 and out:
        out[0]["importo"] = round(out[0]["importo"]+rim, 2)
    return out

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send(text, cid):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":cid,"text":text,"parse_mode":"HTML"},
            timeout=15
        ).raise_for_status()
        print(f"✅ Inviato a {cid}")
    except Exception as e:
        print(f"❌ {cid}: {e}")

def send_tutti(text):
    for cid in CHAT_IDS:
        send(text, cid)
        time.sleep(0.5)

# ── MODALITÀ: AGGIORNA PORTAFOGLIO ───────────────────────────────────────────
def modalita_portafoglio():
    raw = os.environ.get("PORTFOLIO_DATA", "")
    if not raw:
        send_tutti("❌ Nessun dato portafoglio ricevuto.")
        return
    nuovi = []
    for coppia in raw.split(","):
        try:
            display, valore = coppia.strip().split(":")
            display = display.upper().strip()
            valore  = float(valore.strip())
            ticker  = TICKER_MAP.get(display, display)
            nome    = next((c["nome"] for c in CANDIDATI if c["display"]==display),
                          next((p["nome"] for p in PORTAFOGLIO_DEFAULT if p["display"]==display), display))
            nuovi.append({"ticker":ticker,"display":display,"nome":nome,"investito":valore})
        except:
            pass
    if not nuovi:
        send_tutti("❌ Formato non valido. Usa: TICKER:VALORE,TICKER:VALORE\nEs: EUNL:19.59,VUSA:10.33")
        return
    save_portafoglio(nuovi)
    msg = "✅ <b>Portafoglio aggiornato!</b>\n\n"
    tot = 0.0
    for p in nuovi:
        msg += f"  • {p['display']}: €{p['investito']:.2f}\n"
        tot += p["investito"]
    msg += f"\n💼 Totale investito: €{tot:.2f}"
    send_tutti(msg)

# ── MODALITÀ: ANALISI ON-DEMAND ───────────────────────────────────────────────
def modalita_analisi():
    portafoglio = load_portafoglio()
    send_tutti(f"⏳ <b>Analisi in corso...</b>\nScarico dati reali da Yahoo Finance.")
    ap = []
    for p in portafoglio:
        print(f"  → {p['display']}")
        ap.append({**p, **analizza(p["ticker"])})
        time.sleep(1.5)
    ac = []
    for c in CANDIDATI:
        print(f"  → {c['display']}")
        ac.append(analizza(c["ticker"]))
        time.sleep(1.5)
    msg = f"📊 <b>Analisi mercati — {datetime.now().strftime('%d/%m/%Y %H:%M')}</b>\n\n"
    msg += "💼 <b>Il tuo portafoglio ora:</b>\n"
    for a in ap:
        if not a["ok"]: continue
        s = f"+{a['chg']}%" if a["chg"]>=0 else f"{a['chg']}%"
        e = "🟢" if a["chg"]>=0 else "🔴"
        msg += f"  {e} <b>{a['display']}</b>: €{a['prezzo']:.2f} ({s}) · RSI {a['rsi']}\n"
    msg += "\n🎯 <b>Segnali candidati:</b>\n"
    for c, a in zip(CANDIDATI, ac):
        if not a["ok"]: continue
        e = "🟢" if a["rsi"]<40 else "🟡" if a["rsi"]<55 else "⚪"
        tr = "📈" if a["trend"]=="rialzista" else "📉" if a["trend"]=="ribassista" else "➡️"
        msg += f"  {e} {c['display']}: €{a['prezzo']:.2f} · RSI {a['rsi']} · {tr}\n"
    msg += "\n📝 Per il consiglio completo esegui <b>Run workflow → mensile</b> su GitHub."
    send_tutti(msg)

# ── MODALITÀ: CONSIGLIO MENSILE ───────────────────────────────────────────────
def modalita_mensile():
    portafoglio = load_portafoglio()
    now   = datetime.now()
    mesi  = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
              "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    mese  = mesi[now.month-1]
    anno  = now.year
    print(f"🚀 Consiglio mensile {mese} {anno}")
    ap = []
    for p in portafoglio:
        print(f"  → {p['display']}")
        ap.append({**p, **analizza(p["ticker"])})
        time.sleep(1.5)
    ac = []
    for c in CANDIDATI:
        print(f"  → {c['display']}")
        ac.append(analizza(c["ticker"]))
        time.sleep(1.5)
    consigli = genera_consigli(portafoglio, ac)
    msg  = f"📅 <b>InvestoBot — Consiglio {mese} {anno}</b>\n\n"
    msg += "💼 <b>Situazione portafoglio:</b>\n"
    tot_inv = tot_att = 0.0
    for a in ap:
        if not a["ok"]: continue
        s = f"+{a['chg']}%" if a["chg"]>=0 else f"{a['chg']}%"
        e = "🟢" if a["chg"]>=0 else "🔴"
        msg += f"  {e} {a['display']}: €{a['prezzo']:.2f} ({s}) · RSI {a['rsi']}\n"
        tot_inv += a["investito"]
        tot_att += a["prezzo"] if a["prezzo"]>0 else a["investito"]
    pnl = tot_att - tot_inv
    e_t = "🟢" if pnl>=0 else "🔴"
    msg += f"  {e_t} P&amp;L totale: {'+'if pnl>=0 else ''}€{pnl:.2f}\n\n"
    msg += "🌍 <b>Contesto mercati:</b>\n"
    for r in CONTESTO_GEO: msg += f"  {r}\n"
    msg += f"\n💰 <b>Come investire €{BUDGET:.0f} questo mese:</b>\n\n"
    if consigli:
        for i, c in enumerate(consigli, 1):
            ip = "✅ già in portafoglio" if c["in_port"] else "🆕 nuovo"
            tr = "📈" if c["trend"]=="rialzista" else "📉" if c["trend"]=="ribassista" else "➡️"
            msg += (
                f"<b>{i}. {c['nome']} ({c['display']})</b>\n"
                f"   💶 <b>Investi: €{c['importo']:.2f}</b> su Revolut\n"
                f"   {ip} · {c['cat'].upper()}\n"
                f"   {tr} Trend: {c['trend']} · RSI: {c['rsi']} · €{c['prezzo']:.2f}\n"
                f"   📌 {c['note']}\n\n"
            )
        msg += f"Totale: <b>€{sum(c['importo'] for c in consigli):.2f}</b> / €{BUDGET:.0f}\n\n"
    else:
        msg += "⚠️ Dati non disponibili. Riprova con modalita=analisi.\n\n"
    msg += (
        "📝 Dopo ogni acquisto aggiorna il portafoglio:\n"
        "GitHub → <b>Actions → Run workflow → modalita: portafoglio</b>\n\n"
        "⚠️ <i>Non è consulenza finanziaria.</i>"
    )
    send_tutti(msg)
    print("✅ Consiglio mensile inviato!")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Modalità: {MODALITA}")
    if MODALITA == "analisi":
        modalita_analisi()
    elif MODALITA == "portafoglio":
        modalita_portafoglio()
    else:
        modalita_mensile()
