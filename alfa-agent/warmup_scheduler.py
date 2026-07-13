#!/usr/bin/env python3
"""
Zeta-Agent Warmup Scheduler
===========================

Automated daily scheduler for Reddit warmup.
Runs warmup.py once or twice per day to respect comment limits.

Features:
- Runs 1-2 times per day at configurable times
- Uses environment variables for credentials
- Logs all executions to file and console
- Tracks execution status in a state file
- Graceful shutdown handling
- Continuous loop with proper sleep management

Usage:
    python warmup_scheduler.py              # Start scheduler (default: twice daily)
    python warmup_scheduler.py --once       # Run once per day
    python warmup_scheduler.py --twice      # Run twice daily (morning + evening)
    python warmup_scheduler.py --times 09:00 15:00  # Custom times
    python warmup_scheduler.py --status     # Show current status
    python warmup_scheduler.py --stop       # Stop the scheduler
"""
import os
import sys
import time
import signal
import argparse
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread, Event

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ==============================================================================
# Configuration
# ==============================================================================

SCRIPT_DIR = Path(__file__).parent
WARMUP_SCRIPT = SCRIPT_DIR / "warmup.py"
STATE_FILE = SCRIPT_DIR / "data" / "scheduler_state.json"
LOG_FILE = SCRIPT_DIR / "logs" / "warmup_scheduler.log"
PID_FILE = SCRIPT_DIR / "warmup_scheduler.pid"

# Default schedule: 2x daily (morning + afternoon/evening)
DEFAULT_TIMES = ["09:00", "18:00"]

# How often to check if it's time to run (in seconds)
CHECK_INTERVAL = 60  # Check every minute

# ==============================================================================
# Logging Setup
# ==============================================================================

def setup_logging():
    """Configure logging to file and console."""
    LOG_FILE.parent.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==============================================================================
# State Management
# ==============================================================================

def load_state():
    """Load scheduler state from file."""
    import json
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "last_run": None,
        "last_run_date": None,
        "runs_today": 0,
        "total_runs": 0,
        "failed_runs": 0,
        "started_at": datetime.now().isoformat(),
    }

def save_state(state):
    """Save scheduler state to file."""
    import json
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_today_date():
    """Get today's date string."""
    return datetime.now().strftime("%Y-%m-%d")

# ==============================================================================
# Process Management
# ==============================================================================

def write_pid():
    """Write current process ID to file."""
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def read_pid():
    """Read process ID from file."""
    if PID_FILE.exists():
        try:
            with open(PID_FILE, 'r') as f:
                return int(f.read().strip())
        except:
            pass
    return None

def is_running():
    """Check if scheduler is already running."""
    pid = read_pid()
    if pid and pid != os.getpid():
        try:
            # Check if process exists
            os.kill(pid, 0)
            return True
        except OSError:
            pass
    return False

def cleanup_pid():
    """Remove PID file."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except:
        pass

# ==============================================================================
# Schedule Utilities
# ==============================================================================

def parse_time(time_str):
    """Parse time string HH:MM to datetime.time object."""
    from datetime import time
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))

def get_next_run_time(schedule_times, after_time=None):
    """
    Calculate next run time based on schedule.
    
    Args:
        schedule_times: List of time strings ["HH:MM", ...]
        after_time: Only return times after this datetime
        
    Returns:
        datetime of next scheduled run, or None if no more runs today
    """
    now = after_time or datetime.now()
    today = now.date()
    
    for time_str in sorted(schedule_times):
        scheduled_time = parse_time(time_str)
        scheduled_dt = datetime.combine(today, scheduled_time)
        
        # If scheduled time is in the future today, return it
        if scheduled_dt > now:
            return scheduled_dt
    
    # All times passed today, return first time tomorrow
    first_time = parse_time(sorted(schedule_times)[0])
    tomorrow = today + timedelta(days=1)
    return datetime.combine(tomorrow, first_time)

def should_run_today(state, schedule_times, max_runs_per_day):
    """Check if we should run based on today's count."""
    today = get_today_date()
    
    # Reset counter if new day
    if state.get("last_run_date") != today:
        return True
    
    # Check if we still have runs left today
    return state.get("runs_today", 0) < max_runs_per_day

