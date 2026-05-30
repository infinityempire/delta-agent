#!/bin/bash
# OpenManus Quick Start Script
# Fastest way to get OpenManus running

set -e

echo "🚀 OpenManus Quick Start"
echo ""

# Check if OpenManus directory exists
if [ ! -d "OpenManus" ]; then
    echo "📥 Cloning OpenManus..."
    git clone https://github.com/FoundationAgents/OpenManus.git
    cd OpenManus
else
    cd OpenManus
fi

# Create venv if needed
if [ ! -d "venv" ]; then
    echo "🔧 Setting up Python environment..."
    python3 -m venv venv
fi

echo "✅ Activating environment..."
source venv/bin/activate

echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

echo "🎨 Installing Playwright..."
playwright install -q

echo "⚙️  Configuring..."
if [ ! -f "config/config.toml" ]; then
    cp config/config.example.toml config/config.toml
    echo "📝 config.toml created. Edit it to add your API keys!"
fi

echo ""
echo "✨ Ready to go!"
echo ""
echo "Next: Edit config/config.toml with your API key"
echo "Then: python main.py"
echo ""
