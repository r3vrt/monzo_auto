# Monzo Automation App

A Flask-based automation and monitoring dashboard for Monzo accounts. Features include auto topup, sweep pots, autosorter, task history, and live monitoring/metrics.

## Features
- Auto topup from pots when balance is low
- Sweep pots and autosort funds
- Task execution history and status
- System health and Prometheus metrics endpoints
- Modern, responsive UI

## Setup
1. **Clone the repo:**
   ```bash
   git clone <your-repo-url>
   cd monzo_app
   ```
2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Copy and edit config files:**
   ```bash
   cp config/auth.example.json config/auth.json
   cp config/general.example.json config/general.json
   # Edit these files with your Monzo API credentials and preferences
   ```

## Running
- **Start the Flask app:**
  ```bash
  python run.py
  ```
- **Access the dashboard:**
  Open [http://localhost:5000](http://localhost:5000) in your browser.

## Monitoring & Metrics
- **System Status:** `/monitoring/status`
- **Prometheus Metrics:** `/monitoring/metrics`
- **Health Check:** `/monitoring/health`

## Code Quality
- Format: `black .`
- Lint: `flake8 .`
- Imports: `isort .`

## License
MIT 
