# Contributing to Monzo Automation App

Thank you for your interest in contributing to the Monzo Automation App! This document provides guidelines and information for contributors.

## Development Setup

### Prerequisites
- Python 3.11+
- pyenv (recommended for environment management)
- Git

### Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/your-username/monzo_app.git
   cd monzo_app
   ```

3. **Set up the development environment**:
   ```bash
   pyenv install 3.11.6
   pyenv virtualenv 3.11.6 monzo_app_dev
   pyenv activate monzo_app_dev
   pip install -r requirements.txt
   ```

4. **Configure Monzo API credentials**:
   - Create a Monzo developer account at https://developers.monzo.com
   - Create a new OAuth client
   - Set redirect URI to `http://localhost:5000/auth/callback`
   - Update `config/auth.json` with your credentials

5. **Run the application**:
   ```bash
   python run.py
   ```

## Code Style and Standards

### Python Code Style
- **Black**: Code formatting (88 character line length)
- **isort**: Import sorting
- **flake8**: Linting and style checking
- **Type hints**: Required for all functions
- **Docstrings**: Google-style docstrings for all public functions

### Pre-commit Checks
Before submitting a pull request, ensure your code passes all checks:

```bash
# Format code
black app/

# Sort imports
isort app/

# Check code quality
flake8 app/

# Run tests (when available)
pytest
```

### Architecture Principles
- **Separation of Concerns**: Business logic in services, HTTP handling in routes
- **Dependency Injection**: Services injected into routes via Flask's current_app
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Logging**: Structured logging throughout the application
- **Configuration**: JSON-based configuration with web interface

## Adding New Features

### 1. Service Layer
Create a new service module in `app/services/` for business logic:

```python
"""New feature service for business logic."""

from typing import Any, Dict, Optional, Tuple

from flask import current_app


def execute_new_feature() -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """Execute the new feature task.
    
    Returns:
        Tuple of (success, context dict for template, error message if any)
    """
    # Implementation here
    pass


def dry_run_new_feature() -> Tuple[bool, Dict[str, Any], Optional[Dict[str, Any]]]:
    """Simulate a dry run of the new feature without making actual changes.
    
    Returns:
        Tuple of (success, context dict for template, result dict for history)
    """
    # Implementation here
    pass
```

### 2. Route Handlers
Add route handlers in the appropriate blueprint:

```python
@bp.route("/new-feature/execute", methods=["GET", "POST"])
def execute_new_feature():
    """Execute the new feature task.
    
    Returns:
        HTML page with execution results
    """
    try:
        success, context, error = execute_new_feature()
        return render_template(
            "pages/tasks/execute.html",
            success=success,
            task_name="New Feature",
            message=context.get("message", ""),
            error=error,
            home_url="/",
        )
    except Exception as e:
        current_app.logger.error(f"New feature failed: {e}")
        return render_template(
            "pages/tasks/execute.html",
            success=False,
            task_name="New Feature",
            error=str(e),
            home_url="/",
        ), 500
```

### 3. Templates
Create HTML templates in `app/templates/pages/`:

```html
{% extends "base.html" %}

{% block content %}
<div class="container">
    <h1>New Feature</h1>
    <!-- Template content -->
</div>
{% endblock %}
```

### 4. Configuration
Update configuration schema if needed in `app/config.py` and the web interface.

### 5. Tests
Add tests for new functionality (when test framework is set up).

## Pull Request Process

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines

3. **Test your changes**:
   - Run the application locally
   - Test the new functionality
   - Ensure existing functionality still works

4. **Update documentation**:
   - Update README.md if needed
   - Add docstrings for new functions
   - Update API documentation

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add new feature: brief description"
   ```

6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a pull request** on GitHub with:
   - Clear description of the changes
   - Any relevant issue numbers
   - Screenshots if UI changes are involved

## Issue Reporting

When reporting issues, please include:

- **Description**: Clear description of the problem
- **Steps to reproduce**: Detailed steps to reproduce the issue
- **Expected behavior**: What you expected to happen
- **Actual behavior**: What actually happened
- **Environment**: OS, Python version, browser (if applicable)
- **Logs**: Any relevant error messages or logs

## Code of Conduct

- Be respectful and inclusive
- Focus on the code and technical discussions
- Help others learn and improve
- Provide constructive feedback

## Questions?

If you have questions about contributing, please:

1. Check the existing documentation
2. Search existing issues and pull requests
3. Create a new issue with the "question" label

Thank you for contributing to the Monzo Automation App! 