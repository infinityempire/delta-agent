#!/usr/bin/env python3
"""
Verify OpenManus Installation
"""

import sys
import subprocess
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def check(name, condition, error_msg=""):
    """Check a condition and print result"""
    if condition:
        print(f"{Colors.GREEN}✓ {name}{Colors.RESET}")
        return True
    else:
        print(f"{Colors.RED}✗ {name}{Colors.RESET}")
        if error_msg:
            print(f"  {Colors.YELLOW}{error_msg}{Colors.RESET}")
        return False

def main():
    print(f"{Colors.BLUE}")
    print("OpenManus Installation Verification")
    print("="*50)
    print(f"{Colors.RESET}")
    print()
    
    all_good = True
    
    # Check Python version
    all_good &= check(
        "Python 3.12+",
        sys.version_info >= (3, 12),
        f"Current: {sys.version_info.major}.{sys.version_info.minor}"
    )
    
    # Check OpenManus directory
    all_good &= check(
        "OpenManus directory exists",
        Path("OpenManus").exists(),
        "Run this script from the parent directory"
    )
    
    if not Path("OpenManus").exists():
        print(f"{Colors.RED}Cannot verify further without OpenManus directory{Colors.RESET}")
        return
    
    # Check config
    all_good &= check(
        "config.toml exists",
        Path("OpenManus/config/config.toml").exists(),
        "Copy from config/config.example.toml"
    )
    
    # Check venv
    if sys.platform == "win32":
        venv_exists = Path("OpenManus/venv/Scripts/python.exe").exists()
    else:
        venv_exists = Path("OpenManus/venv/bin/python").exists()
    all_good &= check("Virtual environment", venv_exists)
    
    # Try to import OpenManus
    try:
        sys.path.insert(0, str(Path("OpenManus").absolute()))
        import app.agent.manus
        all_good &= check("OpenManus imports successfully")
    except ImportError as e:
        all_good &= check("OpenManus imports successfully", False, str(e))
    
    print()
    if all_good:
        print(f"{Colors.GREEN}✓ All checks passed!{Colors.RESET}")
        print(f"{Colors.YELLOW}Ready to run: python OpenManus/main.py{Colors.RESET}")
    else:
        print(f"{Colors.RED}✗ Some checks failed. Please fix the issues above.{Colors.RESET}")
    print()

if __name__ == "__main__":
    main()
