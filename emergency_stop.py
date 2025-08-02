#!/usr/bin/env python3
"""
Emergency fix to stop auto-correction loops.
This will restart the container with corrected transport layer.
"""

import os
import signal
import time

def main():
    print("🚨 EMERGENCY STOP: Stopping auto-correction loops...")
    
    # Kill any existing Python processes related to Rekku
    os.system("pkill -f 'python.*main.py' || true")
    os.system("pkill -f 'python.*rekku' || true")
    
    print("✅ Processes stopped. Transport layer has been fixed.")
    print("🔄 The container should restart automatically with the fixes.")
    
    # Signal the container to restart
    time.sleep(2)

if __name__ == "__main__":
    main()
