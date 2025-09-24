# Contributing to Aster Liquidation Hunter Bot

Thank you for your interest in contributing! We welcome all contributions, big or small.

## Quick Start

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Run tests (`python -m pytest tests/`)
5. Submit a pull request

That's it! Below are more details if you need them.

## Code of Conduct

- Be respectful and helpful
- Welcome newcomers
- Focus on constructive feedback
- No harassment or discrimination

## How Can I Contribute?

### Reporting Bugs

Check if the issue already exists, then create a new issue with:
- What happened
- What you expected
- Steps to reproduce
- Your environment (OS, Python version)
- Error logs if available

### Suggesting Features

Open an issue describing:
- What you want to add
- Why it's useful
- How it might work

### First Time Contributing?

Look for issues labeled `good first issue` or `help wanted`.

### Pull Request Guidelines

- Keep PRs small and focused
- Add tests for new features
- Update docs if needed

## Development Setup

### Prerequisites
- Python 3.8+
- Git

### Quick Setup

```bash
# Fork and clone the repo
git clone https://github.com/YOUR-USERNAME/aster_lick_hunter.git
cd aster_lick_hunter

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run tests to verify setup
python tests/test_rate_limiter.py
```

### Making Changes

```bash
# Create a feature branch
git checkout -b feature/your-feature

# Make your changes, then test
python -m pytest tests/

# Commit and push
git add .
git commit -m "feat: your feature description"
git push origin feature/your-feature
```

Then create a Pull Request on GitHub.

## Project Structure

```
aster_lick_hunter/
├── src/           # Source code
├── tests/         # Test files
├── scripts/       # Utility scripts
├── static/        # Frontend assets
├── templates/     # HTML templates
├── main.py        # Bot entry point
├── launcher.py    # Runs bot + dashboard
└── settings.json  # Configuration
```

## Coding Standards

### Python Style
- Follow PEP 8
- Use meaningful variable names
- Add docstrings to functions and classes
- Keep functions small and focused

### Commit Messages

Use this format:
```
feat: add new feature
fix: fix bug in X
docs: update README
test: add tests for Y
```

## Testing

### Running Tests

```bash
# Run individual test files
python tests/test_rate_limiter.py
python tests/test_trade_logic.py

# Or use pytest for all tests
python -m pytest tests/
```

### Writing Tests

- Test files start with `test_`
- Test functions start with `test_`
- Mock external API calls
- Keep tests simple and focused

## Submitting Changes

### Before Submitting

1. Ensure tests pass
2. Update docs if needed
3. Check your code works

### Pull Request Template

```markdown
## What does this PR do?
[Brief description]

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation

## Testing
- [ ] Tests pass
- [ ] Manually tested

## Related Issues
Closes #[issue number]
```

## Review Process

We'll review your PR and provide feedback. We look for:
- Working code
- Tests (if applicable)
- Clear commit messages

Most PRs are reviewed within a few days.

## Getting Help

- Open an issue on GitHub
- Check existing issues and discussions
- Join our Discord (link in README)

## Useful Commands

```bash
# Run tests
python -m pytest tests/

# Format code (optional)
pip install black
black src/ tests/

# Check for issues (optional)
pip install pylint
pylint src/
```

---

**Thank you for contributing!** Every contribution helps make this project better.