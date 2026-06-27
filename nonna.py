"""
InvestoBot — Modulo "Buongiornissimo Nonna"
Pesca immagini REALI già pronte (con testo incorporato) da Giphy,
libreria pubblica con migliaia di GIF/immagini "buongiorno" e
"buonanotte" in stile italiano. Nessuna didascalia separata:
manda solo l'immagine, pronta da inoltrare.
Ogni tot immagini, una dedica a tema nonna.
Riconosce le festività italiane (aggiunge solo in quel caso
un piccolo testo Telegram sopra, il resto è muto).
"""
import os, random, requests
from datetime import date, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GIPHY_KEY      = os.environ.get("GIPHY_KEY", "")  # chiave gratuita da developers.giphy.com
CHAT_IDS = [
    os.environ.get("CHAT_ID", "43443426"),
    "495866880",
]
MOMENTO = os.environ.get("MOMENTO", "mattina")

# ── FESTIVITÀ ITALIANE ────────────────────────────────────────────────────────
FESTIVITA_FISSE = {
    (1,1):"🎉 BUON ANNO NUOVO 🎉", (1,6):"✨ BUONA EPIFANIA ✨",
    (4,25):"🇮🇹 BUONA FESTA DELLA LIBERAZIONE 🇮🇹", (5,1):"👷 BUON PRIMO MAGGIO 👷",
    (6,2):"🇮🇹 BUONA FESTA DELLA REPUBBLICA 🇮🇹", (8,15):"🌞 BUON FERRAGOSTO 🌞",
    (11,1):"🕯️ BUON OGNISSANTI 🕯️", (12,8):"🎄 BUONA IMMACOLATA 🎄",
    (12,25):"🎄 BUON NATALE 🎄", (12,26):"🎄 BUON SANTO STEFANO 🎄",
    (12,31):"🎊 BUON ULTIMO DELL'ANNO 🎊",
}

def calcola_pasqua(anno):
    a=anno%19; b=anno//100; c=anno%100; d=b//4; e=b%4; f=(b+8)//25
    g=(b-f+1)//3; h=(19*a+b-d-g+15)%30; i=c//4; k=c%4
    l=(32+2*e+2*i-h-k)%7; m=(a+11*h+22*l)//451
    mese=(h+l-7*m+114)//31; giorno=((h+l-7*m+114)%31)+1
    return date(anno,mese,giorno)

def get_festivita_oggi():
    oggi = date.today()
    if (oggi.month,oggi.day) in FESTIVITA_FISSE:
        return FESTIVITA_FISSE[(oggi.month,oggi.day)]
    pasqua = calcola_pasqua(oggi.year)
    if oggi == pasqua: return "🐣 BUONA PASQUA 🐣"
    if oggi == pasqua + timedelta(days=1): return "🐰 BUONA PASQUETTA 🐰"
    return None

# ── RICERCA TAG SU GIPHY (immagini/gif con testo incorporato) ────────────────
TAG_MATTINA = ["buongiorno", "good morning italian", "buongiorno caffe", "good morning flowers"]
TAG_SERA    = ["buonanotte", "good night italian", "buonanotte stelle"]
TAG_NONNA   = ["nonna", "grandma italian", "buongiorno nonna"]

def fonte_giphy(tags: list) -> str | None:
    """Cerca su Giphy e restituisce l'URL diretto di un'immagine statica (non gif animata)."""
    if not GIPHY_KEY:
        print("[giphy] GIPHY_KEY non configurata")
        return None
    tag = random.choice(tags)
    try:
        r = requests.get(
            "https://api.giphy.com/v1/gifs/search",
            params={"api_key": GIPHY_KEY, "q": tag, "lang": "it",
                    "limit": 25, "rating": "g"},
            timeout=15
        )
        data = r.json().get("data", [])
        if not data:
            return None
        scelta = random.choice(data)
        # Usa il preview statico (immagine fissa), non la gif animata,
        # perché va inoltrata come foto su Telegram
        return scelta["images"]["original_still"]["url"]
    except Exception as e:
        print(f"[giphy] {e}")
        return None

def fonte_cat_api() -> str | None:
    """Fallback finale: foto reale di gatto (sempre disponibile)."""
    try:
        r = requests.get("https://api.thecatapi.com/v1/images/search", timeout=10)
        return r.json()[0]["url"]
    except Exception as e:
        print(f"[cat_api] {e}")
        return None

def get_immagine(tipo: str) -> str | None:
    tags = {"mattina": TAG_MATTINA, "sera": TAG_SERA, "nonna": TAG_NONNA}[tipo]
    return fonte_giphy(tags) or fonte_cat_api()

# ── CONTATORE ──────────────────────────────────────────────────────────────────
COUNTER_FILE = "nonna_counter.txt"
OGNI_QUANTI_NONNA = 5

def get_e_incrementa_contatore():
    n = 0
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE) as f:
                n = int(f.read().strip())
        except:
            n = 0
    n += 1
    with open(COUNTER_FILE, "w") as f:
        f.write(str(n))
    return n

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_photo(url: str, caption: str, cid: str) -> bool:
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": cid, "photo": url, "caption": caption, "parse_mode": "HTML"},
            timeout=20
        ).raise_for_status()
        print(f"✅ Foto inviata a {cid}")
        return True
    except Exception as e:
        print(f"❌ Errore foto a {cid}: {e}")
        return False

def send_text(text: str, cid: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
    except Exception as e:
        print(f"❌ Errore testo a {cid}: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    festivita = get_festivita_oggi()
    contatore = get_e_incrementa_contatore()
    is_dedica_nonna = (contatore % OGNI_QUANTI_NONNA == 0)

    tipo = "nonna" if is_dedica_nonna else MOMENTO
    img  = get_immagine(tipo)

    # Nessuna didascalia normale: solo la foto.
    # Unica eccezione: nei giorni di festa, un piccolo testo sopra l'immagine.
    caption = festivita if festivita else ""

    for cid in CHAT_IDS:
        if img:
            ok = send_photo(img, caption, cid)
            if not ok:
                send_text(caption or "📷", cid)
        else:
            send_text(caption or "📷 Nessuna immagine trovata oggi.", cid)

    tipo_log = "DEDICA NONNA" if is_dedica_nonna else MOMENTO.upper()
    print(f"✅ Inviato — tipo: {tipo_log} — contatore: {contatore} — festività: {festivita or 'nessuna'}")

if __name__ == "__main__":
    main()
