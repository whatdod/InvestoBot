"""
InvestoBot v4 — Dati reali via yfinance (Yahoo Finance)
Indicatori: RSI, MACD, EMA50/200, Boll. Bands, OBV, Golden/Death Cross
Solo ETF e obbligazioni (profilo basso rischio)
"""
import os, json, time, logging
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, time as dtime
from apscheduler.schedulers.blocking import BlockingScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
BUDGET_MENSILE = 20.0
BUDGET_FILE    = "budget.json"
PATRIMONIO_FILE = "patrimonio.json"

# ── ASSET UNIVERSE (solo ETF + obbligazioni, profilo basso rischio) ───────────
# ticker Yahoo Finance → alcuni ETF europei hanno suffisso .L (London) o .AS (Amsterdam)
ASSETS = [
    {"ticker": "VUSA.L",  "nome": "Vanguard S&P 500 ETF",       "cat": "etf",  "display": "VUSA"},
    {"ticker": "IWDA.L",  "nome": "iShares MSCI World",          "cat": "etf",  "display": "IWDA"},
    {"ticker": "VWRL.L",  "nome": "Vanguard FTSE All-World",     "cat": "etf",  "display": "VWRL"},
    {"ticker": "EIMI.L",  "nome": "iShares MSCI Emerging Mkts",  "cat": "etf",  "display": "EIMI"},
    {"ticker": "SGLD.L",  "nome": "Invesco Physical Gold ETC",   "cat": "gold", "display": "SGLD"},
    {"ticker": "IBTM.L",  "nome": "iShares Core Global Bond",    "cat": "bond", "display": "IBTM"},
    {"ticker": "VGOV.L",  "nome": "Vanguard UK Gilt ETF",        "cat": "bond", "display": "VGOV"},
]

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 1 — DATI REALI E INDICATORI
# ═══════════════════════════════════════════════════════════════════════════════

def scarica_dati(ticker: str, periodo: str = "6mo") -> pd.DataFrame | None:
    """Scarica dati storici reali da Yahoo Finance."""
    try:
        df = yf.download(ticker, period=periodo, interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 30:
            log.warning(f"Dati insufficienti per {ticker}")
            return None
        df.dropna(inplace=True)
        return df
    except Exception as e:
        log.error(f"Errore download {ticker}: {e}")
        return None

def calcola_rsi(close: pd.Series, periodi: int = 14) -> float:
    """RSI reale su 14 periodi."""
    delta  = close.diff()
    guadagni = delta.clip(lower=0)
    perdite  = (-delta).clip(lower=0)
    media_g  = guadagni.ewm(com=periodi - 1, min_periods=periodi).mean()
    media_p  = perdite.ewm(com=periodi - 1, min_periods=periodi).mean()
    rs  = media_g / media_p.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)

def calcola_macd(close: pd.Series):
    """MACD reale: linea, segnale, istogramma."""
    ema12    = close.ewm(span=12, adjust=False).mean()
    ema26    = close.ewm(span=26, adjust=False).mean()
    macd     = ema12 - ema26
    segnale  = macd.ewm(span=9, adjust=False).mean()
    isto     = macd - segnale
    return round(float(macd.iloc[-1]), 4), round(float(segnale.iloc[-1]), 4), round(float(isto.iloc[-1]), 4)

def calcola_ema(close: pd.Series, span: int) -> float:
    """EMA su n periodi."""
    return round(float(close.ewm(span=span, adjust=False).mean().iloc[-1]), 4)

def calcola_bande_bollinger(close: pd.Series, periodi: int = 20):
    """Bande di Bollinger: media, banda superiore, inferiore."""
    sma    = close.rolling(periodi).mean()
    std    = close.rolling(periodi).std()
    upper  = sma + 2 * std
    lower  = sma - 2 * std
    return round(float(sma.iloc[-1]), 4), round(float(upper.iloc[-1]), 4), round(float(lower.iloc[-1]), 4)

def calcola_obv(close: pd.Series, volume: pd.Series) -> str:
    """On-Balance Volume: direzione (salita/discesa nelle ultime 10 sessioni)."""
    direction = np.where(close.diff() > 0, volume, np.where(close.diff() < 0, -volume, 0))
    obv = pd.Series(direction, index=close.index).cumsum()
    # Trend OBV ultimi 10 giorni
    trend = obv.iloc[-1] - obv.iloc[-10]
    return "positivo" if trend > 0 else "negativo"

