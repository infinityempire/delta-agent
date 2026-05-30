#!/usr/bin/env python3
"""
OpenManus Automated Setup Script (Python)
Works on Linux, macOS, and Windows
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_step(step_num, total, message):
    """Print a step message"""
    print(f"{Colors.BLUE}[{step_num}/{total}]{Colors.RESET} {Colors.YELLOW}{message}...{Colors.RESET}")

def print_success(message):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")

def print_error(message):
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")
    sys.exit(1)

def run_command(cmd, check=True):
    """Run a shell command"""
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print_error(f"Failed to run command: {e}")

def main():
    print(f"{Colors.BLUE}")
    print("="*50)
    print("  OpenManus Automated Setup")
    print("="*50)
    print(f"{Colors.RESET}")
    print()
    
    # Step 1: Check Python version
    print_step(1, 8, "Checking Python installation")
    if sys.version_info < (3, 12):
        print_error(f"Python 3.12+ required. You have {sys.version}")
    print_success(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} found")
    print()
    
    # Step 2: Check if OpenManus exists, if not clone it
    print_step(2, 8, "Checking OpenManus repository")
    if not Path("OpenManus").exists():
        print("Repository not found. Cloning...")
        if not run_command("git clone https://github.com/FoundationAgents/OpenManus.git"):
            print_error("Failed to clone repository")
        print_success("Repository cloned")
    else:
        print_success("Repository already exists")
    print()
    
    # Change to OpenManus directory
    os.chdir("OpenManus")
    
    # Step 3: Create virtual environment
    print_step(3, 8, "Creating virtual environment")
    venv_path = Path("venv")
    if not venv_path.exists():
        if not run_command(f"{sys.executable} -m venv venv"):
            print_error("Failed to create virtual environment")
        print_success("Virtual environment created")
    else:
        print_success("Virtual environment already exists")
    print()
    
    # Step 4: Get pip executable path
    print_step(4, 8, "Locating pip")
    if sys.platform == "win32":
        pip_cmd = "venv\\Scripts\\pip"
        python_cmd = "venv\\Scripts\\python"
    else:
        pip_cmd = "venv/bin/pip"
        python_cmd = "venv/bin/python"
    print_success("Pip located")
    print()
    
    # Step 5: Upgrade pip
    print_step(5, 8, "Upgrading pip")
    if not run_command(f"{pip_cmd} install --upgrade pip"):
        print_error("Failed to upgrade pip")
    print_success("Pip upgraded")
    print()
    
    # Step 6: Install dependencies
    print_step(6, 8, "Installing dependencies (this may take 5-10 minutes)")
    if not run_command(f"{pip_cmd} install -r requirements.txt"):
        print_error("Failed to install dependencies")
    print_success("Dependencies installed")
    print()
    
    # Step 7: Install Playwright
    print_step(7, 8, "Installing Playwright browsers")
    if not run_command(f"{python_cmd} -m playwright install"):
        print("Warning: Playwright installation had issues, but continuing...")
    else:
        print_success("Playwright browsers installed")
    print()
    
    # Step 8: Configure
    print_step(8, 8, "Configuring OpenManus")
    config_path = Path("config/config.toml")
    example_path = Path("config/config.example.toml")
    
    if not config_path.exists() and example_path.exists():
        shutil.copy(example_path, config_path)
        print("⚠️  config.toml created from example")
        print("⚠️  Please edit config/config.toml and add your API keys")
    print_success("Configuration ready")
    print()
    
    # Success!
    print(f"{Colors.GREEN}")
    print("="*50)
    print("✓ OpenManus Setup Complete!")
    print("="*50)
    print(f"{Colors.RESET}")
    print()
    print(f"{Colors.YELLOW}Next steps:{Colors.RESET}")
    print("1. Edit config/config.toml and add your LLM API key")
    if sys.platform == "win32":
        print("2. Activate venv: venv\\Scripts\\activate")
    else:
        print("2. Activate venv: source venv/bin/activate")
    print("3. Run OpenManus: python main.py")
    print()
    print(f"{Colors.BLUE}For more information, see README.md{Colors.RESET}")
    print()

if __name__ == "__main__":
    main()
