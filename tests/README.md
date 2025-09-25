# Aster Liquidation Hunter - Test Suite

Comprehensive testing framework for the Aster Liquidation Hunter trading bot.

## 📁 Test Structure

```
tests/
├── unit/                  # Fast, isolated unit tests
│   ├── core/             # Core trading logic tests
│   ├── utils/            # Utility function tests
│   └── database/         # Database operation tests
├── integration/          # Component integration tests
├── api/                  # API endpoint tests
├── e2e/                  # End-to-end workflow tests
├── performance/          # Performance and load tests
└── fixtures/             # Test data and mock responses
```

## 🚀 Quick Start

### Install Test Dependencies

```bash
pip install -r tests/requirements-test.txt
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=html --cov-report=term

# Run specific test categories
pytest tests/unit/              # Unit tests only
pytest tests/integration/        # Integration tests
pytest tests/api/               # API tests
pytest tests/e2e/               # End-to-end tests
```

### Run Individual Test Files

```bash
# Run specific test file
pytest tests/unit/core/test_trader.py

# Run with verbose output
pytest -v tests/unit/core/test_trader.py

# Run specific test class or method
pytest tests/unit/core/test_trader.py::TestAsterTrader
pytest tests/unit/core/test_trader.py::TestAsterTrader::test_volume_threshold_check_usdt
```

## 🏷️ Test Categories

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.performance` - Performance tests
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.critical` - Critical functionality tests

### Run Tests by Category

```bash
# Run only unit tests
pytest -m unit

# Run critical tests
pytest -m critical

# Run all except slow tests
pytest -m "not slow"

# Run unit and integration tests
pytest -m "unit or integration"
```

## 📊 Test Coverage

### Generate Coverage Report

```bash
# Terminal report
pytest --cov=src --cov-report=term-missing

# HTML report (opens in browser)
pytest --cov=src --cov-report=html
open htmlcov/index.html

# XML report (for CI/CD)
pytest --cov=src --cov-report=xml
```

### Coverage Goals

- **Overall**: 80% coverage
- **Critical paths**: 95% coverage
  - Trading logic (`src/core/trader.py`)
  - Order management (`src/core/order_cleanup.py`)
  - Position monitoring (`src/core/position_monitor.py`)
- **Utilities**: 70% coverage
- **API endpoints**: 85% coverage

## 🧪 Test Files Overview

### Unit Tests

#### `tests/unit/core/`
- **test_trader.py** - Trading logic, order placement, TP/SL management
- **test_position_monitor.py** - Position monitoring, tranche management
- **test_streamer.py** - WebSocket stream processing
- **test_order_cleanup.py** - Order cleanup service
- **test_order_batcher.py** - Batch order submission
- **test_user_stream.py** - User data stream handling

#### `tests/unit/utils/`
- **test_rate_limiter.py** - Rate limiting with token bucket algorithm
- **test_auth.py** - API authentication and signing
- **test_config.py** - Configuration management
- **test_position_manager.py** - Position tracking utilities
- **test_order_manager.py** - Order state management
- **test_endpoint_weights.py** - API endpoint weight calculations

#### `tests/unit/database/`
- **test_db_operations.py** - Database CRUD operations
- **test_migrations.py** - Database migration logic
- **test_tranche_system.py** - Tranche management system

### Integration Tests

#### `tests/integration/`
- **test_trading_flow.py** - Complete trading workflow
- **test_position_lifecycle.py** - Position creation to closure
- **test_websocket_integration.py** - WebSocket connectivity
- **test_database_integration.py** - Database transactions

### API Tests

#### `tests/api/`
- **test_position_routes.py** - Position management endpoints
- **test_trade_routes.py** - Trade history endpoints
- **test_config_routes.py** - Configuration endpoints
- **test_stats_routes.py** - Statistics endpoints
- **test_streaming_routes.py** - SSE streaming endpoints

### End-to-End Tests

#### `tests/e2e/`
- **test_bot_startup.py** - Full bot initialization
- **test_trade_execution.py** - Complete trade cycle
- **test_dashboard_flow.py** - Dashboard user workflows
- **test_emergency_scenarios.py** - Failure recovery tests

