# 🔧 TROUBLESHOOTING GUIDE

> **Having issues?** This guide covers the most common problems and their solutions.

## 📋 Quick Navigation

- [Installation Issues](#installation-issues)
- [API Connection Problems](#api-connection-problems)
- [Bot Startup Errors](#bot-startup-errors)
- [Trading Issues](#trading-issues)
- [Dashboard Problems](#dashboard-problems)
- [Database Errors](#database-errors)
- [Performance Issues](#performance-issues)
- [WebSocket Disconnections](#websocket-disconnections)

---

## 🔨 Installation Issues

### Python Not Found

**Error:**
```
'python' is not recognized as an internal or external command
```

**Solutions:**
1. **Windows:** Reinstall Python and CHECK "Add Python to PATH"
2. **Try alternative commands:**
   ```bash
   python3 launcher.py  # Mac/Linux
   py launcher.py       # Windows alternative
   ```
3. **Verify installation:**
   ```bash
   where python        # Windows
   which python3       # Mac/Linux
   ```

### Pip Not Found

**Error:**
```
'pip' is not recognized as an internal or external command
```

**Solutions:**
```bash
# Try these alternatives:
python -m pip install -r requirements.txt
python3 -m pip install -r requirements.txt
py -m pip install -r requirements.txt
```

### Module Import Errors

**Error:**
```
ModuleNotFoundError: No module named 'websocket'
```

**Solutions:**
1. **Reinstall requirements:**
   ```bash
   pip install -r requirements.txt --force-reinstall
   ```
2. **Check Python version:**
   ```bash
   python --version  # Should be 3.8 or higher
   ```
3. **Use virtual environment:**
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   pip install -r requirements.txt
   ```

---

## 🔑 API Connection Problems

### Invalid API Key/Secret

**Error:**
```
API Error: Invalid API key/secret
```

**Solutions:**
1. **Check .env file formatting:**
   ```
   API_KEY=your_actual_key_here
   API_SECRET=your_actual_secret_here
   ```
   - No quotes around values
   - No spaces around =
   - No trailing spaces

2. **Verify API permissions on Aster DEX:**
   - Login to Aster DEX
   - Go to API Management
   - Ensure "Enable Trading" is checked
   - Check IP whitelist if enabled

3. **Regenerate keys if needed:**
   - Delete old API key on Aster DEX
   - Create new one with correct permissions
   - Update .env file

### Rate Limit Errors

**Error:**
```
Rate limit exceeded. Please retry after X seconds
```

**Solutions:**
1. **Increase buffer in settings.json:**
   ```json
   "rate_limit_buffer_pct": 0.5  // Increase from 0.4
   ```
2. **Reduce API calls:**
   ```json
   "order_status_check_interval": 10  // Increase from 5
   ```
3. **Wait and restart:**
   - Stop bot (Ctrl+C)
   - Wait 60 seconds
   - Restart

### Connection Timeout

**Error:**
```
Connection timeout to fapi.asterdex.com
```

**Solutions:**
1. **Check internet connection**
2. **Try alternative DNS:**
   - Windows: Use 8.8.8.8 or 1.1.1.1
   - Flush DNS: `ipconfig /flushdns`
3. **Check firewall:**
   - Allow Python through firewall
   - Temporarily disable antivirus
4. **Use VPN if blocked in your region**

---

## 🤖 Bot Startup Errors

### Port Already in Use

**Error:**
```
[Errno 48] Address already in use: 5000
```

**Solutions:**
1. **Kill existing process:**
   ```bash
   # Windows:
   netstat -ano | findstr :5000
   taskkill /PID <PID_NUMBER> /F

   # Mac/Linux:
   lsof -i :5000
   kill -9 <PID>
   ```
2. **Use different port:**
   - Edit `src/api/api_server.py`
   - Change port from 5000 to 5001

### Database Lock Error

**Error:**
```
sqlite3.OperationalError: database is locked
```

**Solutions:**
1. **Close other instances:**
   - Make sure only one bot instance is running
2. **Reset database:**
   ```bash
   # Backup first:
   copy bot.db bot_backup.db
   # Then reset:
   python scripts/init_database.py
   ```
3. **Check file permissions:**
   - Ensure bot.db is writable
   - Windows: Right-click → Properties → Uncheck "Read-only"

### Configuration File Errors

**Error:**
```
json.decoder.JSONDecodeError: Expecting property name
```

**Solutions:**
1. **Validate JSON syntax:**
   - Use online JSON validator
   - Check for missing commas
   - Remove trailing commas
   - Ensure quotes around strings

2. **Common JSON mistakes:**
   ```json
   // WRONG:
   {
     "value": 123,  // No trailing comma!
   }

   // CORRECT:
   {
     "value": 123
   }
   ```

---

## 💰 Trading Issues

### No Trades Executing

**Problem:** Bot is running but not placing trades

**Solutions:**
1. **Check simulation mode:**
   ```json
   "simulate_only": false  // Must be false for real trades
   ```

2. **Lower volume thresholds:**
   ```json
   "volume_threshold_long": 50000,   // Lower from 500000
   "volume_threshold_short": 50000
   ```

3. **Verify account balance:**
   - Need sufficient USDT for margin
   - Check dashboard for balance

4. **Check position limits:**
   ```json
   "max_total_exposure_usdt": 1000,  // Increase if needed
   "max_position_usdt": 500
   ```

### Orders Not Filling

**Problem:** Orders placed but not executing

**Solutions:**
1. **Adjust price offset:**
   ```json
   "price_offset_pct": 0.05  // Reduce from 0.1 for better fills
   ```

2. **Check order time-to-live:**
   ```json
   "order_ttl_seconds": 60  // Increase from 30
   ```

3. **Use market orders (risky):**
   ```json
   "order_type": "MARKET"  // Instead of LIMIT
   ```

### Stop Loss/Take Profit Not Working

**Problem:** TP/SL orders not being placed

**Solutions:**
1. **Enable in configuration:**
   ```json
   "take_profit_enabled": true,
   "stop_loss_enabled": true,
   "use_position_monitor": true
   ```

2. **Check working type:**
   ```json
   "working_type": "CONTRACT_PRICE"  // or "MARK_PRICE"
   ```

3. **Verify position mode:**
   - Must be in hedge mode for separate positions

---

## 🖥️ Dashboard Problems

### Dashboard Not Loading

**Error:** Cannot access http://localhost:5000

**Solutions:**
1. **Check if API server is running:**
   - Look for "[API] Dashboard started" in console
2. **Try alternative URLs:**
   - http://127.0.0.1:5000
   - http://0.0.0.0:5000
3. **Check browser:**
   - Clear cache
   - Try different browser
   - Disable ad blockers

### Real-time Updates Not Working

**Problem:** Dashboard data not updating

**Solutions:**
1. **Check SSE connection:**
   - Open browser console (F12)
   - Look for EventSource errors
2. **Restart dashboard:**
   ```bash
   # Stop with Ctrl+C and restart
   python launcher.py
   ```
3. **Check database updates:**
   - Ensure bot.db is being written to

### Configuration Changes Not Saving

**Problem:** Settings changes don't persist

**Solutions:**
1. **Check file permissions:**
   - settings.json must be writable
2. **Validate JSON syntax:**
   - Use JSON validator before saving
3. **Restart bot after changes:**
   - Some settings require restart

---

## 💾 Database Errors

### Corrupted Database

**Error:**
```
sqlite3.DatabaseError: database disk image is malformed
```

**Solutions:**
1. **Restore from backup:**
   ```bash
   copy bot_backup.db bot.db
   ```
2. **Recreate database:**
   ```bash
   # Delete and recreate:
   del bot.db
   python scripts/init_database.py
   ```
3. **Export and reimport:**
   ```bash
   sqlite3 bot.db ".dump" > dump.sql
   sqlite3 new_bot.db < dump.sql
   move new_bot.db bot.db
   ```

### Migration Errors

**Error:**
```
Migration failed: column already exists
```

**Solutions:**
1. **Reset migration status:**
   ```bash
   python scripts/migrate_db.py --force
   ```
2. **Manual fix:**
   ```sql
   sqlite3 bot.db
   DROP TABLE IF EXISTS migration_status;
   .exit
   ```

---

## ⚡ Performance Issues

### High CPU Usage

**Problem:** Bot using too much CPU

**Solutions:**
1. **Reduce check intervals:**
   ```json
   "order_status_check_interval": 30,  // Increase from 5
   "cleanup_interval_seconds": 60      // Increase from 30
   ```
2. **Disable unnecessary features:**
   ```json
   "use_position_monitor": false  // If not needed
   ```
3. **Reduce symbol count:**
   - Trade fewer pairs simultaneously

### Memory Leaks

**Problem:** Memory usage keeps growing

**Solutions:**
1. **Restart periodically:**
   - Set up daily restart schedule
2. **Check for large logs:**
   ```bash
   # Clear old logs:
   del *.log
   ```
3. **Update dependencies:**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

---

## 🔌 WebSocket Disconnections

### Frequent Disconnections

**Problem:** WebSocket keeps disconnecting

**Solutions:**
1. **Check internet stability:**
   ```bash
   ping fstream.asterdex.com -t
   ```
2. **Increase reconnect delay:**
   ```json
   "price_monitor_reconnect_delay": 10  // Increase from 5
   ```
3. **Use wired connection:**
   - Avoid WiFi for trading bots

### Stream Not Receiving Data

**Problem:** Connected but no liquidations showing

**Solutions:**
1. **Check subscription:**
   - Verify stream subscriptions in logs
2. **Market activity:**
   - Low volatility = fewer liquidations
   - Check during active trading hours
3. **Test with different symbols:**
   - Some symbols more active than others

---

## 🆘 Getting More Help

### Before Asking for Help:

1. **Collect Information:**
   ```bash
   # System info:
   python --version
   pip list

   # Error logs:
   python launcher.py > error.log 2>&1
   ```

2. **Try Basic Fixes:**
   - Restart the bot
   - Check internet connection
   - Verify API keys
   - Review configuration

### When Asking for Help:

**Include:**
- Exact error message
- Steps to reproduce
- Your configuration (remove API keys!)
- System information
- What you've already tried

### Where to Get Help:

1. **Discord Community:** https://discord.gg/P8Ev3Up
2. **GitHub Issues:** https://github.com/CryptoGnome/aster_lick_hunter/issues
3. **Documentation:** Check README.md and Wiki

---

## 🔄 Common Fix Procedures

### Complete Reset Procedure

```bash
# 1. Stop the bot
Ctrl+C

# 2. Backup important files
copy settings.json settings_backup.json
copy .env .env_backup
copy bot.db bot_backup.db

# 3. Reset database
python scripts/init_database.py

# 4. Verify configuration
python scripts/verify_config.py

# 5. Start fresh
python launcher.py
```

### Safe Mode Start

```bash
# 1. Enable simulation mode
# Edit settings.json: "simulate_only": true

# 2. Minimal configuration
# Disable advanced features temporarily

# 3. Start with single symbol
# Remove all but BTCUSDT from config

# 4. Gradual re-enable
# Add features back one by one
```

---

## 📝 Logging and Debugging

### Enable Debug Mode

Add to your launch command:
```bash
# Windows:
set DEBUG=1 && python launcher.py

# Mac/Linux:
DEBUG=1 python launcher.py
```

### View Detailed Logs

```bash
# Save all output to file:
python launcher.py > bot.log 2>&1

# View in real-time:
tail -f bot.log  # Mac/Linux
type bot.log     # Windows
```

### Check Specific Components

```bash
# Test API connection:
python tests/test_api_connection.py

# Test WebSocket:
python tests/test_websocket.py

# Verify database:
python scripts/verify_database.py
```

---

<p align="center">
  <b>Still stuck? Join our Discord for live help! 💬</b>
</p>

<p align="center">
  <i>Remember: Most issues have simple solutions. Stay calm and work through the steps!</i>
</p>