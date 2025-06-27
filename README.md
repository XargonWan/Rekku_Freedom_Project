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

---

## 🧪 Aiuto e comandi

| Comando | Descrizione                             |
| ------- | --------------------------------------- |
| `/help` | Mostra l'elenco dei comandi disponibili |

---

## 🐳 Docker: Avvio rapido

### ✅ Prerequisiti

* File `.env` configurato con i dati richiest, visionare `env.example` per utleriori informazioni.

### ▶️ Build e avvio

Avviare il servizio e vedere l'output su terminale:
```bash
setup.sh
start.sh
```

Tuttavia si consiglia di esegurlo via `docker compose`.

---

## 🔐 Login manuale per plugin Selenium

Il plugin `selenium_chatgpt` richiede che l'utente sia già loggato su ChatGPT. Per motivi di sicurezza, il login va effettuato **manualmente e una sola volta** in ambiente con interfaccia grafica.

### ✅ Preparazione del profilo

1. Assicurati di avere Chromium e ChromeDriver installati sul tuo sistema.
Se non li hai, installali con:
```bash
sudo apt update
sudo apt install -y chromium chromium-driver
```

3. Avvia lo script in locale (fuori da Docker):

```
python3 login_selenium.py
```

4. Una volta completato il login, verrà creata la cartella `selenium_profile/`.

5. Per trasferirla su un server remoto:

```
tar czf selenium_profile.tar.gz selenium_profile
```

Poi copia e decomprimi sul server:

```
tar xzf selenium_profile.tar.gz
```

---

### 📁 Ignora il profilo in Git

Nel file `.gitignore` assicurati che ci siano queste righe:

```
selenium_profile/
selenium_profile.tar.gz
```