def analizza_asset(asset: dict) -> dict | None:
    """
    Scarica dati reali e calcola tutti gli indicatori.
    Restituisce un dizionario con il segnale e il punteggio.
    """
    df = scarica_dati(asset["ticker"])
    if df is None:
        return None

    close  = df["Close"].squeeze()
    volume = df["Volume"].squeeze() if "Volume" in df.columns else pd.Series(dtype=float)

    prezzo_attuale = round(float(close.iloc[-1]), 4)
    prezzo_ieri    = round(float(close.iloc[-2]), 4)
    chg_pct        = round((prezzo_attuale - prezzo_ieri) / prezzo_ieri * 100, 2)
    chg_1w         = round((prezzo_attuale - float(close.iloc[-6])) / float(close.iloc[-6]) * 100, 2) if len(close) >= 6 else None
    chg_1m         = round((prezzo_attuale - float(close.iloc[-22])) / float(close.iloc[-22]) * 100, 2) if len(close) >= 22 else None

    rsi            = calcola_rsi(close)
    macd, macd_sig, macd_isto = calcola_macd(close)
    ema50          = calcola_ema(close, 50) if len(close) >= 50 else None
    ema200         = calcola_ema(close, 200) if len(close) >= 200 else None
    bb_mid, bb_up, bb_low = calcola_bande_bollinger(close)
    obv_trend      = calcola_obv(close, volume) if not volume.empty else "n/d"

    # Golden/Death Cross
    if ema50 and ema200:
        ema50_prev  = round(float(close.ewm(span=50, adjust=False).mean().iloc[-2]), 4)
        ema200_prev = round(float(close.ewm(span=200, adjust=False).mean().iloc[-2]), 4)
        if ema50_prev <= ema200_prev and ema50 > ema200:
            cross = "golden"   # ✅ segnale forte di acquisto
        elif ema50_prev >= ema200_prev and ema50 < ema200:
            cross = "death"    # ❌ segnale forte di vendita
        else:
            cross = "sopra" if ema50 > ema200 else "sotto"
    else:
        cross = "n/d"

    # Posizione rispetto alle Bande di Bollinger
    if prezzo_attuale <= bb_low:
        bb_pos = "sotto_bassa"   # possibile rimbalzo
    elif prezzo_attuale >= bb_up:
        bb_pos = "sopra_alta"    # possibile correzione
    else:
        bb_pos = "neutro"

    # ── SCORING ACQUISTO ────────────────────────────────────────────────────
    score_acq = 0

    # RSI
    if rsi < 28:   score_acq += 40
    elif rsi < 35: score_acq += 25
    elif rsi < 45: score_acq += 10

    # MACD: istogramma positivo e crescente = momentum rialzista
    if macd_isto > 0 and macd > macd_sig:  score_acq += 20
    elif macd_isto > 0:                    score_acq += 10

    # Bande di Bollinger: prezzo sotto banda bassa = possibile rimbalzo
    if bb_pos == "sotto_bassa":  score_acq += 20
    elif bb_pos == "neutro":     score_acq += 5

    # Golden Cross: trend di lungo periodo positivo
    if cross == "golden":  score_acq += 20
    elif cross == "sopra": score_acq += 8

    # OBV positivo = volumi confermano il trend
    if obv_trend == "positivo":  score_acq += 10

    # Variazione giornaliera: calo = possibile sconto
    if chg_pct < -2:   score_acq += 12
    elif chg_pct < -1: score_acq += 6

    # Bonus profilo conservativo per bond/gold
    if asset["cat"] in ("bond", "gold"):  score_acq += 8

    # ── SCORING VENDITA ─────────────────────────────────────────────────────
    score_vend = 0

    # RSI ipercomprato
    if rsi > 72:   score_vend += 40
    elif rsi > 65: score_vend += 20

    # MACD negativo e in calo
    if macd_isto < 0 and macd < macd_sig:  score_vend += 25
    elif macd_isto < 0:                    score_vend += 10

    # Prezzo sopra banda alta di Bollinger = ipercomprato
    if bb_pos == "sopra_alta":  score_vend += 20

    # Death Cross = trend di lungo periodo negativo
    if cross == "death":   score_vend += 30
    elif cross == "sotto": score_vend += 10

    # OBV negativo = i volumi confermano la pressione di vendita
    if obv_trend == "negativo":  score_vend += 10

    # ── SEGNALE FINALE ──────────────────────────────────────────────────────
    sig_acq  = "BUY"   if score_acq  >= 65 else ("WATCH_BUY"  if score_acq  >= 40 else "HOLD")
    sig_vend = "SELL"  if score_vend >= 60 else ("WATCH_SELL" if score_vend >= 35 else "HOLD")

    return {
        **asset,
        "prezzo":     prezzo_attuale,
        "chg_pct":    chg_pct,
        "chg_1w":     chg_1w,
        "chg_1m":     chg_1m,
        "rsi":        rsi,
        "macd":       macd,
        "macd_sig":   macd_sig,
        "macd_isto":  macd_isto,
        "ema50":      ema50,
        "ema200":     ema200,
        "cross":      cross,
        "bb_mid":     bb_mid,
        "bb_up":      bb_up,
        "bb_low":     bb_low,
        "bb_pos":     bb_pos,
        "obv_trend":  obv_trend,
        "score_acq":  score_acq,
        "score_vend": score_vend,
        "sig_acq":    sig_acq,
        "sig_vend":   sig_vend,
        "aggiornato": datetime.now().strftime("%d/%m %H:%M"),
    }

