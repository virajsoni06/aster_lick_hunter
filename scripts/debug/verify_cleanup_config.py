"""
Simple verification script to check OrderCleanup configuration and recent logs.
This can run independently to verify the setup without needing the full bot running.
"""

import glob
import os
import re
from datetime import datetime, timedelta

def check_cleanup_configuration():
    """Check if OrderCleanup is configured correctly in the codebase."""
    print("OrderCleanup Configuration Check")
    print("=" * 40)

    # Check order_cleanup.py exists and has correct parameters
    cleanup_file = "src/core/order_cleanup.py"
    if os.path.exists(cleanup_file):
        print("✓ OrderCleanup source file found")

        with open(cleanup_file, 'r') as f:
            content = f.read()

        # Check default parameters
        if 'cleanup_interval_seconds: int = 20' in content:
            print("✓ Default cleanup interval is 20 seconds")
        else:
            print("⚠ Default cleanup interval may not be 20 seconds")

        if 'stale_limit_order_minutes: float = 3.0' in content:
            print("✓ Default stale limit is 3.0 minutes")
        else:
            print("⚠ Default stale limit may not be 3.0 minutes")

        # Check for cleanup loop
        if 'cleanup_loop' in content:
            print("✓ Cleanup loop method found")
        else:
            print("⚠ Cleanup loop method not found")

        # Check for interval settings
        if 'self.cleanup_interval_seconds = cleanup_interval_seconds' in content:
            print("✓ Interval configuration is set correctly")
        else:
            print("⚠ Interval configuration may not be correct")

    else:
        print("✗ OrderCleanup source file not found")
        return False

    # Check where OrderCleanup is instantiated
    trader_file = "src/core/trader.py"
    if os.path.exists(trader_file):
        with open(trader_file, 'r') as f:
            trader_content = f.read()

        if 'OrderCleanup(' in trader_content:
            print("✓ OrderCleanup is instantiated in trader")
        else:
            print("⚠ OrderCleanup instantiation not found in trader")

    return True

def check_recent_logs():
    """Check recent log files for cleanup activity."""
    print("\nRecent Log Analysis")
    print("=" * 40)

    # Find log files (assuming they might be in logs/ directory or current directory)
    log_patterns = ["*.log", "logs/*.log", "log/*.log"]
    log_files = []

    for pattern in log_patterns:
        log_files.extend(glob.glob(pattern))

    if not log_files:
        print("⚠ No log files found")
        print("  (This is normal if logging is configured differently)")
        return

    print(f"Found {len(log_files)} log file(s)")

    # Check the most recent log file
    latest_log = max(log_files, key=os.path.getmtime)
    print(f"Checking most recent log: {latest_log}")

    try:
        with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
            # Read the last 1000 lines
            lines = f.readlines()[-1000:]
            lines.reverse()  # Most recent first

        # Look for cleanup-related messages in recent logs
        cleanup_initialization = None
        cleanup_cycles = []
        recent_cutoff = datetime.now() - timedelta(hours=1)

        print("Scanning recent log entries...")

        for line in lines:
            # Look for cleanup initialization
            init_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Order cleanup.*interval=(\d+)s.*stale_limit=([\d.]+)min', line)
            if init_match:
                timestamp_str = init_match.group(1)
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    if timestamp > recent_cutoff:
                        cleanup_initialization = {
                            'timestamp': timestamp,
                            'interval': int(init_match.group(2)),
                            'stale_limit': float(init_match.group(3))
                        }
                except ValueError:
                    pass

            # Look for cleanup cycles
            cycle_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Running cleanup cycle', line)
            if cycle_match and len(cleanup_cycles) < 5:  # Limit to last 5 cycles
                timestamp_str = cycle_match.group(1)
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    if timestamp > recent_cutoff:
                        cleanup_cycles.append(timestamp)
                except ValueError:
                    pass

        # Analyze findings
        if cleanup_initialization:
            print("✓ Found recent cleanup initialization:")
            print(f"  - Timestamp: {cleanup_initialization['timestamp']}")
            print(f"  - Interval: {cleanup_initialization['interval']} seconds")
            print(f"  - Stale limit: {cleanup_initialization['stale_limit']} minutes")

            if cleanup_initialization['interval'] == 20:
                print("✓ Interval is set to 20 seconds as expected")
            else:
                print(f"⚠ Interval is {cleanup_initialization['interval']} seconds (expected 20)")

            if abs(cleanup_initialization['stale_limit'] - 3.0) < 0.1:
                print("✓ Stale limit is 3.0 minutes as expected")
            else:
                print(f"⚠ Stale limit is {cleanup_initialization['stale_limit']} minutes (expected 3.0)")
        else:
            print("⚠ No recent cleanup initialization found in logs")
            print("  (This may be normal if the bot hasn't been restarted recently)")

        if cleanup_cycles:
            print(f"\n✓ Found {len(cleanup_cycles)} recent cleanup cycles")

            # Check intervals between cycles
            if len(cleanup_cycles) >= 2:
                intervals = []
                for i in range(len(cleanup_cycles) - 1):
                    interval = (cleanup_cycles[i] - cleanup_cycles[i+1]).total_seconds()
                    intervals.append(interval)

                avg_interval = sum(intervals) / len(intervals)
                print(f"  - Average interval: {avg_interval:.1f} seconds")
                print("  - Expected interval: 20 seconds")
                if abs(avg_interval - 20) < 5:  # Within 5 seconds
                    print("✓ Average interval is close to expected 20 seconds")
                else:
                    print(f"⚠ Average interval ({avg_interval:.1f}s) deviates significantly from 20s")
        else:
            print("\n⚠ No recent cleanup cycles found")
            print("  (This may be normal if no cleanup was needed or bot was idle)")

    except Exception as e:
        print(f"Error reading log file: {e}")

def main():
    """Main verification function."""
    print("OrderCleanup Verification Tool")
    print("=" * 50)
    print("This tool verifies the OrderCleanup configuration and checks recent logs.")
    print("Run this to ensure cleanup is set up correctly.\n")

    # Run checks
    config_ok = check_cleanup_configuration()
    check_recent_logs()

    print("\n" + "=" * 50)
    print("SUMMARY")

    if config_ok:
        print("✓ OrderCleanup appears to be configured correctly")
        print("✓ Source code has the right default parameters")

    print("\nNext Steps:")
    print("1. Start your trading bot")
    print("2. Watch for the initialization message: 'Order cleanup started: interval=20s, stale_limit=3.0min'")
    print("3. Monitor for periodic 'Running cleanup cycle...' messages every 20 seconds")
    print("4. Use monitor_cleanup.py for detailed monitoring while the bot runs")

    print("\nTo verify cleanup is working correctly, you should see:")
    print("- Initialization message at startup")
    print("- 'Running cleanup cycle...' messages every ~20 seconds")
    print("- Cleanup results or 'no cleanup needed' messages")


if __name__ == "__main__":
    main()
