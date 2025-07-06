#!/bin/bash
set -e

echo "📦 Estrazione profilo utente Selenium..."

rm -rf selenium_profile
tar xzf selenium_profile.tar.gz

echo "🔐 Sistemazione permessi..."
chown -R "$(id -u):$(id -g)" selenium_profile
chmod -R u+rwX selenium_profile

echo "✅ Profilo pronto per l'uso su questo host."
