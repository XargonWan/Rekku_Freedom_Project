# Usa un'immagine Python ufficiale
FROM python:3.13-slim

# Variabili per path binari
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Installa Chromium, ChromeDriver e librerie necessarie
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libgtk-3-0 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libdrm2 \
    libxss1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file nel container
COPY . .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Monta la directory del profilo utente (persistente se vuoi salvarlo tra riavvii)
VOLUME ["/app/selenium_profile"]

# Avvia il bot
CMD ["python", "main.py"]
