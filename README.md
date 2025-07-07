## 🧞‍♀️ Rekku_the_bot

A Telegram bot designed to manage non-linear conversations, spontaneous thought and manual assistance through a dedicated "trainer".

An optional [Telethon](https://github.com/LonamiWebs/Telethon) userbot is available in `interface/telethon_userbot.py` for advanced scenarios.

<img src="res/wink.webp" alt="Rekku Wink" width="300" />

---

## 📤 Automatic behavior

Rekku automatically forwards messages to the trainer (`OWNER_ID`) when:

* She is **mentioned** in a group (`@Rekku_the_bot`)
* She receives a **reply to one of her messages**
* She is in a **group with only two members**
* She receives a message in **private chat** from a user who isn't blocked

---

## 🧠 Context mode

When context mode is active, every forwarded message also includes a JSON history of the **last 10 messages** in the same chat, for example:

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

### Available commands (only `OWNER_ID`):

| Command    | Description                     |
| ---------- | ------------------------------- |
| `/context` | Toggle context mode on or off   |

⚠️ The context remains in memory while the bot is running. It isn't saved to file.

---

## 🧩 Manual mode

### 🎭 Manually handled replies

The trainer can respond to forwarded messages via Telegram and Rekku will answer back in the original chat on their behalf.

The trainer may also reply with **multimedia content** (stickers, images, audio, video, files, etc.):

* Simply **reply to a forwarded message** with the desired content
* Rekku automatically forwards it back to the original chat
* No need to use commands like `/sticker`, `/photo`, etc.

| Command   | Description            |
| --------- | ---------------------- |
| `/cancel` | Cancel a pending send  |

---

## 🧱 User management (only `OWNER_ID`)

| Command              | Description                                |
| -------------------- | ------------------------------------------ |
| `/block <user_id>`   | Block a user (ignore future messages)      |
| `/unblock <user_id>` | Unblock a user                             |
| `/block_list`        | Show the list of currently blocked users   |

---

## ⚙️ LLM plugins

Rekku can switch between different language model backends using the `/llm` command.
Built-in choices are:

* `manual` – forwards every message for manual replies.
* `openai_chatgpt` – uses the OpenAI API (`OPENAI_API_KEY` required).
* `selenium_chatgpt` – drives ChatGPT through a real browser session.

When supported by the plugin you can also change the active model with `/model`.

---

## ✏️ `/say` command

| Command             | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `/say`              | Show the latest active chats (choose one)               |
| `/say <id> <text>`  | Send a message directly to a chat by ID                 |

After the selection you can send **any content** (text, photo, audio, file, video, sticker). Rekku forwards it to the chosen chat.

---

## 🧪 Help and commands

| Command          | Description                          |
| ---------------- | ------------------------------------ |
| `/help`          | Display a list of available commands |
| `/last_chats`    | Show recent active chats            |
| `/purge_map [d]` | Purge stored message mappings       |

---

## 🐳 Docker: Quick start

### ✅ Requirements

* Configure a `.env` file with the required values. See `env.example` for more information.

### ▶️ Build and run

Start the service and watch the output on the terminal:
```bash
setup.sh
start.sh
```

The `rekku_home/` folder is mounted inside the container as `/home/rekku`, ensuring data persistence between runs.

To run the setup in non-interactive mode (e.g., CI/CD) use:
```bash
setup.sh --cicd
```

However running it through `docker compose` is recommended.

---

## 🔐 Manual login for Selenium plugin

The `selenium_chatgpt` plugin requires the user to be logged in to ChatGPT already. For security reasons, the login must be performed **manually and only once** in an environment with a graphical interface.

### ✅ Preparing the profile

1. Ensure Chromium and ChromeDriver are installed on your system. If not, install them with:
```bash
sudo apt update
sudo apt install -y chromium chromium-driver
```

3. Run `automation_tools/prepare_profile.sh` on a machine with a GUI. The script
   downloads a portable Chrome build and opens ChatGPT for login.

4. After logging in, a `selenium_profile.tar.gz` archive will be created.

5. Copy `selenium_profile.tar.gz` to the server and extract it:
```bash
tar xzf selenium_profile.tar.gz
```

---

### 📁 Ignore the profile in Git

Make sure these lines are in your `.gitignore` file:

```
selenium_profile/
selenium_profile.tar.gz
```
