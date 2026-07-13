"""
Logging utilities for the Reddit Distributor Agent.
"""
import logging
import sys
from pathlib import Path
from colorlog import ColoredFormatter

from config.settings import LOG_CONFIG


def setup_logger(name: str = "zeta_agent") -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_CONFIG["level"]))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatters
    console_formatter = ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    
    file_formatter = logging.Formatter(LOG_CONFIG["format"])
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    log_file = LOG_CONFIG["file"]
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


# Global logger instance
logger = setup_logger()
