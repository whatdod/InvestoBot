"""
InvestoBot v5
- Dati reali via Alpha Vantage (più affidabile in cloud)
- Budget separato per utente
- Notifiche automatiche live ogni ora (solo segnali reali)
- Indicatori: RSI, MACD, EMA50/200, Bollinger, OBV, Golden/Death Cross
"""
import os, json, time, logging
import numpy as np
import pandas as pd
import requests
from datetime import datetime, time as dtime
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
AV_KEY         = os.environ.get("AV_KEY", "YJ6NGFMM6LQB6192")  # Alpha Vantage API key
BUDGET_MENSILE = 20.0
PATRIMONIO_FILE = "patrimonio.json"

# Chat ID → nome utente (aggiungi qui nuovi utenti)
UTENTI = {
    int(os.environ.get("CHAT_ID", 0)): "Utente 1",
    495866880: "Utente 2",
}

# ── ASSET UNIVERSE ────────────────────────────────────────────────────────────
# Alpha Vantage usa ticker US. Per ETF europei usiamo i loro equivalenti
# o il ticker con suffisso .LON per London Stock Exchange
# Ticker US compatibili con Alpha Vantage piano gratuito
# Sono gli equivalenti americani degli stessi ETF che hai su Revolut
ASSETS = [
    {"ticker": "VOO",   "display": "VOO",  "nome": "Vanguard S&P 500 ETF (=VUSA)",       "cat": "etf"},
    {"ticker": "URTH",  "display": "URTH", "nome": "iShares MSCI World (=IWDA)",          "cat": "etf"},
    {"ticker": "VT",    "display": "VT",   "nome": "Vanguard All-World (=VWRL)",           "cat": "etf"},
    {"ticker": "EEM",   "display": "EEM",  "nome": "iShares Emerging Markets (=EIMI)",     "cat": "etf"},
    {"ticker": "GLD",   "display": "GLD",  "nome": "SPDR Gold Shares (=SGLD)",             "cat": "gold"},
    {"ticker": "AGG",   "display": "AGG",  "nome": "iShares Core US Aggregate Bond (bond)","cat": "bond"},
    {"ticker": "BND",   "display": "BND",  "nome": "Vanguard Total Bond Market (bond)",    "cat": "bond"},
]

# Cache locale per evitare troppe chiamate API (Alpha Vantage: 25 call/giorno gratis)
_cache: dict = {}
CACHE_TTL = 3600  # secondi — aggiorna al massimo ogni ora

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 1 — DATI REALI (ALPHA VANTAGE)
# ═══════════════════════════════════════════════════════════════════════════════

def scarica_dati_av(ticker: str) -> pd.DataFrame | None:
    """
    Scarica dati giornalieri da Alpha Vantage.
    Usa cache TTL per non superare il limite gratuito (25 call/giorno).
    """
    now_ts = time.time()
    if ticker in _cache and now_ts - _cache[ticker]["ts"] < CACHE_TTL:
        log.info(f"Cache hit: {ticker}")
        return _cache[ticker]["df"]

    key = AV_KEY
    if not key:
        log.error("AV_KEY non trovata nelle variabili d'ambiente!")
        return None

    log.info(f"Chiamo Alpha Vantage per {ticker} con chiave {key[:6]}...")
    url = (
        f"https://www.alphavantage.co/query"
        f"?function=TIME_SERIES_DAILY"
        f"&symbol={ticker}&outputsize=compact&apikey={key}"
    )
    try:
        r    = requests.get(url, timeout=20)
        data = r.json()
        log.info(f"AV risposta chiavi: {list(data.keys())}")

        # Gestione rate limit (5 call/min nel piano free)
        if "Note" in data:
            log.warning(f"AV rate limit: {data['Note']}")
            time.sleep(15)
            return None

        if "Error Message" in data:
            log.error(f"AV errore per {ticker}: {data['Error Message']}")
            return None

        key_ts = "Time Series (Daily)"
        if key_ts not in data:
            log.warning(f"Nessuna serie per {ticker}. Chiavi: {list(data.keys())}")
            return None

        ts = data[key_ts]
        df = pd.DataFrame.from_dict(ts, orient="index").sort_index()
        df.index = pd.to_datetime(df.index)
        df = df.rename(columns={
            "1. open":   "Open",
            "2. high":   "High",
            "3. low":    "Low",
            "4. close":  "Close",
            "5. volume": "Volume",
        })
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(inplace=True)

        if len(df) < 30:
            log.warning(f"Dati insufficienti per {ticker}: {len(df)} righe")
            return None

        _cache[ticker] = {"df": df, "ts": now_ts}
        log.info(f"OK {ticker}: {len(df)} sessioni, ultimo prezzo {float(df['Close'].iloc[-1]):.2f}")
        return df

    except Exception as e:
        log.error(f"Eccezione Alpha Vantage {ticker}: {e}")
        return None

