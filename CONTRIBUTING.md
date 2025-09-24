# 🤝 Contributing to Aster Liquidation Hunter Bot

First off, thank you for considering contributing to the Aster Liquidation Hunter Bot! It's people like you that make this project better for everyone.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Submitting Changes](#submitting-changes)
- [Review Process](#review-process)

---

## 📜 Code of Conduct

### Our Pledge

We pledge to make participation in our project a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity, level of experience, nationality, personal appearance, race, religion, or sexual identity.

### Expected Behavior

- Be respectful and inclusive
- Welcome newcomers and help them get started
- Focus on constructive criticism
- Show empathy towards other community members

### Unacceptable Behavior

- Harassment, discriminatory language, or personal attacks
- Publishing others' private information
- Trolling or insulting comments
- Any conduct which could reasonably be considered inappropriate

---

## 🎯 How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates.

**When reporting bugs, include:**

```markdown
## Bug Description
Clear and concise description of the bug

## To Reproduce
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

## Expected Behavior
What you expected to happen

## Actual Behavior
What actually happened

## Environment
- OS: [e.g., Windows 10]
- Python Version: [e.g., 3.11.0]
- Bot Version: [e.g., 1.2.0]

## Logs
```
Paste relevant log output here
```

## Screenshots
If applicable, add screenshots
```

### Suggesting Enhancements

**Enhancement suggestions should include:**

```markdown
## Feature Description
Clear description of the proposed feature

## Motivation
Why this feature would be useful

## Proposed Implementation
How you think it could be implemented

## Alternatives Considered
Other solutions you've thought about

## Additional Context
Any other context, mockups, or examples
```

### Your First Code Contribution

Unsure where to begin? Look for issues labeled:
- `good first issue` - Simple fixes perfect for beginners
- `help wanted` - More involved issues needing attention
- `documentation` - Help improve docs

### Pull Requests

1. **Small PRs are better** - Easier to review and merge
2. **One feature per PR** - Keep changes focused
3. **Update tests** - Add tests for new features
4. **Update docs** - Document new features

---

## 🛠️ Development Setup

### Prerequisites

```bash
# Required tools
- Python 3.8+
- Git
- pip
- virtualenv (recommended)
```

### Setting Up Your Development Environment

1. **Fork the repository**
   ```
   Click "Fork" on GitHub
   ```

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR-USERNAME/aster_lick_hunter.git
   cd aster_lick_hunter
   ```

3. **Add upstream remote**
   ```bash
   git remote add upstream https://github.com/CryptoGnome/aster_lick_hunter.git
   ```

4. **Create virtual environment**
   ```bash
   python -m venv venv

   # Windows:
   venv\Scripts\activate

   # Mac/Linux:
   source venv/bin/activate
   ```

5. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # Development dependencies
   ```

6. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

### Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write code
   - Add tests
   - Update documentation

3. **Run tests**
   ```bash
   python -m pytest tests/
   ```

4. **Check code style**
   ```bash
   # Format code
   black src/ tests/

   # Check linting
   pylint src/

   # Type checking
   mypy src/
   ```

5. **Commit changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create Pull Request**
   - Go to GitHub
   - Click "New Pull Request"
   - Select your branch

---

## 📁 Project Structure

```
aster_lick_hunter/
├── src/
│   ├── api/               # Dashboard API endpoints
│   ├── core/              # Core trading logic
│   ├── database/          # Database operations
│   └── utils/             # Utility functions
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── fixtures/          # Test data
├── scripts/               # Utility scripts
├── static/                # Frontend assets
├── templates/             # HTML templates
└── docs/                  # Documentation
```

### Key Files

- `main.py` - Bot entry point
- `launcher.py` - Process orchestrator
- `settings.json` - Configuration
- `requirements.txt` - Dependencies

---

## 💻 Coding Standards

### Python Style Guide

We follow PEP 8 with these additions:

```python
# File header
"""
Module description.

This module handles X functionality for the trading bot.
"""

import os
import sys
from typing import Optional, List, Dict

# Constants
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3

# Classes
class TradingEngine:
    """Main trading engine class."""

    def __init__(self, config: Dict):
        """Initialize trading engine.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self._is_running = False

    def start(self) -> bool:
        """Start the trading engine.

        Returns:
            True if started successfully
        """
        try:
            self._connect()
            self._is_running = True
            return True
        except Exception as e:
            logger.error(f"Failed to start: {e}")
            return False

# Functions
def calculate_position_size(
    balance: float,
    risk_pct: float = 0.01
) -> float:
    """Calculate position size based on risk.

    Args:
        balance: Account balance
        risk_pct: Risk percentage per trade

    Returns:
        Calculated position size
    """
    return balance * risk_pct
```

### Commit Message Format

We use conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Build/tool changes

**Examples:**
```bash
feat(trading): add stop-loss order validation
fix(websocket): handle reconnection on timeout
docs(readme): update installation instructions
test(trader): add unit tests for position sizing
```

### Documentation Standards

```python
def complex_function(
    param1: str,
    param2: Optional[int] = None,
    **kwargs
) -> Dict[str, Any]:
    """Brief description of function.

    Longer description explaining the function's purpose,
    behavior, and any important details.

    Args:
        param1: Description of param1
        param2: Description of param2 (default: None)
        **kwargs: Additional keyword arguments:
            - key1: Description
            - key2: Description

    Returns:
        Dictionary containing:
            - 'status': Operation status
            - 'data': Result data

    Raises:
        ValueError: If param1 is invalid
        ConnectionError: If unable to connect

    Example:
        >>> result = complex_function("test", param2=42)
        >>> print(result['status'])
        'success'
    """
    pass
```

---

## 🧪 Testing Guidelines

### Test Structure

```python
# tests/test_trader.py
import pytest
from unittest.mock import Mock, patch
from src.core.trader import Trader

class TestTrader:
    """Test suite for Trader class."""

    @pytest.fixture
    def trader(self):
        """Create trader instance for testing."""
        config = {"symbol": "BTCUSDT"}
        return Trader(config)

    def test_calculate_position_size(self, trader):
        """Test position size calculation."""
        # Arrange
        balance = 1000
        risk_pct = 0.02

        # Act
        size = trader.calculate_position_size(balance, risk_pct)

        # Assert
        assert size == 20
        assert isinstance(size, float)

    @patch('src.core.trader.api_client')
    def test_place_order_success(self, mock_api, trader):
        """Test successful order placement."""
        # Arrange
        mock_api.place_order.return_value = {"orderId": 123}

        # Act
        result = trader.place_order("BUY", 100)

        # Assert
        assert result["orderId"] == 123
        mock_api.place_order.assert_called_once()
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_trader.py

# Run specific test
pytest tests/test_trader.py::TestTrader::test_place_order_success

# Run with verbose output
pytest -v

# Run only marked tests
pytest -m "not slow"
```

### Test Categories

Mark tests appropriately:
```python
@pytest.mark.unit          # Fast unit tests
@pytest.mark.integration   # Integration tests
@pytest.mark.slow          # Slow tests
@pytest.mark.requires_api  # Needs API connection
```

---

## 📤 Submitting Changes

### Pull Request Process

1. **Update your branch**
   ```bash
   git fetch upstream
   git rebase upstream/master
   ```

2. **Ensure all tests pass**
   ```bash
   pytest
   black --check src/ tests/
   pylint src/
   ```

3. **Update documentation**
   - Update README.md if needed
   - Add docstrings to new functions
   - Update CHANGELOG.md

4. **Create Pull Request**

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Tests added/updated

## Related Issues
Closes #123
```

---

## 👀 Review Process

### What We Look For

1. **Code Quality**
   - Clean, readable code
   - Proper error handling
   - Efficient algorithms

2. **Testing**
   - Adequate test coverage
   - Tests pass
   - Edge cases covered

3. **Documentation**
   - Clear docstrings
   - Updated README if needed
   - Comments for complex logic

4. **Security**
   - No hardcoded secrets
   - Input validation
   - Safe API usage

### Review Timeline

- Simple changes: 1-2 days
- Medium changes: 3-5 days
- Large changes: 1 week+

---

## 🎁 Recognition

### Contributors

All contributors are recognized in:
- CONTRIBUTORS.md file
- GitHub contributors page
- Release notes

### Top Contributors

Exceptional contributors may receive:
- Collaborator access
- Priority issue assignment
- Special Discord role

---

## 💬 Getting Help

### For Contributors

- **Discord**: #dev-discussion channel
- **GitHub Discussions**: Technical questions
- **Email**: dev@asterliquidationhunter.com (coming soon)

### Resources

- [Python Style Guide](https://www.python.org/dev/peps/pep-0008/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Flow](https://guides.github.com/introduction/flow/)
- [Writing Good Commit Messages](https://chris.beams.io/posts/git-commit/)

---

## 🚀 Development Commands

### Quick Reference

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Run linter
pylint src/
flake8 src/

# Type checking
mypy src/

# Run tests
pytest
pytest --cov=src

# Generate docs
sphinx-build -b html docs docs/_build

# Clean up
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete
```

### Makefile Commands

```bash
make format    # Format code
make lint      # Run linters
make test      # Run tests
make coverage  # Generate coverage report
make docs      # Build documentation
make clean     # Clean artifacts
make all       # Run everything
```

---

<p align="center">
  <b>Thank you for contributing! 🎉</b>
</p>

<p align="center">
  <i>Together we're building something amazing!</i>
</p>