"""
Launcher script for running both the bot and the dashboard.
"""

import subprocess
import sys
import time
import signal
import os
from threading import Thread

processes = []

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print("\n[Launcher] Shutting down all processes...")
    for process in processes:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            process.kill()
    sys.exit(0)

def run_bot():
    """Run the main bot."""
    print("[Launcher] Starting Aster Liquidation Hunter Bot...")
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    processes.append(process)

    # Stream bot output
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"[Bot] {line.rstrip()}")

def run_dashboard():
    """Run the Flask dashboard."""
    print("[Launcher] Starting Dashboard API Server...")
    process = subprocess.Popen(
        [sys.executable, "api_server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    processes.append(process)

    # Stream dashboard output
    for line in iter(process.stdout.readline, ''):
        if line:
            print(f"[Dashboard] {line.rstrip()}")

def main():
    """Main launcher function."""
    print("=" * 60)
    print("Aster Liquidation Hunter - Launcher")
    print("=" * 60)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check for required files
    required_files = ['main.py', 'api_server.py', 'settings.json', '.env']
    for file in required_files:
        if not os.path.exists(file):
            print(f"[Launcher] Error: Required file '{file}' not found!")
            sys.exit(1)

    print("[Launcher] All required files found.")
    print("[Launcher] Starting services...")

    # Start bot in a thread
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Give bot time to initialize
    time.sleep(2)

    # Start dashboard in a thread
    dashboard_thread = Thread(target=run_dashboard, daemon=True)
    dashboard_thread.start()

    # Wait a moment for services to start
    time.sleep(3)

    print("\n" + "=" * 60)
    print("Services are running!")
    print("Dashboard: http://localhost:5000")
    print("Press Ctrl+C to stop all services")
    print("=" * 60 + "\n")

    try:
        # Keep main thread alive
        bot_thread.join()
        dashboard_thread.join()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()