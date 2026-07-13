"""
Configuration settings for Alfa-Agent (Gemini AI Content Writer).
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

# Gemini API Configuration
# OPTIMIZATION: Using gemini-1.5-flash for 75% cost reduction
# See: https://ai.google.dev/gemini-api/docs/models#gemini-1.5-flash
GEMINI_CONFIG = {
    "api_key": os.getenv("GEMINI_API_KEY"),
    "model": "gemini-1.5-flash",
}

# Writing/Generation settings
WRITING_CONFIG = {
    "system_prompt": """Write like an experienced, supportive professional. Never sound salesy, 
    never use AI buzzwords (delve, revolutionary, critical, landscape), and focus entirely on 
    providing direct value. Keep responses conversational, authentic, 
    and helpful. Include relevant insights from data when applicable but don't be preachy.""",
    "max_response_length": 500,
    "temperature": 0.8,
}

# Data source path (local reporting data)
DELTA_DATA_PATH = DATA_DIR / "delta_reporting_data.json"

# Logging configuration
LOG_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": LOGS_DIR / "alfa_agent.log",
}

# State persistence
STATE_FILE = DATA_DIR / "state.json"
GENERATED_COMMENTS_FILE = DATA_DIR / "generated_comments.json"
