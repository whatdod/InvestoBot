"""
InvestoBot — Modulo "Buongiornissimo Nonna"
Pesca immagini REALI già pronte da librerie online gratuite
(non generate, non create da noi) e le manda via Telegram
con una didascalia in stile "Buongiornissimo".
Ogni tot immagini, una dedica speciale a tema nonna.
Riconosce le festività italiane.
"""
import os, random, requests
from datetime import date, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
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

# ── DIDASCALIE (testo Telegram separato dalla foto, stile buongiornissimo) ───
DIDASCALIE_MATTINA = [
    "☕🌻✨ <b>BUONGIORNISSIMO KAFFEEEE!!!</b> ☕☕☕\nChe questa giornata sia bollente come il caffè e dolce come il miele! 🍯",
    "🌞🌸🦋 <b>UN'ALTRA GIORNATA BOLLENTE!!! BUONGIORNO!!!</b> ☀️\nSorridete sempre, vi voglio bene amici miei 💖",
    "🐦🌷💐 <b>BUONGIORNO A TUTTI VOI!!!</b> 🌅\nChi vi ama vi pensa sempre, anche quando non lo dice ❤️",
    "☕🧁🌼 <b>BUONGIORNISSIMO AMICI MIEI!!!</b> ☕✨\nLa vita è come il caffè: amara senza il giusto zucchero di allegria! 😄",
    "🌅🕊️💕 <b>SVEGLIA SVEGLIAAA!!! È GIÀ MATTINA!!!</b> ☀️\nOgni nuovo giorno è un regalo, apritelo col sorriso! 🎁",
    "🌻🦋☕ <b>BUONGIORNO CON IL SOLE PER VOI!!!</b> 🌞\nChi semina sorrisi raccoglie amicizie! 🌱💛",
    "💐🐝🌸 <b>BUONGIORNISSIMO E BUON INIZIO SETTIMANA!!!</b> 🎉\nVoi siete più forti di ogni difficoltà! 💪😘",
    "🌺🦜🍃 <b>BUONGIORNO TROPICALE A TUTTI!!!</b> 🌴\nLa felicità non si compra, si regala... eccola! 🎁❤️",
]

DIDASCALIE_SERA = [
    "🌙⭐🕯️ <b>BUONANOTTE A TUTTI VOI!!!</b> 😴\nChe i sogni siano dolci come una fetta di torta! 🍰💕",
    "🌌💫🌃 <b>BUONA NOTTE STELLATA AMICI MIEI!!!</b> ✨\nDomani sarà un giorno migliore, ora riposatevi! 😘",
    "🌙🦉🕊️ <b>È ORA DI ANDARE A NANNA!!!</b> 😴💤\nVi auguro la buonanotte più dolce di sempre 💕",
    "✨🌃🛏️ <b>BUONANOTTE CON UN ABBRACCIO VIRTUALE!!!</b> 🤗\nLasciate andare i pensieri della giornata 🌅",
    "🌙🍃🕯️ <b>LA LUNA VI AUGURA BUONANOTTE!!!</b> 🌕\nChiudete gli occhi e sognate in grande ✨",
    "💤🌟🦋 <b>BUONANOTTE DOLCISSIMA A TUTTI!!!</b> 😴\nChe ogni sogno sia un viaggio meraviglioso ✈️",
]

DEDICHE_NONNA = [
    "👵💕🌹 <b>LA NONNA È... AMORE PURO!!!</b> 💖\nAbbracciatela forte oggi, è il cuore della famiglia 🥰",
    "👵🍪☕ <b>LA NONNA È... PROFUMO DI BISCOTTI E COCCOLE!!!</b> 🍪💕\nNessun abbraccio è caldo come il suo 😋",
    "👵🌺💌 <b>LA NONNA È... CUSTODE DEI RICORDI PIÙ BELLI!!!</b> 📸💕\nLe sue mani hanno cresciuto intere famiglie 🥰",
    "👵🧶✨ <b>LA NONNA È... SAGGEZZA E DOLCEZZA INSIEME!!!</b> 🌟\nUn regalo che non dura per sempre, abbracciatela! 🤗",
    "👵🌻🍰 <b>LA NONNA È... LA TORTA PIÙ BUONA DEL MONDO!!!</b> 🎂😋\nGrazie infinite a tutte le nonne speciali 👵💕",
]

