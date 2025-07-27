-- 🌱 Create database and user if not exists (defaults from .env)
CREATE DATABASE IF NOT EXISTS rekku;

-- 👤 Create user for Rekku (non root)
CREATE USER IF NOT EXISTS 'rekku'@'%' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON rekku.* TO 'rekku'@'%';

-- 👤 Create root access from any host (for DBeaver or remote admin)
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED BY '${DB_ROOT_PASS}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;

-- ♻️ Apply changes
FLUSH PRIVILEGES;

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS recent_chats (
    chat_id BIGINT PRIMARY KEY,
    last_active DOUBLE
);

CREATE TABLE IF NOT EXISTS memories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp VARCHAR(40),
    content TEXT,
    author VARCHAR(255),
    source VARCHAR(255),
    tags TEXT,
    scope VARCHAR(255),
    emotion VARCHAR(255),
    intensity INT,
    emotion_state VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS emotion_diary (
    id VARCHAR(255) PRIMARY KEY,
    source VARCHAR(255),
    event TEXT,
    emotion VARCHAR(255),
    intensity INT,
    state VARCHAR(255),
    trigger_condition TEXT,
    decision_logic TEXT,
    next_check VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS tag_links (
    tag VARCHAR(255),
    related_tag VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS blocklist (
    user_id BIGINT PRIMARY KEY,
    reason TEXT,
    blocked_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_map (
    trainer_message_id BIGINT PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    timestamp DOUBLE
);

CREATE TABLE IF NOT EXISTS chatgpt_links (
    telegram_chat_id BIGINT NOT NULL,
    thread_id BIGINT,
    chatgpt_chat_id VARCHAR(255) NOT NULL,
    is_full TINYINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (telegram_chat_id, thread_id)
);

CREATE TABLE IF NOT EXISTS scheduled_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    scheduled VARCHAR(40) NOT NULL,
    repeat VARCHAR(50) DEFAULT 'none',
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered TINYINT DEFAULT 0,
    created_by VARCHAR(255) DEFAULT 'rekku',
    UNIQUE (scheduled, description)
);
