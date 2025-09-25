# 📝 Changelog

All notable changes to the Aster Liquidation Hunter Bot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🚀 Added
- **Enhanced Rate Limiter** - Dynamic endpoint weights for improved API rate limit management
- **Order Recovery System** - Failed attempt tracking with recovery cooldowns
- **Retry Logic** - Automatic retry for position fetching with configurable attempts
- **Trade History Enhancements** - Extended default range and improved UI controls
- **Liquidation Buffering** - Collects liquidations before batch processing
- **Order Batching** - Batch order submission for API efficiency
- **Header Improvements** - Added logo and social links (GitHub, Aster DEX, Discord)
- **Mobile Responsiveness** - Better dashboard experience on mobile devices
- **Documentation Suite** - QUICKSTART, TROUBLESHOOTING, CONTRIBUTING guides
- **Enhanced README** - User-friendly structure with video tutorials and feature details
- **Circuit Breaker Pattern** - Prevents infinite error loops in instant profit capture
- **Enhanced Error Handling** - Improved error code detection and recovery mechanisms

### 🔧 Fixed
- **Instant Profit Capture -1106 Error** - Fixed critical bug causing "Parameter 'reduceOnly' sent when not required" errors
  - Position monitor now correctly handles order parameters based on hedge mode setting
  - Added conditional logic: `reduceOnly` only sent in one-way mode, not in hedge mode
  - Properly sends `positionSide` parameter when in hedge mode
  - Added circuit breaker to prevent infinite retry loops (disables after 3 failures)
  - Enhanced position validation before attempting closure
  - Improved error handling for various API error codes (-1106, -2022, -2019)
- **Database Location Issue** - bot.db now correctly created in data/ directory instead of root
  - Updated config.py to use absolute path for database
  - Added automatic data directory creation if it doesn't exist
  - Ensured all database connections use the correct path
- **Margin Calculation Logic** - Improved handling for isolated and cross positions
- **Position Monitor** - Enhanced TP/SL fill handling and close logic
- **Re-entrant Locking** - Replaced Lock with RLock in PositionMonitor for thread safety
- **Multi-Assets Mode** - Enhanced error handling for mode changes
- **Recovery Cooldown** - Reduced cooldown time and improved margin type error handling

### 🛠️ Changed
- **Logging System** - Reduced verbosity in batch order logging for cleaner output
- **Trade Filtering** - Enhanced filtering capabilities with improved performance
- **Liquidation Notifications** - Toast notifications now display USDT values
- **Documentation** - Condensed and improved clarity across all docs

### 🧪 Testing
- **Comprehensive Test Suite** - Added unit and integration tests for position monitor
  - Unit tests for hedge mode order parameter validation
  - Integration tests for instant profit capture flow
  - Circuit breaker activation tests
  - Order parameter verification script for debugging

---

## [2.0.0] - 2024-09-24

### 🚀 Major Release - Position Monitor & Advanced Features

### Added
- **Position Monitor System** - Unified TP/SL management with real-time price monitoring
- **Order Batching** - Batch order submission for API efficiency
- **Liquidation Buffering** - Collects liquidations before processing
- **Instant TP** - Immediate profit capture when prices spike
- **Re-entrant Locking** - Thread-safe operations with RLock
- **Auto-migration System** - Automatic database schema updates on startup
- **Enhanced Dashboard** - Account performance overview with improved UI
- **Social Links** - GitHub, Aster DEX, and Discord links in header
- **Mobile Responsiveness** - Better dashboard experience on mobile devices

### Changed
- Replaced Lock with RLock in PositionMonitor for re-entrant locking
- Enhanced position details API with TP/SL integration
- Improved header layout and mobile responsiveness
- Enhanced liquidation toast notifications with USDT values

### Fixed
- Database tranche_id handling issues
- Position closure modal handling
- Open orders calculation in positions API

### Documentation
- Enhanced documentation for Position Monitor
- Added Order Batcher documentation
- Improved auto-migration documentation

---

## [1.5.0] - 2024-09-15

### Added
- **Intelligent Tranche System** - Dynamic position scaling based on P&L
- **Position Routes Enhancement** - Better TP/SL order handling
- **Close Position Endpoint** - Programmatic position closure via API
- **Emergency Scripts** - TP/SL placement for unprotected positions
- **Position Protection Verification** - Verify all positions have protective orders

