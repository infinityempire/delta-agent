# OpenManus Complete Setup Guide

## Quick Start

### Option 1: Automated Setup (Recommended)

#### Linux/macOS:
```bash
bash setup.sh
```

#### Windows:
```batch
setup.bat
```

### Option 2: Docker Setup

```bash
# Create .env file with your API keys
cp .env.example .env
# Edit .env with your credentials

# Start OpenManus
docker-compose up -d

# View logs
docker-compose logs -f openmanus
```

### Option 3: Manual Setup

#### Prerequisites
- Python 3.12 or higher
- Git
- pip (Python package manager)

#### Step-by-Step Installation

1. **Clone the repository:**
```bash
git clone https://github.com/FoundationAgents/OpenManus.git
cd OpenManus
```

2. **Create virtual environment:**
```bash
# Using venv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# OR using conda
conda create -n open_manus python=3.12
conda activate open_manus
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Install browser automation (optional but recommended):**
```bash
playwright install
```

5. **Configure API keys:**
```bash
cp config/config.example.toml config/config.toml
# Edit config/config.toml with your API keys
```

6. **Verify installation:**
```bash
python -c "import app.agent.manus; print('OpenManus import successful!')"
```

## Configuration

### Supported LLM Providers

#### Anthropic Claude (Default)
```toml
[llm]
model = "claude-3-7-sonnet-20250219"
base_url = "https://api.anthropic.com/v1/"
api_key = "your-anthropic-api-key"
```

#### OpenAI
```toml
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."
```

#### Azure OpenAI
```toml
[llm]
api_type = "azure"
model = "gpt-4o-mini"
base_url = "https://your-resource.openai.azure.com/openai/deployments/your-deployment"
api_key = "your-azure-key"
api_version = "2024-08-01-preview"
```

#### Ollama (Local)
```toml
[llm]
api_type = "ollama"
model = "llama3.2"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
```

#### AWS Bedrock
```toml
[llm]
api_type = "aws"
model = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
base_url = "bedrock-runtime.us-west-2.amazonaws.com"
api_key = "required_but_not_used"
```

## Running OpenManus

### Standard Mode
```bash
python main.py
```

Then enter your prompt when prompted.

### With Command-Line Argument
```bash
python main.py --prompt "Your task here"
```

### MCP Mode
```bash
python run_mcp.py
```

### Multi-Agent Flow Mode (Unstable)
```bash
python run_flow.py
```

### Sandbox Mode with Daytona
```bash
python sandbox_main.py
```

## Troubleshooting

### Python Version Error
```bash
# Check your Python version
python --version

# Should be 3.12 or higher
# Install Python 3.12 if needed
```

### Missing Dependencies
```bash
# Reinstall all dependencies
pip install -r requirements.txt --force-reinstall
```

### Playwright Installation Issues
```bash
# Install Playwright with dependencies
playwright install --with-deps
```

### API Key Configuration Issues
1. Check that `config/config.toml` exists
2. Verify API key is correct and valid
3. Ensure `api_key` is not commented out with `#`
4. Test API connection:
   ```bash
   python -c "from app.agent.manus import Manus; import asyncio; asyncio.run(Manus.create())"
   ```

### Import Errors
```bash
# Update pip and setuptools
pip install --upgrade pip setuptools

# Reinstall in development mode
pip install -e .
```

### Memory Issues
If you experience memory issues:
1. Reduce `max_tokens` in config.toml
2. Use a lighter model
3. Increase available system memory
4. Run in Docker with memory limits

### Browser Issues
```bash
# Reinstall Playwright browsers
playwright install --with-deps

# On Linux, install additional dependencies
sudo apt-get install -y libgbm1 libxss1
```

## Data Visualization (Optional)

### Install Node.js

**Linux/macOS:**
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install node
nvm use 22
```

**Windows:**
1. Download nvm-setup.exe from [nvm-windows](https://github.com/coreybutler/nvm-windows)
2. Install and run:
   ```powershell
   nvm install node
   nvm use 22
   ```

### Install Chart Visualization Dependencies
```bash
cd app/tool/chart_visualization
npm install
cd ../../..
```

### Enable in Config
```toml
[runflow]
use_data_analysis_agent = true
```

## Docker Setup

### Using Docker Compose

1. **Prepare environment:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

2. **Build and start:**
```bash
docker-compose up -d
```

3. **View logs:**
```bash
docker-compose logs -f openmanus
```

4. **Stop:**
```bash
docker-compose down
```

### Development Container
```bash
docker-compose -f docker-compose-dev.yml up -d
docker-compose -f docker-compose-dev.yml exec openmanus-dev bash
```

## Environment Variables

See `.env.example` for all available environment variables:

- `LLM_API_KEY` - Your LLM provider API key
- `LLM_MODEL` - Model name (default: claude-3-7-sonnet-20250219)
- `LLM_BASE_URL` - API endpoint URL
- `BROWSER_HEADLESS` - Browser headless mode (true/false)
- `SEARCH_ENGINE` - Search engine (Google, Baidu, DuckDuckGo, Bing)
- `USE_DATA_ANALYSIS_AGENT` - Enable data analysis (true/false)

## Support & Resources

- **GitHub Repository:** https://github.com/FoundationAgents/OpenManus
- **Issues:** https://github.com/FoundationAgents/OpenManus/issues
- **Discussions:** https://github.com/FoundationAgents/OpenManus/discussions
- **Discord:** https://discord.gg/DYn29wFk9z

## Getting API Keys

### Anthropic Claude
1. Visit https://console.anthropic.com/
2. Sign up or log in
3. Create an API key in the dashboard

### OpenAI
1. Visit https://platform.openai.com/api-keys
2. Sign up or log in
3. Create an API key

### Azure OpenAI
1. Create Azure account and OpenAI resource
2. Get endpoint and key from Azure portal

### AWS Bedrock
1. Enable Bedrock in AWS console
2. Configure credentials with AWS CLI

## Next Steps

1. Configure your LLM API keys in `config/config.toml`
2. Test with a simple prompt: `python main.py --prompt "Hello, what can you do?"`
3. Explore advanced features in the README
4. Join the community for support