# ── INDICATORI ────────────────────────────────────────────────────────────────

def calcola_rsi(close: pd.Series, n: int = 14) -> float:
    delta = close.diff()
    g = delta.clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    l = (-delta).clip(lower=0).ewm(com=n-1, min_periods=n).mean()
    rs = g / l.replace(0, np.nan)
    return round(float((100 - 100/(1+rs)).iloc[-1]), 1)

def calcola_macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    isto  = macd - sig
    return round(float(macd.iloc[-1]),4), round(float(sig.iloc[-1]),4), round(float(isto.iloc[-1]),4)

def calcola_ema(close: pd.Series, span: int) -> float | None:
    if len(close) < span: return None
    return round(float(close.ewm(span=span, adjust=False).mean().iloc[-1]), 4)

def calcola_bollinger(close: pd.Series, n: int = 20):
    sma = close.rolling(n).mean()
    std = close.rolling(n).std()
    return round(float(sma.iloc[-1]),4), round(float((sma+2*std).iloc[-1]),4), round(float((sma-2*std).iloc[-1]),4)

def calcola_obv(close: pd.Series, volume: pd.Series) -> str:
    direction = np.where(close.diff()>0, volume, np.where(close.diff()<0, -volume, 0))
    obv = pd.Series(direction, index=close.index).cumsum()
    return "positivo" if obv.iloc[-1] > obv.iloc[-10] else "negativo"

def analizza_asset(asset: dict) -> dict | None:
    df = scarica_dati_av(asset["ticker"])
    if df is None: return None

    close  = df["Close"]
    volume = df["Volume"]
    pr     = round(float(close.iloc[-1]), 4)
    pr_ieri = round(float(close.iloc[-2]), 4)
    chg    = round((pr - pr_ieri) / pr_ieri * 100, 2)
    chg_1w = round((pr - float(close.iloc[-6]))  / float(close.iloc[-6])  * 100, 2) if len(close)>=6 else None
    chg_1m = round((pr - float(close.iloc[-22])) / float(close.iloc[-22]) * 100, 2) if len(close)>=22 else None

    rsi              = calcola_rsi(close)
    macd, msig, mist = calcola_macd(close)
    ema50            = calcola_ema(close, 50)
    ema200           = calcola_ema(close, 200)
    bb_mid, bb_up, bb_low = calcola_bollinger(close)
    obv_trend        = calcola_obv(close, volume)

    # Golden / Death Cross
    cross = "n/d"
    if ema50 and ema200:
        e50s = close.ewm(span=50,  adjust=False).mean()
        e200s= close.ewm(span=200, adjust=False).mean()
        if e50s.iloc[-2] <= e200s.iloc[-2] and e50s.iloc[-1] > e200s.iloc[-1]:
            cross = "golden"
        elif e50s.iloc[-2] >= e200s.iloc[-2] and e50s.iloc[-1] < e200s.iloc[-1]:
            cross = "death"
        else:
            cross = "sopra" if ema50 > ema200 else "sotto"

    bb_pos = ("sotto_bassa" if pr <= bb_low else "sopra_alta" if pr >= bb_up else "neutro")

    # ── SCORING ACQUISTO ──────────────────────────────────────────────────────
    sa = 0
    if rsi < 28:   sa += 40
    elif rsi < 35: sa += 25
    elif rsi < 45: sa += 10
    if mist > 0 and macd > msig: sa += 20
    elif mist > 0:               sa += 10
    if bb_pos == "sotto_bassa":  sa += 20
    elif bb_pos == "neutro":     sa +=  5
    if cross == "golden":        sa += 20
    elif cross == "sopra":       sa +=  8
    if obv_trend == "positivo":  sa += 10
    if chg < -2:   sa += 12
    elif chg < -1: sa +=  6
    if asset["cat"] in ("bond","gold"): sa += 8

    # ── SCORING VENDITA ───────────────────────────────────────────────────────
    sv = 0
    if rsi > 72:   sv += 40
    elif rsi > 65: sv += 20
    if mist < 0 and macd < msig: sv += 25
    elif mist < 0:               sv += 10
    if bb_pos == "sopra_alta":   sv += 20
    if cross == "death":         sv += 30
    elif cross == "sotto":       sv += 10
    if obv_trend == "negativo":  sv += 10

    sig_acq  = "BUY"  if sa >= 65 else ("WATCH_BUY"  if sa >= 40 else "HOLD")
    sig_vend = "SELL" if sv >= 60 else ("WATCH_SELL" if sv >= 35 else "HOLD")

    return {
        **asset,
        "prezzo": pr, "chg": chg, "chg_1w": chg_1w, "chg_1m": chg_1m,
        "rsi": rsi, "macd": macd, "macd_sig": msig, "macd_isto": mist,
        "ema50": ema50, "ema200": ema200, "cross": cross,
        "bb_mid": bb_mid, "bb_up": bb_up, "bb_low": bb_low, "bb_pos": bb_pos,
        "obv_trend": obv_trend,
        "score_acq": sa, "score_vend": sv,
        "sig_acq": sig_acq, "sig_vend": sig_vend,
        "aggiornato": datetime.now().strftime("%d/%m %H:%M"),
    }

