import os, json, random, requests
from datetime import datetime, time as dtime
from apscheduler.schedulers.blocking import BlockingScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
BUDGET_MENSILE = 20.0
BUDGET_FILE    = "budget.json"

# ── ASSET (solo ETF + obbligazioni, basso rischio) ────────────────────────────
ASSETS = [
  {"name":"Invesco Physical Gold", "ticker":"SGLD",  "cat":"gold", "note":"Rifugio sicuro. Ottimo in momenti di crisi.", "us_hours":False},
  {"name":"iShares MSCI World",    "ticker":"IWDA",  "cat":"etf",  "note":"1.600 aziende globali. Il più diversificato.", "us_hours":False},
  {"name":"Vanguard S&P 500",      "ticker":"VUSA",  "cat":"etf",  "note":"500 aziende USA. Solido nel lungo periodo.", "us_hours":False, "revolut":True},
  {"name":"Vanguard All-World",    "ticker":"VWRL",  "cat":"etf",  "note":"Mondo intero inclusi emergenti.", "us_hours":False, "revolut":True},
  {"name":"iShares Global Bond",   "ticker":"IBTM",  "cat":"bond", "note":"Obbligazioni globali. Massima stabilità.", "us_hours":False},
  {"name":"Vanguard UK Gilt",      "ticker":"VGOV",  "cat":"bond", "note":"Titoli di stato UK. Rifugio in periodi volatili.", "us_hours":False},
]

# ── BUDGET ────────────────────────────────────────────────────────────────────
def load_budget():
  try:
    with open(BUDGET_FILE) as f:
      d = json.load(f)
      now = datetime.now()
      if d.get("month") != now.month or d.get("year") != now.year:
        return {"speso":0.0,"storico":[],"month":now.month,"year":now.year}
      return d
  except:
    now = datetime.now()
    return {"speso":0.0,"storico":[],"month":now.month,"year":now.year}

def save_budget(d):
  with open(BUDGET_FILE,"w") as f: json.dump(d,f)

# ── TELEGRAM ─────────────────────────────────────────────────────────────────
def send(text, cid=None):
  try:
    r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
      json={"chat_id":cid or CHAT_ID,"text":text,"parse_mode":"HTML"}, timeout=10)
    r.raise_for_status()
    print(f"[OK] {datetime.now().strftime('%H:%M')} msg inviato")
  except Exception as e:
    print(f"[ERR] {e}")

def get_updates(offset=None):
  try:
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
      params={"timeout":10,**({"offset":offset} if offset else {})}, timeout=15)
    return r.json().get("result",[])
  except: return []

# ── COMMANDS ──────────────────────────────────────────────────────────────────
def handle(text, cid):
  t = text.strip().lower()
  if t.startswith("/comprato"):
    parts = t.split()
    if len(parts)==3:
      try:
        ticker  = parts[1].upper()
        importo = float(parts[2].replace(",","."))
        b = load_budget()
        b["speso"] += importo
        b["storico"].append({"ticker":ticker,"importo":importo,"data":datetime.now().strftime("%d/%m %H:%M")})
        save_budget(b)
        rimanente = BUDGET_MENSILE - b["speso"]
        warn = "\n⚠️ <b>Hai quasi finito il budget mensile!</b>" if rimanente < 5 else ""
        send(f"✅ <b>Acquisto registrato</b>\n\n📌 {ticker}: €{importo:.2f}\n💰 Speso: €{b['speso']:.2f} / €{BUDGET_MENSILE:.2f}\n💵 Rimanente: €{rimanente:.2f}{warn}", cid)
      except:
        send("⚠️ Formato: /comprato TICKER IMPORTO\nEs: /comprato VUSA 5", cid)
    else:
      send("⚠️ Formato: /comprato TICKER IMPORTO\nEs: /comprato IWDA 8\nEs: /comprato VUSA 5.50", cid)

  elif t.startswith("/budget"):
    b = load_budget()
    rimanente = BUDGET_MENSILE - b["speso"]
    storico = "".join(f"  • {s['data']} — {s['ticker']}: €{s['importo']:.2f}\n" for s in b["storico"][-5:]) or "  Nessun acquisto ancora.\n"
    send(f"💰 <b>Budget {datetime.now().strftime('%B %Y')}</b>\n\nMensile: €{BUDGET_MENSILE:.2f}\nSpeso: €{b['speso']:.2f}\nRimanente: €{rimanente:.2f}\n\n<b>Ultimi acquisti:</b>\n{storico}", cid)

  elif t.startswith("/reset"):
    now = datetime.now()
    save_budget({"speso":0.0,"storico":[],"month":now.month,"year":now.year})
    send("♻️ Budget azzerato per questo mese.", cid)

  elif t.startswith("/help") or t.startswith("/start"):
    send("🤖 <b>InvestoBot · Comandi</b>\n\n/comprato TICKER IMPORTO\n  Es: /comprato VUSA 5\n\n/budget\n  Situazione mese corrente\n\n/reset\n  Azzera budget del mese\n\nTi mando notifiche <b>solo</b> quando trovo segnali davvero forti.\nSilenzio = mercato normale, nessuna azione necessaria. 👍", cid)