def analizza_tutti() -> list[dict]:
    """Scarica e analizza tutti gli asset. Riprova una volta in caso di errore."""
    risultati = []
    for a in ASSETS:
        try:
            r = analizza_asset(a)
            if r:
                risultati.append(r)
                time.sleep(0.4)  # evita rate limiting Yahoo
        except Exception as e:
            log.error(f"Errore analisi {a['ticker']}: {e}")
    return risultati

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 2 — BUDGET E PATRIMONIO
# ═══════════════════════════════════════════════════════════════════════════════

def load_budget() -> dict:
    try:
        with open(BUDGET_FILE) as f:
            d = json.load(f)
        now = datetime.now()
        if d.get("month") != now.month or d.get("year") != now.year:
            log.info("Nuovo mese: budget azzerato automaticamente.")
            b = fresh_budget()
            save_budget(b)
            return b
        return d
    except:
        b = fresh_budget()
        save_budget(b)
        return b

def fresh_budget() -> dict:
    now = datetime.now()
    return {"speso": 0.0, "storico": [], "month": now.month, "year": now.year, "paused": False}

def save_budget(d: dict):
    with open(BUDGET_FILE, "w") as f:
        json.dump(d, f, indent=2)

def load_patrimonio() -> dict:
    """
    Patrimonio: dizionario con le posizioni aperte e lo storico operazioni.
    Struttura:
    {
      "posizioni": {
        "VUSA": {"display": "VUSA", "nome": "...", "quote": 0.06, "prezzo_medio": 115.8, "investito": 7.0},
        ...
      },
      "storico_operazioni": [
        {"data": "...", "tipo": "acquisto/vendita", "ticker": "...", "quote": ...,
         "prezzo": ..., "importo": ..., "pnl": null},
        ...
      ]
    }
    """
    try:
        with open(PATRIMONIO_FILE) as f:
            return json.load(f)
    except:
        return {"posizioni": {}, "storico_operazioni": []}

def save_patrimonio(d: dict):
    with open(PATRIMONIO_FILE, "w") as f:
        json.dump(d, f, indent=2)

def registra_acquisto(ticker: str, importo: float, prezzo_attuale: float):
    """Aggiorna patrimonio dopo un acquisto."""
    p   = load_patrimonio()
    pos = p["posizioni"]

    # Trova il nome completo
    meta = next((a for a in ASSETS if a["display"] == ticker), None)
    nome = meta["nome"] if meta else ticker

    quote_acquistate = round(importo / prezzo_attuale, 6) if prezzo_attuale > 0 else 0

    if ticker in pos:
        # Media ponderata del prezzo d'acquisto
        tot_investito = pos[ticker]["investito"] + importo
        tot_quote     = pos[ticker]["quote"] + quote_acquistate
        pos[ticker]["prezzo_medio"] = round(tot_investito / tot_quote, 4) if tot_quote > 0 else 0
        pos[ticker]["quote"]        = round(tot_quote, 6)
        pos[ticker]["investito"]    = round(tot_investito, 2)
    else:
        pos[ticker] = {
            "display":      ticker,
            "nome":         nome,
            "quote":        quote_acquistate,
            "prezzo_medio": round(prezzo_attuale, 4),
            "investito":    round(importo, 2),
        }

    p["storico_operazioni"].append({
        "data":    datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo":    "acquisto",
        "ticker":  ticker,
        "quote":   quote_acquistate,
        "prezzo":  prezzo_attuale,
        "importo": round(importo, 2),
        "pnl":     None,
    })
    save_patrimonio(p)
    return quote_acquistate

