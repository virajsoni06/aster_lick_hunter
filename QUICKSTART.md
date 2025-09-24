<div align="center">
  <img src="static/logo.svg" alt="Aster Logo" width="250" />

  # 🚀 QUICKSTART GUIDE

  ### From Zero to Trading in 5 Minutes!
</div>

> **👋 Complete Beginner?** This guide is for you! We'll walk through every step with pictures and simple explanations.

## 📋 Table of Contents
1. [What You Need Before Starting](#-what-you-need-before-starting)
2. [Step 1: Install Python](#-step-1-install-python)
3. [Step 2: Download the Bot](#-step-2-download-the-bot)
4. [Step 3: Install Requirements](#-step-3-install-requirements)
5. [Step 4: Get Your API Keys](#-step-4-get-your-api-keys)
6. [Step 5: Configure the Bot](#-step-5-configure-the-bot)
7. [Step 6: Run Your First Test](#-step-6-run-your-first-test)
8. [Understanding the Dashboard](#-understanding-the-dashboard)
9. [Common Issues & Solutions](#-common-issues--solutions)
10. [Next Steps](#-next-steps)

---

## 🎯 What You Need Before Starting

### Required:
- ✅ A computer (Windows, Mac, or Linux)
- ✅ Internet connection
- ✅ About 15 minutes of time
- ✅ Basic ability to copy/paste commands

### NOT Required:
- ❌ Programming experience
- ❌ Trading experience
- ❌ Money to start (we'll use simulation mode!)

---

## 🐍 Step 1: Install Python

Python is the programming language the bot uses. Think of it as the engine that runs the bot.

### For Windows Users:

1. **Download Python:**
   - Go to: https://www.python.org/downloads/
   - Click the big yellow "Download Python 3.11.x" button
   - Save the file

2. **Install Python:**
   ```
   ⚠️ IMPORTANT: Check "Add Python to PATH" before clicking Install!
   ```
   - Run the downloaded file
   - ✅ CHECK "Add Python 3.11 to PATH" (VERY IMPORTANT!)
   - Click "Install Now"
   - Wait for installation to complete
   - Click "Close"

3. **Verify Installation:**
   - Press `Windows + R`
   - Type `cmd` and press Enter
   - In the black window, type:
   ```bash
   python --version
   ```
   - You should see: `Python 3.11.x` (or similar)
   - If you see an error, restart your computer and try again

### For Mac Users:

1. **Open Terminal:**
   - Press `Command + Space`
   - Type "Terminal" and press Enter

2. **Install Python:**
   ```bash
   # Check if Python is installed
   python3 --version

   # If not installed, install it:
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   brew install python@3.11
   ```

### For Linux Users:

1. **Open Terminal and run:**
   ```bash
   sudo apt update
   sudo apt install python3.11 python3-pip
   python3 --version
   ```

---

## 📥 Step 2: Download the Bot

### Option A: Download as ZIP (Easiest for Beginners)

1. **Go to the bot page:**
   - Visit: https://github.com/CryptoGnome/aster_lick_hunter

2. **Download the code:**
   - Click the green "Code" button
   - Click "Download ZIP"
   - Save to your Desktop

3. **Extract the files:**
   - Find the ZIP file on your Desktop
   - Right-click → "Extract All" (Windows) or double-click (Mac)
   - Remember where you extracted it!

### Option B: Use Git (If you have it)

```bash
cd Desktop
git clone https://github.com/CryptoGnome/aster_lick_hunter.git
cd aster_lick_hunter
```

---

## 📦 Step 3: Install Requirements

Now we need to install the bot's dependencies (helper programs it needs).

### Windows:

1. **Open Command Prompt:**
   - Press `Windows + R`
   - Type `cmd` and press Enter

2. **Navigate to the bot folder:**
   ```bash
   cd Desktop\aster_lick_hunter
   ```

3. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

   Wait for everything to install (this might take 2-3 minutes).

### Mac/Linux:

1. **Open Terminal**

2. **Navigate to the bot folder:**
   ```bash
   cd ~/Desktop/aster_lick_hunter
   ```

3. **Install requirements:**
   ```bash
   pip3 install -r requirements.txt
   ```

### ⚠️ Troubleshooting:
- If you see "pip not found", try `python -m pip install -r requirements.txt`
- If you see permission errors, try adding `--user` at the end

---

## 🔑 Step 4: Get Your API Keys

API keys let the bot trade on your behalf. Think of them as a special password for the bot.

### Creating Your Aster DEX Account:

1. **Sign up using our referral link (supports development):**
   - Visit: https://www.asterdex.com/en/referral/3TixB2
   - Click "Register"
   - Complete registration (email, password, etc.)
   - Verify your email

2. **Generate API Keys:**
   - Log into your Aster DEX account
   - Go to Account → API Management
   - Click "Create API"
   - Give it a name like "Trading Bot"
   - ⚠️ **IMPORTANT Settings:**
     - ✅ Enable "Enable Trading"
     - ✅ Enable "Enable Reading"
     - ❌ Disable "Enable Withdrawal" (for safety!)
   - Save your API Key and Secret somewhere safe!

### Setting Up Your Keys:

1. **In the bot folder, create your .env file:**

   **Windows (Command Prompt):**
   ```bash
   copy .env.example .env
   notepad .env
   ```

   **Mac/Linux (Terminal):**
   ```bash
   cp .env.example .env
   nano .env
   ```

2. **Edit the file:**
   Replace the placeholder text with your actual keys:
   ```
   API_KEY=your_actual_api_key_here
   API_SECRET=your_actual_api_secret_here
   ```

3. **Save the file:**
   - Windows: `Ctrl + S`, then close Notepad
   - Mac/Linux: `Ctrl + X`, then `Y`, then Enter

---

## ⚙️ Step 5: Configure the Bot

The bot needs to know how to trade. We'll start with SAFE settings.

### Edit settings.json:

**Windows:**
```bash
notepad settings.json
```

**Mac/Linux:**
```bash
nano settings.json
```

### 🚨 CRITICAL SAFETY SETTINGS for Beginners:

```json
{
  "globals": {
    "simulate_only": true,  // 👈 MUST BE TRUE TO START!
    "volume_window_sec": 60,
    "max_total_exposure_usdt": 100,  // Start small!
    "use_position_monitor": true
  },
  "symbols": {
    "BTCUSDT": {
      "volume_threshold_long": 500000,  // High threshold = fewer trades
      "volume_threshold_short": 500000,
      "leverage": 5,  // Low leverage = less risk
      "trade_value_usdt": 10,  // Very small position size
      "take_profit_pct": 2.0,
      "stop_loss_pct": 1.0
    }
  }
}
```

**Save the file!**

---

## 🎮 Step 6: Run Your First Test

### Start the Bot:

**Windows:**
```bash
python launcher.py
```

**Mac/Linux:**
```bash
python3 launcher.py
```

### What You Should See:

```
===========================================
 ASTER LIQUIDATION HUNTER BOT - LAUNCHER
===========================================
Starting services...

[BOT] ✅ Bot process started
[API] ✅ Dashboard started at http://localhost:5000
[LAUNCHER] All services running. Press Ctrl+C to stop.

[BOT] 🚀 STARTUP: Order cleanup service initialized
[BOT] 📊 Connected to Aster DEX
[BOT] 🔍 Monitoring liquidations...
```

### Open the Dashboard:

1. Open your web browser
2. Go to: http://localhost:5000
3. You should see the trading dashboard!

---

## 📊 Understanding the Dashboard

### Main Sections:

1. **Account Overview (Top)**
   - Balance: Your account balance
   - Positions: Current open trades
   - P&L: Profit and Loss

2. **Live Feed (Left)**
   - Shows liquidations as they happen
   - Green = threshold met, trade triggered
   - Red = below threshold, no trade

3. **Positions (Center)**
   - Your current open positions
   - Entry price, current price, P&L

4. **Configuration (Right)**
   - Change settings without editing files
   - Add/remove trading pairs

### 🟢 Status Indicators:

- **"SIMULATION MODE"** = No real trades (safe!)
- **"CONNECTED"** = Bot is running properly
- **"MONITORING"** = Watching for liquidations

---

## ❗ Common Issues & Solutions

### Problem: "Python not found"
**Solution:** Restart your computer after installing Python, make sure you checked "Add to PATH"

### Problem: "pip not found"
**Solution:** Try `python -m pip install -r requirements.txt` instead

### Problem: "API Error: Invalid API Key"
**Solution:** Double-check your .env file, make sure you copied the keys correctly

### Problem: Dashboard won't load
**Solution:** Make sure no other program is using port 5000, try http://127.0.0.1:5000

### Problem: No liquidations showing
**Solution:** This is normal! Liquidations don't happen every second. Be patient.

### Problem: "Permission denied" errors
**Solution:**
- Windows: Run Command Prompt as Administrator
- Mac/Linux: Add `sudo` before commands

---

## ✅ Next Steps

### 1. Watch and Learn (Day 1-3)
- Keep the bot running in **SIMULATION MODE**
- Watch how it responds to liquidations
- Note when trades happen and why

### 2. Understand the Strategy (Day 4-7)
- Read about liquidations and why they matter
- Understand the "counter-trade" strategy
- Join our Discord to ask questions

### 3. Paper Trading (Week 2-4)
- Keep using simulation mode
- Track hypothetical profits/losses
- Adjust settings based on observations

### 4. Small Real Trades (After 1 Month)
- Start with tiny amounts ($10-20)
- Set `simulate_only` to `false`
- Monitor closely!

### 5. Gradual Scaling (Months 2+)
- Slowly increase position sizes
- Never risk more than you can afford to lose
- Keep learning and improving

---

## 🎓 Learning Resources

### Essential Reading:
- 📖 [What are Liquidations?](https://www.binance.com/en/support/faq/what-is-liquidation-360033525271)
- 📊 [Understanding Leverage](https://www.investopedia.com/terms/l/leverage.asp)
- 🛡️ [Risk Management Basics](https://www.babypips.com/learn/forex/risk-management)

### Our Resources:
- 💬 [Discord Community](https://discord.gg/P8Ev3Up) - Get help!
- 📺 Video Tutorials (Coming Soon)
- 📚 [Full Documentation](README.md)

---

## 🆘 Getting Help

### Before Asking for Help:

1. **Check this guide again** - Did you miss a step?
2. **Read error messages** - They often tell you what's wrong
3. **Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues
4. **Search Discord** - Someone might have had the same issue

### When Asking for Help:

Include:
- What step you're on
- The exact error message
- What you've already tried
- Screenshots if possible

### Where to Get Help:
- 💬 **Discord**: https://discord.gg/P8Ev3Up (Fastest!)
- 🐛 **GitHub Issues**: For bug reports
- 📧 **Email**: (Coming soon)

---

## 🎉 Congratulations!

You've successfully:
- ✅ Installed Python
- ✅ Downloaded the bot
- ✅ Set up API keys
- ✅ Configured safe settings
- ✅ Started the bot in simulation mode
- ✅ Opened the dashboard

**You're now running a cryptocurrency trading bot!**

### Remember:
- 🧪 **Stay in simulation mode** until you fully understand the bot
- 📚 **Keep learning** about trading and risk management
- 💬 **Join the Discord** for community support
- ⚠️ **Never invest more than you can afford to lose**
- 🎯 **Start small, scale gradually**

---

## 🚀 Quick Command Reference

### Daily Operations:

```bash
# Start the bot
python launcher.py

# Stop the bot
Press Ctrl+C in the terminal

# Check if bot is running
# Look for python processes or check http://localhost:5000

# View logs
# Check the terminal window where you started the bot
```

### Maintenance:

```bash
# Update the bot (when new versions are released)
git pull
pip install -r requirements.txt

# Backup your settings
copy settings.json settings_backup.json
copy .env .env_backup

# Reset database (if needed)
python scripts/init_database.py
```

---

<p align="center">
  <b>Welcome to the Aster Liquidation Hunter Community! 🎉</b>
</p>

<p align="center">
  <i>Remember: Every expert was once a beginner. Take your time, stay safe, and happy trading!</i>
</p>