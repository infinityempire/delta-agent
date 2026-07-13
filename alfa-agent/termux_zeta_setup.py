#!/usr/bin/env python3
"""
Zeta Runner Setup & Watchdog for Termux
========================================
הרץ פעם אחת ב-Termux — הסקריפט יתקין הכל, יגדיר את ה-Runner,
ויישאר פעיל ברקע כ-Watchdog שמתקן בעיות אוטומטית.

שימוש:
    python zeta_setup.py
"""

import os
import sys
import subprocess
import time
import threading
import json
import urllib.request
import urllib.error
import platform
import shutil
import signal

# ─────────────────────────────────────────
# הגדרות — שנה רק אם צריך
# ─────────────────────────────────────────
GITHUB_REPO_URL = "https://github.com/infinityempire/alfa-agent"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN", "")  # Set via: export GITHUB_TOKEN=your_token
RUNNER_NAME     = "termux-zeta-runner"
RUNNER_DIR      = os.path.expanduser("~/actions-runner")
RUNNER_VERSION  = "2.321.0"
WATCHDOG_INTERVAL = 60  # בדיקה כל 60 שניות

# ─────────────────────────────────────────
# צבעים לפלט
# ─────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

def log(msg, level="info"):
    prefix = {
        "info":    f"{GREEN}[✓]{RESET}",
        "warning": f"{YELLOW}[!]{RESET}",
        "error":   f"{RED}[✗]{RESET}",
        "step":    f"{CYAN}[→]{RESET}",
    }.get(level, "[?]")
    ts = time.strftime("%H:%M:%S")
    print(f"{prefix} [{ts}] {msg}", flush=True)

