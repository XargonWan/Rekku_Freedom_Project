#!/bin/bash
# Script to clean up Chromium processes and lock files
# Useful for resolving issues after abrupt Ctrl+C termination
# Can be used both manually and as container init script

echo "🧹 Cleaning Chromium processes and lock files..."

# Determine configuration directories
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
ALT_CONFIG_HOME="/home/rekku/.config"

# Terminate all Chromium processes
echo "🔪 Terminating Chromium processes..."
pkill -f chromium 2>/dev/null || echo "No Chromium processes found"
pkill -f chromedriver 2>/dev/null || echo "No chromedriver processes found"

# Wait for processes to close gracefully
sleep 2

# Force termination if necessary
pkill -9 -f chromium 2>/dev/null || true
pkill -9 -f chromedriver 2>/dev/null || true

echo "🗑️  Removing lock files and temporary cache (preserving login sessions)..."

# Remove Chromium lock files (these cause "cannot connect" errors)
# Note: We only remove lock files, NOT the actual profile data to preserve logins
rm -f "$CONFIG_HOME"/chromium*/SingletonLock 2>/dev/null || true
rm -f "$CONFIG_HOME"/chromium*/Default/SingletonLock 2>/dev/null || true
rm -f "$CONFIG_HOME"/chromium*/lockfile 2>/dev/null || true
rm -f "$ALT_CONFIG_HOME"/chromium*/SingletonLock 2>/dev/null || true
rm -f "$ALT_CONFIG_HOME"/chromium*/Default/SingletonLock 2>/dev/null || true
rm -f "$ALT_CONFIG_HOME"/chromium*/lockfile 2>/dev/null || true

# Remove undetected-chromedriver cache (this can be safely regenerated)
rm -rf /tmp/undetected_chromedriver 2>/dev/null || true

# Remove ONLY temporary profile directories (those with timestamp suffix)
# This preserves the main persistent profile "chromium-rfp" but removes temporary ones
rm -rf "$CONFIG_HOME"/chromium-[0-9]* 2>/dev/null || true
rm -rf "$ALT_CONFIG_HOME"/chromium-[0-9]* 2>/dev/null || true

# Note: We specifically preserve "$CONFIG_HOME/chromium-rfp" (the persistent profile)
# This keeps ChatGPT login sessions and other site data intact

# Remove Chromium temporary files and crash reports (safe to remove)
rm -rf /tmp/.org.chromium.* 2>/dev/null || true
rm -rf /tmp/chromium_* 2>/dev/null || true

# Remove Chromium process crash dumps and temp directories
rm -rf "$CONFIG_HOME"/chromium*/Crash\ Reports/pending/* 2>/dev/null || true
rm -rf "$ALT_CONFIG_HOME"/chromium*/Crash\ Reports/pending/* 2>/dev/null || true

echo "✅ Cleanup completed!"

# Only show verification commands if running manually (not as init script)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo ""
    echo "📋 To verify everything is clean:"
    echo "   ps aux | grep chromium"
    echo ""
    echo "🚀 You can now restart the bot without issues."
fi