# ==============================================================================
# Warmup Execution
# ==============================================================================

def run_warmup():
    """
    Execute the warmup script.
    
    Returns:
        tuple: (success: bool, output: str)
    """
    logger.info("=" * 50)
    logger.info("Starting warmup execution...")
    logger.info("=" * 50)
    
    try:
        # Set environment variables for credentials
        env = os.environ.copy()
        
        # Ensure credentials are set (required for warmup)
        if not env.get("REDDIT_USERNAME"):
            username = input("Enter REDDIT_USERNAME: ").strip()
            env["REDDIT_USERNAME"] = username
            
        if not env.get("REDDIT_PASSWORD"):
            import getpass
            password = getpass.getpass("Enter REDDIT_PASSWORD: ")
            env["REDDIT_PASSWORD"] = password
        
        # Run warmup in --live mode
        result = subprocess.run(
            [sys.executable, str(WARMUP_SCRIPT), "--live"],
            env=env,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        output = result.stdout + result.stderr
        
        if result.returncode == 0:
            logger.info("Warmup completed successfully!")
            logger.info(output)
            return True, output
        else:
            logger.error(f"Warmup failed with exit code {result.returncode}")
            logger.error(output)
            return False, output
            
    except subprocess.TimeoutExpired:
        logger.error("Warmup execution timed out (10 minutes)")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"Warmup execution error: {e}")
        return False, str(e)

# ==============================================================================
# Scheduler Loop
# ==============================================================================

class WarmupScheduler:
    """Main scheduler class."""
    
    def __init__(self, schedule_times, max_runs_per_day=2):
        self.schedule_times = schedule_times
        self.max_runs_per_day = max_runs_per_day
        self.state = load_state()
        self.running = Event()
        self.running.set()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running.clear()
    
    def _check_and_run(self):
        """Check if it's time to run, and execute if so."""
        state = load_state()
        
        if not should_run_today(state, self.schedule_times, self.max_runs_per_day):
            return  # Already done for today
        
        next_run = get_next_run_time(self.schedule_times)
        
        if next_run is None:
            return  # No more runs scheduled for today
        
        now = datetime.now()
        
        # Check if current time matches a scheduled time (within CHECK_INTERVAL)
        for time_str in self.schedule_times:
            scheduled = parse_time(time_str)
            current_scheduled = now.replace(
                hour=scheduled.hour, 
                minute=scheduled.minute, 
                second=0, 
                microsecond=0
            )
            
            time_diff = abs((now - current_scheduled).total_seconds())
            
            if time_diff <= CHECK_INTERVAL:
                # Time to run!
                logger.info(f"Scheduled warmup time reached: {time_str}")
                
                success, output = run_warmup()
                
                # Update state
                state = load_state()
                state["total_runs"] = state.get("total_runs", 0) + 1
                
                if get_today_date() != state.get("last_run_date"):
                    state["runs_today"] = 0
                    state["last_run_date"] = get_today_date()
                
                state["runs_today"] += 1
                state["last_run"] = datetime.now().isoformat()
                
                if not success:
                    state["failed_runs"] = state.get("failed_runs", 0) + 1
                
                save_state(state)
                return
    
    def run(self):
        """Main scheduler loop."""
        write_pid()
        
        logger.info("=" * 60)
        logger.info("ZETA-AGENT WARMUP SCHEDULER STARTED")
        logger.info("=" * 60)
        logger.info(f"Schedule: {', '.join(self.schedule_times)}")
        logger.info(f"Max runs per day: {self.max_runs_per_day}")
        logger.info(f"Check interval: {CHECK_INTERVAL} seconds")
        logger.info("=" * 60)
        
        while self.running.is_set():
            self._check_and_run()
            time.sleep(CHECK_INTERVAL)
        
        cleanup_pid()
        logger.info("Scheduler stopped.")

