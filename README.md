[![License](https://img.shields.io/github/license/XargonWan/Rekku_Freedom_Project)](https://img.shields.io/github/license/XargonWan/Rekku_Freedom_Project)
![Docker Pulls](https://img.shields.io/docker/pulls/xargonwan/rekku_freedom_project)

| Branch   | Build Status                                                                                                                                         |
|----------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| `main`   | [![CI Status](https://img.shields.io/github/actions/workflow/status/XargonWan/Rekku_Freedom_Project/build-release.yml)](https://github.com/XargonWan/Rekku_Freedom_Project/actions)      |
| `develop`| [![Develop CI Status](https://img.shields.io/github/actions/workflow/status/XargonWan/Rekku_Freedom_Project/build-release.yml?branch=develop)](https://github.com/XargonWan/Rekku_Freedom_Project/actions) |

# 🧞‍♀️ Rekku Freedom Project

**Rekku Freedom Project** is a modular infrastructure to support a fully-autonomous AI "person" with real-world interaction capabilities via messaging platforms like Telegram, powered by switchable LLM engines (manual proxy, OpenAI API, and live browser-controlled ChatGPT via Selenium), and more.

![Rekku Wink](res/wink.webp)

---

## 📦 Features Overview

### 🧠 Adaptive Intelligence

Rekku can run in multiple, pluginnabile, modes:

* `manual`: all messages are forwarded to a human trainer for manual response.
* `openai_chatgpt`: uses the OpenAI API with context and memory injection.
* `selenium_chatgpt`: drives the real ChatGPT interface using Chromium and Selenium.

The trainer can dynamically switch modes using the `/llm` command.

### 📤 Automatic Forwarding

Rekku will automatically forward messages to the trainer (`OWNER_ID`) if:

* She is **mentioned** in a group (`@rekku_freedom_project`)
* Someone **replies** to one of her messages
* She is in a group with only **two members**
* She receives a **private message** from an unblocked user

---

## 🧩 Plugin-Based Architecture

Each LLM engine is implemented as a plugin conforming to a standard interface. Switching or adding engines is simple and dynamic.

Plugins currently supported:

* `manual`
* `openai_chatgpt`
* `selenium_chatgpt`

They implement:

* JSON prompt ingestion
* Message generation
* Optional model selection (`/model`)

---

## 🧠 Context Memory

When context mode is enabled, Rekku includes the last 10 messages from the conversation in her prompt. This is toggled with `/context`.

```json
[
  {
    "message_id": 42,
    "username": "Hiroki Mishima",
    "usertag": "@hiromishi",
    "text": "Hi Rekku!",
    "timestamp": "2025-06-21T20:58:00+00:00"
  },
  ...
]
```

> ⚠️ Context is stored in memory only (not persisted to disk).

---

## 🎭 Manual Proxy Mode

Manual mode enables human-in-the-loop interaction.

* Trainer receives a full JSON prompt and forwarded message
* Replies with any content (text, photo, file, audio, video, sticker)
* Rekku will deliver the response to the original sender/chat

| Command   | Description            |
| --------- | ---------------------- |
| `/cancel` | Cancel a pending reply |

---

## ✏️ `/say` Command

Send messages or media to a chosen chat:

| Command            | Description                      |
| ------------------ | -------------------------------- |
| `/say`             | List recent chats and choose one |
| `/say <id> <text>` | Send directly to chat ID         |

After selection, send any content (text, image, file, audio, etc.) to be delivered.

---

## 🧱 User Management

Only the `OWNER_ID` can control these commands:

| Command              | Description        |
| -------------------- | ------------------ |
| `/block <user_id>`   | Block a user       |
| `/unblock <user_id>` | Unblock a user     |
| `/block_list`        | Show blocked users |

Blocked users are ignored across all interaction modes.

---

## ⚙️ LLM and Model Commands

| Command  | Description                                |
| -------- | ------------------------------------------ |
| `/llm`   | Show or switch the current LLM plugin      |
| `/model` | List or switch active model (if supported) |

---

## 🧪 Misc Commands

| Command       | Description                  |
| ------------- | ---------------------------- |
| `/help`       | Show available commands      |
| `/last_chats` | Show recent active chat list |
| `/purge_map`  | Purge stored reply mappings  |

---

## 🐳 Docker Deployment

### ⚙️ Requirements

Create a `.env` file with the required variables. See `env.example`.

### ▶️ Build and Start

```bash
./setup.sh
./start.sh
```

This mounts `rekku_home/` to `/home/rekku` in the container for persistent data.

For non-interactive environments (e.g., CI/CD), use:

```bash
./setup.sh --cicd
```

---

## 🔐 Selenium Setup (Manual Login Required)

The `selenium_chatgpt` plugin uses a real browser and requires a manual login to ChatGPT **only once**.

This is done **inside the container** via a graphical VNC session — no external machine or profile preparation needed.

### ✅ Steps

1. Make sure `chromium` and `chromedriver` are installed in your image (already handled in `Dockerfile`)
2. Start the container normally with:

   ```bash
   ./start.sh
   ```
3. Open the VNC session in your browser:

   ```
   http://<your-server-ip>:6901
   ```
4. Inside the virtual desktop, open Chrome and log in to [https://chat.openai.com](https://chat.openai.com)
5. Once you're logged in, type `✔️ Fatto` in the Telegram chat with Rekku to confirm

✅ Rekku will now be able to interact with ChatGPT in real time using a real browser.
