#!/bin/bash
# Script to clean up Chrome processes and lock files
# Useful for resolving issues after abrupt Ctrl+C termination
# Can be used both manually and as container init script

echo "🧹 Cleaning Chrome processes and lock files..."

# Terminate all Chrome processes
echo "🔪 Terminating Chrome processes..."
pkill -f chrome 2>/dev/null || echo "No Chrome processes found"
pkill -f chromedriver 2>/dev/null || echo "No chromedriver processes found"

# Wait for processes to close gracefully
sleep 2

# Force termination if necessary
pkill -9 -f chrome 2>/dev/null || true
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

# Remove undetected-chromedriver cache (this can be safely regenerated)
rm -rf /tmp/undetected_chromedriver 2>/dev/null || true

# Remove ONLY temporary profile directories (those with timestamp suffix)
# This preserves the main persistent profile "google-chrome-rekku" but removes temporary ones
rm -rf ~/.config/google-chrome-[0-9]* 2>/dev/null || true
rm -rf /home/rekku/.config/google-chrome-[0-9]* 2>/dev/null || true

# Note: We specifically preserve ~/.config/google-chrome-rekku (the persistent profile)
# This keeps ChatGPT login sessions and other site data intact

# Remove Chrome temporary files and crash reports (safe to remove)
rm -rf /tmp/.com.google.Chrome* 2>/dev/null || true
rm -rf /tmp/chrome_* 2>/dev/null || true

# Remove Chrome process crash dumps and temp directories
rm -rf ~/.config/google-chrome*/Crash\ Reports/pending/* 2>/dev/null || true
rm -rf /home/rekku/.config/google-chrome*/Crash\ Reports/pending/* 2>/dev/null || true

echo "✅ Cleanup completed!"

# Only show verification commands if running manually (not as init script)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo ""
    echo "📋 To verify everything is clean:"
    echo "   ps aux | grep chrome"
    echo ""
    echo "🚀 You can now restart the bot without issues."
fi
