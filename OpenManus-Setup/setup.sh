#!/bin/bash

# OpenManus Automated Setup Script (Linux/macOS)
# This script automates the complete setup of OpenManus

set -e  # Exit on error

echo "================================="
echo "  OpenManus Automated Setup"
echo "================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${YELLOW}[1/7] Checking Python installation...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is not installed. Please install Python 3.12+${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION} found${NC}"

# Clone OpenManus repository
echo ""
echo -e "${YELLOW}[2/7] Cloning OpenManus repository...${NC}"
if [ ! -d "OpenManus" ]; then
    git clone https://github.com/FoundationAgents/OpenManus.git
    echo -e "${GREEN}✓ Repository cloned${NC}"
else
    echo -e "${GREEN}✓ Repository already exists${NC}"
fi

cd OpenManus

# Create Python virtual environment
echo ""
echo -e "${YELLOW}[3/7] Creating Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}[4/7] Activating virtual environment...${NC}"
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Upgrade pip
echo ""
echo -e "${YELLOW}[5/7] Upgrading pip...${NC}"
pip install --upgrade pip
echo -e "${GREEN}✓ pip upgraded${NC}"

# Install dependencies
echo ""
echo -e "${YELLOW}[6/7] Installing dependencies (this may take several minutes)...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Install Playwright browsers
echo ""
echo -e "${YELLOW}[7/7] Installing Playwright browsers...${NC}"
playwright install
echo -e "${GREEN}✓ Playwright browsers installed${NC}"

# Create config directory and copy example config
echo ""
echo -e "${YELLOW}Configuring OpenManus...${NC}"
if [ ! -f "config/config.toml" ]; then
    if [ -f "config/config.example.toml" ]; then
        cp config/config.example.toml config/config.toml
        echo -e "${YELLOW}⚠️  config.toml created from example${NC}"
        echo -e "${YELLOW}⚠️  Please edit config/config.toml and add your API keys${NC}"
    fi
fi

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}✓ OpenManus Setup Complete!${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Edit config/config.toml and add your LLM API keys"
echo "2. Activate the virtual environment: source venv/bin/activate"
echo "3. Run OpenManus: python main.py"
echo ""
echo -e "${YELLOW}For more information, see README.md${NC}"