def analizza_tutti() -> list[dict]:
    out = []
    for a in ASSETS:
        try:
            r = analizza_asset(a)
            if r: out.append(r)
            time.sleep(1.2)   # Alpha Vantage: max ~5 call/minuto nel piano free
        except Exception as e:
            log.error(f"Errore {a['ticker']}: {e}")
    return out

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — BUDGET PER UTENTE
# ═══════════════════════════════════════════════════════════════════════════════

def budget_file(cid: int) -> str:
    return f"budget_{cid}.json"

def load_budget(cid: int) -> dict:
    try:
        with open(budget_file(cid)) as f:
            d = json.load(f)
        now = datetime.now()
        if d.get("month") != now.month or d.get("year") != now.year:
            b = fresh_budget(cid)
            save_budget(cid, b)
            return b
        return d
    except:
        b = fresh_budget(cid)
        save_budget(cid, b)
        return b

def fresh_budget(cid: int) -> dict:
    now = datetime.now()
    return {"cid": cid, "speso": 0.0, "storico": [],
            "month": now.month, "year": now.year, "paused": False}

def save_budget(cid: int, d: dict):
    with open(budget_file(cid), "w") as f:
        json.dump(d, f, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — PATRIMONIO PER UTENTE
# ═══════════════════════════════════════════════════════════════════════════════

def patrimonio_file(cid: int) -> str:
    return f"patrimonio_{cid}.json"

def load_patrimonio(cid: int) -> dict:
    try:
        with open(patrimonio_file(cid)) as f:
            return json.load(f)
    except:
        return {"posizioni": {}, "storico_operazioni": []}

def save_patrimonio(cid: int, d: dict):
    with open(patrimonio_file(cid), "w") as f:
        json.dump(d, f, indent=2)

def registra_acquisto(cid: int, ticker: str, importo: float, prezzo: float) -> float:
    p   = load_patrimonio(cid)
    pos = p["posizioni"]
    meta = next((a for a in ASSETS if a["display"] == ticker), None)
    nome = meta["nome"] if meta else ticker
    quote = round(importo / prezzo, 6) if prezzo > 0 else 0
    if ticker in pos:
        tot_inv   = pos[ticker]["investito"] + importo
        tot_quote = pos[ticker]["quote"] + quote
        pos[ticker].update({
            "prezzo_medio": round(tot_inv / tot_quote, 4),
            "quote":        round(tot_quote, 6),
            "investito":    round(tot_inv, 2),
        })
    else:
        pos[ticker] = {"display": ticker, "nome": nome,
                       "quote": quote, "prezzo_medio": round(prezzo,4), "investito": round(importo,2)}
    p["storico_operazioni"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": "acquisto",
        "ticker": ticker, "quote": quote, "prezzo": prezzo, "importo": round(importo,2), "pnl": None,
    })
    save_patrimonio(cid, p)
    return quote

def registra_vendita(cid: int, ticker: str, importo_eur: float, prezzo: float):
    p   = load_patrimonio(cid)
    pos = p["posizioni"]
    if ticker not in pos or pos[ticker]["quote"] <= 0: return None
    quote_v  = min(round(importo_eur / prezzo, 6), pos[ticker]["quote"])
    imp_reale = round(quote_v * prezzo, 2)
    costo     = round(quote_v * pos[ticker]["prezzo_medio"], 2)
    pnl       = round(imp_reale - costo, 2)
    pos[ticker]["quote"]     = round(pos[ticker]["quote"] - quote_v, 6)
    pos[ticker]["investito"] = round(pos[ticker]["investito"] - costo, 2)
    if pos[ticker]["quote"] <= 0.000001: del pos[ticker]
    p["storico_operazioni"].append({
        "data": datetime.now().strftime("%d/%m/%Y %H:%M"), "tipo": "vendita",
        "ticker": ticker, "quote": quote_v, "prezzo": prezzo, "importo": imp_reale, "pnl": pnl,
    })
    save_patrimonio(cid, p)
    return quote_v, pnl

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def send(text: str, cid):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=10
        ).raise_for_status()
    except Exception as e:
        log.error(f"Send error a {cid}: {e}")

def send_tutti(text: str):
    for cid in UTENTI: send(text, cid)

