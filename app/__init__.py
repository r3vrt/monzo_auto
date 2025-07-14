"""Monzo Automation Application Factory."""

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, current_app
import flask_profiler
import os
import logging
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime

# Import blueprints
from app.auth import bp as auth_bp
from app.configuration import bp as config_bp
from app.monitoring import bp as monitoring_bp
from app.pages.accounts import bp as accounts_bp
from app.pages.analytics import bp as analytics_bp
from app.pages.dashboard import bp as dashboard_bp
from app.pages.transactions import bp as transactions_bp
from app.tasks import bp as tasks_bp
from app.services.auto_topup_service import scheduled_auto_topup, run_auto_topup_on_startup
from app.services.sweep_pots_service import execute_sweep_pots
from app.services.autosorter_service import execute_autosorter
from app.services.database_service import db_service
from app.database import init_database
from app.configuration.routes import schedule_struct_to_trigger

scheduler = BackgroundScheduler()


def scheduled_sweep_pots():
    """Scheduled job wrapper for sweep pots with app context."""
    from app import app
    with app.app_context():
        return execute_sweep_pots()


def scheduled_autosorter():
    """Scheduled job wrapper for autosorter with app context."""
    from app import app
    with app.app_context():
        return execute_autosorter()


def scheduled_combined_automation():
    """Scheduled job for combined sweep and autosorter, using real values only."""
    import logging
    from app import app  # Import inside the function to avoid circular import
    with app.app_context():
        sweep_success, sweep_context, sweep_result = execute_sweep_pots()
        logging.info(f"[Scheduled][Combined] Sweep: {sweep_context.get('message') or sweep_context.get('error')}")
        autosorter_success, autosorter_context, autosorter_result = execute_autosorter()
        logging.info(f"[Scheduled][Combined] Autosorter: {autosorter_context.get('message') or autosorter_context.get('error')}")
        # Optionally, save combined task history here


def setup_logging(log_level="INFO", log_file="logs/app.log", json_logs=False):
    """Configure logging for the app."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove default handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler()
    if json_logs:
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                log_record = {
                    "level": record.levelname,
                    "time": self.formatTime(record, self.datefmt),
                    "name": record.name,
                    "message": record.getMessage(),
                }
                if hasattr(record, 'task_name'):
                    log_record["task_name"] = record.task_name
                if record.exc_info:
                    log_record["exception"] = self.formatException(record.exc_info)
                return json.dumps(log_record)
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s'))
    root_logger.addHandler(console_handler)

    # Rotating file handler
    file_handler = RotatingFileHandler(log_file, maxBytes=2*1024*1024, backupCount=5)
    if json_logs:
        file_handler.setFormatter(JsonFormatter())
    else:
        file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s in %(name)s: %(message)s'))
    root_logger.addHandler(file_handler)


def datetime_utc(ts):
    if not ts:
        return "-"
    try:
        return datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    # Set secret key for session support
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-monzo-automation-secret-key")

    # Load log level and json_logs from config or env
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    json_logs = os.environ.get("JSON_LOGS", "0") == "1"
    setup_logging(log_level=log_level, json_logs=json_logs)

    # Initialize database
    init_database(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")
    app.register_blueprint(monitoring_bp, url_prefix="/monitoring")
    app.register_blueprint(config_bp, url_prefix="/configuration")
    app.register_blueprint(dashboard_bp, url_prefix="/")  # Handles root URL
    app.register_blueprint(accounts_bp, url_prefix="/accounts")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(transactions_bp, url_prefix="/transactions")

    # Only schedule jobs in the main process to avoid duplicates in debug mode
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true' and not scheduler.running:
        with app.app_context():
            scheduler.start()
            for job in scheduler.get_jobs():
                scheduler.remove_job(job.id)
            
            # Check if auto topup should run on startup
            run_auto_topup_on_startup()
            # Register jobs for all automation tasks if enabled and scheduled
            automation_config = db_service.get_setting("general.automation_tasks", {})
            def register_job(task_id, func, config):
                schedule = config.get("schedule", {"type": "none"})
                enabled = config.get("enabled", True)  # Default to True if not present
                if enabled and schedule.get("type") != "none":
                    trigger_type, trigger_args = schedule_struct_to_trigger(schedule)
                    if trigger_type and trigger_args:
                        scheduler.add_job(
                            func,
                            trigger_type,
                            id=f"{task_id}_job",
                            replace_existing=True,
                            **trigger_args
                        )
            # Auto Topup
            auto_topup_config = automation_config.get("auto_topup", {})
            register_job("auto_topup", scheduled_auto_topup, auto_topup_config)
            # Sweep Pots
            sweep_config = automation_config.get("sweep_pots", {})
            register_job("sweep_pots", scheduled_sweep_pots, sweep_config)
            # Autosorter
            autosorter_config = automation_config.get("autosorter", {})
            register_job("autosorter", scheduled_autosorter, autosorter_config)
            # Combined
            combined_config = automation_config.get("combined", {})
            register_job("combined_automation", scheduled_combined_automation, combined_config)

    app.config["flask_profiler"] = {
        "enabled": True,
        "storage": {
            "engine": "sqlite",
            "FILE": "./profiler.sqlite"
        },
        "basicAuth": {
            "enabled": False
        },
        "ignore": [
            "^/static/.*"
        ]
    }
    flask_profiler.init_app(app)

    app.jinja_env.filters['datetime_utc'] = datetime_utc

    return app


app = create_app()
