# Alfa-Agent - Gemini AI Content Writer

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

**Alfa-Agent** is a Gemini AI-powered content writer agent that generates human-like, contextually relevant text.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/infinityempire/alfa-agent.git
cd alfa-agent

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Gemini API key

# Run the agent
python -c "from agents import GeminiWriterAgent; agent = GeminiWriterAgent(); print('Alfa-Agent ready!')"
```

## Overview

**GeminiWriterAgent** is an AI-powered content generator that:
- Uses Google Gemini API for high-quality text generation
- Implements cost optimizations (caching, rate limiting, input truncation)
- Generates contextually relevant content based on custom data

## Project Structure

```
alfa-agent/
├── agents/
│   ├── __init__.py
│   └── gemini_writer.py        # Gemini AI content generator
├── config/
│   └── settings.py             # Configuration settings
├── utils/
│   └── logger.py               # Logging utilities
├── data/
│   └── delta_reporting_data.json.example  # Context data template
├── requirements.txt           # Python dependencies
├── .env.example                # Environment template
└── README.md
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
LOG_LEVEL=INFO
```

## Cost Optimizations

This agent includes several Gemini API cost optimizations:

| Optimization | Description | Savings |
|-------------|-------------|---------|
| Model | Uses `gemini-1.5-flash` | 75% cheaper |
| Caching | LRU cache (50 entries) | 20-40% fewer calls |
| Truncation | 4000 char input limit | Reduces tokens |
| Rate Limiting | 1.5s delay between calls | Prevents 429 errors |

## License

MIT License
