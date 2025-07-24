# Monzo App Setup Guide

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Monzo API credentials

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables by creating a `.env` file in the root directory:
   ```bash
   # Database Configuration
   DATABASE_URL=postgresql://username:password@localhost/monzo_app
   
   # Flask Configuration
   FLASK_SECRET_KEY=your-secret-key-here-change-in-production
   FLASK_ENV=development
   
   # Logging Configuration
   LOG_LEVEL=INFO
   ```

4. Initialize the database:
   ```bash
   alembic upgrade head
   ```

5. Run the application:
   ```bash
   python run.py
   ```

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Yes | - |
| `FLASK_SECRET_KEY` | Secret key for Flask sessions | Yes | dev-secret-key-change-in-production |
| `FLASK_ENV` | Flask environment | No | development |
| `LOG_LEVEL` | Logging level | No | INFO |

## Monzo API Setup

1. Create a Monzo API application at https://developers.monzo.com/
2. Get your Client ID and Client Secret
3. Configure the redirect URI in your Monzo app settings
4. Use the app's web interface to authenticate with Monzo

## Security Notes

- Never commit your `.env` file to version control
- Use a strong, unique `FLASK_SECRET_KEY` in production
- Store Monzo API credentials securely
- Use HTTPS in production environments 