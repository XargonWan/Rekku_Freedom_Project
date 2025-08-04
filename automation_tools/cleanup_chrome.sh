#!/bin/bash
# Script to clean up Chrome/Chromium processes and lock files
# Useful for resolving issues after abrupt Ctrl+C termination
# Can be used both manually and as container init script

echo "🧹 Cleaning Chrome/Chromium processes and lock files..."

# Terminate all Chrome and Chromium processes
echo "🔪 Terminating Chrome/Chromium processes..."
pkill -f chrome 2>/dev/null || echo "No Chrome processes found"
pkill -f chromium 2>/dev/null || echo "No Chromium processes found"
pkill -f chromedriver 2>/dev/null || echo "No chromedriver processes found"

# Wait for processes to close gracefully
sleep 2

# Force termination if necessary
pkill -9 -f chrome 2>/dev/null || true
pkill -9 -f chromium 2>/dev/null || true
pkill -9 -f chromedriver 2>/dev/null || true

echo "🗑️  Removing lock files and temporary cache (preserving login sessions)..."

# Remove Chrome lock files (these cause "cannot connect" errors)
# Note: We only remove lock files, NOT the actual profile data to preserve logins
rm -f ~/.config/google-chrome*/SingletonLock 2>/dev/null || true
rm -f ~/.config/google-chrome*/Default/SingletonLock 2>/dev/null || true
rm -f ~/.config/google-chrome*/lockfile 2>/dev/null || true
rm -f /home/rekku/.config/google-chrome*/SingletonLock 2>/dev/null || true
rm -f /home/rekku/.config/google-chrome*/Default/SingletonLock 2>/dev/null || true
rm -f /home/rekku/.config/google-chrome*/lockfile 2>/dev/null || true

# Remove Chromium lock files
rm -f ~/.config/chromium*/SingletonLock 2>/dev/null || true
rm -f ~/.config/chromium*/Default/SingletonLock 2>/dev/null || true
rm -f ~/.config/chromium*/lockfile 2>/dev/null || true
rm -f /home/rekku/.config/chromium*/SingletonLock 2>/dev/null || true
rm -f /home/rekku/.config/chromium*/Default/SingletonLock 2>/dev/null || true
rm -f /home/rekku/.config/chromium*/lockfile 2>/dev/null || true

# Remove undetected-chromedriver cache (this can be safely regenerated)
rm -rf /tmp/undetected_chromedriver 2>/dev/null || true

# Remove ONLY temporary profile directories (those with timestamp suffix)
# This preserves the main persistent profiles but removes temporary ones
rm -rf ~/.config/google-chrome-[0-9]* 2>/dev/null || true
rm -rf /home/rekku/.config/google-chrome-[0-9]* 2>/dev/null || true
rm -rf ~/.config/chromium-[0-9]* 2>/dev/null || true
rm -rf /home/rekku/.config/chromium-[0-9]* 2>/dev/null || true

# Note: We specifically preserve ~/.config/google-chrome-rekku and ~/.config/chromium-rekku
# This keeps ChatGPT login sessions and other site data intact

# Remove browser temporary files and crash reports (safe to remove)
rm -rf /tmp/.com.google.Chrome* 2>/dev/null || true
rm -rf /tmp/.com.Chromium* 2>/dev/null || true
rm -rf /tmp/chrome_* 2>/dev/null || true
rm -rf /tmp/chromium_* 2>/dev/null || true

# Remove browser process crash dumps and temp directories
rm -rf ~/.config/google-chrome*/Crash\ Reports/pending/* 2>/dev/null || true
rm -rf /home/rekku/.config/google-chrome*/Crash\ Reports/pending/* 2>/dev/null || true
rm -rf ~/.config/chromium*/Crash\ Reports/pending/* 2>/dev/null || true
rm -rf /home/rekku/.config/chromium*/Crash\ Reports/pending/* 2>/dev/null || true

echo "✅ Cleanup completed!"

# Only show verification commands if running manually (not as init script)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo ""
    echo "📋 To verify everything is clean:"
    echo "   ps aux | grep chrome"
    echo ""
    echo "🚀 You can now restart the bot without issues."
fi
