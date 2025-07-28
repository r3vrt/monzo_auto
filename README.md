# Monzo Automation App

A Flask-based web application for automating Monzo bank transactions, pot management, and financial workflows.

## Features

- **Account Synchronization**: Automatic sync of Monzo accounts, transactions, and pots
- **Automation Rules**: Create custom rules for pot sweeps, auto-topups, and transaction sorting
- **Bills Pot Logic**: Intelligent management of bills pot with spending analysis
- **Real-time Monitoring**: Live balance updates and transaction tracking
- **Web Interface**: User-friendly dashboard for managing automations
- **API Integration**: RESTful API for external integrations

## Technology Stack

- **Backend**: Flask 3.0.2, Python 3.11+
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Scheduling**: APScheduler for background tasks
- **API**: Monzo API integration
- **Testing**: pytest with responses for mocking
- **Code Quality**: black, flake8, isort, mypy

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd monzo_app
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   Create a `.env` file in the root directory:
   ```bash
   DATABASE_URL=postgresql://username:password@localhost/monzo_app
   FLASK_SECRET_KEY=your-secret-key-here
   FLASK_ENV=development
   ```

4. **Initialize the database**
   ```bash
   alembic upgrade head
   ```

5. **Run the application**
   ```bash
   python run.py
   ```

6. **Access the web interface**
   Open http://localhost:5000 in your browser

## Setup Guide

For detailed setup instructions, see [SETUP.md](SETUP.md).

## API Documentation

The application provides a RESTful API for managing automations and accessing account data. See [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) for complete API documentation.

## Automation Features

### Pot Sweeps
Automatically move money between pots based on configurable rules and triggers.

### Auto Topup
Keep pots topped up to target amounts with intelligent scheduling.

### Bills Pot Logic
Analyze spending patterns and manage bills pot allocations automatically.

### Transaction Sorting
Automatically categorize and sort transactions into appropriate pots.

## Development

### Code Style
- Follow PEP 8 with Black formatting
- Use type hints throughout
- Write comprehensive docstrings
- Run tests before committing

### Testing
```bash
pytest
```

### Code Quality
```bash
black .
isort .
flake8 .
mypy .
```

## Security

- Never commit `.env` files or sensitive credentials
- Use environment variables for all configuration
- Store Monzo API tokens securely in the database
- Use HTTPS in production environments

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions, please check the documentation in the `docs/` directory or create an issue in the repository. 