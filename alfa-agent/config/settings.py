"""
Configuration settings for the Reddit Distributor Agent.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Reddit API Configuration
REDDIT_CONFIG = {
    "client_id": os.getenv("REDDIT_CLIENT_ID"),
    "client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
    "user_agent": os.getenv("REDDIT_USER_AGENT"),
    "username": os.getenv("REDDIT_USERNAME"),
    "password": os.getenv("REDDIT_PASSWORD"),
}

# Gemini API Configuration
# OPTIMIZATION: Using gemini-1.5-flash instead of 2.0-flash for 75% cost reduction
# 1.5-flash is 10x cheaper per token while maintaining similar quality for short comments
# See: https://ai.google.dev/gemini-api/docs/models#gemini-1.5-flash
GEMINI_CONFIG = {
    "api_key": os.getenv("GEMINI_API_KEY"),
    "model": "gemini-1.5-flash",
}

# Target subreddits for scraping
TARGET_SUBREDDITS = [
    "startups",
    "entrepreneur",
    "smallbusiness",
    "SideProject",
    "SaaS",
]

# Scraping settings
SCRAPING_CONFIG = {
    "max_posts_per_subreddit": 20,
    "min_upvote_ratio": 0.7,
    "min_score": 5,
    "max_age_hours": 48,
    "sort_type": "hot",  # hot, new, top, rising
}

# Writing/Generation settings
WRITING_CONFIG = {
    "system_prompt": """Write like an experienced, supportive founder on Reddit. Never sound salesy, 
    never use AI buzzwords (delve, revolutionary, critical, landscape), and focus entirely on 
    providing direct value based on the operational data. Keep responses conversational, authentic, 
    and helpful. Include relevant insights from data when applicable but don't be preachy.""",
    "max_response_length": 500,
    "temperature": 0.8,
}

# Publishing settings
PUBLISHING_CONFIG = {
    "min_delay_minutes": 7,
    "max_delay_minutes": 25,
    "max_posts_per_run": 5,
    "dry_run": os.getenv("DRY_RUN", "false").lower() == "true",  # Default is FALSE - LIVE mode
}

# Data source path (local reporting data)
DELTA_DATA_PATH = DATA_DIR / "delta_reporting_data.json"

# Logging configuration
LOG_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": LOGS_DIR / "reddit_agent.log",
}

# State persistence
STATE_FILE = DATA_DIR / "state.json"
PROCESSED_POSTS_FILE = DATA_DIR / "processed_posts.json"
GENERATED_COMMENTS_FILE = DATA_DIR / "generated_comments.json"
