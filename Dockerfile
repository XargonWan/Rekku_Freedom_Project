# Usa un'immagine Python ufficiale
FROM python:3.11-slim

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file nel container
COPY . .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Esponi la porta se necessario (non obbligatorio per Telegram bot)
EXPOSE 8080

# Avvia il bot
CMD ["python", "main.py"]