## 🔧 Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

- `test_db` - Temporary test database
- `test_config` - Test configuration
- `mock_exchange_info` - Mock exchange information
- `mock_orderbook` - Mock orderbook data
- `sample_liquidation` - Sample liquidation event
- `mock_trader` - Mock trader instance
- `mock_api_client` - Mock API client
- `mock_websocket` - Mock WebSocket connection

### Using Fixtures

```python
def test_example(test_db, test_config, mock_trader):
    """Example test using fixtures."""
    # test_db provides a temporary database
    # test_config provides test configuration
    # mock_trader provides a configured trader instance
    assert mock_trader.simulate_only == True
```

## 🎯 Writing New Tests

### Test Naming Convention

```python
# Test files
test_<module_name>.py

# Test classes
class Test<ClassName>:

# Test methods
def test_<method_name>_<scenario>_<expected_outcome>():
```

### Example Test Structure

```python
import pytest
from unittest.mock import Mock, patch

class TestNewFeature:
    """Test suite for new feature."""

    @pytest.fixture
    def setup_feature(self, test_db):
        """Set up test environment."""
        # Setup code
        yield fixture_data
        # Teardown code

    @pytest.mark.unit
    def test_feature_success_case(self, setup_feature):
        """Test successful feature execution."""
        # Arrange
        data = setup_feature

        # Act
        result = feature_function(data)

        # Assert
        assert result.success == True

    @pytest.mark.unit
    def test_feature_error_handling(self, setup_feature):
        """Test feature error handling."""
        with pytest.raises(ExpectedException):
            feature_function(invalid_data)
```

## 🏃 Performance Testing

### Run Performance Tests

```bash
# Run all performance tests
pytest -m performance

# Run with benchmarking
pytest tests/performance/ --benchmark-only

# Profile slow tests
pytest --durations=10
```

### Load Testing

```python
# Example load test
@pytest.mark.performance
def test_high_volume_processing(benchmark):
    """Test processing high volume of liquidations."""
    def process_batch():
        for i in range(1000):
            process_liquidation(sample_data[i])

    benchmark(process_batch)
```

## 🐛 Debugging Tests

### Run Tests with Debugging

```bash
# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest -l

# Verbose output with full diffs
pytest -vv

# Stop on first failure
pytest -x

# Show print statements
pytest -s
```

### VS Code Integration

Add to `.vscode/settings.json`:

```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": [
    "tests"
  ],
  "python.testing.unittestEnabled": false,
  "python.testing.autoTestDiscoverOnSaveEnabled": true
}
```

## 🔄 Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - run: pip install -r requirements.txt
      - run: pip install -r tests/requirements-test.txt
      - run: pytest --cov=src --cov-report=xml
      - uses: codecov/codecov-action@v2
```

## 🔍 Test Maintenance

### Regular Tasks

1. **Weekly**: Run full test suite
2. **Before commits**: Run relevant unit tests
3. **Before releases**: Run all tests including E2E
4. **After major changes**: Update affected tests

### Keeping Tests Updated

- Update tests when modifying code
- Remove obsolete tests
- Add tests for new features
- Maintain test documentation

## 📈 Test Metrics

Track these metrics:
- Code coverage percentage
- Test execution time
- Test failure rate
- Number of tests per module
- Test maintenance frequency

## 🆘 Troubleshooting

### Common Issues

**ImportError**: Ensure src is in Python path
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Database Lock**: Use separate test database
```python
# In conftest.py
@pytest.fixture
def isolated_db():
    with tempfile.NamedTemporaryFile() as f:
        yield f.name
```

**Slow Tests**: Use markers and run subsets
```bash
pytest -m "not slow"
```

**Flaky Tests**: Add retries for network-dependent tests
```python
@pytest.mark.flaky(reruns=3, reruns_delay=2)
def test_external_api():
    pass
```

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://realpython.com/pytest-python-testing/)
- [Test Coverage Guide](https://coverage.readthedocs.io/)
- [Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)