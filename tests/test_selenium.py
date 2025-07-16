#!/usr/bin/env python3
"""
Test specifico per Selenium con Chrome nel container.
"""
import os
import sys
import time
import subprocess

# Aggiungi il path del progetto
sys.path.insert(0, '/home/xargon/gits/rekku_the_bot')

def test_selenium_chrome():
    """Test di Selenium con Chrome."""
    try:
        import undetected_chromedriver as uc
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        print("✅ Import Selenium completati")
        
        # Configurazione Chrome
        chrome_path = "/usr/bin/google-chrome-stable"
        profile_dir = os.path.expanduser("~/.config/google-chrome-test")
        os.makedirs(profile_dir, exist_ok=True)
        
        # Ensure DISPLAY is set
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":1"
            
        print(f"DISPLAY: {os.environ.get('DISPLAY')}")
        print(f"Chrome path: {chrome_path}")
        print(f"Profile dir: {profile_dir}")
        
        # Test 1: Undetected Chrome
        print("\n🔧 Test 1: Undetected Chrome")
        try:
            options = uc.ChromeOptions()
            chrome_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage", 
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-blink-features=AutomationControlled",
                "--disable-extensions",
                "--disable-infobars",
                "--disable-web-security",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--single-process",
                "--disable-logging",
                "--log-level=3"
            ]
            
            for arg in chrome_args:
                options.add_argument(arg)
            
            options.add_argument(f"--user-data-dir={profile_dir}")
            
            print("Creazione driver UC...")
            driver = uc.Chrome(
                options=options,
                browser_executable_path=chrome_path,
                user_data_dir=profile_dir,
                headless=False,
                use_subprocess=False,
                version_main=None,
                suppress_welcome=True,
                log_level=3
            )
            
            print("✅ UC Chrome creato con successo")
            
            # Test navigazione
            print("Test navigazione...")
            driver.get("data:text/html,<html><body><h1>Test UC Chrome</h1></body></html>")
            
            # Verifica che la pagina sia caricata
            title_element = driver.find_element(By.TAG_NAME, "h1")
            if title_element.text == "Test UC Chrome":
                print("✅ UC Chrome navigation test passed")
                
            driver.quit()
            return True
            
        except Exception as e:
            print(f"❌ UC Chrome failed: {e}")
            
        # Test 2: Selenium standard
        print("\n🔧 Test 2: Selenium Standard")
        try:
            options = webdriver.ChromeOptions()
            chrome_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage", 
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-infobars",
                "--start-maximized",
                "--no-first-run",
                "--disable-default-apps",
                "--single-process",
                "--disable-logging",
                "--log-level=3"
            ]
            
            for arg in chrome_args:
                options.add_argument(arg)
                
            options.add_argument(f"--user-data-dir={profile_dir}")
            
            service = Service(chrome_path)
            driver = webdriver.Chrome(service=service, options=options)
            
            print("✅ Standard Selenium Chrome creato con successo")
            
            # Test navigazione
            driver.get("data:text/html,<html><body><h1>Test Standard Chrome</h1></body></html>")
            
            # Verifica che la pagina sia caricata
            title_element = driver.find_element(By.TAG_NAME, "h1")
            if title_element.text == "Test Standard Chrome":
                print("✅ Standard Chrome navigation test passed")
                
            driver.quit()
            return True
            
        except Exception as e:
            print(f"❌ Standard Chrome failed: {e}")
            
        return False
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ General error: {e}")
        return False

def main():
    print("🔍 Test Selenium Chrome specifico\n")
    
    # Kill any existing chrome processes
    try:
        subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
        time.sleep(2)
        print("🧹 Killed existing Chrome processes")
    except:
        pass
    
    success = test_selenium_chrome()
    
    if success:
        print("\n🎉 Selenium Chrome test SUCCESS!")
    else:
        print("\n❌ Selenium Chrome test FAILED!")
        print("\n🔧 TROUBLESHOOTING:")
        print("   1. Verifica che il container abbia accesso al display")
        print("   2. Prova a aumentare la memoria condivisa: --shm-size=2g")
        print("   3. Verifica i permessi del container")
        print("   4. Considera di usare headless mode")

if __name__ == "__main__":
    main()
