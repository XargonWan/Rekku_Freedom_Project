#!/usr/bin/env python3
"""
Script di test per verificare se Chrome può essere avviato in ambiente container.
"""
import os
import subprocess
import sys
import time

def check_display():
    """Verifica se DISPLAY è configurato."""
    display = os.environ.get("DISPLAY")
    print(f"DISPLAY: {display}")
    if not display:
        print("❌ DISPLAY non configurato")
        return False
    return True

def check_chrome_binary():
    """Verifica se Chrome è installato."""
    chrome_paths = [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium"
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            print(f"✅ Chrome trovato: {path}")
            # Test version
            try:
                result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print(f"   Versione: {result.stdout.strip()}")
                    return path
                else:
                    print(f"   ❌ Errore ottenendo versione: {result.stderr}")
            except subprocess.TimeoutExpired:
                print("   ❌ Timeout durante verifica versione")
            except Exception as e:
                print(f"   ❌ Errore: {e}")
    
    print("❌ Nessun binario Chrome trovato")
    return None

def test_chrome_minimal():
    """Test di Chrome con opzioni minime."""
    chrome_path = check_chrome_binary()
    if not chrome_path:
        return False
    
    print("\n🔧 Test Chrome con opzioni minime...")
    
    cmd = [
        chrome_path,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--headless",
        "--dump-dom",
        "data:text/html,<html><body>Test</body></html>"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and "Test" in result.stdout:
            print("✅ Chrome headless funziona")
            return True
        else:
            print(f"❌ Chrome headless fallito: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Timeout Chrome headless")
        return False
    except Exception as e:
        print(f"❌ Errore Chrome headless: {e}")
        return False

def test_xvfb():
    """Test se Xvfb è disponibile."""
    try:
        result = subprocess.run(["which", "Xvfb"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Xvfb disponibile")
            return True
        else:
            print("❌ Xvfb non trovato")
            return False
    except Exception as e:
        print(f"❌ Errore verifica Xvfb: {e}")
        return False

def test_chrome_gui():
    """Test Chrome in modalità GUI."""
    chrome_path = check_chrome_binary()
    if not chrome_path:
        return False
    
    print("\n🖥️ Test Chrome GUI...")
    
    cmd = [
        chrome_path,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-setuid-sandbox",
        "--disable-gpu",
        "--start-maximized",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--disable-default-apps",
        "data:text/html,<html><body><h1>Test GUI</h1></body></html>"
    ]
    
    print(f"Comando: {' '.join(cmd)}")
    
    try:
        # Avvia Chrome in background
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Aspetta un momento per vedere se si avvia
        time.sleep(5)
        
        # Verifica se il processo è ancora in esecuzione
        if process.poll() is None:
            print("✅ Chrome GUI avviato con successo")
            # Termina il processo
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            return True
        else:
            stdout, stderr = process.communicate()
            print(f"❌ Chrome GUI terminato immediatamente")
            print(f"   stdout: {stdout.decode()[:200]}")
            print(f"   stderr: {stderr.decode()[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Errore Chrome GUI: {e}")
        return False

def main():
    print("🔍 Test ambiente Chrome per Selenium\n")
    
    # Check 1: DISPLAY
    print("1. Verifica DISPLAY:")
    display_ok = check_display()
    
    # Check 2: Chrome binary
    print("\n2. Verifica Chrome binary:")
    chrome_path = check_chrome_binary()
    
    # Check 3: Chrome headless
    print("\n3. Test Chrome headless:")
    headless_ok = test_chrome_minimal()
    
    # Check 4: Xvfb
    print("\n4. Verifica Xvfb:")
    xvfb_ok = test_xvfb()
    
    # Check 5: Chrome GUI
    print("\n5. Test Chrome GUI:")
    gui_ok = test_chrome_gui()
    
    # Riassunto
    print("\n" + "="*50)
    print("📊 RIASSUNTO:")
    print(f"   DISPLAY configurato: {'✅' if display_ok else '❌'}")
    print(f"   Chrome installato: {'✅' if chrome_path else '❌'}")
    print(f"   Chrome headless: {'✅' if headless_ok else '❌'}")
    print(f"   Xvfb disponibile: {'✅' if xvfb_ok else '❌'}")
    print(f"   Chrome GUI: {'✅' if gui_ok else '❌'}")
    
    if chrome_path and (headless_ok or gui_ok):
        print("\n🎉 Chrome dovrebbe funzionare con Selenium!")
        if chrome_path:
            print(f"\n💡 Usa questo path: {chrome_path}")
    else:
        print("\n❌ Problemi con Chrome. Selenium potrebbe non funzionare.")
        
        print("\n🔧 SUGGERIMENTI:")
        if not display_ok:
            print("   - Configura DISPLAY (es: export DISPLAY=:1)")
        if not chrome_path:
            print("   - Installa Chrome: apt-get install google-chrome-stable")
        if not gui_ok and not headless_ok:
            print("   - Verifica permessi: --no-sandbox potrebbe essere necessario")
            print("   - Verifica /dev/shm: --disable-dev-shm-usage potrebbe aiutare")

if __name__ == "__main__":
    main()
