#!/usr/bin/env python3
"""
Environment Setup Utility for Aster Liquidation Hunter Bot
Creates and manages .env file with API credentials
"""

import os
import sys
from pathlib import Path
from typing import Optional
import getpass
from dotenv import load_dotenv

def has_credentials() -> bool:
    """
    Check if API credentials are available from environment variables or .env file.
    Uses python-dotenv to properly load .env files.
    
    Returns:
        True if both API_KEY and API_SECRET are available
    """
    # Load .env file if it exists (no-op if already loaded or doesn't exist)
    load_dotenv()
    
    # Now check for credentials (could be from system env vars OR .env file)
    return bool(os.getenv('API_KEY') and os.getenv('API_SECRET'))

class EnvSetup:
    def __init__(self):
        self.env_path = Path(".env")
        self.referral_link = "https://www.asterdex.com/en/referral/3TixB2"

    def check_env_exists(self) -> bool:
        """Check if credentials are available (uses python-dotenv to load .env automatically)"""
        return has_credentials()

    def load_existing_env(self) -> dict:
        """Load existing environment variables or .env file contents"""
        env_vars = {}
        
        # First try to load from process environment variables
        if os.getenv('API_KEY'):
            env_vars['API_KEY'] = os.getenv('API_KEY')
        if os.getenv('API_SECRET'):
            env_vars['API_SECRET'] = os.getenv('API_SECRET')
        
        # If we found env vars, return them (cloud deployment)
        if env_vars:
            return env_vars
        
        # Fallback to .env file parsing (local development)
        if self.env_path.exists():
            with open(self.env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
        return env_vars

    def create_env_file(self, api_key: str, api_secret: str) -> None:
        """Create or update .env file with API credentials"""
        content = f"""# API Authentication - Simple API key (generate via Aster DEX dashboard)
API_KEY={api_key}
API_SECRET={api_secret}

"""
        with open(self.env_path, 'w') as f:
            f.write(content)
        print(f"\n[OK] .env file created successfully at: {self.env_path.absolute()}")

    def interactive_setup(self) -> None:
        """Interactive setup process for API credentials"""
        print("\n" + "="*70)
        print("ASTER LIQUIDATION HUNTER BOT - SETUP WIZARD")
        print("="*70)

        # Check if .env exists
        if self.check_env_exists():
            env_vars = self.load_existing_env()
            print("\n[!] Existing .env file found!")
            if 'API_KEY' in env_vars and 'API_SECRET' in env_vars:
                print("   Current API credentials are configured.")
                response = input("\nDo you want to update the existing credentials? (y/n): ").lower()
                if response != 'y':
                    print("[OK] Using existing configuration.")
                    return

        print("\nTo use this bot, you need API credentials from Aster DEX.")
        print("\nGet your API key using this referral link:")
        print(f"   {self.referral_link}")
        print("\n   Steps:")
        print("   1. Open the link above in your browser")
        print("   2. Create an account or login to Aster DEX")
        print("   3. Navigate to API Management in your dashboard")
        print("   4. Create a new API key with trading permissions")
        print("   5. Copy the API Key and Secret (keep them safe!)")

        print("\n" + "-"*70)
        print("\nEnter your API credentials below:")

        # Get API Key
        while True:
            api_key = input("\nAPI Key: ").strip()
            if len(api_key) >= 20:  # Basic validation
                break
            print("[ERROR] Invalid API key. Please enter a valid key.")

        # Get API Secret
        while True:
            print("\nAPI Secret (input will be hidden):")
            api_secret = getpass.getpass("").strip()
            if len(api_secret) >= 20:  # Basic validation
                break
            print("[ERROR] Invalid API secret. Please enter a valid secret.")

        # Confirm before saving
        print("\n" + "-"*70)
        print("\nConfiguration Summary:")
        print(f"   API Key: {api_key[:10]}...{api_key[-10:]}")
        print(f"   API Secret: {'*' * (len(api_secret) - 10)}...{api_secret[-10:]}")

        response = input("\nSave these credentials? (y/n): ").lower()
        if response == 'y':
            self.create_env_file(api_key, api_secret)
            print("\n[SUCCESS] Setup complete! You can now run the bot with:")
            print("   python launcher.py  (bot + dashboard)")
            print("   python main.py      (bot only)")
        else:
            print("\n[CANCELLED] Setup cancelled. No changes were made.")

    def quick_setup(self, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> bool:
        """Quick setup with provided credentials (for automation)"""
        if not api_key or not api_secret:
            return False

        try:
            self.create_env_file(api_key, api_secret)
            return True
        except Exception as e:
            print(f"[ERROR] Error creating .env file: {e}")
            return False

def main():
    """Main entry point for setup utility"""
    setup = EnvSetup()

    # Check for command line arguments for non-interactive mode
    if len(sys.argv) == 3:
        api_key = sys.argv[1]
        api_secret = sys.argv[2]
        success = setup.quick_setup(api_key, api_secret)
        sys.exit(0 if success else 1)

    # Interactive mode
    setup.interactive_setup()

if __name__ == "__main__":
    main()