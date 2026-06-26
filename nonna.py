"""
InvestoBot — Modulo "Buongiornissimo Nonna"
Genera messaggi in stile "Buongiornissimo Kaffeè" — lo stile tipico
delle immagini WhatsApp con fiori, cuoricini, caffè e frasi sdolcinate.
Ogni tot messaggi, lancia una dedica speciale a tema nonna.
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

# ── TEMPLATE "BUONGIORNISSIMO" — stile autentico WhatsApp ────────────────────
TEMPLATE_MATTINA = [
    "☕🌻✨\n\n<b>BUONGIORNISSIMO KAFFEEEE!!! ☕☕☕</b>\n\nChe questa giornata sia bollente come il caffè e dolce come il miele! 🍯 Un abbraccio a tutti voi 🤗💕",
    "🌞🌸🦋\n\n<b>UN'ALTRA GIORNATA BOLLENTE!!! BUONGIORNO!!! ☀️</b>\n\nSorridete sempre, la vita è troppo breve per i pensieri brutti! 😘 Vi voglio bene amici miei 💖",
    "🐦🌷💐\n\n<b>BUONGIORNO A TUTTI VOI CHE LEGGETE QUESTO MESSAGGIO!!! 🌅</b>\n\nChi vi ama vi pensa anche quando non ve lo dice... e io vi penso sempre! ❤️🥰",
    "☕🧁🌼\n\n<b>BUONGIORNISSIMO AMICI MIEI!!! ☕✨</b>\n\nLa vita è come il caffè: amara se non ci metti il giusto zucchero di allegria! 😄💛 Buona giornata a tutti!",
    "🌅🕊️💕\n\n<b>SVEGLIA SVEGLIAAA!!! È GIÀ MATTINA!!! ☀️🌞</b>\n\nOgni nuovo giorno è un regalo, apritelo con il sorriso! 🎁😍 Un bacio enorme a tutti voi!",
    "🌻🦋☕\n\n<b>BUONGIORNO CON IL SOLE CHE SPLENDE PER VOI!!! 🌞</b>\n\nChi semina sorrisi raccoglie amicizie! 🌱💛 Buona giornata splendida gente!",
    "💐🐝🌸\n\n<b>BUONGIORNISSIMO E BUON INIZIO SETTIMANA!!! 🎉</b>\n\nNon importa quanto sia difficile la giornata, voi siete più forti! 💪😘 Vi abbraccio forte!",
    "☁️🌈☕\n\n<b>ANCHE OGGI IL SOLE SI È SVEGLIATO PER VOI!!! ☀️</b>\n\nRicordate: siete unici e speciali, nessuno può rubarvi il sorriso! 😇💕",
    "🌺🦜🍃\n\n<b>BUONGIORNO TROPICALE A TUTTI GLI AMICI!!! 🌴</b>\n\nLa felicità non si compra, si regala... e io ve la regalo tutta! 🎁❤️",
    "🐓🌅🥐\n\n<b>CHICCHIRICHIIII!!! È ORA DI SVEGLIARSI AMICI!!! 🌞</b>\n\nUn nuovo giorno, mille nuove possibilità! Cogliamole tutte insieme! 🙌💖",
]

TEMPLATE_SERA = [
    "🌙⭐🕯️\n\n<b>BUONANOTTE A TUTTI VOI CHE LEGGETE!!! 😴</b>\n\nChe i sogni siano dolci come una fetta di torta della nonna! 🍰💕 Vi voglio bene!",
    "🌌💫🌃\n\n<b>BUONA NOTTE STELLATA AMICI MIEI!!! ✨</b>\n\nDomani sarà un giorno migliore, ma stanotte... riposatevi! 😘🛏️",
    "🌙🦉🕊️\n\n<b>È ORA DI ANDARE A NANNA!!! 😴💤</b>\n\nChi vi ama vi augura la buonanotte più dolce di sempre! 💕🌙",
    "✨🌃🛏️\n\n<b>BUONANOTTE CON UN ABBRACCIO VIRTUALE!!! 🤗</b>\n\nLasciate andare i pensieri della giornata, domani è un altro giorno! 🌅😴",
    "🌙🍃🕯️\n\n<b>LA LUNA VI AUGURA BUONANOTTE!!! 🌕</b>\n\nChiudete gli occhi e sognate in grande, ve lo meritate! ✨💖",
    "💤🌟🦋\n\n<b>BUONANOTTE DOLCISSIMA A TUTTI!!! 😴</b>\n\nChe ogni sogno sia un viaggio meraviglioso! ✈️💫 Vi penso sempre!",
    "🌌🛌🕊️\n\n<b>SOGNI D'ORO AMICI MIEI!!! 🌙</b>\n\nLa giornata è finita ma il vostro sorriso resta nel mio cuore! 💛😘",
    "⭐🌃🍵\n\n<b>BUONANOTTE CON UNA TISANA CALDA!!! ☕</b>\n\nRiposate bene, domani vi aspetta una giornata fantastica! 🌞💕",
]

# ── DEDICHE SPECIALI "NONNA" — ogni N messaggi ───────────────────────────────
DEDICHE_NONNA = [
    "👵💕🌹\n\n<b>LA NONNA È... AMORE PURO!!! 💖</b>\n\nChi ha la fortuna di avere ancora la nonna, l'abbracci forte oggi! Le nonne sono il cuore della famiglia, la dolcezza fatta persona! 🥰👵💐\n\nUn pensiero speciale per tutte le nonne del mondo, quelle in cielo e quelle che ci coccolano ancora! 🕊️❤️",
    "👵🍪☕\n\n<b>LA NONNA È... PROFUMO DI BISCOTTI E COCCOLE INFINITE!!! 🍪💕</b>\n\nNessun abbraccio è caldo come quello della nonna, nessuna minestra è buona come la sua! 😋🥣 Tanti auguri a tutte le nonne speciali! 👵💖",
    "👵🌺💌\n\n<b>LA NONNA È... LA CUSTODE DEI RICORDI PIÙ BELLI!!! 📸💕</b>\n\nLe sue mani hanno cresciuto intere famiglie, il suo cuore non finisce mai di amare! 🥰 Un bacio enorme a tutte le nonne del mondo! 👵❤️",
    "👵🧶✨\n\n<b>LA NONNA È... SAGGEZZA E DOLCEZZA INSIEME!!! 🌟</b>\n\nOgni nonna porta con sé una vita di amore da raccontare. Abbracciatela forte oggi, è un regalo che non dura per sempre! 🤗💐",
    "👵🌻🍰\n\n<b>LA NONNA È... LA TORTA PIÙ BUONA DEL MONDO!!! 🎂😋</b>\n\nNessuno cucina con amore come fa lei! Un grazie infinito a tutte le nonne che ci hanno coccolato! 👵💕🙏",
]

# ── QUERY IMMAGINI (collage colorati, fiori, cuoricini — stile buongiornissimo) ──
QUERY_MATTINA = [
    "flowers coffee morning colorful", "sunrise flowers pastel", "coffee cup flowers cute",
    "morning sunshine flowers", "tea flowers pastel aesthetic", "butterfly flowers spring",
]
QUERY_SERA = [
    "moon stars night sky aesthetic", "candle night cozy aesthetic", "night sky stars purple",
    "moon flowers night aesthetic", "starry night peaceful",
]
QUERY_NONNA = [
    "grandmother cartoon illustration flowers", "vintage grandma illustration cozy",
    "grandmother hugging cartoon warm", "elderly woman cartoon flowers vintage",
]

def get_immagine_unsplash(query: str):
    try:
        url = f"https://source.unsplash.com/600x600/?{query.replace(' ','%20')}"
        r = requests.get(url, timeout=12, allow_redirects=True)
        return r.url if r.status_code == 200 else None
    except Exception as e:
        print(f"Errore Unsplash: {e}")
        return None

def get_immagine_picsum():
    try:
        seed = random.randint(1, 1000)
        return f"https://picsum.photos/seed/{seed}/600/600"
    except:
        return None

# ── CONTATORE MESSAGGI ────────────────────────────────────────────────────────
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
def send_photo(url, caption, cid):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": cid, "photo": url, "caption": caption, "parse_mode": "HTML"},
            timeout=20
        ).raise_for_status()
        print(f"✅ Foto inviata a {cid}")
        return True
    except Exception as e:
        print(f"❌ Errore foto {cid}: {e}")
        return False

def send_text(text, cid):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=15
        ).raise_for_status()
    except Exception as e:
        print(f"❌ Errore testo {cid}: {e}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    festivita = get_festivita_oggi()
    contatore = get_e_incrementa_contatore()
    is_dedica_nonna = (contatore % OGNI_QUANTI_NONNA == 0)

    if is_dedica_nonna:
        testo = random.choice(DEDICHE_NONNA)
        query = random.choice(QUERY_NONNA)
    elif MOMENTO == "mattina":
        testo = random.choice(TEMPLATE_MATTINA)
        query = random.choice(QUERY_MATTINA)
    else:
        testo = random.choice(TEMPLATE_SERA)
        query = random.choice(QUERY_SERA)

    if festivita:
        caption = f"{festivita}\n\n{testo}\n\n<i>📤 Pronto da inoltrare!</i>"
    else:
        caption = f"{testo}\n\n<i>📤 Pronto da inoltrare!</i>"

    img = get_immagine_unsplash(query) or get_immagine_picsum()

    for cid in CHAT_IDS:
        if img:
            ok = send_photo(img, caption, cid)
            if not ok:
                send_text(caption, cid)
        else:
            send_text(caption, cid)

    tipo = "DEDICA NONNA" if is_dedica_nonna else MOMENTO.upper()
    print(f"✅ Messaggio inviato — tipo: {tipo} — contatore: {contatore} — festività: {festivita or 'nessuna'}")

if __name__ == "__main__":
    main()