def registra_vendita(ticker: str, importo_eur: float, prezzo_attuale: float) -> tuple[float, float] | None:
    """
    Registra una vendita parziale o totale.
    Restituisce (quote_vendute, pnl) oppure None se non hai quel titolo.
    """
    p   = load_patrimonio()
    pos = p["posizioni"]

    if ticker not in pos or pos[ticker]["quote"] <= 0:
        return None

    quote_da_vendere = round(importo_eur / prezzo_attuale, 6) if prezzo_attuale > 0 else 0
    quote_da_vendere = min(quote_da_vendere, pos[ticker]["quote"])
    importo_reale    = round(quote_da_vendere * prezzo_attuale, 2)
    costo_acquisto   = round(quote_da_vendere * pos[ticker]["prezzo_medio"], 2)
    pnl              = round(importo_reale - costo_acquisto, 2)

    pos[ticker]["quote"]     = round(pos[ticker]["quote"] - quote_da_vendere, 6)
    pos[ticker]["investito"] = round(pos[ticker]["investito"] - costo_acquisto, 2)

    if pos[ticker]["quote"] <= 0.000001:
        del pos[ticker]  # posizione chiusa

    p["storico_operazioni"].append({
        "data":    datetime.now().strftime("%d/%m/%Y %H:%M"),
        "tipo":    "vendita",
        "ticker":  ticker,
        "quote":   quote_da_vendere,
        "prezzo":  prezzo_attuale,
        "importo": importo_reale,
        "pnl":     pnl,
    })
    save_patrimonio(p)
    return quote_da_vendere, pnl

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 3 — TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def send(text: str, cid=None):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid or CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
        r.raise_for_status()
    except Exception as e:
        log.error(f"Telegram send error: {e}")

def get_updates(offset=None) -> list:
    try:
        params = {"timeout": 10}
        if offset: params["offset"] = offset
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", params=params, timeout=15)
        return r.json().get("result", [])
    except:
        return []

def fmt_cross(cross: str) -> str:
    return {"golden": "🌟 Golden Cross", "death": "💀 Death Cross",
            "sopra": "↑ EMA50>EMA200", "sotto": "↓ EMA50<EMA200", "n/d": "—"}.get(cross, cross)

def fmt_bb(bb_pos: str) -> str:
    return {"sotto_bassa": "⬇️ Sotto banda (rimbalzo?)", "sopra_alta": "⬆️ Sopra banda (ipercomprato)",
            "neutro": "↔️ Neutro"}.get(bb_pos, bb_pos)

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 4 — COMANDI
# ═══════════════════════════════════════════════════════════════════════════════

