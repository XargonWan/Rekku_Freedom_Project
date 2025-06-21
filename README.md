# 🧞‍♀️ Rekku\_the\_bot


<img src="res/wink.webp" alt="Rekku Wink" width="300" />

---

## 🧩 Modalità Manuale

### 🎭 Risposte gestite manualmente

Il trainer può rispondere a messaggi inoltrati via Telegram, e Rekku risponderà per suo conto.

---

## 📦 Comandi speciali (solo `OWNER_ID`)

### 🧱 Gestione utenti

| Comando              | Descrizione                                 |
| -------------------- | ------------------------------------------- |
| `/block <user_id>`   | Blocca un utente (ignora messaggi futuri)   |
| `/unblock <user_id>` | Sblocca un utente                           |
| `/block_list`        | Mostra la lista utenti attualmente bloccati |

---

### 🖼 Invio sticker "proxy"

Flusso:

1. Rispondi a un messaggio in gruppo con `/sticker`
2. Rekku ti scrive in privato: “🖼 Inviami ora lo sticker...”
3. Invia uno sticker nel privato entro **60 secondi**
4. Rekku lo invia nel gruppo come risposta

#### Comandi:

| Comando           | Descrizione                                                  |
| ----------------- | ------------------------------------------------------------ |
| `/sticker`        | (In risposta a un messaggio) Avvia la modalità invio sticker |
| `/cancel_sticker` | Annulla l’invio sticker attivo                               |

⚠️ Dopo 60 secondi, se non invii lo sticker:

> `❌ Ok, niente sticker.`

---

### 🧪 Test rapido

| Comando | Descrizione                                             |
| ------- | ------------------------------------------------------- |
| `/test` | Verifica che il bot sia online (risponde con ✅ Test OK) |

---

## 📤 Comportamento automatico

Rekku inoltra messaggi **al trainer (OWNER)** quando:

* Viene **menzionata** in un gruppo (`@Rekku_the_bot`)
* Riceve una **risposta a un suo messaggio**
* Si trova in un **gruppo con solo due membri**
* Riceve un messaggio in **chat privata** da un utente non bloccato

---

## 🔒 Solo il trainer può:

* Usare i comandi speciali
* Inviare risposte (in privato)
* Annullare o gestire sticker

---

## 🐳 Docker: Avvio rapido

### ✅ Prerequisiti

* Docker installato
* File `.env` configurato con:

  ```env
  TELEGRAM_TOKEN=123456:ABC-DEF...
  OWNER_ID=123456789
  ```

### 📄 Esempio `Dockerfile`

```Dockerfile
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

```