# ── FONTI IMMAGINI REALI ONLINE (no generazione, no AI) ──────────────────────
# Ogni fonte ha priorità diversa per momento/tipo. Tutte restituiscono foto vere.

def fonte_cat_api():
    """The Cat API — foto reali di gatti."""
    try:
        r = requests.get("https://api.thecatapi.com/v1/images/search", timeout=10)
        return r.json()[0]["url"]
    except Exception as e:
        print(f"[cat_api] {e}"); return None

def fonte_dog_api():
    """The Dog API — foto reali di cani."""
    try:
        r = requests.get("https://api.thedogapi.com/v1/images/search", timeout=10)
        return r.json()[0]["url"]
    except Exception as e:
        print(f"[dog_api] {e}"); return None

def fonte_picsum():
    """Lorem Picsum — foto reali fotografiche casuali, alta qualità."""
    try:
        seed = random.randint(1, 5000)
        url  = f"https://picsum.photos/seed/{seed}/700/700"
        r = requests.head(url, timeout=10, allow_redirects=True)
        return url if r.status_code == 200 else None
    except Exception as e:
        print(f"[picsum] {e}"); return None

def fonte_loremflickr(tag: str):
    """LoremFlickr — foto reali da Flickr filtrate per tag tematico."""
    try:
        url = f"https://loremflickr.com/700/700/{tag}"
        r = requests.head(url, timeout=10, allow_redirects=True)
        return r.url if r.status_code == 200 else None
    except Exception as e:
        print(f"[loremflickr] {e}"); return None

def get_immagine(tipo: str) -> str | None:
    """
    Pesca un'immagine reale a tema, provando più fonti in cascata.
    tipo: 'mattina', 'sera', 'nonna'
    """
    if tipo == "mattina":
        tag = random.choice(["flowers", "coffee", "sunrise", "morning", "garden"])
        fonti = [lambda: fonte_loremflickr(tag), fonte_picsum, fonte_cat_api, fonte_dog_api]
    elif tipo == "sera":
        tag = random.choice(["night", "moon", "stars", "candle"])
        fonti = [lambda: fonte_loremflickr(tag), fonte_picsum, fonte_cat_api, fonte_dog_api]
    else:  # nonna
        tag = random.choice(["grandmother", "elderly", "garden", "vintage"])
        fonti = [lambda: fonte_loremflickr(tag), fonte_picsum, fonte_cat_api]

    for fonte in fonti:
        img = fonte()
        if img:
            print(f"✅ Immagine trovata: {img[:60]}")
            return img
    return None

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

    if is_dedica_nonna:
        testo = random.choice(DEDICHE_NONNA)
        tipo  = "nonna"
    elif MOMENTO == "mattina":
        testo = random.choice(DIDASCALIE_MATTINA)
        tipo  = "mattina"
    else:
        testo = random.choice(DIDASCALIE_SERA)
        tipo  = "sera"

    if festivita:
        caption = f"{festivita}\n\n{testo}\n\n<i>📤 Pronta da inoltrare!</i>"
    else:
        caption = f"{testo}\n\n<i>📤 Pronta da inoltrare!</i>"

    img = get_immagine(tipo)

    for cid in CHAT_IDS:
        if img:
            ok = send_photo(img, caption, cid)
            if not ok:
                send_text(caption, cid)
        else:
            send_text(caption, cid)

    tipo_log = "DEDICA NONNA" if is_dedica_nonna else MOMENTO.upper()
    print(f"✅ Messaggio inviato — tipo: {tipo_log} — contatore: {contatore} — festività: {festivita or 'nessuna'}")

if __name__ == "__main__":
    main()