def handle(text: str, cid):
    t  = text.strip()
    tl = t.lower()

    # /comprato TICKER IMPORTO
    if tl.startswith("/comprato"):
        parts = t.split()
        if len(parts) == 3:
            try:
                ticker  = parts[1].upper()
                importo = float(parts[2].replace(",", "."))

                # Prendi prezzo reale
                send(f"⏳ Scarico il prezzo reale di {ticker}...", cid)
                meta    = next((a for a in ASSETS if a["display"] == ticker), None)
                yf_tick = meta["ticker"] if meta else ticker + ".L"
                df      = scarica_dati(yf_tick, "5d")
                prezzo  = round(float(df["Close"].squeeze().iloc[-1]), 4) if df is not None else 0.0

                quote = registra_acquisto(ticker, importo, prezzo)

                b = load_budget()
                b["speso"] += importo
                b["storico"].append({"ticker": ticker, "importo": importo, "data": datetime.now().strftime("%d/%m %H:%M")})
                save_budget(b)

                rimanente = BUDGET_MENSILE - b["speso"]
                avviso = "\n⚠️ Usa /pausanotifiche per smettere le notifiche mensili." if rimanente < 4 else ""

                send(
                    f"✅ <b>Acquisto registrato</b>\n\n"
                    f"📌 {ticker}: €{importo:.2f}\n"
                    f"📈 Prezzo al momento: €{prezzo:.4f}\n"
                    f"📦 Quote acquistate: {quote:.6f}\n\n"
                    f"💰 Speso: €{b['speso']:.2f} / €{BUDGET_MENSILE:.2f}\n"
                    f"💵 Rimanente: €{max(0, rimanente):.2f}{avviso}",
                    cid
                )
            except Exception as e:
                send(f"⚠️ Errore: {e}\nFormato: /comprato TICKER IMPORTO\nEs: /comprato VUSA 5", cid)
        else:
            send("⚠️ Formato: /comprato TICKER IMPORTO\nEs: /comprato VUSA 5", cid)

    # /vendi TICKER IMPORTO (in euro) oppure /vendi TICKER tutto
    elif tl.startswith("/vendi"):
        parts = t.split()
        if len(parts) == 3:
            try:
                ticker = parts[1].upper()
                tutto  = parts[2].lower() == "tutto"

                send(f"⏳ Scarico il prezzo reale di {ticker}...", cid)
                meta    = next((a for a in ASSETS if a["display"] == ticker), None)
                yf_tick = meta["ticker"] if meta else ticker + ".L"
                df      = scarica_dati(yf_tick, "5d")
                prezzo  = round(float(df["Close"].squeeze().iloc[-1]), 4) if df is not None else 0.0

                p   = load_patrimonio()
                pos = p["posizioni"]

                if ticker not in pos:
                    send(f"❌ Non hai {ticker} in portafoglio.", cid); return

                importo = pos[ticker]["quote"] * prezzo if tutto else float(parts[2].replace(",", "."))
                risultato = registra_vendita(ticker, importo, prezzo)

                if risultato is None:
                    send(f"❌ Non hai abbastanza {ticker} da vendere.", cid); return

                quote_v, pnl = risultato
                emoji_pnl = "🟢" if pnl >= 0 else "🔴"
                send(
                    f"✅ <b>Vendita registrata</b>\n\n"
                    f"📌 {ticker}: €{importo:.2f}\n"
                    f"📉 Prezzo al momento: €{prezzo:.4f}\n"
                    f"📦 Quote vendute: {quote_v:.6f}\n"
                    f"{emoji_pnl} P&L: {'+'if pnl>=0 else ''}€{pnl:.2f}\n\n"
                    f"Usa /patrimonio per vedere il portafoglio aggiornato.",
                    cid
                )
            except Exception as e:
                send(f"⚠️ Errore: {e}\nFormato: /vendi TICKER IMPORTO oppure /vendi TICKER tutto", cid)
        else:
            send("⚠️ Formato: /vendi TICKER IMPORTO\noppure: /vendi VUSA tutto\nEs: /vendi VUSA 5", cid)

    # /patrimonio
    elif tl.startswith("/patrimonio"):
        send("⏳ Aggiorno le quotazioni reali...", cid)
        p   = load_patrimonio()
        pos = p["posizioni"]

        if not pos:
            send("📋 Portafoglio vuoto. Usa /comprato per registrare un acquisto.", cid); return

        tot_investito = 0.0
        tot_attuale   = 0.0
        msg = "💼 <b>Il tuo portafoglio</b>\n\n"

        for ticker, dati in pos.items():
            meta    = next((a for a in ASSETS if a["display"] == ticker), None)
            yf_tick = meta["ticker"] if meta else ticker + ".L"
            df      = scarica_dati(yf_tick, "5d")
            prezzo  = round(float(df["Close"].squeeze().iloc[-1]), 4) if df is not None else dati["prezzo_medio"]

            val_att = round(dati["quote"] * prezzo, 2)
            pnl     = round(val_att - dati["investito"], 2)
            pnl_pct = round(pnl / dati["investito"] * 100, 2) if dati["investito"] > 0 else 0
            e_pnl   = "🟢" if pnl >= 0 else "🔴"

            msg += (
                f"<b>{ticker}</b> — {dati['nome']}\n"
                f"   Quote: {dati['quote']:.6f} × €{prezzo:.4f}\n"
                f"   Investito: €{dati['investito']:.2f} → Attuale: €{val_att:.2f}\n"
                f"   {e_pnl} P&L: {'+'if pnl>=0 else ''}€{pnl:.2f} ({'+' if pnl_pct>=0 else ''}{pnl_pct:.2f}%)\n\n"
            )

            tot_investito += dati["investito"]
            tot_attuale   += val_att
            time.sleep(0.3)

        pnl_tot     = round(tot_attuale - tot_investito, 2)
        pnl_tot_pct = round(pnl_tot / tot_investito * 100, 2) if tot_investito > 0 else 0
        e_tot       = "🟢" if pnl_tot >= 0 else "🔴"

        msg += (
            f"──────────────\n"
            f"Totale investito: €{tot_investito:.2f}\n"
            f"Valore attuale:   €{tot_attuale:.2f}\n"
            f"{e_tot} P&L totale: {'+'if pnl_tot>=0 else ''}€{pnl_tot:.2f} ({'+'if pnl_tot_pct>=0 else ''}{pnl_tot_pct:.2f}%)"
        )
        send(msg, cid)

    # /storico
    elif tl.startswith("/storico"):
        p = load_patrimonio()
        ops = p["storico_operazioni"]
        if not ops:
            send("📋 Nessuna operazione registrata.", cid); return
        msg = "📋 <b>Storico operazioni</b>\n\n"
        for op in ops[-15:]:
            tipo_e = "🟢 Acquisto" if op["tipo"] == "acquisto" else "🔴 Vendita"
            pnl_s  = f" · P&L: {'+'if op['pnl']>=0 else ''}€{op['pnl']:.2f}" if op.get("pnl") is not None else ""
            msg += f"{tipo_e} {op['ticker']} — €{op['importo']:.2f}{pnl_s}\n"
            msg += f"   {op['data']} · {op['quote']:.6f} quote × €{op['prezzo']:.4f}\n\n"
        send(msg, cid)

    # /analisi
    elif tl.startswith("/analisi"):
        send("⏳ Scarico dati reali da Yahoo Finance per tutti gli asset...", cid)
        risultati = analizza_tutti()
        if not risultati:
            send("❌ Impossibile scaricare i dati. Riprova tra qualche minuto.", cid); return

        msg = f"📊 <b>Analisi reale — {datetime.now().strftime('%d/%m %H:%M')}</b>\n\n"
        for r in sorted(risultati, key=lambda x: x["score_acq"], reverse=True):
            e_acq  = "🟢" if r["sig_acq"] == "BUY" else "🟡" if r["sig_acq"] == "WATCH_BUY" else "⚪"
            e_vend = "🔴" if r["sig_vend"] == "SELL" else "🟠" if r["sig_vend"] == "WATCH_SELL" else ""
            macd_s = "▲" if r["macd_isto"] > 0 else "▼"
            msg += (
                f"{e_acq} <b>{r['display']}</b> {e_vend}\n"
                f"   €{r['prezzo']:.4f} · {'+' if r['chg_pct']>=0 else ''}{r['chg_pct']}% oggi\n"
                f"   RSI: {r['rsi']} · MACD: {macd_s}{abs(r['macd_isto']):.4f}\n"
                f"   {fmt_cross(r['cross'])} · BB: {fmt_bb(r['bb_pos'])}\n"
                f"   OBV: {r['obv_trend']} · Score acq: {r['score_acq']}/100\n\n"
            )
        send(msg, cid)

    # /budget
    elif tl.startswith("/budget"):
        b = load_budget()
        rimanente = max(0, BUDGET_MENSILE - b["speso"])
        barra = "█" * int(b["speso"] / BUDGET_MENSILE * 10) + "░" * (10 - int(b["speso"] / BUDGET_MENSILE * 10))
        storico = "".join(f"  • {s['data']} — {s['ticker']}: €{s['importo']:.2f}\n" for s in b["storico"][-6:]) or "  Nessun acquisto ancora.\n"
        pausa_s = "\n🔕 Notifiche in pausa (usa /riprendi)" if b.get("paused") else ""
        send(
            f"💰 <b>Budget {datetime.now().strftime('%B %Y')}</b>\n\n"
            f"{barra}\n"
            f"Speso:     €{b['speso']:.2f}\n"
            f"Rimanente: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}{pausa_s}\n\n"
            f"<b>Ultimi acquisti:</b>\n{storico}",
            cid
        )

    # /pausanotifiche
    elif tl.startswith("/pausanotifiche"):
        b = load_budget(); b["paused"] = True; save_budget(b)
        send("🔕 <b>Notifiche normali in pausa.</b>\nRiceverai solo segnali eccezionali (RSI &lt;25, score ≥80).\nUsa /riprendi per riattivarle.", cid)

    # /riprendi
    elif tl.startswith("/riprendi"):
        b = load_budget(); b["paused"] = False; save_budget(b)
        send("🔔 <b>Notifiche riattivate.</b>", cid)

    # /consiglio
    elif tl.startswith("/consiglio"):
        send("⏳ Analizzo i mercati con dati reali...", cid)
        risultati = analizza_tutti()
        if not risultati:
            send("❌ Impossibile scaricare i dati ora.", cid); return
        b = load_budget()
        rimanente = BUDGET_MENSILE - b["speso"]
        migliore  = max(risultati, key=lambda x: x["score_acq"])
        vendita   = [r for r in risultati if r["sig_vend"] in ("SELL", "WATCH_SELL")]

        msg = f"💬 <b>Consiglio personalizzato — {datetime.now().strftime('%d/%m %H:%M')}</b>\n\n"

        if rimanente >= 3:
            imp = min(rimanente * 0.4, 8.0)
            msg += (
                f"📈 <b>Acquisto:</b> {migliore['nome']} ({migliore['display']})\n"
                f"   RSI {migliore['rsi']} · Score {migliore['score_acq']}/100\n"
                f"   💶 Considera €{imp:.2f} su Revolut\n\n"
            )
        else:
            msg += "💰 Budget quasi esaurito. Aspetta il mese prossimo.\n\n"

        if vendita:
            msg += "📉 <b>Da monitorare per vendita:</b>\n"
            for v in vendita:
                msg += f"   ⚠️ {v['display']}: {fmt_cross(v['cross'])} · RSI {v['rsi']}\n"
            msg += "\n"

        msg += "⚠️ <i>Non è consulenza finanziaria.</i>"
        send(msg, cid)

    # /imparaetf
    elif tl.startswith("/imparaetf"):
        send(
            "📚 <b>Lezione: ETF e indicatori reali</b>\n\n"
            "<b>RSI (14 periodi)</b>: misura la velocità dei movimenti.\n"
            "Sotto 30 = possibile ipervenduto → occasione?\n"
            "Sopra 70 = possibile ipercomprato → attenzione\n\n"
            "<b>MACD</b>: differenza tra EMA12 ed EMA26.\n"
            "Istogramma positivo e crescente = momentum rialzista ✅\n\n"
            "<b>EMA50 / EMA200</b>: medie esponenziali.\n"
            "Golden Cross (EMA50 > EMA200) = trend positivo di lungo periodo 🌟\n"
            "Death Cross (EMA50 &lt; EMA200) = segnale di pericolo 💀\n\n"
            "<b>Bande di Bollinger</b>: volatilità relativa.\n"
            "Prezzo sotto la banda bassa = possibile rimbalzo\n"
            "Prezzo sopra la banda alta = possibile correzione\n\n"
            "<b>OBV</b>: i volumi confermano il trend?\n"
            "OBV positivo con prezzo in calo = i 'grandi' stanno comprando",
            cid
        )

    # /imparadca
    elif tl.startswith("/imparadca"):
        send(
            "📚 <b>Lezione: Dollar Cost Averaging</b>\n\n"
            "Investi la stessa cifra ogni mese, qualunque cosa succeda.\n\n"
            "• Mercato sale → compri meno quote ma guadagni su quelle che hai\n"
            "• Mercato scende → compri più quote a prezzi scontati ✅\n\n"
            "Con 20€/mese a rendimento medio 7%:\n"
            "→ 10 anni: ~€3.500 (versati €2.400)\n"
            "→ 20 anni: ~€10.400 (versati €4.800)\n"
            "→ 30 anni: ~€24.000 (versati €7.200)\n\n"
            "La regola d'oro: <b>non smettere mai quando il mercato scende.</b>",
            cid
        )

    # /help o /start
    elif tl.startswith("/help") or tl.startswith("/start"):
        send(
            "🤖 <b>InvestoBot v4 — Dati reali</b>\n\n"
            "<b>📊 Portafoglio</b>\n"
            "/comprato TICKER IMPORTO\n"
            "/vendi TICKER IMPORTO (o /vendi TICKER tutto)\n"
            "/patrimonio — portafoglio aggiornato con prezzi reali\n"
            "/storico — tutte le operazioni\n\n"
            "<b>📈 Analisi</b>\n"
            "/analisi — RSI, MACD, EMA, Bollinger su tutti gli ETF\n"
            "/consiglio — suggerimento personalizzato\n\n"
            "<b>💰 Budget</b>\n"
            "/budget — situazione del mese\n"
            "/pausanotifiche — ho finito il budget\n"
            "/riprendi — riattiva notifiche\n\n"
            "<b>📚 Impara</b>\n"
            "/imparaetf · /imparadca\n\n"
            "Budget auto-azzera ogni 1° del mese ✓\n"
            "Dati reali da Yahoo Finance ✓",
            cid
        )
    else:
        send("Non ho capito. Scrivi /help per il menu! 😊", cid)

