"""
Launcher script for running both the bot and the dashboard with colored output.
"""

import subprocess
import sys
import time
import signal
import os
from threading import Thread

# Enable ANSI colors on Windows
if sys.platform == "win32":
    os.system("color")

try:
    from colorama import init, Fore, Style, Back
    init(autoreset=True)
    COLORS_AVAILABLE = True
except ImportError:
    COLORS_AVAILABLE = False
    # Define dummy classes for fallback
    class Fore:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Back:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ''
    class Style:
        DIM = NORMAL = BRIGHT = RESET_ALL = ''

processes = []

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"\n{colorize_prefix('Launcher', Fore.RED)} Shutting down all processes...")
    for process in processes:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            process.kill()
    sys.exit(0)

def colorize_prefix(prefix, color=Fore.CYAN):
    """Add color to prefix labels."""
    if COLORS_AVAILABLE:
        return f"{color}{Style.BRIGHT}[{prefix}]{Style.RESET_ALL}"
    return f"[{prefix}]"

def run_bot():
    """Run the main bot."""
    print(f"{colorize_prefix('Launcher', Fore.YELLOW)} Starting Aster Liquidation Hunter Bot...")

    # On Windows, don't capture output to preserve colors from the subprocess
    if sys.platform == "win32":
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'

        # Print a colored header for the bot output
        if COLORS_AVAILABLE:
            print(f"\n{Fore.GREEN}{Style.BRIGHT}{'─' * 60}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}  BOT OUTPUT:{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{Style.BRIGHT}{'─' * 60}{Style.RESET_ALL}\n")

        process = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            env=env
            # Don't capture stdout/stderr - let it print directly with colors
        )
        processes.append(process)
        process.wait()  # Wait for the process to complete to keep thread alive
    else:
        # On Unix-like systems, we can capture and add prefix
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'

        process = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            encoding='utf-8',
            errors='replace'
        )

        prefix = colorize_prefix("Bot", Fore.GREEN)
        # Stream output with colored prefix
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"{prefix} {line.rstrip()}")

    processes.append(process)

def run_dashboard():
    """Run the Flask dashboard."""
    print(f"{colorize_prefix('Launcher', Fore.YELLOW)} Starting Dashboard API Server...")

    # Get the current directory to ensure proper module path
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # On Windows, don't capture output to preserve colors
    if sys.platform == "win32":
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONPATH'] = current_dir

        # Print a colored header for the dashboard output
        if COLORS_AVAILABLE:
            print(f"\n{Fore.BLUE}{Style.BRIGHT}{'─' * 60}{Style.RESET_ALL}")
            print(f"{Fore.BLUE}{Style.BRIGHT}  DASHBOARD OUTPUT:{Style.RESET_ALL}")
            print(f"{Fore.BLUE}{Style.BRIGHT}{'─' * 60}{Style.RESET_ALL}\n")

        process = subprocess.Popen(
            [sys.executable, "-u", "src/api/api_server.py"],
            cwd=current_dir,
            env=env
            # Don't capture stdout/stderr - let it print directly with colors
        )
        processes.append(process)
        process.wait()  # Wait for the process to complete to keep thread alive
    else:
        # On Unix-like systems, we can capture and add prefix
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONPATH'] = current_dir

        process = subprocess.Popen(
            [sys.executable, "-u", "src/api/api_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=current_dir,
            env=env,
            encoding='utf-8',
            errors='replace'
        )

        prefix = colorize_prefix("Dashboard", Fore.BLUE)
        # Stream output with colored prefix
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"{prefix} {line.rstrip()}")

    processes.append(process)

def main():
    """Main launcher function."""
    if COLORS_AVAILABLE:
        print(f"{Fore.CYAN}{Style.BRIGHT}{'═' * 60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}  Aster Liquidation Hunter - Launcher{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{Style.BRIGHT}{'═' * 60}{Style.RESET_ALL}")
    else:
        print("=" * 60)
        print("  Aster Liquidation Hunter - Launcher")
        print("=" * 60)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check for .env file first
    if not os.path.exists('.env'):
        print(f"\n{colorize_prefix('Launcher', Fore.RED)} No .env file found!")
        print(f"{colorize_prefix('Launcher', Fore.YELLOW)} Starting setup wizard to configure API credentials...")
        print("")

        # Run the setup utility
        try:
            result = subprocess.run([sys.executable, "scripts/setup_env.py"], check=False)
            if result.returncode != 0:
                print(f"\n{colorize_prefix('Launcher', Fore.RED)} Setup cancelled or failed. Exiting...")
                sys.exit(1)
        except FileNotFoundError:
            print(f"{colorize_prefix('Launcher', Fore.RED)} Error: scripts/setup_env.py not found!")
            print(f"{colorize_prefix('Launcher', Fore.RED)} Please create .env file manually with API_KEY and API_SECRET")
            print(f"{colorize_prefix('Launcher', Fore.YELLOW)} Get your API key at: https://www.asterdex.com/en/referral/3TixB2")
            sys.exit(1)

        # Verify .env was created
        if not os.path.exists('.env'):
            print(f"{colorize_prefix('Launcher', Fore.RED)} .env file was not created. Exiting...")
            sys.exit(1)

        print("")

    # Check for required files
    required_files = ['main.py', 'src/api/api_server.py', 'settings.json', '.env']
    missing_files = []
    for file in required_files:
        if not os.path.exists(file):
            missing_files.append(file)

    if missing_files:
        print(f"{colorize_prefix('Launcher', Fore.RED)} Error: Required files not found:")
        for file in missing_files:
            print(f"  {Fore.RED}• {file}{Style.RESET_ALL}")
        sys.exit(1)

    print(f"{colorize_prefix('Launcher', Fore.GREEN)} All required files found.")
    print(f"{colorize_prefix('Launcher', Fore.YELLOW)} Starting services...")

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

    if COLORS_AVAILABLE:
        print(f"\n{Fore.GREEN}{Style.BRIGHT}{'═' * 60}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}  Services are running!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Dashboard: {Fore.CYAN}{Style.BRIGHT}http://localhost:5000{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}  Press {Fore.RED}{Style.BRIGHT}Ctrl+C{Style.RESET_ALL}{Fore.YELLOW} to stop all services{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{Style.BRIGHT}{'═' * 60}{Style.RESET_ALL}\n")
    else:
        print("\n" + "=" * 60)
        print("  Services are running!")
        print("  Dashboard: http://localhost:5000")
        print("  Press Ctrl+C to stop all services")
        print("=" * 60 + "\n")

    try:
        # Keep main thread alive
        bot_thread.join()
        dashboard_thread.join()
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