def fmt_cross(c: str) -> str:
    return {"golden":"🌟 Golden Cross","death":"💀 Death Cross",
            "sopra":"↑ EMA50>200","sotto":"↓ EMA50<200","n/d":"—"}.get(c, c)

def fmt_bb(b: str) -> str:
    return {"sotto_bassa":"⬇️ Sotto banda bassa","sopra_alta":"⬆️ Sopra banda alta",
            "neutro":"↔️ Neutro"}.get(b, b)

def prezzo_live(ticker_display: str) -> float | None:
    meta = next((a for a in ASSETS if a["display"] == ticker_display), None)
    if not meta:
        log.warning(f"Ticker {ticker_display} non trovato in ASSETS")
        return None
    df = scarica_dati_av(meta["ticker"])
    if df is None: return None
    return round(float(df["Close"].iloc[-1]), 4)

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 5 — COMANDI
# ═══════════════════════════════════════════════════════════════════════════════

def handle(text: str, cid: int):
    t  = text.strip()
    tl = t.lower()
    nome_utente = UTENTI.get(cid, f"utente {cid}")

    # /comprato TICKER IMPORTO
    if tl.startswith("/comprato"):
        parts = t.split()
        if len(parts) == 3:
            try:
                ticker  = parts[1].upper()
                importo = float(parts[2].replace(",","."))
                send(f"⏳ Scarico prezzo reale di {ticker}...", cid)
                pr = prezzo_live(ticker)
                if not pr:
                    send("❌ Impossibile scaricare il prezzo ora. Riprova tra qualche minuto.", cid); return
                quote = registra_acquisto(cid, ticker, importo, pr)
                b = load_budget(cid)
                b["speso"] += importo
                b["storico"].append({"ticker": ticker, "importo": importo,
                                     "data": datetime.now().strftime("%d/%m %H:%M")})
                save_budget(cid, b)
                rim = BUDGET_MENSILE - b["speso"]
                avv = "\n\n⚠️ Usa /pausanotifiche per fermare le notifiche mensili." if rim < 4 else ""
                send(
                    f"✅ <b>Acquisto registrato</b>\n\n"
                    f"📌 {ticker}: €{importo:.2f}\n"
                    f"📈 Prezzo reale: €{pr:.4f}\n"
                    f"📦 Quote: {quote:.6f}\n\n"
                    f"💰 Speso: €{b['speso']:.2f} / €{BUDGET_MENSILE:.2f}\n"
                    f"💵 Rimanente: €{max(0,rim):.2f}{avv}", cid
                )
            except Exception as e:
                send(f"⚠️ Errore: {e}\nFormato: /comprato TICKER IMPORTO", cid)
        else:
            send("⚠️ Formato: /comprato TICKER IMPORTO\nEs: /comprato VUSA 5", cid)

    # /vendi TICKER IMPORTO | tutto
    elif tl.startswith("/vendi"):
        parts = t.split()
        if len(parts) == 3:
            try:
                ticker = parts[1].upper()
                tutto  = parts[2].lower() == "tutto"
                send(f"⏳ Scarico prezzo reale di {ticker}...", cid)
                pr = prezzo_live(ticker)
                if not pr:
                    send("❌ Impossibile scaricare il prezzo ora.", cid); return
                p   = load_patrimonio(cid)
                if ticker not in p["posizioni"]:
                    send(f"❌ Non hai {ticker} in portafoglio.", cid); return
                importo = p["posizioni"][ticker]["quote"] * pr if tutto else float(parts[2].replace(",","."))
                res = registra_vendita(cid, ticker, importo, pr)
                if not res:
                    send("❌ Quote insufficienti.", cid); return
                q, pnl = res
                e = "🟢" if pnl >= 0 else "🔴"
                send(
                    f"✅ <b>Vendita registrata</b>\n\n"
                    f"📌 {ticker}: €{importo:.2f}\n"
                    f"📉 Prezzo reale: €{pr:.4f}\n"
                    f"📦 Quote vendute: {q:.6f}\n"
                    f"{e} P&L: {'+'if pnl>=0 else ''}€{pnl:.2f}\n\n"
                    f"Usa /patrimonio per aggiornare il saldo.", cid
                )
            except Exception as e:
                send(f"⚠️ Errore: {e}\nFormato: /vendi TICKER IMPORTO", cid)
        else:
            send("⚠️ Formato: /vendi TICKER IMPORTO\noppure: /vendi VUSA tutto", cid)

    # /patrimonio
    elif tl.startswith("/patrimonio"):
        send("⏳ Aggiorno le quotazioni reali...", cid)
        p   = load_patrimonio(cid)
        pos = p["posizioni"]
        if not pos:
            send("📋 Portafoglio vuoto. Usa /comprato per registrare il primo acquisto.", cid); return
        tot_inv = tot_att = 0.0
        msg = f"💼 <b>Portafoglio di {nome_utente}</b>\n\n"
        for tk, d in pos.items():
            pr = prezzo_live(tk) or d["prezzo_medio"]
            va = round(d["quote"] * pr, 2)
            pnl = round(va - d["investito"], 2)
            pct = round(pnl / d["investito"] * 100, 2) if d["investito"] else 0
            e   = "🟢" if pnl >= 0 else "🔴"
            msg += (f"<b>{tk}</b> — {d['nome']}\n"
                    f"   {d['quote']:.6f} quote × €{pr:.4f}\n"
                    f"   Investito: €{d['investito']:.2f} → Attuale: €{va:.2f}\n"
                    f"   {e} P&L: {'+'if pnl>=0 else ''}€{pnl:.2f} ({'+' if pct>=0 else ''}{pct:.2f}%)\n\n")
            tot_inv += d["investito"]; tot_att += va
            time.sleep(0.5)
        pnl_t = round(tot_att - tot_inv, 2)
        pct_t = round(pnl_t / tot_inv * 100, 2) if tot_inv else 0
        e_t   = "🟢" if pnl_t >= 0 else "🔴"
        msg += (f"──────────────\n"
                f"Investito: €{tot_inv:.2f}\n"
                f"Attuale:   €{tot_att:.2f}\n"
                f"{e_t} P&L totale: {'+'if pnl_t>=0 else ''}€{pnl_t:.2f} ({'+'if pct_t>=0 else ''}{pct_t:.2f}%)")
        send(msg, cid)

    # /storico
    elif tl.startswith("/storico"):
        p   = load_patrimonio(cid)
        ops = p["storico_operazioni"]
        if not ops:
            send("📋 Nessuna operazione registrata.", cid); return
        msg = f"📋 <b>Storico di {nome_utente}</b>\n\n"
        for op in ops[-15:]:
            te  = "🟢 Acquisto" if op["tipo"]=="acquisto" else "🔴 Vendita"
            ps  = f" · P&L: {'+'if op['pnl']>=0 else ''}€{op['pnl']:.2f}" if op.get("pnl") is not None else ""
            msg += f"{te} {op['ticker']} — €{op['importo']:.2f}{ps}\n   {op['data']}\n\n"
        send(msg, cid)

    # /analisi
    elif tl.startswith("/analisi"):
        send("⏳ Scarico dati reali da Alpha Vantage...\n(può richiedere 1-2 minuti)", cid)
        risultati = analizza_tutti()
        if not risultati:
            send("❌ Impossibile scaricare i dati. Controlla che AV_KEY sia configurata in Railway.", cid); return
        msg = f"📊 <b>Analisi reale — {datetime.now().strftime('%d/%m %H:%M')}</b>\n\n"
        for r in sorted(risultati, key=lambda x: x["score_acq"], reverse=True):
            ea = "🟢" if r["sig_acq"]=="BUY" else "🟡" if r["sig_acq"]=="WATCH_BUY" else "⚪"
            ev = "🔴" if r["sig_vend"]=="SELL" else "🟠" if r["sig_vend"]=="WATCH_SELL" else ""
            msg += (f"{ea} <b>{r['display']}</b> {ev} — €{r['prezzo']:.4f}\n"
                    f"   RSI {r['rsi']} · MACD {'▲' if r['macd_isto']>0 else '▼'} · {fmt_cross(r['cross'])}\n"
                    f"   BB: {fmt_bb(r['bb_pos'])} · OBV: {r['obv_trend']}\n"
                    f"   Score acq: {r['score_acq']}/100 · vend: {r['score_vend']}/100\n\n")
        send(msg, cid)

    # /budget
    elif tl.startswith("/budget"):
        b  = load_budget(cid)
        rim = max(0, BUDGET_MENSILE - b["speso"])
        barra = "█"*int(b["speso"]/BUDGET_MENSILE*10) + "░"*(10-int(b["speso"]/BUDGET_MENSILE*10))
        sto   = "".join(f"  • {s['data']} — {s['ticker']}: €{s['importo']:.2f}\n" for s in b["storico"][-6:]) or "  Nessun acquisto ancora.\n"
        ps    = "\n🔕 Notifiche in pausa — /riprendi" if b.get("paused") else ""
        send(f"💰 <b>Budget di {nome_utente} — {datetime.now().strftime('%B %Y')}</b>\n\n"
             f"{barra}\nSpeso: €{b['speso']:.2f} / €{BUDGET_MENSILE:.2f}\nRimanente: €{rim:.2f}{ps}\n\n"
             f"<b>Ultimi acquisti:</b>\n{sto}", cid)

    # /pausanotifiche
    elif tl.startswith("/pausanotifiche"):
        b = load_budget(cid); b["paused"] = True; save_budget(cid, b)
        send("🔕 <b>Notifiche in pausa per te.</b>\nRiceverai solo segnali eccezionali (RSI &lt;25).\nUsa /riprendi per riattivarle.", cid)

    # /riprendi
    elif tl.startswith("/riprendi"):
        b = load_budget(cid); b["paused"] = False; save_budget(cid, b)
        send("🔔 <b>Notifiche riattivate.</b>", cid)

    # /consiglio
    elif tl.startswith("/consiglio"):
        send("⏳ Analizzo con dati reali...", cid)
        risultati = analizza_tutti()
        if not risultati:
            send("❌ Dati non disponibili ora.", cid); return
        b   = load_budget(cid)
        rim = BUDGET_MENSILE - b["speso"]
        mig = max(risultati, key=lambda x: x["score_acq"])
        vend = [r for r in risultati if r["sig_vend"] in ("SELL","WATCH_SELL")]
        msg  = f"💬 <b>Consiglio per {nome_utente} — {datetime.now().strftime('%d/%m %H:%M')}</b>\n\n"
        if rim >= 3:
            imp = min(rim * 0.4, 8.0)
            msg += (f"📈 <b>Acquisto:</b> {mig['nome']} ({mig['display']})\n"
                    f"   RSI {mig['rsi']} · Score {mig['score_acq']}/100\n"
                    f"   💶 Considera €{imp:.2f} su Revolut\n\n")
        else:
            msg += "💰 Budget quasi esaurito. Aspetta il mese prossimo.\n\n"
        if vend:
            msg += "📉 <b>Monitorare per vendita:</b>\n"
            for v in vend:
                msg += f"   ⚠️ {v['display']}: RSI {v['rsi']} · {fmt_cross(v['cross'])}\n"
        msg += "\n⚠️ <i>Non è consulenza finanziaria.</i>"
        send(msg, cid)

    # /imparaetf
    elif tl.startswith("/imparaetf"):
        send(
            "📚 <b>ETF e indicatori — guida rapida</b>\n\n"
            "<b>RSI &lt;30</b> = possibile ipervenduto (occasione?)\n"
            "<b>RSI >70</b> = possibile ipercomprato (attenzione)\n\n"
            "<b>MACD▲</b> = momentum rialzista in formazione\n"
            "<b>MACD▼</b> = momentum ribassista\n\n"
            "<b>Golden Cross</b> 🌟 = EMA50 supera EMA200 → trend positivo di lungo\n"
            "<b>Death Cross</b> 💀 = EMA50 scende sotto EMA200 → pericolo\n\n"
            "<b>Bollinger bassa</b> = prezzo ai minimi relativi → possibile rimbalzo\n"
            "<b>Bollinger alta</b>  = prezzo ai massimi relativi → possibile correzione\n\n"
            "<b>OBV positivo</b> = i grandi investitori stanno comprando (segnale nascosto)", cid)

    # /imparadca
    elif tl.startswith("/imparadca"):
        send(
            "📚 <b>Dollar Cost Averaging — strategia base</b>\n\n"
            "Investi la stessa cifra ogni mese, qualunque cosa succeda.\n\n"
            "• Mercato scende → compri più quote a sconto ✅\n"
            "• Mercato sale   → le tue quote valgono di più ✅\n\n"
            "Con 20€/mese al 7% medio annuo:\n"
            "→ 10 anni: ~€3.500 (versati €2.400)\n"
            "→ 20 anni: ~€10.400 (versati €4.800)\n\n"
            "<b>Regola d'oro: non smettere quando il mercato scende.</b>\n"
            "Quelli sono i mesi più preziosi.", cid)

    # /testapi — verifica connessione Alpha Vantage
    elif tl.startswith("/testapi"):
        send("⏳ Verifico connessione Alpha Vantage...", cid)
        key = AV_KEY
        if not key:
            send("❌ AV_KEY non configurata in Railway!", cid)
            return
        try:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=VOO&outputsize=compact&apikey={key}"
            r = requests.get(url, timeout=20)
            data = r.json()
            keys = list(data.keys())
            if "Time Series (Daily)" in data:
                ultimo = list(data["Time Series (Daily)"].keys())[0]
                prezzo = data["Time Series (Daily)"][ultimo]["4. close"]
                send(f"✅ Alpha Vantage funziona!\n\nVOO ultimo prezzo: ${prezzo}\nData: {ultimo}\n\nChiave: {key[:6]}...", cid)
            elif "Note" in data:
                send(f"⚠️ Rate limit raggiunto (5 call/min).\nAspetta 1 minuto e riprova.\n\nMessaggio AV: {data['Note'][:200]}", cid)
            elif "Error Message" in data:
                send(f"❌ Errore AV: {data['Error Message']}", cid)
            else:
                send(f"⚠️ Risposta inattesa.\nChiavi ricevute: {keys}", cid)
        except Exception as e:
            send(f"❌ Errore connessione: {e}", cid)

    # /help
    elif tl.startswith("/help") or tl.startswith("/start"):
        send(
            f"🤖 <b>InvestoBot v5 — Ciao {nome_utente}!</b>\n\n"
            "<b>📊 Portafoglio</b>\n"
            "/comprato TICKER IMPORTO\n"
            "/vendi TICKER IMPORTO (o tutto)\n"
            "/patrimonio — saldo con prezzi reali\n"
            "/storico — tutte le operazioni\n\n"
            "<b>📈 Analisi</b>\n"
            "/analisi — tutti gli indicatori ora\n"
            "/consiglio — suggerimento personalizzato\n"
            "/testapi — verifica connessione dati\n\n"
            "<b>💰 Budget</b>\n"
            "/budget — situazione tuo budget\n"
            "/pausanotifiche · /riprendi\n\n"
            "<b>📚 Impara</b>\n"
            "/imparaetf · /imparadca\n\n"
            "✅ Dati reali da Alpha Vantage\n"
            "✅ Budget separato per utente\n"
            "✅ Notifiche automatiche ogni ora (solo segnali reali)", cid)
    else:
        send("Non ho capito. Scrivi /help per il menu 😊", cid)

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 6 — SCAN AUTOMATICO (ogni ora, dati reali)
# ═══════════════════════════════════════════════════════════════════════════════