def run(cmd, check=True, capture=False, shell=False):
    """הרצת פקודה עם טיפול בשגיאות."""
    try:
        if isinstance(cmd, str) and not shell:
            cmd = cmd.split()
        result = subprocess.run(
            cmd, shell=shell, check=check,
            capture_output=capture, text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        if check:
            log(f"Command failed: {cmd}\n{e.stderr}", "error")
            raise
        return e

def detect_arch():
    """זיהוי ארכיטקטורת המעבד."""
    machine = platform.machine().lower()
    if "aarch64" in machine or "arm64" in machine:
        return "arm64"
    elif "armv7" in machine or "arm" in machine:
        return "arm"
    elif "x86_64" in machine or "amd64" in machine:
        return "x64"
    else:
        return "x64"

def get_runner_download_url():
    """בניית URL להורדת ה-Runner לפי ארכיטקטורה."""
    arch = detect_arch()
    base = f"https://github.com/actions/runner/releases/download/v{RUNNER_VERSION}"
    filename = f"actions-runner-linux-{arch}-{RUNNER_VERSION}.tar.gz"
    return f"{base}/{filename}", filename

def get_registration_token():
    """קבלת Registration Token חדש מ-GitHub API."""
    log("Fetching fresh registration token from GitHub...", "step")
    url = f"https://api.github.com/repos/infinityempire/alfa-agent/actions/runners/registration-token"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            token = data["token"]
            expires = data["expires_at"]
            log(f"Token received (expires: {expires})", "info")
            return token
    except Exception as e:
        log(f"Failed to get token: {e}", "error")
        return None

def install_packages():
    """התקנת חבילות נדרשות ב-Termux."""
    log("Installing required Termux packages...", "step")
    packages = ["python", "git", "curl", "wget", "proot", "binutils"]
    for pkg in packages:
        log(f"  Installing {pkg}...", "step")
        subprocess.run(["pkg", "install", "-y", pkg], check=False, capture_output=True, text=True)
    log("Termux packages installed", "info")

def install_python_deps():
    """התקנת תלויות Python."""
    log("Installing Python dependencies...", "step")
    deps = ["requests", "playwright"]
    for dep in deps:
        log(f"  pip install {dep}...", "step")
        subprocess.run(["pip", "install", dep], check=False, capture_output=True, text=True)
    log("Python dependencies installed", "info")

def download_runner():
    """הורדת GitHub Actions Runner."""
    url, filename = get_runner_download_url()
    arch = detect_arch()
    log(f"Detected architecture: {arch}", "info")
    log(f"Downloading runner from: {url}", "step")

    os.makedirs(RUNNER_DIR, exist_ok=True)
    dest = os.path.join(RUNNER_DIR, filename)

    if os.path.exists(dest):
        log("Runner archive already exists, skipping download", "info")
    else:
        subprocess.run(["curl", "-L", "-o", dest, url], check=True, capture_output=True, text=True)
        log("Runner downloaded", "info")

    log("Extracting runner...", "step")
    subprocess.run(["tar", "xzf", dest, "-C", RUNNER_DIR], check=True, capture_output=True, text=True)
    log("Runner extracted", "info")

def configure_runner(token):
    """הגדרת ה-Runner עם ה-Token."""
    config_script = os.path.join(RUNNER_DIR, "config.sh")
    if not os.path.exists(config_script):
        log("config.sh not found — runner not extracted properly", "error")
        return False

    log("Configuring runner...", "step")
    cmd = [
        "./config.sh",
        "--url", GITHUB_REPO_URL,
        "--token", token,
        "--name", RUNNER_NAME,
        "--labels", "self-hosted,Linux,termux",
        "--unattended",
        "--replace"
    ]
    result = subprocess.run(cmd, cwd=RUNNER_DIR, check=False, capture_output=True, text=True)
    if result.returncode == 0:
        log("Runner configured successfully!", "info")
        return True
    else:
        log(f"Runner configuration failed (exit code {result.returncode})", "error")
        return False

def is_runner_running():
    """בדיקה אם ה-Runner פעיל."""
    result = run("pgrep -f 'Runner.Listener'", check=False, capture=True, shell=True)
    return result.returncode == 0

def start_runner():
    """הפעלת ה-Runner ברקע."""
    run_script = os.path.join(RUNNER_DIR, "run.sh")
    if not os.path.exists(run_script):
        log("run.sh not found", "error")
        return False

    log("Starting runner in background...", "step")
    log_file = os.path.expanduser("~/zeta_runner.log")
    with open(log_file, "a") as f:
        subprocess.Popen(
            ["./run.sh"],
            cwd=RUNNER_DIR,
            stdout=f,
            stderr=subprocess.STDOUT
        )
    time.sleep(3)

    if is_runner_running():
        log(f"Runner is running! Logs: {log_file}", "info")
        return True
    else:
        log("Runner failed to start", "error")
        return False

def stop_runner():
    """עצירת ה-Runner."""
    run("pkill -f 'Runner.Listener'", check=False, shell=True)
    run("pkill -f 'run.sh'", check=False, shell=True)
    time.sleep(2)

def check_internet():
    """בדיקת חיבור לאינטרנט."""
    try:
        urllib.request.urlopen("https://github.com", timeout=5)
        return True
    except:
        return False

def check_runner_registered():
    """בדיקה אם ה-Runner רשום ב-GitHub."""
    url = "https://api.github.com/repos/infinityempire/alfa-agent/actions/runners"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            runners = data.get("runners", [])
            for r in runners:
                if r["name"] == RUNNER_NAME:
                    status = r.get("status", "unknown")
                    return True, status
            return False, "not_registered"
    except Exception as e:
        return None, str(e)

def full_setup():
    """התקנה מלאה מאפס."""
    print(f"\n{CYAN}{'='*50}")
    print("  ZETA RUNNER - FULL SETUP")
    print(f"{'='*50}{RESET}\n")

    # 1. בדיקת אינטרנט
    log("Checking internet connection...", "step")
    if not check_internet():
        log("No internet connection! Please connect and retry.", "error")
        sys.exit(1)
    log("Internet OK", "info")

    # 2. התקנת חבילות
    install_packages()

    # 3. הורדת Runner
    download_runner()

    # 4. קבלת Token והגדרה
    token = get_registration_token()
    if not token:
        log("Cannot proceed without token", "error")
        sys.exit(1)

    if not configure_runner(token):
        log("Setup failed at configuration step", "error")
        sys.exit(1)

    # 5. הפעלה
    if not start_runner():
        log("Setup failed at start step", "error")
        sys.exit(1)

    print(f"\n{GREEN}{'='*50}")
    print("  ✅ SETUP COMPLETE!")
    print(f"{'='*50}{RESET}")
    print(f"\n  Runner Name: {RUNNER_NAME}")
    print(f"  Repo: {GITHUB_REPO_URL}")
    print(f"  Logs: ~/zeta_runner.log")
    print(f"\n  The runner is now active and will execute")
    print(f"  Zeta warmup jobs automatically every day.")
    print(f"\n  Starting watchdog...\n")

def watchdog_loop():
    """לולאת Watchdog — בודקת ומתקנת בעיות כל 60 שניות."""
    log("Watchdog started — monitoring runner health...", "info")
    consecutive_failures = 0

    while True:
        time.sleep(WATCHDOG_INTERVAL)

        # בדיקת אינטרנט
        if not check_internet():
            log("No internet — waiting...", "warning")
            consecutive_failures += 1
            continue

        # בדיקה אם ה-Runner פועל
        if not is_runner_running():
            log("Runner is not running! Attempting restart...", "warning")
            consecutive_failures += 1

            if consecutive_failures >= 3:
                # ניסיון הגדרה מחדש עם Token חדש
                log("3 consecutive failures — reconfiguring with fresh token...", "warning")
                stop_runner()
                token = get_registration_token()
                if token:
                    configure_runner(token)
                consecutive_failures = 0

            start_runner()
        else:
            # בדיקת סטטוס ב-GitHub
            registered, status = check_runner_registered()
            if registered is True:
                if status == "online":
                    log(f"Runner healthy — status: {status}", "info")
                    consecutive_failures = 0
                elif status == "offline":
                    log("Runner offline on GitHub — restarting...", "warning")
                    stop_runner()
                    time.sleep(5)
                    start_runner()
            elif registered is False:
                log("Runner not registered on GitHub — reconfiguring...", "warning")
                stop_runner()
                token = get_registration_token()
                if token:
                    configure_runner(token)
                    start_runner()
            else:
                log(f"Could not check GitHub status: {status}", "warning")

def main():
    # טיפול ב-Ctrl+C
    def handle_exit(sig, frame):
        print(f"\n{YELLOW}[!] Watchdog stopped by user.{RESET}")
        print("    Runner continues in background.")
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_exit)

    # בדיקה אם כבר מוגדר
    run_script = os.path.join(RUNNER_DIR, "run.sh")
    if os.path.exists(run_script) and is_runner_running():
        log("Runner already installed and running!", "info")
        log("Starting watchdog only...", "step")
    else:
        full_setup()

    # הפעלת Watchdog
    watchdog_loop()

if __name__ == "__main__":
    main()
