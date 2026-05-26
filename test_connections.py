"""
test_connections.py
Tests that Gemini API and Gmail SMTP are properly configured and working.
Exits with code 0 on success, 1 on failure.
"""

import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── 1. Check required env vars ──────────────────────────────────────────────
print("=" * 60)
print("DELTA AGENT – Connection Test")
print("=" * 60)

required = ["GEMINI_API_KEY", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_TO"]
missing = [v for v in required if not os.environ.get(v)]
if missing:
    print(f"[FAIL] Missing environment variables: {missing}")
    sys.exit(1)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SMTP_HOST      = os.environ["SMTP_HOST"]
SMTP_PORT      = int(os.environ["SMTP_PORT"])
SMTP_USER      = os.environ["SMTP_USER"]
SMTP_PASSWORD  = os.environ["SMTP_PASSWORD"]
SMTP_TO        = os.environ["SMTP_TO"]

print(f"[OK] All env vars present")
print(f"     SMTP: {SMTP_USER} → {SMTP_TO} via {SMTP_HOST}:{SMTP_PORT}")
print()

# ── 2. Test Gemini API ───────────────────────────────────────────────────────
print("[TEST 1] Gemini API...")
try:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content("Say 'Delta Agent online' in exactly 3 words.")
    gemini_reply = response.text.strip()
    print(f"[OK] Gemini responded: {gemini_reply}")
except Exception as e:
    print(f"[FAIL] Gemini API error: {e}")
    sys.exit(1)

print()

# ── 3. Test Gmail SMTP ───────────────────────────────────────────────────────
print("[TEST 2] Gmail SMTP...")
try:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Delta Agent – Connection Test Passed"
    msg["From"]    = SMTP_USER
    msg["To"]      = SMTP_TO

    body = f"""
שלום טל,

Delta Agent עבר את בדיקת החיבורים בהצלחה! 🚀

✅ Gemini API: עובד
   תשובה: {gemini_reply}

✅ Gmail SMTP: עובד
   שולח מ: {SMTP_USER}
   שולח אל: {SMTP_TO}

המערכת מוכנה לפעולה.
    """
    msg.attach(MIMEText(body, "plain", "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, SMTP_TO, msg.as_string())

    print(f"[OK] Test email sent successfully to {SMTP_TO}")
except Exception as e:
    print(f"[FAIL] SMTP error: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("ALL TESTS PASSED ✅ – Delta Agent is ready!")
print("=" * 60)
sys.exit(0)