def mercato_aperto() -> bool:
    now = datetime.utcnow()
    if now.weekday() >= 5: return False
    return dtime(8, 0) <= now.time() <= dtime(16, 30)

def scan():
    log.info("Scansione automatica con dati reali...")
    if not mercato_aperto():
        log.info("Mercato chiuso."); return

    risultati = analizza_tutti()
    if not risultati:
        log.warning("Nessun dato da Alpha Vantage."); return

    for cid, nome in UTENTI.items():
        b      = load_budget(cid)
        rim    = BUDGET_MENSILE - b["speso"]
        paused = b.get("paused", False)

        if paused:
            # Solo segnali eccezionali: RSI < 25 e score >= 82
            ecc = [r for r in risultati if r["rsi"] < 25 and r["score_acq"] >= 82]
            if not ecc: continue
            msg = f"🚨 <b>Segnale ECCEZIONALE per {nome}</b>\n\n"
            for r in ecc:
                msg += (f"⭐ <b>{r['display']}</b>: RSI {r['rsi']} · Score {r['score_acq']}/100\n"
                        f"   {fmt_cross(r['cross'])} · Prezzo: €{r['prezzo']:.4f}\n"
                        f"   💶 Considera €3–5 anche fuori budget\n\n")
            msg += "⚠️ <i>Non è consulenza finanziaria.</i>"
            send(msg, cid)
            continue

        # Segnali normali: score_acq >= 65 e RSI < 35
        buy = [r for r in risultati if r["sig_acq"] == "BUY" and r["rsi"] < 35]
        if rim < 3 or not buy:
            log.info(f"{nome}: nessun segnale forte (rim €{rim:.2f})"); continue

        buy = sorted(buy, key=lambda x: x["score_acq"], reverse=True)[:2]
        msg  = f"📈 <b>Segnale reale di acquisto — {nome}</b>\n\n"
        msg += f"Dati aggiornati: {datetime.now().strftime('%d/%m %H:%M')}\n\n"
        for r in buy:
            imp = max(3.0, min(round(rim * 0.40 / len(buy), 2), 8.0))
            sgn = "+" if r["chg"] >= 0 else ""
            msg += (f"🟢 <b>{r['nome']} ({r['display']})</b>\n"
                    f"   Prezzo: €{r['prezzo']:.4f} · {sgn}{r['chg']}% oggi\n"
                    f"   RSI: {r['rsi']} · Score: {r['score_acq']}/100\n"
                    f"   {fmt_cross(r['cross'])} · BB: {fmt_bb(r['bb_pos'])}\n"
                    f"   MACD: {'▲ positivo' if r['macd_isto']>0 else '▼ negativo'} · OBV: {r['obv_trend']}\n"
                    f"   💶 <b>Consiglio: €{imp:.2f} su Revolut</b>\n\n")
        msg += (f"💰 Il tuo budget rimasto: €{rim:.2f} / €{BUDGET_MENSILE:.2f}\n"
                f"📱 Revolut → cerca ticker → acquista\n"
                f"📝 Poi: /comprato TICKER IMPORTO\n\n"
                f"⚠️ <i>Non è consulenza finanziaria.</i>")
        send(msg, cid)

        # Alert vendita per posizioni aperte di questo utente
        p   = load_patrimonio(cid)
        pos = p["posizioni"]
        if pos:
            vend = [r for r in risultati if r["display"] in pos and r["sig_vend"] == "SELL"]
            if vend:
                msg_v = f"⚠️ <b>Possibile vendita — {nome}</b>\n\n"
                for r in vend:
                    msg_v += (f"🔴 <b>{r['display']}</b>: RSI {r['rsi']} · {fmt_cross(r['cross'])}\n"
                              f"   Score vendita: {r['score_vend']}/100\n"
                              f"   /vendi {r['display']} IMPORTO\n\n")
                msg_v += "⚠️ <i>Non è consulenza finanziaria.</i>"
                send(msg_v, cid)