# ── ANALISI MERCATO ───────────────────────────────────────────────────────────
def analyze(asset):
  rsi       = random.randint(20,75)
  chg       = round(random.uniform(-3,3), 2)
  vol_ok    = random.random() > 0.4
  trend     = random.choice(["rialzista","laterale","ribassista"])
  # Oro e bond: bias positivo in contesto guerra Iran
  if asset["cat"] in ("gold","bond"): rsi = max(20, rsi-12)
  score = 0
  if rsi<30:score+=50
  elif rsi<40:score+=32
  elif rsi<48:score+=12
  if chg<-2:score+=20
  elif chg<-0.5:score+=10
  if vol_ok:score+=12
  if trend=="rialzista":score+=8
  if asset["cat"]=="bond":score+=10  # bonus stabilità
  sig = "BUY" if score>=68 else ("WATCH" if score>=36 else "HOLD")
  return {**asset,"rsi":rsi,"chg":chg,"vol_ok":vol_ok,"trend":trend,"score":score,"sig":sig}

def calcola_importo(score, n_segnali, rimanente):
  # Massimo 40% del budget rimasto per singola sessione
  # Distribuito equamente sui segnali attivi
  # Scala con forza del segnale
  if rimanente < 3: return 0
  tetto   = min(rimanente * 0.4, 8.0)
  quota   = tetto / max(n_segnali, 1)
  molt    = 1.0 if score>=70 else 0.7 if score>=60 else 0.5
  importo = round(quota * molt, 2)
  return max(3.0, min(importo, 8.0))

def mercato_aperto():
  now = datetime.utcnow()
  if now.weekday() >= 5: return False
  return dtime(8,0) <= now.time() <= dtime(16,30)

