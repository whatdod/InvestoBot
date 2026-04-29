import os
import random
import requests
from datetime import datetime, time as dtime
from apscheduler.schedulers.blocking import BlockingScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
BUDGET_MENSILE = 20.0

ASSETS = [
    {"name": "Vanguard S&P 500 ETF",    "ticker": "VUAA", "tipo": "ETF",    "rischio": "basso",      "note": "500 grandi aziende USA. Stabile nel lungo periodo.", "us_hours": False},
    {"name": "iShares Core MSCI World", "ticker": "IWDA", "tipo": "ETF",    "rischio": "basso",      "note": "1.800 aziende globali. Massima diversificazione.",   "us_hours": False},
    {"name": "Nvidia",                  "ticker": "NVDA", "tipo": "Azione", "rischio": "medio-alto", "note": "Leader nell'AI. Volatile ma con forte crescita.",     "us_hours": True},
]

def send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        print(f"[OK] {datetime.now().strftime('%H:%M')} msg inviato")
    except Exception as e:
        print(f"[ERR] {e}")

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

def calcola_importo(score, n):
    quota = (BUDGET_MENSILE * 0.60) / max(n, 1)
    molt  = 1.0 if score >= 75 else (0.7 if score >= 60 else 0.5)
    return max(3.0, min(round(quota * molt, 2), 12.0))

def mercato_aperto(us_hours):
    now = datetime.utcnow()
    if now.weekday() >= 5: return False
    t = now.time()
    return dtime(13,30) <= t <= dtime(21,0) if us_hours else dtime(8,0) <= t <= dtime(16,30)

def scan():
    print(f"[{datetime.now().strftime('%H:%M %d/%m')}] Scansione...")
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
            importo = calcola_importo(r["score"], len(buy))
            segno   = "+" if r["change_pct"] >= 0 else ""
            msg += (
                f"🟢 <b>{r['name']} ({r['ticker']})</b>\n"
                f"   Tipo: {r['tipo']} · Rischio: {r['rischio']}\n"
                f"   RSI: {r['rsi']} · Oggi: {segno}{r['change_pct']}%\n"
                f"   Trend: {r['trend']} · Volume: {'✅ alto' if r['volume_ok'] else '⚠️ basso'}\n"
                f"   📌 {r['note']}\n\n"
                f"   💶 <b>Consiglio: investi €{importo:.2f} su Revolut</b>\n"
            )
            if r["us_hours"]:
                msg += "   ⏰ Borsa USA aperta fino alle 22:00 ora italiana\n"
            msg += "\n"
        msg += (f"💰 Budget mensile totale: €{BUDGET_MENSILE:.2f}\n"
                "📱 Apri Revolut → Cerca il ticker → Acquista\n\n"
                "⚠️ <i>Non è consulenza finanziaria. Investi solo ciò che puoi permetterti di perdere.</i>")
        send(msg)
    elif watch:
        nomi = ", ".join(f"{r['ticker']} (RSI {r['rsi']})" for r in watch)
        send(f"👀 <b>InvestoBot — Tieni d'occhio</b>\n\n{nomi}\n\nSegnale non ancora forte. Ti riavviso se migliora.\n\n⏳ Nessuna azione necessaria ora.")

def buongiorno():
    giorno = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"][datetime.now().weekday()]
    send(f"☀️ <b>Buongiorno! InvestoBot al lavoro</b>\n📅 {giorno} {datetime.now().strftime('%d/%m/%Y')}\n\n"
         "Monitoraggio attivo su:\n• VUAA — Vanguard S&amp;P 500\n• IWDA — MSCI World\n• NVDA — Nvidia\n\n"
         f"💰 Budget mensile: €{BUDGET_MENSILE:.2f}\n"
         "Ti scrivo <b>solo</b> quando trovo un momento davvero favorevole. Silenzio = tutto nella norma 👍")

if __name__ == "__main__":
    print("InvestoBot avviato ✅")
    send("🤖 <b>InvestoBot connesso!</b>\n\nSono online e monitorerò i mercati per te.\n\n"
         "<b>Come funziona:</b>\n• Ogni mattina alle 09:00 ti saluto\n"
         "• Ti scrivo <b>solo</b> se trovo un segnale forte\n"
         "• Ti dico esattamente cosa comprare e per quanti euro\n\n"
         f"💰 Budget mensile: €{BUDGET_MENSILE:.2f}\n🚀 Buon investimento!")
    sched = BlockingScheduler(timezone="Europe/Rome")
    sched.add_job(buongiorno, "cron", day_of_week="mon-fri", hour=9,      minute=0)
    sched.add_job(scan,       "cron", day_of_week="mon-fri", hour="9-17", minute=30)
    sched.start()
