# Position Monitor Test Guide

Comprehensive guide for testing the Position Monitor implementation.

## Test Suite Overview

The Position Monitor system includes three levels of testing:

### 1. Unit Tests (`tests/test_position_monitor.py`)
- Tests individual PositionMonitor methods
- Validates tranche logic and calculations
- Mocks all external dependencies

### 2. Integration Tests (`tests/test_integration_position_monitor.py`)  
- Tests component interactions
- Validates trader.py and user_stream.py integration
- Tests backward compatibility

### 3. End-to-End Tests (`tests/test_position_monitor_e2e.py`)
- Tests complete workflows
- Simulates real trading scenarios
- Performance and error handling tests

## Running the Tests

### Quick Test Commands

```bash
# Run all Position Monitor tests
python tests/test_position_monitor.py
python tests/test_integration_position_monitor.py
python tests/test_position_monitor_e2e.py

# Run specific test categories
python -c "from tests.test_position_monitor import *; asyncio.run(test_tranche_determination())"
python -c "from tests.test_integration_position_monitor import *; asyncio.run(TestIntegration().test_trader_position_monitor_integration())"
python -c "from tests.test_position_monitor_e2e import *; asyncio.run(TestE2E().test_complete_trade_lifecycle())"
```

### Test Output Interpretation

#### Successful Test Run:
```
========================================
🧪 POSITION MONITOR TEST SUITE
========================================

🎯 Testing Tranche Determination...
  ✅ Initial order creates tranche 0
  ✅ Same price adds to existing tranche
  ✅ New tranche when PnL < -5%

📊 Testing TP/SL Calculation...
  ✅ TP price: 45450.0 (+1.0%)
  ✅ SL price: 42750.0 (-5.0%)

========================================
📊 TEST RESULTS
   ✅ Passed: 10
   ❌ Failed: 0
   📈 Success Rate: 100.0%
========================================
```

#### Failed Test Example:
```
❌ Test test_instant_closure failed: AssertionError: Market order should be placed
Traceback (most recent call last):
  ...
```

## Test Coverage Areas

### Unit Test Coverage

| Test Name | What It Tests | Key Assertions |
|-----------|--------------|----------------|
| `test_tranche_determination` | Tranche ID assignment logic | New tranches only when PnL < -5% |
| `test_tp_sl_calculation` | TP/SL price calculations | Correct percentage-based pricing |
| `test_instant_closure` | Instant market closure trigger | Market orders when price > TP |
| `test_order_registration` | Order tracking | Proper order state management |
| `test_websocket_handling` | Price update processing | Mark price parsing and updates |
| `test_database_recovery` | Startup recovery | Tranches restored from DB |
| `test_batch_operations` | API call batching | Multiple orders in single call |
| `test_error_handling` | Failure scenarios | Graceful degradation |
| `test_position_aggregation` | Multi-tranche positions | Correct quantity/price averaging |
| `test_cleanup_operations` | Order cancellation | Proper cleanup on position close |

### Integration Test Coverage

| Test Name | Components Tested | Key Validation |
|-----------|-------------------|----------------|
| `test_trader_position_monitor_integration` | trader.py + PositionMonitor | Order flow and notifications |
| `test_user_stream_integration` | user_stream.py + PositionMonitor | Fill notifications |
| `test_main_initialization` | main.py startup | Proper initialization |
| `test_order_flow_end_to_end` | Complete order lifecycle | Placement to closure |
| `test_backwards_compatibility` | Legacy system fallback | Works when disabled |
| `test_error_handling` | Error recovery | Handles failures gracefully |

### E2E Test Coverage

| Test Name | Scenario | Success Criteria |
|-----------|----------|------------------|
| `test_complete_trade_lifecycle` | Liquidation → Fill → TP Hit | Position closed at profit |
| `test_multi_tranche_scenario` | Multiple tranches forming | Independent TP/SL per tranche |
| `test_websocket_reconnection` | Connection loss/recovery | Auto-reconnect works |
| `test_database_recovery` | Startup with existing positions | All tranches recovered |
| `test_api_error_handling` | API failures | No crashes, graceful handling |
| `test_concurrent_operations` | Multiple simultaneous fills | Thread-safe operations |
| `test_performance_monitoring` | Latency measurements | <100ms instant closure |

## Testing in Different Modes

### 1. Simulation Mode Testing

```json
// settings.json
{
  "globals": {
    "simulate_only": true,
    "use_position_monitor": true,
    "instant_tp_enabled": true
  }
}
```

Run: `python main.py`
- Orders logged but not sent to exchange
- Perfect for initial testing
- Check logs for "SIMULATED" orders

### 2. Legacy Mode Testing

```json
{
  "globals": {
    "use_position_monitor": false
  }
}
```

Verify:
- Old TP/SL system still works
- No PositionMonitor initialization
- Legacy `place_tp_sl_orders()` called

### 3. Production Mode Testing

```json
{
  "globals": {
    "simulate_only": false,
    "use_position_monitor": true,
    "instant_tp_enabled": true
  }
}
```

**CAUTION**: Real orders will be placed!

## Manual Testing Checklist