### Changed
- Improved trade data integration in position routes
- Enhanced database schema for tranche management
- Better error handling in order cleanup service

### Fixed
- Tranche ID database issues
- Order cleanup edge cases
- Mismatched order cleanup

---

## [1.0.0] - 2024-09-01

### 🎉 Initial Release

### Core Features
- **Real-time Liquidation Monitoring** - WebSocket connection to Aster DEX
- **Volume-Based Trading** - Configurable thresholds for trade execution
- **Automated Risk Management** - Automatic TP/SL order placement
- **Web Dashboard** - Real-time monitoring and configuration
- **Database Layer** - SQLite with indexed tables for performance
- **Order Cleanup Service** - Automated stale order management
- **User Data Stream** - Real-time position updates
- **P&L Tracking** - Comprehensive profit/loss calculations

### Trading Features
- **Hedge Mode Support** - Separate LONG/SHORT positions
- **Multi-Symbol Trading** - Trade multiple pairs simultaneously
- **Simulation Mode** - Test strategies without real trades
- **Smart Order Placement** - Orderbook analysis for optimal entries
- **Position Size Management** - Configurable limits and exposure control

### Dashboard Features
- **Real-time Updates** - Server-Sent Events for live data
- **Trade History** - Complete record with filtering
- **Performance Charts** - Visual analytics
- **Configuration UI** - Easy settings management
- **Symbol Management** - Add/remove trading pairs

### Security Features
- **HMAC Authentication** - Secure API communication
- **Rate Limiting** - Built-in protection with buffer
- **Environment Variables** - Secure credential storage
- **Input Validation** - Pre-trade checks

---

## [0.9.0-beta] - 2024-08-15

### 🔬 Beta Release

### Added
- Initial WebSocket implementation
- Basic trading logic
- Simple web interface
- Database structure
- Configuration system

### Known Issues
- WebSocket reconnection issues
- Memory leaks in long-running sessions
- Dashboard refresh problems

---

## Version History

### Versioning Scheme

We use Semantic Versioning (SemVer):
- **MAJOR** version (X.0.0) - Incompatible API changes
- **MINOR** version (0.X.0) - New functionality, backwards compatible
- **PATCH** version (0.0.X) - Bug fixes, backwards compatible

### Migration Guide

#### From 1.x to 2.0

1. **Database Migration Required:**
   ```bash
   python scripts/migrate_to_position_monitor.py
   ```

2. **New Configuration Options:**
   ```json
   {
     "use_position_monitor": true,
     "instant_tp_enabled": true,
     "buffer_liquidations": true,
     "batch_orders": true
   }
   ```

3. **API Changes:**
   - `/api/positions` now includes TP/SL details
   - New endpoint: `/api/positions/<symbol>/close`

#### From 0.9 to 1.0

1. **Complete reinstall recommended:**
   ```bash
   git pull
   pip install -r requirements.txt --upgrade
   python scripts/init_database.py
   ```

2. **Configuration format changed** - Review settings.json.example

---

## Deprecated Features

### Version 2.0
- `use_old_tp_sl_system` - Replaced by Position Monitor
- Manual TP/SL placement - Now automated

### Version 1.0
- Legacy WebSocket handler - Replaced with improved version
- Old dashboard UI - Complete redesign

---

## Roadmap

### Version 2.1 (Planned)
- [ ] Advanced charting with TradingView integration
- [ ] Multi-exchange support
- [ ] Telegram notifications
- [ ] Strategy backtesting framework

### Version 2.2 (Future)
- [ ] Machine learning price predictions
- [ ] Custom strategy plugins
- [ ] Mobile app
- [ ] Cloud deployment templates

### Version 3.0 (Long-term)
- [ ] Full automation with AI
- [ ] Social trading features
- [ ] Copy trading functionality
- [ ] Advanced risk analytics

---

## Support

For questions about versions and updates:
- 💬 **Discord**: https://discord.gg/P8Ev3Up
- 🐛 **Issues**: https://github.com/CryptoGnome/aster_lick_hunter/issues
- 📚 **Wiki**: https://github.com/CryptoGnome/aster_lick_hunter/wiki

---

## Contributors

See [CONTRIBUTORS.md](CONTRIBUTORS.md) for a list of contributors to each version.

---

<p align="center">
  <b>Stay updated with the latest features! ⭐ Star the repo for notifications!</b>
</p>