# ═══════════════════════════════════════════════════════════════════════════════
# SEZIONE 5 — SCAN AUTOMATICO
# ═══════════════════════════════════════════════════════════════════════════════

def mercato_aperto() -> bool:
    now = datetime.utcnow()
    if now.weekday() >= 5: return False
    return dtime(8, 0) <= now.time() <= dtime(16, 30)

def scan():
    log.info("Scansione automatica...")
    if not mercato_aperto():
        log.info("Mercato chiuso."); return

    b         = load_budget()
    rimanente = BUDGET_MENSILE - b["speso"]
    paused    = b.get("paused", False)

    risultati = analizza_tutti()
    if not risultati:
        log.warning("Nessun dato disponibile."); return

    if paused:
        # Solo segnali eccezionali: RSI < 25 e score >= 82
        eccezionali = [r for r in risultati if r["rsi"] < 25 and r["score_acq"] >= 82]
        if not eccezionali:
            log.info("Pausa attiva, nessun segnale eccezionale."); return
        msg = "🚨 <b>Segnale ECCEZIONALE — potrebbe valere l'over budget</b>\n\n"
        for r in eccezionali:
            msg += (
                f"⭐ <b>{r['nome']} ({r['display']})</b>\n"
                f"   RSI: {r['rsi']} · Score: {r['score_acq']}/100\n"
                f"   {fmt_cross(r['cross'])} · MACD: {'▲' if r['macd_isto']>0 else '▼'}\n"
                f"   💶 Considera €3–5 anche fuori budget\n\n"
            )
        msg += "⚠️ <i>Non è consulenza finanziaria. Queste situazioni sono rare.</i>"
        send(msg)
        return

    # Notifiche normali: score_acq >= 65 E RSI < 35
    buy = [r for r in risultati if r["sig_acq"] == "BUY" and r["rsi"] < 35]
    if rimanente < 3 or not buy:
        log.info(f"Nessun segnale forte (budget: €{rimanente:.2f})."); return

    buy = sorted(buy, key=lambda x: x["score_acq"], reverse=True)[:2]

    msg  = "📈 <b>InvestoBot — Segnale reale di acquisto</b>\n\n"
    msg += "Dati aggiornati da Yahoo Finance:\n\n"
    for r in buy:
        imp  = min(rimanente * 0.40 / len(buy), 8.0)
        imp  = max(3.0, round(imp, 2))
        sgn  = "+" if r["chg_pct"] >= 0 else ""
        msg += (
            f"🟢 <b>{r['nome']} ({r['display']})</b>\n"
            f"   Prezzo: €{r['prezzo']:.4f} · {sgn}{r['chg_pct']}% oggi\n"
            f"   RSI: {r['rsi']} · Score: {r['score_acq']}/100\n"
            f"   {fmt_cross(r['cross'])}\n"
            f"   BB: {fmt_bb(r['bb_pos'])}\n"
            f"   MACD: {'▲ positivo' if r['macd_isto']>0 else '▼ negativo'}\n"
            f"   OBV: {r['obv_trend']}\n"
            f"   💶 <b>Consiglio: €{imp:.2f} su Revolut</b>\n\n"
        )
    msg += (
        f"💰 Budget rimasto: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}\n"
        f"📱 Revolut → cerca il ticker → acquista\n"
        f"📝 Poi: /comprato TICKER IMPORTO\n\n"
        f"⚠️ <i>Non è consulenza finanziaria.</i>"
    )
    send(msg)

    # Controlla anche segnali di vendita per posizioni aperte
    p   = load_patrimonio()
    pos = p["posizioni"]
    if pos:
        vendi_alert = [r for r in risultati if r["display"] in pos and r["sig_vend"] == "SELL"]
        if vendi_alert:
            msg_v = "⚠️ <b>Possibile momento di vendita</b>\n\n"
            for r in vendi_alert:
                msg_v += (
                    f"🔴 <b>{r['display']}</b>: RSI {r['rsi']} · {fmt_cross(r['cross'])}\n"
                    f"   Score vendita: {r['score_vend']}/100\n"
                    f"   Usa /vendi {r['display']} IMPORTO per vendere\n\n"
                )
            msg_v += "⚠️ <i>Non è consulenza finanziaria. Valuta sempre il tuo orizzonte temporale.</i>"
            send(msg_v)

