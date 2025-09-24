# 🚀 Aster Liquidation Hunter Bot
[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-success)](https://github.com/CryptoGnome/aster_lick_hunter)
[![Dashboard](https://img.shields.io/badge/dashboard-web--based-orange)](http://localhost:5000)

## 💝 Support Development - This Bot is 100% FREE!

**This bot is completely free and open-source!** If you find it useful and want to support ongoing development, please consider creating your Aster DEX account using our referral link:

### 👉 [**Create Aster DEX Account - Support Development**](https://www.asterdex.com/en/referral/3TixB2)

*By using this referral link for your new account, you help fund continued improvements and new features while getting the exact same trading conditions. Thank you for your support!*

---

An advanced cryptocurrency trading bot that monitors real-time liquidation events on Aster DEX and executes intelligent counter-trades based on configurable volume thresholds. Features a comprehensive web dashboard for monitoring, analytics, and configuration management.

## 🎯 Key Features

### Core Trading Engine
- **Real-time Liquidation Monitoring** - WebSocket connection to Aster DEX liquidation stream
- **Volume-Based Triggers** - Executes trades when liquidation volume exceeds configured thresholds
- **Intelligent Order Placement** - Uses orderbook analysis for optimal entry prices
- **Automated Risk Management** - Automatic Take Profit and Stop Loss order placement
- **Hedge Mode Support** - Separate LONG/SHORT position management
- **Multi-Symbol Trading** - Trade multiple cryptocurrency pairs simultaneously

### Advanced Features
- **🆕 Intelligent Tranche System** - Revolutionary position management that automatically splits positions into tranches based on PnL performance
  - Creates new tranches when existing positions reach configurable loss thresholds
  - Merges profitable tranches to optimize capital efficiency
  - Limits maximum tranches per symbol/side for risk control
  - Configurable PnL increment percentage for tranche triggers (default 5%)
- **Smart Position Sizing** - Calculates optimal position sizes based on leverage and risk parameters
- **Order Lifecycle Management** - Automated cleanup of stale orders and position tracking
- **Real-time P&L Tracking** - Monitor realized and unrealized profits/losses
- **Simulation Mode** - Test strategies without risking capital
- **Rate Limit Protection** - Built-in rate limiting with configurable buffer

### Web Dashboard
- **Real-time Monitoring** - Live updates via Server-Sent Events (SSE)
- **Position Management** - View and track all open positions
- **Trade Analytics** - Comprehensive trade history with P&L metrics
- **Configuration UI** - Easy symbol addition/removal and parameter adjustment
- **Performance Charts** - Visual representation of trading performance
- **Account Overview** - Balance, margin, and exposure monitoring

## 📊 Dashboard Preview

<img width="1896" height="954" alt="image" src="https://github.com/user-attachments/assets/3fbba51a-8111-40d8-9a35-c6bf2bd31236" />



## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- Aster DEX API credentials
- Git (for cloning the repository)

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/CryptoGnome/aster_lick_hunter.git
cd aster_lick_hunter
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
# Create .env file
cp .env.example .env

# Edit .env with your API credentials
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here
```

4. **Configure trading parameters**
```bash
# Edit settings.json to customize your trading strategy
nano settings.json
```

5. **Run the bot**
```bash
# Run both bot and dashboard
python launcher.py

# Or run components separately
python main.py                # Bot only
python src/api/api_server.py  # Dashboard only
```

6. **Access the dashboard**
```
Open your browser and navigate to: http://localhost:5000
```

## ⚙️ Configuration

### Global Settings (`settings.json`)
<img width="1062" height="665" alt="image" src="https://github.com/user-attachments/assets/1393efa4-34bc-4575-9a05-b80e4efc98cc" />


```json
{
  "globals": {
    "volume_window_sec": 60,        // Time window for volume calculation
    "simulate_only": false,         // Enable simulation mode
    "multi_assets_mode": true,      // Use multi-assets margin
    "hedge_mode": true,            // Enable hedge mode
    "order_ttl_seconds": 30,       // Order time-to-live
    "max_open_orders_per_symbol": 5,
    "max_total_exposure_usdt": 1000.0,
    "tranche_pnl_increment_pct": 5.0,  // PnL threshold for new tranche creation
    "max_tranches_per_symbol_side": 5  // Maximum tranches per symbol/side
  }
}
```

### Symbol Configuration

```json
{
  "symbols": {
    "BTCUSDT": {
      "volume_threshold": 20000,     // USDT volume trigger threshold
      "leverage": 10,                // Trading leverage
      "trade_value_usdt": 100,      // Position size in USDT
      "price_offset_pct": 0.1,      // Entry price offset from market
      "take_profit_pct": 2.0,       // Take profit percentage
      "stop_loss_pct": 1.0,         // Stop loss percentage
      "max_position_usdt": 1000     // Maximum position size
    }
  }
}
```

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     WebSocket Streams                       │
│  ┌──────────────────┐        ┌──────────────────┐         │
│  │ Liquidation Data │        │ User Data Stream │         │
│  └────────┬─────────┘        └────────┬─────────┘         │
│           │                            │                    │
│  ┌────────▼─────────────────────────────▼─────────┐       │
│  │            Core Trading Engine                  │       │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │       │
│  │  │ Streamer │  │  Trader  │  │  Order   │    │       │
│  │  │          │  │          │  │ Manager  │    │       │
│  │  └──────────┘  └──────────┘  └──────────┘    │       │
│  └──────────────────┬───────────────────────────┘        │
│                     │                                      │
│  ┌──────────────────▼───────────────────────────┐        │
│  │              Database Layer                   │        │
│  │  ┌──────────────────────────────────────┐   │        │
│  │  │ SQLite: liquidations, trades, orders │   │        │
│  │  └──────────────────────────────────────┘   │        │
│  └───────────────────┬──────────────────────────┘        │
│                      │                                     │
│  ┌───────────────────▼──────────────────────────┐        │
│  │            Web Dashboard API                  │        │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │        │
│  │  │   Flask  │  │   SSE    │  │   PNL    │  │        │
│  │  │  Server  │  │  Events  │  │ Tracker  │  │        │
│  │  └──────────┘  └──────────┘  └──────────┘  │        │
│  └───────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Liquidation Detection** → WebSocket receives liquidation event
2. **Data Storage** → Event stored in SQLite database
3. **Volume Analysis** → Calculate volume in time window
4. **Trade Decision** → Evaluate against configured thresholds
5. **Order Execution** → Place limit order with optimal pricing
6. **Risk Management** → Automatic TP/SL order placement
7. **Position Tracking** → Real-time position and P&L updates

## 📈 Trading Strategy

The bot implements a counter-trend strategy based on liquidation cascades with advanced tranche management:

1. **Monitor** - Continuously monitor liquidation events
2. **Aggregate** - Calculate total liquidation volume in rolling window
3. **Trigger** - Execute trade when volume exceeds threshold
4. **Position** - Take opposite position to liquidation direction
5. **Tranche Management** - Intelligently manage positions through tranches:
   - Create new tranches when losses exceed PnL threshold (default 5%)
   - Merge profitable tranches to optimize capital efficiency
   - Limit maximum tranches per symbol/side for risk control
6. **Manage** - Set automatic take profit and stop loss levels
7. **Track** - Monitor position performance in real-time

### Example Trade Flow with Tranche System

```
Liquidation Detected:
  └─> Symbol: BTCUSDT
  └─> Side: LONG liquidated
  └─> Volume: $25,000

Volume Check:
  └─> 60s window: $45,000
  └─> Threshold: $20,000 ✓

Execute Trade (Tranche 0):
  └─> Side: SHORT (opposite)
  └─> Size: $100 × 10 leverage = $1,000 position
  └─> Entry: $98,500 (0.1% below market)
  └─> Tranche ID: 0 (first position)

Risk Management:
  └─> Take Profit: $96,530 (2% profit)
  └─> Stop Loss: $99,485 (1% loss)

If Price Moves Against (Loss > 5%):
  └─> New Liquidation Triggers
  └─> Create Tranche 1 (separate from Tranche 0)
  └─> Independent entry price tracking
  └─> Automatic merge when profitable
```

## 🔒 Security Features

- **API Key Encryption** - Secure storage of credentials in `.env` file
- **HMAC Authentication** - SHA256 signature-based API authentication
- **Rate Limiting** - Built-in protection against API rate limits
- **Order Validation** - Pre-trade checks for position limits
- **Error Handling** - Comprehensive error catching and logging
- **Graceful Shutdown** - Clean disconnection and resource cleanup

## 📝 API Documentation

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/positions` | GET | Current positions |
| `/api/account` | GET | Account information |
| `/api/trades` | GET | Trade history |
| `/api/liquidations` | GET | Recent liquidations |
| `/api/stats` | GET | Performance statistics |
| `/api/config` | GET/POST | Configuration management |
| `/api/stream` | GET | Real-time SSE stream |

### WebSocket Streams

- **Liquidation Stream**: `wss://fstream.asterdex.com/stream?streams=!forceOrder@arr`
- **User Data Stream**: Account updates, order updates, position changes

## 🧪 Testing

### Simulation Mode

Enable simulation mode to test strategies without real trades:

```json
{
  "globals": {
    "simulate_only": true
  }
}
```

### Unit Tests

```bash
# Run test suite
python -m pytest tests/

# Run with coverage
python -m pytest --cov=src tests/
```

## 📊 Performance Metrics

- **Response Time**: < 100ms order placement
- **WebSocket Latency**: < 50ms message processing
- **Database Queries**: Indexed for < 10ms response
- **Dashboard Updates**: Real-time via SSE
- **Memory Usage**: < 200MB typical operation

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## ⚠️ Risk Warning

**IMPORTANT**: Cryptocurrency trading carries significant risk. This bot is provided as-is without any guarantee of profit. Always:

- Start with small position sizes
- Test thoroughly in simulation mode
- Never invest more than you can afford to lose
- Monitor the bot's operation regularly
- Understand the code before using real funds

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Aster DEX for providing the trading API
- The open-source community for invaluable tools and libraries
- Contributors and testers who helped improve the bot

## 📞 Support

- **Discord Community**: [Join our Discord](https://discord.gg/P8Ev3Up) - Get help, share strategies, and connect with other traders
- **Issues**: [GitHub Issues](https://github.com/CryptoGnome/aster_lick_hunter/issues)
- **Discussions**: [GitHub Discussions](https://github.com/CryptoGnome/aster_lick_hunter/discussions)
- **Documentation**: [Wiki](https://github.com/CryptoGnome/aster_lick_hunter/wiki)

## 🚦 Status

- ✅ Core Trading Engine
- ✅ WebSocket Integration
- ✅ Database Layer
- ✅ Order Management
- ✅ Web Dashboard
- ✅ Real-time Updates
- ✅ P&L Tracking
- ✅ Configuration UI
- ✅ Intelligent Tranche System

---

<p align="center">
  Made with ❤️ by the Aster Liquidation Hunter Team
</p>

<p align="center">
  <a href="https://github.com/CryptoGnome/aster_lick_hunter">
    <img src="https://img.shields.io/github/stars/CryptoGnome/aster_lick_hunter?style=social" alt="Stars">
  </a>
  <a href="https://github.com/CryptoGnome/aster_lick_hunter/network/members">
    <img src="https://img.shields.io/github/forks/CryptoGnome/aster_lick_hunter?style=social" alt="Forks">
  </a>
</p>
