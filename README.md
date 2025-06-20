# 🤖 Rekku_the_bot

Un bot Telegram progettato per gestire interazioni conversazionali non lineari, pensiero spontaneo e assistenza manuale.

---

## 🧩 Modalità Manuale

### 🎭 Risposte gestite manualmente
Il trainer può rispondere a messaggi inoltrati via Telegram, e Rekku risponderà per suo conto.

---

## 📦 Comandi speciali (solo OWNER_ID)

### 🧱 Gestione utenti

| Comando | Descrizione |
|--------|-------------|
| `/block <user_id>` | Blocca un utente (ignora messaggi futuri) |
| `/unblock <user_id>` | Sblocca un utente |
| `/block_list` | Mostra la lista utenti attualmente bloccati |

---

### 🖼 Invio sticker "proxy"

Flusso:

1. Rispondi a un messaggio in gruppo con `/sticker`
2. Rekku ti scrive in privato: “🖼 Inviami ora lo sticker...”
3. Invia uno sticker nel privato entro **60 secondi**
4. Rekku lo invia nel gruppo come risposta

#### Comandi:

| Comando | Descrizione |
|--------|-------------|
| `/sticker` | (In risposta a un messaggio) Avvia la modalità invio sticker |
| `/cancel_sticker` | Annulla l’invio sticker attivo |

⚠️ Dopo 60 secondi, se non invii lo sticker:
> `❌ Ok, niente sticker.`

---

## 📤 Comportamento automatico

Rekku inoltra messaggi **al trainer** quando:

- Viene menzionata in un gruppo
- Riceve una risposta a un suo messaggio
- Un utente le scrive in privato

---

## 🔒 Solo il trainer può:
- Usare i comandi speciali
- Inviare risposte (in privato)
- Annullare o gestire sticker

---

## 📁 Struttura progetto (parziale)