### Pre-Launch Verification
- [ ] All tests pass (`python tests/test_position_monitor*.py`)
- [ ] Database has `tranche_id`, `tp_order_id`, `sl_order_id` columns
- [ ] Settings.json has Position Monitor flags
- [ ] WebSocket URL is accessible

### Simulation Testing
- [ ] Enable simulation mode
- [ ] Monitor logs for proper tranche assignment
- [ ] Verify TP/SL calculations are correct
- [ ] Check instant closure triggers in logs
- [ ] Confirm no real orders placed

### Integration Testing
- [ ] Start with 1 symbol only
- [ ] Place small test order
- [ ] Verify TP/SL orders appear on exchange
- [ ] Test instant closure with price movement
- [ ] Check database for proper records

### Stress Testing
- [ ] Multiple symbols active
- [ ] Rapid liquidation events
- [ ] WebSocket disconnection/reconnection
- [ ] API rate limit handling
- [ ] Database lock scenarios

## Troubleshooting Test Failures

### Common Issues and Solutions

#### 1. Import Errors
```python
ModuleNotFoundError: No module named 'src'
```
**Solution**: Ensure you're running from project root:
```bash
cd /path/to/aster_lick_hunter
python tests/test_position_monitor.py
```

#### 2. Async Test Failures
```python
RuntimeWarning: coroutine 'test_function' was never awaited
```
**Solution**: Tests must be run with `asyncio.run()`

#### 3. Database Lock Errors
```python
sqlite3.OperationalError: database is locked
```
**Solution**: Close other connections or use test database

#### 4. Mock Setup Issues
```python
AttributeError: 'NoneType' object has no attribute 'call_count'
```
**Solution**: Ensure mocks are properly initialized before test

## Performance Benchmarks

Expected performance metrics:

| Operation | Target | Acceptable |
|-----------|--------|------------|
| Tranche determination | <1ms | <5ms |
| TP/SL calculation | <1ms | <5ms |
| Instant closure check | <10ms | <50ms |
| Database recovery | <100ms | <500ms |
| WebSocket reconnection | <5s | <15s |
| Batch order placement | <200ms | <500ms |

## Continuous Testing

### Automated Test Script

Create `scripts/test_position_monitor.sh`:

```bash
#!/bin/bash
echo "Running Position Monitor Test Suite"
echo "===================================="

# Run all test files
for test in test_position_monitor test_integration_position_monitor test_position_monitor_e2e; do
    echo "\nRunning $test..."
    python tests/$test.py
    if [ $? -ne 0 ]; then
        echo "FAILED: $test"
        exit 1
    fi
done

echo "\n✅ All tests passed!"
```

### GitHub Actions Integration

`.github/workflows/test.yml`:
```yaml
name: Position Monitor Tests

on:
  push:
    paths:
      - 'src/core/position_monitor.py'
      - 'tests/test_position_monitor*.py'
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      - run: pip install -r requirements.txt
      - run: python tests/test_position_monitor.py
      - run: python tests/test_integration_position_monitor.py
      - run: python tests/test_position_monitor_e2e.py
```

## Test Data Management

### Creating Test Fixtures

`tests/fixtures/position_monitor_data.json`:
```json
{
  "test_positions": [
    {
      "symbol": "BTCUSDT",
      "side": "LONG",
      "quantity": 0.1,
      "entry_price": 45000,
      "tranche_id": 0
    }
  ],
  "test_liquidations": [
    {
      "symbol": "BTCUSDT",
      "side": "SELL",
      "quantity": 0.5,
      "price": 44500
    }
  ]
}
```

### Cleaning Test Data

```python
# scripts/cleanup_test_data.py
import sqlite3

def cleanup_test_tranches():
    """Remove test tranches from database."""
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Remove test orders (IDs starting with TEST)
    cursor.execute("""
        DELETE FROM trades 
        WHERE order_id LIKE 'TEST%'
        OR order_id LIKE 'MOCK%'
    """)
    
    conn.commit()
    conn.close()
    print("Test data cleaned up")

if __name__ == "__main__":
    cleanup_test_data()
```

## Next Steps After Testing

### If All Tests Pass:

1. **Enable in Simulation Mode**
   - Set `"simulate_only": true`
   - Set `"use_position_monitor": true`
   - Run for 24 hours
   - Review logs for issues

2. **Limited Production Test**
   - Enable for 1 low-volume symbol
   - Use minimal position sizes
   - Monitor for 48 hours
   - Check dashboard for correct TP/SL

3. **Full Production Rollout**
   - Enable for all symbols
   - Monitor performance metrics
   - Keep legacy system ready as fallback

### If Tests Fail:

1. **Identify Failure Pattern**
   - Unit test failure = Logic issue
   - Integration failure = Component communication issue
   - E2E failure = Workflow issue

2. **Debug Steps**
   - Add print statements in failing test
   - Check mock configurations
   - Verify test data setup
   - Review error stack traces

3. **Get Help**
   - Check implementation plan: `docs/POSITION_MONITOR_IMPLEMENTATION_PLAN.md`
   - Review source code comments
   - Check git history for recent changes

## Summary

The Position Monitor test suite provides comprehensive coverage of:
- Core functionality (tranches, TP/SL, instant closure)
- System integration (trader, user_stream, main)
- Error handling and recovery
- Performance characteristics
- Backward compatibility

Run all tests before any production deployment to ensure system stability.
