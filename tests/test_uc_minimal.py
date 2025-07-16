#!/usr/bin/env python3
"""
Minimal test script to diagnose undetected-chromedriver issues in container
"""
import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

def log(msg):
    print(f"[TEST] {msg}")

def check_environment():
    """Check the container environment"""
    log("=== Environment Check ===")
    
    # Check DISPLAY
    display = os.environ.get("DISPLAY")
    log(f"DISPLAY: {display}")
    
    # Check if Xvfb is running
    try:
        result = subprocess.run(["pgrep", "-f", "Xvfb"], capture_output=True, text=True)
        if result.returncode == 0:
            log(f"Xvfb processes: {result.stdout.strip()}")
        else:
            log("No Xvfb processes found")
    except Exception as e:
        log(f"Failed to check Xvfb: {e}")
    
    # Check Chrome installation
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/opt/google/chrome/chrome"
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            log(f"Chrome found at: {path}")
            try:
                result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    log(f"Chrome version: {result.stdout.strip()}")
                else:
                    log(f"Chrome version check failed: {result.stderr}")
            except Exception as e:
                log(f"Failed to get Chrome version: {e}")
            break
    else:
        log("No Chrome binary found")
    
    # Check /dev/shm
    shm_size = subprocess.run(["df", "-h", "/dev/shm"], capture_output=True, text=True)
    log(f"/dev/shm status:\n{shm_size.stdout}")
    
    # Check temp directory permissions
    temp_dir = tempfile.gettempdir()
    log(f"Temp directory: {temp_dir}")
    log(f"Temp dir writable: {os.access(temp_dir, os.W_OK)}")

def test_chrome_direct():
    """Test Chrome directly without Selenium"""
    log("\n=== Direct Chrome Test ===")
    
    chrome_cmd = [
        "/usr/bin/google-chrome-stable",
        "--headless",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--version"
    ]
    
    try:
        result = subprocess.run(chrome_cmd, capture_output=True, text=True, timeout=10)
        log(f"Direct Chrome test - Return code: {result.returncode}")
        if result.stdout:
            log(f"Chrome stdout: {result.stdout.strip()}")
        if result.stderr:
            log(f"Chrome stderr: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        log("Direct Chrome test - TIMEOUT")
    except Exception as e:
        log(f"Direct Chrome test - FAILED: {e}")

def test_undetected_chromedriver():
    """Test undetected-chromedriver with minimal setup"""
    log("\n=== Undetected ChromeDriver Test ===")
    
    try:
        import undetected_chromedriver as uc
        log("undetected-chromedriver imported successfully")
        
        # Clear cache
        uc_cache_dir = os.path.join(tempfile.gettempdir(), 'undetected_chromedriver')
        if os.path.exists(uc_cache_dir):
            shutil.rmtree(uc_cache_dir, ignore_errors=True)
            log("Cleared UC cache")
        
        # Minimal options
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=0")  # Enable all logs
        
        log("Attempting to create UC driver...")
        
        driver = uc.Chrome(
            options=options,
            headless=True,
            use_subprocess=False,
            version_main=None,
            suppress_welcome=True,
            log_level=0,  # Enable all logs
        )
        
        log("UC driver created successfully!")
        
        # Try to navigate to a simple page
        log("Navigating to Google...")
        driver.get("https://www.google.com")
        
        title = driver.title
        log(f"Page title: {title}")
        
        driver.quit()
        log("UC driver test completed successfully!")
        
    except Exception as e:
        log(f"UC driver test FAILED: {e}")
        import traceback
        log(f"Full traceback:\n{traceback.format_exc()}")

def test_selenium_standard():
    """Test standard Selenium WebDriver"""
    log("\n=== Standard Selenium Test ===")
    
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        # Try to find chromedriver
        chromedriver_paths = [
            "/usr/bin/chromedriver",
            "/usr/local/bin/chromedriver",
            shutil.which("chromedriver")
        ]
        
        chromedriver_path = None
        for path in chromedriver_paths:
            if path and os.path.exists(path):
                chromedriver_path = path
                log(f"Found chromedriver at: {path}")
                break
        
        if not chromedriver_path:
            log("No chromedriver found, skipping standard Selenium test")
            return
        
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        
        service = Service(chromedriver_path)
        
        log("Creating standard Selenium driver...")
        driver = webdriver.Chrome(service=service, options=options)
        
        log("Standard Selenium driver created!")
        driver.get("https://www.google.com")
        title = driver.title
        log(f"Page title: {title}")
        
        driver.quit()
        log("Standard Selenium test completed successfully!")
        
    except Exception as e:
        log(f"Standard Selenium test FAILED: {e}")
        import traceback
        log(f"Full traceback:\n{traceback.format_exc()}")

if __name__ == "__main__":
    log("Starting comprehensive Chrome/Selenium diagnostics...")
    
    check_environment()
    test_chrome_direct()
    test_undetected_chromedriver()
    test_selenium_standard()
    
    log("\nDiagnostics completed!")