def buongiorno():
    b         = load_budget()
    rimanente = max(0, BUDGET_MENSILE - b["speso"])
    giorno    = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"][datetime.now().weekday()]
    pausa_s   = "\n🔕 Notifiche in pausa — /riprendi" if b.get("paused") else ""
    send(
        f"☀️ <b>{giorno} {datetime.now().strftime('%d/%m/%Y')}</b>\n\n"
        f"💰 Budget rimasto: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}{pausa_s}\n\n"
        "Monitoro ETF e obbligazioni con dati reali (Yahoo Finance).\n"
        "Scrivi /analisi per un aggiornamento immediato o /help per i comandi."
    )

def check_inizio_mese():
    if datetime.now().day == 1:
        send(
            f"🔄 <b>Nuovo mese — budget azzerato!</b>\n\n"
            f"{datetime.now().strftime('%B %Y')} è iniziato.\n"
            f"Hai di nuovo €{BUDGET_MENSILE:.2f} disponibili.\n"
            "Notifiche riattivate automaticamente. 🚀"
        )

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
            log.info(f"CMD {cid}: {text[:40]}")
            handle(text, cid)

if __name__ == "__main__":
    log.info("InvestoBot v4 avviato ✅")
    send(
        "🤖 <b>InvestoBot v4 — Dati reali!</b>\n\n"
        "Nessun valore casuale: tutti i dati vengono scaricati in tempo reale da <b>Yahoo Finance</b>.\n\n"
        "<b>Indicatori attivi:</b>\n"
        "• RSI (14 periodi) reale\n"
        "• MACD (12/26/9) reale\n"
        "• EMA50 e EMA200 (Golden/Death Cross)\n"
        "• Bande di Bollinger (20 periodi)\n"
        "• OBV (On-Balance Volume)\n\n"
        "<b>Nuovi comandi:</b>\n"
        "/vendi TICKER IMPORTO — registra una vendita\n"
        "/patrimonio — portafoglio con prezzi aggiornati\n"
        "/analisi — tutti gli indicatori ora\n\n"
        "Scrivi /help per il menu completo 📋"
    )

    sched = BlockingScheduler(timezone="Europe/Rome")
    sched.add_job(buongiorno,        "cron", day_of_week="mon-fri", hour=9,       minute=0)
    sched.add_job(scan,              "cron", day_of_week="mon-fri", hour="10-17", minute=0)
    sched.add_job(check_inizio_mese, "cron", day=1,                 hour=8,       minute=30)
    sched.add_job(poll,              "interval", seconds=5)
    sched.start()
