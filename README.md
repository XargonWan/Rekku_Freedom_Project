## 🧞‍♀️ Rekku\_the\_bot

Un bot Telegram progettato per gestire interazioni conversazionali non lineari, pensiero spontaneo e assistenza manuale tramite un "trainer".

<img src="res/wink.webp" alt="Rekku Wink" width="300" />

---

## 📤 Comportamento automatico

Rekku inoltra automaticamente i messaggi al trainer (`OWNER_ID`) quando:

* Viene **menzionata** in un gruppo (`@Rekku_the_bot`)
* Riceve una **risposta a un suo messaggio**
* Si trova in un **gruppo con solo due membri**
* Riceve un messaggio in **chat privata** da un utente non bloccato

---

## 🧠 Modalità Context

Quando la modalità context è attiva, ogni messaggio inoltrato include anche una cronologia in formato JSON dei **10 messaggi più recenti** nella stessa chat, ad esempio:

```json
[
  {
    "message_id": 42,
    "username": "Marco Rossi",
    "usertag": "@marco23",
    "text": "ciao rekku",
    "timestamp": "2025-06-21T20:58:00+00:00"
  },
  ...
]
```

### Comandi disponibili (solo `OWNER_ID`):

| Comando    | Descrizione                          |
| ---------- | ------------------------------------ |
| `/context` | Attiva/disattiva la modalità context |

⚠️ Il context viene mantenuto in memoria finché il bot è acceso. Non viene salvato su file.

---

## 🧩 Modalità Manuale

### 🎭 Risposte gestite manualmente

Il trainer può rispondere a messaggi inoltrati via Telegram, e Rekku risponderà per suo conto nella chat d'origine.

Può anche rispondere con **contenuti multimediali** (sticker, immagini, audio, video, file, ecc.):

* Basta **rispondere a un messaggio inoltrato** con il contenuto desiderato
* Rekku inoltrerà automaticamente nella chat d'origine
* Non è più necessario usare comandi come `/sticker`, `/photo`, ecc.

| Comando   | Descrizione                |
| --------- | -------------------------- |
| `/cancel` | Annulla un invio in attesa |

---

## 🧱 Gestione utenti (solo `OWNER_ID`)

| Comando              | Descrizione                                 |
| -------------------- | ------------------------------------------- |
| `/block <user_id>`   | Blocca un utente (ignora messaggi futuri)   |
| `/unblock <user_id>` | Sblocca un utente                           |
| `/block_list`        | Mostra la lista utenti attualmente bloccati |

---

## ✏️ Comando `/say`

| Comando             | Descrizione                                           |
| ------------------- | ----------------------------------------------------- |
| `/say`              | Mostra le ultime chat attive (da selezionare)         |
| `/say <id> <testo>` | Invia direttamente il messaggio a una chat tramite ID |

Dopo la selezione, puoi inviare **qualsiasi contenuto** (testo, foto, audio, file, video, sticker).
Rekku lo inoltrerà alla chat selezionata.

Perfetto, aggiorniamo quella sezione del README rimuovendo `/test` e promuovendo `/help` come comando informativo principale.

Ecco la nuova versione modificata:

---

## 🧪 Aiuto e comandi

| Comando | Descrizione                             |
| ------- | --------------------------------------- |
| `/help` | Mostra l'elenco dei comandi disponibili |

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
docker build -t rekku-bot .
docker run -d --name rekku-bot --env-file .env rekku-bot
```

### 📋 Logs

```bash
docker logs -f rekku-bot
```