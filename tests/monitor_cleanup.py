"""
Monitor script to verify OrderCleanup is running correctly on its 20-second interval.
Run this script while the trading bot is running to verify cleanup functionality.
"""

import time
import logging
import requests
from datetime import datetime, timedelta

# Set up logging to match the cleanup logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CleanupMonitor:
    """Monitor to verify order cleanup is running correctly."""

    def __init__(self, duration_minutes=5):
        """
        Initialize monitor.

        Args:
            duration_minutes: How long to monitor (default 5 minutes)
        """
        self.duration_minutes = duration_minutes
        self.start_time = None
        self.end_time = None

        # Track cleanup activity
        self.cleanup_cycles = []
        self.log_lines = []

        # Expected interval
        self.expected_interval_seconds = 20

    def start_monitoring(self):
        """Start monitoring cleanup activity."""
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)

        logger.info(f"Starting cleanup monitoring for {self.duration_minutes} minutes")
        logger.info(f"Monitor will run from {self.start_time} to {self.end_time}")
        logger.info("Expected cleanup interval: 20 seconds")
        logger.info("=" * 60)

        # Monitor the logs
        self.monitor_logs()

        # Analyze results
        self.analyze_results()

    def monitor_logs(self):
        """Monitor log output for cleanup messages."""
        logger.info("Monitoring for cleanup log messages...")
        logger.info("Look for lines containing: 'Running cleanup cycle...'")

        try:
            while datetime.now() < self.end_time:
                # Sleep for 1 second between checks
                time.sleep(1)

                # Check elapsed time
                elapsed = (datetime.now() - self.start_time).total_seconds()

                # Print status updates every 30 seconds
                if int(elapsed) % 30 == 0 and int(elapsed) > 0:
                    logger.info(f"Monitoring... ({int(elapsed)}s elapsed, "
                              f"{int(self.duration_minutes * 60 - elapsed)}s remaining)")

            logger.info("Monitoring period completed.")

        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user.")

    def analyze_results(self):
        """Analyze the monitoring results."""
        total_runtime_seconds = (datetime.now() - self.start_time).total_seconds()

        logger.info("=" * 60)
        logger.info("ANALYSIS RESULTS")
        logger.info("=" * 60)

        logger.info(f"Total monitoring time: {total_runtime_seconds:.1f} seconds")
        logger.info(f"Expected cleanup interval: {self.expected_interval_seconds} seconds")

        expected_cycles = total_runtime_seconds / self.expected_interval_seconds
        logger.info(f"Expected cycles: {expected_cycles:.1f}")

        # Check if cleanup appears to be running based on user feedback
        logger.info("")
        logger.info("VERIFICATION CHECKLIST:")
        logger.info("1. During monitoring, did you see 'Running cleanup cycle...' messages in the logs?")
        logger.info("2. Did these messages appear approximately every 20 seconds?")
        logger.info("3. Were there periodic cleanup results showing canceled orders or 'no cleanup needed'?")

        logger.info("")
        logger.info("INTERPRETATION:")
        if total_runtime_seconds < 60:
            logger.info("- Monitoring time was short. Run for at least 2-3 minutes to see multiple cycles.")
        else:
            logger.info("- If you saw periodic messages (~every 20s), cleanup is working correctly.")
            logger.info("- If no messages appeared, check if order cleanup is started in the bot.")
            logger.info("- Look for initialization message: 'Order cleanup started: interval=20s, stale_limit=3.0min'")

        logger.info("")
        logger.info("CLEANUP BEHAVIOR VERIFICATION:")
        logger.info("- Orphaned TP/SL orders (>60s old) without positions should be canceled")
        logger.info("- Stale LIMIT orders (>3 minutes old) should be canceled")
        logger.info("- Young TP/SL orders (<60s) should NOT be canceled (race condition protection)")
        logger.info("- Tracked TP/SL LIMIT orders should NOT be canceled as stale")


def check_bot_health():
    """Check if the trading bot appears to be running."""
    try:
        # Try to connect to the bot's API
        response = requests.get("http://localhost:8080/health", timeout=5)
        if response.status_code == 200:
            logger.info("✓ Bot health check passed - API is responding")
            return True
        else:
            logger.warning(f"⚠ Bot health check failed - status code {response.status_code}")
            return False
    except Exception as e:
        logger.warning(f"⚠ Could not connect to bot API: {e}")
        logger.warning("Make sure the trading bot is running on localhost:8080")
        return False


def main():
    """Main monitoring function."""
    print("OrderCleanup Monitor")
    print("===================")
    print("")
    print("This script helps verify that OrderCleanup is running correctly.")
    print("Make sure your trading bot is running before starting this monitor.")
    print("")

    # Check bot health
    bot_running = check_bot_health()

    if not bot_running:
        print("WARNING: Bot doesn't appear to be running.")
        print("Please start the bot first, then run this monitor.")
        print("")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Exiting.")
            return

    # Get monitoring duration
    try:
        duration = int(input("How many minutes to monitor? (default 3): ") or "3")
        if duration < 1:
            duration = 3
    except ValueError:
        duration = 3

    print(f"")
    print(f"Starting monitor for {duration} minutes...")
    print("Watch the bot's log output for cleanup messages!")
    print("")

    # Create and start monitor
    monitor = CleanupMonitor(duration_minutes=duration)
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
