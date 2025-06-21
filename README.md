# 🧞‍♀️ Rekku\_the\_bot

Un bot Telegram progettato per gestire interazioni conversazionali non lineari, pensiero spontaneo e assistenza manuale tramite un "trainer".

<img src="res/wink.webp" alt="Rekku Wink" width="300" />

---

## 🧩 Modalità Manuale

### 🎭 Risposte gestite manualmente

Il trainer può rispondere a messaggi inoltrati via Telegram, e Rekku risponderà per suo conto nella chat d'origine del messaggio.

---

## 📦 Comandi speciali (solo `OWNER_ID`)

### 🧱 Gestione utenti

| Comando              | Descrizione                                 |
| -------------------- | ------------------------------------------- |
| `/block <user_id>`   | Blocca un utente (ignora messaggi futuri)   |
| `/unblock <user_id>` | Sblocca un utente                           |
| `/block_list`        | Mostra la lista utenti attualmente bloccati |

---

### 🖼️ Risposte con contenuti (Sticker, Immagini, Audio, File, Video)

#### Flusso consigliato:

1. Rispondi a un messaggio inoltrato con uno di questi comandi:

   * `/sticker` – per rispondere con uno sticker
   * `/photo` – per rispondere con una foto
   * `/audio` – per rispondere con un file audio o nota vocale
   * `/file` – per rispondere con un documento
   * `/video` – per rispondere con un video

2. Rekku ti scrive in privato:
   **"📎 Inviami ora il file \[TIPO] da usare come risposta."**

3. Invia il contenuto richiesto **entro 60 secondi**

4. Rekku lo inoltra nella chat originale come risposta

✅ **Alternativa veloce**: puoi anche **rispondere direttamente** a un messaggio inoltrato con un contenuto (es. audio, sticker, ecc.) — anche senza comando.

#### Comandi disponibili:

| Comando    | Descrizione                                               |
| ---------- | --------------------------------------------------------- |
| `/sticker` | Rispondi a un messaggio inoltrato per inviare uno sticker |
| `/photo`   | Rispondi per inviare una foto                             |
| `/audio`   | Rispondi per inviare un audio o nota vocale               |
| `/file`    | Rispondi per inviare un documento                         |
| `/video`   | Rispondi per inviare un video                             |
| `/cancel`  | Annulla un invio in attesa (qualsiasi tipo)               |

⚠️ Se non invii nulla entro il tempo limite:
**❌ Ok, niente \[tipo].**

---

### 🧪 Test rapido

| Comando | Descrizione                                  |
| ------- | -------------------------------------------- |
| `/test` | Verifica che il bot sia online (`✅ Test OK`) |

---

## 📤 Comportamento automatico

Rekku inoltra automaticamente i messaggi al trainer (`OWNER_ID`) quando:

* Viene **menzionata** in un gruppo (`@Rekku_the_bot`)
* Riceve una **risposta a un suo messaggio**
* Si trova in un **gruppo con solo due membri**
* Riceve un messaggio in **chat privata** da un utente non bloccato

---

## 🔐 Solo il trainer può:

* Usare i comandi speciali
* Inviare risposte (in privato)
* Inviare media in risposta a messaggi inoltrati
* Gestire contenuti e annullare invii con `/cancel`

---

## 🐳 Docker: Avvio rapido

### ✅ Prerequisiti

* Docker installato
* File `.env` configurato con:

```
TELEGRAM_TOKEN=123456:ABC-DEF...
OWNER_ID=123456789
```

### 📄 Esempio Dockerfile

```
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
```

### ▶️ Build e avvio

```bash
# Costruisci l'immagine
docker build -t rekku-bot .

# Avvia il container
docker run -d \
  --name rekku-bot \
  --env-file .env \
  rekku-bot
```

### 📋 Logs

```bash
docker logs -f rekku-bot
```
