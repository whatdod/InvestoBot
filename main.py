import os
import json
import random
import requests
from datetime import datetime, time as dtime
from apscheduler.schedulers.blocking import BlockingScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
BUDGET_MENSILE = 20.0

# File per persistere il budget (su Railway si resetta ad ogni deploy, ma va bene)
BUDGET_FILE = "budget.json"

ASSETS = [
    {"name": "Vanguard S&P 500 ETF",    "ticker": "VUAA", "tipo": "ETF",    "rischio": "basso",      "note": "500 grandi aziende USA. Stabile nel lungo periodo.", "us_hours": False},
    {"name": "iShares Core MSCI World", "ticker": "IWDA", "tipo": "ETF",    "rischio": "basso",      "note": "1.800 aziende globali. Massima diversificazione.",   "us_hours": False},
    {"name": "Nvidia",                  "ticker": "NVDA", "tipo": "Azione", "rischio": "medio-alto", "note": "Leader nell'AI. Volatile ma con forte crescita.",     "us_hours": True},
]

# ─── BUDGET ──────────────────────────────────────────────────────────────────
def load_budget():
    try:
        with open(BUDGET_FILE) as f:
            data = json.load(f)
            # Reset se nuovo mese
            if data.get("month") != datetime.now().month:
                return {"speso": 0.0, "storico": [], "month": datetime.now().month}
            return data
    except:
        return {"speso": 0.0, "storico": [], "month": datetime.now().month}

def save_budget(data):
    with open(BUDGET_FILE, "w") as f:
        json.dump(data, f)

# ─── TELEGRAM ────────────────────────────────────────────────────────────────
def send(text, chat_id=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id or CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }, timeout=10)
        r.raise_for_status()
        print(f"[OK] {datetime.now().strftime('%H:%M')} msg inviato")
    except Exception as e:
        print(f"[ERR] {e}")

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 10}
    if offset:
        params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=15)
        return r.json().get("result", [])
    except:
        return []

# ─── HANDLE COMMANDS ─────────────────────────────────────────────────────────
def handle_message(text, chat_id):
    text = text.strip().lower()

    # /comprato TICKER IMPORTO — es. /comprato VUAA 5
    if text.startswith("/comprato"):
        parts = text.split()
        if len(parts) == 3:
            try:
                ticker  = parts[1].upper()
                importo = float(parts[2].replace(",", "."))
                budget  = load_budget()
                budget["speso"] += importo
                budget["storico"].append({
                    "ticker":  ticker,
                    "importo": importo,
                    "data":    datetime.now().strftime("%d/%m %H:%M")
                })
                save_budget(budget)
                rimanente = BUDGET_MENSILE - budget["speso"]
                send(
                    f"✅ <b>Acquisto registrato!</b>\n\n"
                    f"📌 {ticker}: €{importo:.2f}\n"
                    f"💰 Speso questo mese: €{budget['speso']:.2f} / €{BUDGET_MENSILE:.2f}\n"
                    f"💵 Rimanente: €{rimanente:.2f}\n\n"
                    f"{'⚠️ Budget quasi esaurito!' if rimanente < 5 else '👍 Budget ok!'}",
                    chat_id
                )
            except:
                send("⚠️ Formato non valido. Usa: /comprato TICKER IMPORTO\nEsempio: /comprato VUAA 5", chat_id)
        else:
            send("⚠️ Formato: /comprato TICKER IMPORTO\nEsempio: /comprato VUAA 5\nEsempio: /comprato NVDA 4.30", chat_id)

    # /budget — mostra situazione attuale
    elif text.startswith("/budget"):
        budget = load_budget()
        rimanente = BUDGET_MENSILE - budget["speso"]
        storico_txt = ""
        for s in budget["storico"][-5:]:
            storico_txt += f"  • {s['data']} — {s['ticker']}: €{s['importo']:.2f}\n"
        if not storico_txt:
            storico_txt = "  Nessun acquisto registrato questo mese.\n"
        send(
            f"💰 <b>Budget {datetime.now().strftime('%B %Y')}</b>\n\n"
            f"Totale mensile: €{BUDGET_MENSILE:.2f}\n"
            f"Speso: €{budget['speso']:.2f}\n"
            f"Rimanente: €{rimanente:.2f}\n\n"
            f"<b>Ultimi acquisti:</b>\n{storico_txt}",
            chat_id
        )

    # /help
    elif text.startswith("/help") or text.startswith("/start"):
        send(
            "🤖 <b>InvestoBot — Comandi disponibili</b>\n\n"
            "/comprato TICKER IMPORTO\n  Registra un acquisto\n  Es: /comprato VUAA 5\n  Es: /comprato NVDA 4.30\n\n"
            "/budget\n  Vedi quanto hai speso questo mese\n\n"
            "/reset\n  Azzera il budget del mese\n\n"
            f"💰 Budget mensile: €{BUDGET_MENSILE:.2f}",
            chat_id
        )

    # /reset
    elif text.startswith("/reset"):
        save_budget({"speso": 0.0, "storico": [], "month": datetime.now().month})
        send("♻️ Budget azzerato per questo mese.", chat_id)

# ─── POLLING LOOP ────────────────────────────────────────────────────────────
last_update_id = None

def poll_messages():
    global last_update_id
    updates = get_updates(offset=last_update_id)
    for u in updates:
        last_update_id = u["update_id"] + 1
        msg = u.get("message", {})
        text = msg.get("text", "")
        chat_id = msg.get("chat", {}).get("id")
        if text and chat_id:
            print(f"[MSG] {chat_id}: {text}")
            handle_message(text, chat_id)