def get_cat_photo() -> str | None:
    """Ottiene URL di una foto reale di gatto da The Cat API (non AI)."""
    try:
        r = requests.get("https://api.thecatapi.com/v1/images/search", timeout=10)
        data = r.json()
        return data[0]["url"] if data else None
    except Exception as e:
        log.error(f"Cat API error: {e}")
        return None

def send_photo(photo_url: str, caption: str, cid):
    """Manda una foto via Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": cid, "photo": photo_url, "caption": caption, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
    except Exception as e:
        log.error(f"Send photo error a {cid}: {e}")

def buongiorno():
    risultati = analizza_tutti()
    cat_url   = get_cat_photo()
    giorni    = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"]
    mesi      = ["gennaio","febbraio","marzo","aprile","maggio","giugno",
                 "luglio","agosto","settembre","ottobre","novembre","dicembre"]
    now       = datetime.now()
    data_str  = f"{giorni[now.weekday()]} {now.day} {mesi[now.month-1]} {now.year}"

    for cid, nome in UTENTI.items():
        b   = load_budget(cid)
        rim = max(0, BUDGET_MENSILE - b["speso"])
        ps  = "\n🔕 Notifiche in pausa — /riprendi" if b.get("paused") else ""
        migliore = max(risultati, key=lambda x: x["score_acq"]).get("display","—") if risultati else "—"

        testo = (
            f"☀️ <b>Buongiorno {nome}!</b>\n"
            f"📅 {data_str}\n\n"
            f"🐱 Fred puzza e pure Dod\n\n"
            f"💰 Il tuo budget rimasto: €{rim:.2f} / €{BUDGET_MENSILE:.2f}{ps}\n"
            f"📊 Asset più forte stamattina: <b>{migliore}</b>\n\n"
            "Scrivi /analisi per i dettagli o /help per i comandi."
        )

        if cat_url:
            send_photo(cat_url, testo, cid)
        else:
            send(testo, cid)

def check_inizio_mese():
    if datetime.now().day == 1:
        for cid, nome in UTENTI.items():
            send(f"🔄 <b>Nuovo mese — budget azzerato, {nome}!</b>\n\n"
                 f"Hai di nuovo €{BUDGET_MENSILE:.2f} disponibili.\n"
                 "Notifiche riattivate automaticamente. 🚀", cid)

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

last_id = None

def poll():
    global last_id
    for u in get_updates(offset=last_id):
        last_id = u["update_id"] + 1
        msg  = u.get("message", {})
        text = msg.get("text", "")
        cid  = msg.get("chat", {}).get("id")
        if text and cid:
            if cid not in UTENTI:
                send("⛔ Non sei autorizzato.", cid)
                log.warning(f"Accesso non autorizzato: {cid}")
                continue
            log.info(f"CMD {cid}: {text[:40]}")
            handle(text, cid)

def get_updates(offset=None):
    try:
        params = {"timeout": 10}
        if offset: params["offset"] = offset
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                         params=params, timeout=15)
        return r.json().get("result", [])
    except: return []

if __name__ == "__main__":
    log.info("InvestoBot v5 avviato ✅")
    send_tutti(
        "🤖 <b>InvestoBot v5 — Budget separati + Dati reali</b>\n\n"
        "✅ Ogni utente ha il suo budget indipendente\n"
        "✅ Dati reali da Alpha Vantage (nessun valore casuale)\n"
        "✅ Scan automatico ogni ora durante il mercato\n\n"
        "<b>⚠️ Azione richiesta:</b>\n"
        "Vai su Railway → Variables → aggiungi:\n"
        "<code>AV_KEY = la_tua_chiave_alpha_vantage</code>\n\n"
        "Ottienila gratis su alphavantage.co\n\n"
        "Scrivi /help per il menu completo."
    )
    sched = BlockingScheduler(timezone="Europe/Rome")
    sched.add_job(buongiorno,        "cron", day_of_week="mon-fri", hour=9,       minute=0)
    sched.add_job(scan,              "cron", day_of_week="mon-fri", hour="10-17", minute=0)
    sched.add_job(check_inizio_mese, "cron", day=1,                 hour=8,       minute=30)
    sched.add_job(poll,              "interval", seconds=5)
    sched.start()