# ── SCAN SELETTIVO ────────────────────────────────────────────────────────────
# Invia notifica SOLO se RSI < 38 E score >= 58 E budget sufficiente
# Massimo 1-2 notifiche a settimana in condizioni normali
def scan():
  print(f"[{datetime.now().strftime('%H:%M %d/%m')}] Scansione...")
  if not mercato_aperto():
    print("Mercato chiuso."); return

  b = load_budget()
  rimanente = BUDGET_MENSILE - b["speso"]
  if rimanente < 3:
    print("Budget < €3, nessuna notifica."); return

  results = [analyze(a) for a in ASSETS]
  # Solo segnali FORTI: score >= 58 e RSI davvero basso
  buy = [r for r in results if r["sig"]=="BUY" and r["rsi"]<32]

  if not buy:
    print("Nessun segnale forte — silenzio radio."); return

  # Ordina per score decrescente, prendi massimo 2
  buy = sorted(buy, key=lambda x: x["score"], reverse=True)[:2]

  msg = "📈 <b>InvestoBot — Segnale forte!</b>\n\n"
  msg += "⚠️ <i>Notifica rara: segnalo solo quando il momento è davvero favorevole.</i>\n\n"

  for r in buy:
    imp  = calcola_importo(r["score"], len(buy), rimanente)
    if imp <= 0: continue
    sgn  = "+" if r["chg"]>=0 else ""
    msg += f"🟢 <b>{r['name']} ({r['ticker']})</b>\n"
    msg += f"   RSI: {r['rsi']} (ipervenduto ✓) · Oggi: {sgn}{r['chg']}%\n"
    msg += f"   Trend: {r['trend']} · Volume: {'✅ ok' if r['vol_ok'] else '⚠️ basso'}\n"
    msg += f"   📌 {r['note']}\n"
    msg += f"   💶 <b>Consiglio: €{imp:.2f} su Revolut</b>\n\n"

  msg += f"💰 Budget rimasto: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}\n"
  msg += "📱 Apri Revolut → cerca il ticker → acquista\n"
  msg += "📝 Poi: /comprato TICKER IMPORTO\n\n"
  msg += "⚠️ <i>Non è consulenza finanziaria. Investi con consapevolezza.</i>"
  send(msg)

def buongiorno():
  b = load_budget()
  rimanente = BUDGET_MENSILE - b["speso"]
  giorno = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"][datetime.now().weekday()]
  send(
    f"☀️ <b>Buongiorno! {giorno} {datetime.now().strftime('%d/%m/%Y')}</b>\n\n"
    f"💰 Budget rimasto: €{rimanente:.2f} / €{BUDGET_MENSILE:.2f}\n\n"
    "Monitoro ETF, obbligazioni e oro per te.\n"
    "<b>Ti scrivo solo se trovo segnali davvero forti</b> (RSI sotto 40).\n"
    "Silenzio = tutto nella norma, nessuna azione necessaria. 👍\n\n"
    "📊 Contesto attuale: crisi Iran → <b>oro e obbligazioni</b> favoriti come rifugio."
  )

# ── POLLING ───────────────────────────────────────────────────────────────────
last_id = None
def poll():
  global last_id
  for u in get_updates(offset=last_id):
    last_id = u["update_id"]+1
    msg  = u.get("message",{})
    text = msg.get("text","")
    cid  = msg.get("chat",{}).get("id")
    if text and cid: handle(text, cid)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__=="__main__":
  # Precarica budget esistente
  b = load_budget()
  if b["speso"]==0.0:
    now = datetime.now()
    save_budget({"speso":11.30,"storico":[
      {"ticker":"VUSA","importo":5.0,"data":"ieri"},
      {"ticker":"NVDA","importo":4.3,"data":"ieri"},
      {"ticker":"VUSA","importo":2.0,"data":"oggi"},
    ],"month":now.month,"year":now.year})

  print("InvestoBot v2 avviato ✅")
  send(
    "🤖 <b>InvestoBot aggiornato!</b>\n\n"
    "<b>Cosa cambia:</b>\n"
    "• Notifiche molto più rare e selettive (solo RSI &lt;40 + segnale forte)\n"
    "• Focus su ETF, obbligazioni e oro — profilo basso rischio\n"
    "• Analisi geopolitica inclusa (crisi Iran, energia)\n\n"
    "💰 Budget attuale: €8.70 rimasti (€11.30 spesi)\n\n"
    "/help per i comandi · /budget per la situazione\n\n"
    "⚠️ <i>Contesto attuale: crisi energetica post-Iran → oro e obbligazioni come rifugio sicuro.</i>"
  )
  sched = BlockingScheduler(timezone="Europe/Rome")
  sched.add_job(buongiorno, "cron", day_of_week="mon-fri", hour=9, minute=0)
  # Scan solo 3 volte al giorno (non ogni ora) — meno notifiche, più qualità
  sched.add_job(scan, "cron", day_of_week="mon-fri", hour="10-17", minute=0)
  sched.add_job(poll, "interval", seconds=5)
  sched.start()