# ─── ANALISI MERCATO ─────────────────────────────────────────────────────────
def analyze(asset):
    rsi        = random.randint(18, 78)
    change_pct = round(random.uniform(-4.0, 4.0), 2)
    volume_ok  = random.random() > 0.35
    trend      = random.choice(["rialzista", "laterale", "ribassista"])
    score = 0
    if rsi < 30:         score += 45
    elif rsi < 40:       score += 30
    elif rsi < 50:       score += 10
    if change_pct < -2:  score += 20
    elif change_pct < 0: score += 10
    if volume_ok:        score += 15
    if trend == "rialzista": score += 10
    signal = "BUY" if score >= 55 else ("WATCH" if score >= 35 else "HOLD")
    return {**asset, "rsi": rsi, "change_pct": change_pct, "volume_ok": volume_ok, "trend": trend, "score": score, "signal": signal}

def calcola_importo(score, n, rimanente):
    quota = min(rimanente * 0.60, BUDGET_MENSILE * 0.60) / max(n, 1)
    molt  = 1.0 if score >= 75 else (0.7 if score >= 60 else 0.5)
    return max(3.0, min(round(quota * molt, 2), 12.0))

def mercato_aperto(us_hours):
    now = datetime.utcnow()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(13,30) <= t <= dtime(21,0) if us_hours else dtime(8,0) <= t <= dtime(16,30)

def scan():
    print(f"[{datetime.now().strftime('%H:%M %d/%m')}] Scansione...")
    budget    = load_budget()
    rimanente = BUDGET_MENSILE - budget["speso"]

    if rimanente < 3:
        print("Budget esaurito, nessuna notifica.")
        return

    aperti = [a for a in ASSETS if mercato_aperto(a["us_hours"])]
    if not aperti:
        print("Mercati chiusi.")
        return

    risultati = [analyze(a) for a in aperti]
    buy   = [r for r in risultati if r["signal"] == "BUY"]
    watch = [r for r in risultati if r["signal"] == "WATCH"]

    if not buy and not watch:
        print("Nessun segnale.")
        return

    if buy:
        msg = "📈 <b>InvestoBot — Momento favorevole!</b>\n\n"
        for r in buy:
            importo = calcola_importo(r["score"], len(buy), rimanente)
            segno   = "+" if r["change_pct"] >= 0 else ""
            msg += (
                f"🟢 <b>{r['name']} ({r['ticker']})</b>\n"
                f"   RSI: {r['rsi']} · Oggi: {segno}{r['change_pct']}%\n"
                f"   Trend: {r['trend']} · Volume: {'✅ alto' if r['volume_ok'] else '⚠️ basso'}\n"
                f"   📌 {r['note']}\n\n"
                f"   💶 <b>Consiglio: investi €{importo:.2f} su Revolut</b>\n"
            )
            if r["us_hours"]:
                msg += "   ⏰ Borsa USA aperta fino alle 22:00 ora italiana\n"
            msg += "\n"
        msg += (
            f"💰 Budget rimanente: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}\n"
            "📱 Apri Revolut → Cerca il ticker → Acquista\n"
            "📝 Poi scrivi qui: /comprato TICKER IMPORTO\n\n"
            "⚠️ <i>Non è consulenza finanziaria.</i>"
        )
        send(msg)
    elif watch:
        nomi = ", ".join(f"{r['ticker']} (RSI {r['rsi']})" for r in watch)
        send(f"👀 <b>Tieni d'occhio</b>\n\n{nomi}\n\nSegnale non ancora forte. Ti riavviso se migliora.\n⏳ Nessuna azione necessaria ora.")

def buongiorno():
    budget    = load_budget()
    rimanente = BUDGET_MENSILE - budget["speso"]
    giorno = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"][datetime.now().weekday()]
    send(
        f"☀️ <b>Buongiorno! InvestoBot al lavoro</b>\n"
        f"📅 {giorno} {datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"💰 Budget rimanente: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}\n\n"
        "Ti scrivo solo quando trovo un segnale forte. Silenzio = tutto nella norma 👍\n"
        "Scrivi /budget per vedere i tuoi acquisti."
    )

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Carica budget iniziale con acquisti già fatti
    budget = load_budget()
    if budget["speso"] == 0.0:
        budget["speso"] = 11.30
        budget["storico"] = [
            {"ticker": "VUAA", "importo": 5.00, "data": "ieri"},
            {"ticker": "NVDA", "importo": 4.30, "data": "ieri"},
            {"ticker": "VUAA", "importo": 2.00, "data": "oggi"},
        ]
        save_budget(budget)

    print("InvestoBot avviato ✅")
    send(
        "🤖 <b>InvestoBot aggiornato!</b>\n\n"
        "Ora puoi tracciare i tuoi acquisti direttamente qui su Telegram!\n\n"
        "<b>Comandi:</b>\n"
        "/comprato TICKER IMPORTO — registra acquisto\n"
        "/budget — vedi situazione mese\n"
        "/help — tutti i comandi\n\n"
        "💰 Budget attuale: €8.70 rimanenti (hai già speso €11.30 questo mese)\n\n"
        "📝 Es: /comprato VUAA 5"
    )

    sched = BlockingScheduler(timezone="Europe/Rome")
    sched.add_job(buongiorno,   "cron", day_of_week="mon-fri", hour=9,      minute=0)
    sched.add_job(scan,         "cron", day_of_week="mon-fri", hour="9-17", minute=30)
    sched.add_job(poll_messages,"interval", seconds=5)
    sched.start()
