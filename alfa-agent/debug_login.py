#!/usr/bin/env python3
"""Debug: check what Firefox sees on Reddit login page"""
import time, sys

GECKODRIVER_PATH = "/data/data/com.termux/files/usr/bin/geckodriver"
FIREFOX_PATH     = "/data/data/com.termux/files/usr/bin/firefox"

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By

opts = Options()
opts.add_argument("-headless")
opts.binary_location = FIREFOX_PATH
opts.set_preference("dom.webdriver.enabled", False)

service = Service(executable_path=GECKODRIVER_PATH, log_path="/dev/null")
driver = webdriver.Firefox(options=opts, service=service)
driver.set_page_load_timeout(30)

print("[*] Firefox started. Loading Reddit login...")
driver.get("https://www.reddit.com/login/")
time.sleep(6)

print(f"[*] URL: {driver.current_url}")
print(f"[*] Title: {driver.title}")

# Save full page source
html = driver.page_source
with open("/data/data/com.termux/files/home/reddit_login_debug.html", "w") as f:
    f.write(html)
print(f"[*] Page source saved ({len(html)} chars)")

# Check inputs
inputs = driver.find_elements(By.TAG_NAME, "input")
print(f"[*] <input> elements: {len(inputs)}")
for i, inp in enumerate(inputs):
    print(f"  [{i}] type={inp.get_attribute('type')} name={inp.get_attribute('name')} id={inp.get_attribute('id')}")

# Check faceplate elements
fp = driver.find_elements(By.CSS_SELECTOR, "faceplate-text-input")
print(f"[*] faceplate-text-input elements: {len(fp)}")

# Try shadow DOM
try:
    result = driver.execute_script("""
        var el = document.querySelector('faceplate-text-input');
        if (!el) return 'no faceplate found';
        if (!el.shadowRoot) return 'no shadowRoot';
        var inp = el.shadowRoot.querySelector('input');
        return inp ? 'shadow input found: ' + inp.name : 'no input in shadow';
    """)
    print(f"[*] Shadow DOM check: {result}")
except Exception as e:
    print(f"[*] Shadow DOM error: {e}")

# Print first 3000 chars of page
print("\n[*] Page source (first 3000 chars):")
print(html[:3000])

driver.quit()
print("[*] Done.")
