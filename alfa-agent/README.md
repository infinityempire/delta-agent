# Zeta - Reddit Marketing Agent

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![GitHub](https://img.shields.io/badge/GitHub-infinityempire/zeta--agent-lightgrey.svg)

**Zeta** is a multi-agent marketing and distribution system for Reddit, designed to run in a Linux/Termux environment.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/infinityempire/zeta-agent.git
cd zeta-agent

# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Reddit and Gemini API keys

# Run in dry-run mode
python zeta.py --dry-run

# Run live (posts to Reddit)
python zeta.py --live
```

## Overview

This system consists of three distinct components that work together in a pipeline:

1. **Reddit Scraper & Matcher Agent**: Periodically fetches recent posts from target subreddits using the Reddit API (PRAW)
2. **Contextual Writer Agent (Vibe-Checker)**: Processes matched posts alongside local Delta reporting data and uses Google Gemini API to generate tailored, human-sounding Reddit comments
3. **Humanization & Publishing Engine**: Manages publishing schedules, implements random delays (7-25 minutes), and posts comments to Reddit without triggering bot-detection

## Project Structure

```
zeta-agent/
├── agents/
│   ├── __init__.py
│   ├── zeta.py                # Main Zeta agent orchestrator
│   ├── reddit_scraper.py       # PRAW-based subreddit scraper
│   ├── gemini_writer.py        # Gemini API comment generator
│   └── publishing_engine.py    # Humanized comment publisher
├── config/
│   ├── __init__.py
│   └── settings.py             # All configuration settings
├── utils/
│   ├── __init__.py
│   ├── logger.py               # Colored logging utilities
│   ├── state.py                # State persistence manager
│   └── delay.py                # Random delay utilities
├── data/
│   └── delta_reporting_data.json.example  # Business metrics template
├── logs/                       # Application logs
├── zeta.py                    # Zeta entry point
├── main.py                     # Central controller
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

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# Reddit API Credentials
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_app_name_v1.0 (by u/your_username)
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password

# Google Gemini API Key
GEMINI_API_KEY=your_gemini_api_key

# Application Settings
DRY_RUN=true
LOG_LEVEL=INFO
```

### 3. Configure Your Data

Edit `data/delta_reporting_data.json` with your company's metrics (copy from the `.example` file).

### 4. Configure Target Subreddits

Edit `config/settings.py` to customize target subreddits:

```python
TARGET_SUBREDDITS = [
    "startups",
    "entrepreneur", 
    "smallbusiness",
    "SideProject",
    "SaaS",
]
```

## Usage

### Test Connections

```bash
python zeta.py --status
```

### Run Full Pipeline (Dry Run)

```bash
python zeta.py --dry-run --max-posts 3
```

### Run Full Pipeline (Live)

```bash
python zeta.py --live --max-posts 5
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--dry-run` | Don't post to Reddit (default) |
| `--live` | Actually post to Reddit |
| `--subreddits` | Specific subreddits to target |
| `--max-posts` | Maximum posts to process |
| `--limit` | Posts per subreddit (default: 20) |
| `--status` | Show agent status |

## Pipeline Flow

1. **Scout**: Fetches posts from configured subreddits
2. **Think**: Generates human-like comments using Gemini AI
3. **Act**: Publishes with random delays (7-25 minutes)

## Safety Features

- **Dry-run mode** by default - never posts accidentally
- **Random delays** between posts
- **Processed post tracking** - never posts twice
- **Human-like timing** with jitter

## License

MIT License
