#!/usr/bin/env python3
"""Debug: check comment box structure on a Reddit post"""
import os, time, sys

USERNAME = os.environ.get("REDDIT_USERNAME", "")
PASSWORD = os.environ.get("REDDIT_PASSWORD", "")

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

# Login first
print("[*] Logging in...")
driver.get("https://www.reddit.com/login/")
time.sleep(4)

user_field = driver.execute_script("""
    var els = document.querySelectorAll('faceplate-text-input');
    for (var i=0; i<els.length; i++) {
        var sr = els[i].shadowRoot;
        if (!sr) continue;
        var inp = sr.querySelector('input');
        if (inp && (inp.name === 'username' || inp.type === 'text' || inp.type === '')) return inp;
    }
    return null;
""")
driver.execute_script("arguments[0].value = '';", user_field)
driver.execute_script("arguments[0].focus();", user_field)
user_field.send_keys(USERNAME)
driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", user_field)
time.sleep(0.3)

pass_field = driver.execute_script("""
    var els = document.querySelectorAll('faceplate-text-input');
    for (var i=0; i<els.length; i++) {
        var sr = els[i].shadowRoot;
        if (!sr) continue;
        var inp = sr.querySelector('input[type=password]');
        if (inp) return inp;
    }
    return null;
""")
driver.execute_script("arguments[0].value = '';", pass_field)
driver.execute_script("arguments[0].focus();", pass_field)
pass_field.send_keys(PASSWORD)
driver.execute_script("arguments[0].dispatchEvent(new Event('input', {bubbles:true}));", pass_field)
time.sleep(0.3)

from selenium.webdriver.common.keys import Keys
submit = driver.execute_script("return document.querySelector('button[type=submit]');")
if submit:
    submit.click()
else:
    pass_field.send_keys(Keys.RETURN)
time.sleep(6)
print(f"[*] Logged in. URL: {driver.current_url}")

# Go to a post
TEST_URL = "https://www.reddit.com/r/science/comments/1lm0xtq/a_lowprotein_mediterraneanstyle_diet_rich_in/"
print(f"[*] Loading post: {TEST_URL}")
driver.get(TEST_URL)
time.sleep(5)

print(f"[*] Post URL: {driver.current_url}")
print(f"[*] Title: {driver.title[:80]}")

# Check for comment-related elements
checks = [
    ("div[contenteditable='true']", "contenteditable div"),
    ("textarea", "textarea"),
    ("shreddit-composer", "shreddit-composer"),
    ("[data-testid='comment-submission-form-richtext']", "comment-submission-form"),
    ("comment-composer-host", "comment-composer-host"),
    ("[slot='comment']", "slot=comment"),
    ("faceplate-textarea", "faceplate-textarea"),
]

for selector, name in checks:
    els = driver.find_elements(By.CSS_SELECTOR, selector)
    print(f"[*] {name}: {len(els)} found")

# Try JS to find any editable element
result = driver.execute_script("""
    var results = [];
    // Check all contenteditable
    var ce = document.querySelectorAll('[contenteditable]');
    ce.forEach(function(el) {
        results.push('contenteditable: ' + el.tagName + ' ce=' + el.getAttribute('contenteditable'));
    });
    // Check shreddit-composer shadow
    var sc = document.querySelector('shreddit-composer');
    if (sc) {
        results.push('shreddit-composer found');
        if (sc.shadowRoot) {
            var inp = sc.shadowRoot.querySelector('[contenteditable]');
            results.push('shreddit-composer shadow contenteditable: ' + (inp ? inp.tagName : 'none'));
        }
    }
    // Check comment-composer-host
    var cch = document.querySelector('comment-composer-host');
    if (cch) {
        results.push('comment-composer-host found');
        if (cch.shadowRoot) {
            var inp2 = cch.shadowRoot.querySelector('[contenteditable]');
            results.push('comment-composer-host shadow ce: ' + (inp2 ? inp2.tagName : 'none'));
        }
    }
    return results.join('\\n');
""")
print(f"[*] JS scan:\n{result}")

# Save page source
html = driver.page_source
with open("/data/data/com.termux/files/home/reddit_post_debug.html", "w") as f:
    f.write(html)
print(f"[*] Page source saved ({len(html)} chars)")

# Print relevant section
import re
idx = html.find("comment")
if idx > 0:
    print(f"\n[*] Around 'comment' in HTML:\n{html[max(0,idx-200):idx+500]}")

driver.quit()
print("[*] Done.")