# ==============================================================================
# Status & Control Functions
# ==============================================================================

def show_status():
    """Display current scheduler status."""
    state = load_state()
    pid = read_pid()
    
    print("\n" + "=" * 60)
    print("WARMUP SCHEDULER STATUS")
    print("=" * 60)
    
    if is_running():
        print(f"  Status:        🟢 RUNNING")
        print(f"  PID:           {pid}")
    else:
        print(f"  Status:        🔴 STOPPED")
        print(f"  PID:           (not running)")
    
    print(f"  Last Run:      {state.get('last_run', 'Never')}")
    print(f"  Runs Today:    {state.get('runs_today', 0)}")
    print(f"  Total Runs:    {state.get('total_runs', 0)}")
    print(f"  Failed Runs:   {state.get('failed_runs', 0)}")
    print(f"  Started At:    {state.get('started_at', 'Unknown')}")
    
    # Check if should run today
    schedule_times = DEFAULT_TIMES
    max_runs = 2
    if should_run_today(state, schedule_times, max_runs):
        next_run = get_next_run_time(schedule_times)
        if next_run:
            wait_minutes = (next_run - datetime.now()).total_seconds() / 60
            print(f"  Next Run:      {next_run.strftime('%Y-%m-%d %H:%M')} (in {wait_minutes:.0f} min)")
    else:
        print(f"  Next Run:      Tomorrow (daily limit reached)")
    
    print("=" * 60 + "\n")

def stop_scheduler():
    """Stop the running scheduler."""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped scheduler (PID: {pid})")
        except OSError:
            print("Could not stop scheduler - process not found")
            cleanup_pid()
    else:
        print("Scheduler not running")

def start_scheduler(args):
    """Start the scheduler."""
    if is_running():
        print("Scheduler is already running!")
        show_status()
        return
    
    # Determine schedule
    if args.times:
        schedule_times = args.times
    elif args.once:
        schedule_times = [DEFAULT_TIMES[0]]  # Just morning
    else:
        schedule_times = DEFAULT_TIMES  # Twice daily
    
    max_runs = 2 if len(schedule_times) > 1 else 1
    
    scheduler = WarmupScheduler(schedule_times, max_runs)
    scheduler.run()

# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Zeta-Agent Warmup Scheduler - Automated daily warmup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python warmup_scheduler.py --start          Start the scheduler
  python warmup_scheduler.py --once           Run once daily (morning only)
  python warmup_scheduler.py --twice          Run twice daily (default)
  python warmup_scheduler.py --times 09:00    Run once at specific time
  python warmup_scheduler.py --times 09:00 18:00  Run twice at specific times
  python warmup_scheduler.py --status         Show scheduler status
  python warmup_scheduler.py --stop           Stop the scheduler

Environment Variables (set these before starting):
  REDDIT_USERNAME=your_username
  REDDIT_PASSWORD=your_password
  GEMINI_API_KEY=your_key (optional)
        """
    )
    
    parser.add_argument("--start", action="store_true", help="Start the scheduler")
    parser.add_argument("--once", action="store_true", help="Run once per day (morning only)")
    parser.add_argument("--twice", action="store_true", help="Run twice per day (morning + evening)")
    parser.add_argument("--times", nargs="+", help="Specific times to run (HH:MM format)")
    parser.add_argument("--status", action="store_true", help="Show scheduler status")
    parser.add_argument("--stop", action="store_true", help="Stop the scheduler")
    parser.add_argument("--now", action="store_true", help="Run warmup immediately (bypass schedule)")
    
    args = parser.parse_args()
    
    # Handle status/stop commands
    if args.status:
        show_status()
        return
    
    if args.stop:
        stop_scheduler()
        return
    
    # Handle immediate run
    if args.now:
        print("Running warmup immediately...")
        success, output = run_warmup()
        if success:
            print("\n✅ Warmup completed successfully!")
        else:
            print("\n❌ Warmup failed!")
        return
    
    # Start scheduler
    start_scheduler(args)

if __name__ == "__main__":
    main()
