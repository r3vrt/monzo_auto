"""Monzo Automation Application Factory."""

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, current_app
import flask_profiler
import os
import logging
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
import threading
from app.database import get_db_session, close_db_session, Account, Pot, Transaction
from app.services.monzo_service import MonzoService
from app.services.transaction_utils import batch_fetch_transactions

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


def startup_full_sync():
    # Block sync if not authenticated
    access_token = db_service.get_setting("auth.access_token", "")
    refresh_token = db_service.get_setting("auth.refresh_token", "")
    if not access_token or not refresh_token:
        print("[Startup Sync] User not authenticated. Waiting for login before sync...")
        return
    session = get_db_session()
    try:
        # Check if this is the first run (no accounts in DB)
        if session.query(Account).count() == 0:
            print("[Startup Sync] No accounts found in DB. Performing full Monzo sync...")
            monzo_service = MonzoService()
            # 1. Sync accounts
            accounts = monzo_service.get_accounts()
            for acc in accounts:
                account = Account(
                    id=acc["id"],
                    name=acc.get("name"),
                    type=acc.get("type"),
                    currency=acc.get("currency"),
                    is_selected=True,  # or acc.get("is_selected", True)
                    custom_name=acc.get("name"),
                    last_sync=datetime.utcnow(),
                )
                session.merge(account)
            session.commit()
            # 2. Sync pots
            for acc in accounts:
                pots = monzo_service.get_pots(acc["id"])
                for pot in pots:
                    pot_obj = Pot(
                        id=pot["id"],
                        account_id=acc["id"],
                        name=pot.get("name"),
                        balance=pot.get("balance", 0),
                        goal_amount=pot.get("goal_amount"),
                        currency=pot.get("currency"),
                        last_sync=datetime.utcnow(),
                    )
                    session.merge(pot_obj)
            session.commit()
            # 3. Sync transactions (batched)
            for acc in accounts:
                print(f"[Startup Sync] Syncing transactions for account {acc['id']}...")
                txns = batch_fetch_transactions(monzo_service, acc["id"], "2015-01-01T00:00:00Z", datetime.utcnow().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"), batch_days=int(10))
                for txn in txns:
                    try:
                        print(f"[SYNC DEBUG] Inserting txn {txn['id']} for account {acc['id']} (created={txn.get('created')})")
                        # Handle created and settled fields as string or datetime
                        created = txn["created"]
                        if isinstance(created, str):
                            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        settled = txn.get("settled")
                        if settled:
                            if isinstance(settled, str):
                                settled = datetime.fromisoformat(settled.replace("Z", "+00:00"))
                            else:
                                settled = None
                        txn_obj = Transaction(
                            id=txn["id"],
                            account_id=acc["id"],
                            amount=txn.get("amount", 0),
                            currency=txn.get("currency"),
                            description=txn.get("description"),
                            category=txn.get("category"),
                            created=created,
                            settled=settled,
                            notes=txn.get("notes"),
                            metadata_json=str(txn.get("metadata", {})),
                            last_sync=datetime.utcnow(),
                        )
                        session.merge(txn_obj)
                        print(f"[SYNC DEBUG] Merged txn {txn['id']} successfully.")
                    except Exception as e:
                        import traceback
                        print(f"[SYNC ERROR] Failed to insert txn {txn.get('id')}: {e}")
                        traceback.print_exc()
                try:
                    session.commit()
                    print(f"[SYNC DEBUG] Committed {len(txns)} transactions for account {acc['id']}.")
                except Exception as e:
                    import traceback
                    print(f"[SYNC ERROR] Commit failed for account {acc['id']}: {e}")
                    traceback.print_exc()
            print("[Startup Sync] Full Monzo data sync complete.")
        else:
            print("[Startup Sync] Accounts found in DB. Skipping full sync.")
    except Exception as e:
        print(f"[Startup Sync] Error during sync: {e}")
    finally:
        close_db_session(session)


def incremental_sync():
    # Block sync if not authenticated
    access_token = db_service.get_setting("auth.access_token", "")
    refresh_token = db_service.get_setting("auth.refresh_token", "")
    if not access_token or not refresh_token:
        print("[Incremental Sync] User not authenticated. Waiting for login before sync...")
        return
    session = get_db_session()
    try:
        monzo_service = MonzoService()
        print("[Incremental Sync] Starting incremental Monzo sync...")
        # 1. Sync all accounts (batch if needed)
        # Monzo API usually returns all accounts at once, but structure for batching
        accounts = [acc for acc in monzo_service.get_accounts() if not acc.get('closed', False) and acc['id'] != 'acc_0000AvMJ5C8fnO1yI9tnPP']
        for acc in accounts:
            account = Account(
                id=acc["id"],
                name=acc.get("name"),
                type=acc.get("type"),
                currency=acc.get("currency"),
                is_selected=True,
                custom_name=acc.get("name"),
                last_sync=datetime.utcnow(),
            )
            session.merge(account)
        session.commit()
        # 2. Sync all pots for each account (batch if needed)
        for acc in accounts:
            # If Monzo API supports pot pagination, implement here (currently, get_pots returns all)
            pots = monzo_service.get_pots(acc["id"])
            for pot in pots:
                pot_obj = Pot(
                    id=pot["id"],
                    account_id=acc["id"],
                    name=pot.get("name"),
                    balance=pot.get("balance", 0),
                    goal_amount=pot.get("goal_amount"),
                    currency=pot.get("currency"),
                    last_sync=datetime.utcnow(),
                )
                session.merge(pot_obj)
        session.commit()
        # 3. Sync new transactions for each account (batching)
        for acc in accounts:
            print(f"[DEBUG] Looking for latest transaction for account_id={acc['id']}")
            count = session.query(Transaction).filter_by(account_id=acc["id"]).count()
            print(f"[DEBUG] Found {count} transactions for account_id={acc['id']}")
            latest_txn = session.query(Transaction).filter_by(account_id=acc["id"]).order_by(Transaction.created.desc()).first()
            print(f"[DEBUG] Latest txn: {latest_txn}")
            if latest_txn:
                since = latest_txn.created.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                since = "2015-01-01T00:00:00Z"
            before = datetime.utcnow().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[DEBUG] Fetching transactions for account_id={acc['id']} from since={since} to before={before}")
            print(f"[Incremental Sync] Syncing new transactions for account {acc['id']} since {since}...")
            txns = batch_fetch_transactions(monzo_service, acc["id"], since, before, batch_days=int(10))
            batch_size = 200
            txn_count = 0
            for txn in txns:
                try:
                    print(f"[SYNC DEBUG] Inserting txn {txn['id']} for account {acc['id']} (created={txn.get('created')})")
                    # Handle created and settled fields as string or datetime
                    created = txn["created"]
                    if isinstance(created, str):
                        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    settled = txn.get("settled")
                    if settled:
                        if isinstance(settled, str):
                            settled = datetime.fromisoformat(settled.replace("Z", "+00:00"))
                        else:
                            settled = None
                    txn_obj = Transaction(
                        id=txn["id"],
                        account_id=acc["id"],
                        amount=txn.get("amount", 0),
                        currency=txn.get("currency"),
                        description=txn.get("description"),
                        category=txn.get("category"),
                        created=created,
                        settled=settled,
                        notes=txn.get("notes"),
                        metadata_json=str(txn.get("metadata", {})),
                        last_sync=datetime.utcnow(),
                    )
                    session.merge(txn_obj)
                    print(f"[SYNC DEBUG] Merged txn {txn['id']} successfully.")
                    txn_count += 1
                    if txn_count % batch_size == 0:
                        try:
                            session.commit()
                            print(f"[SYNC DEBUG] Committed {batch_size} transactions for account {acc['id']} (batch commit).")
                        except Exception as e:
                            import traceback
                            print(f"[SYNC ERROR] Commit failed for account {acc['id']} (batch): {e}")
                            traceback.print_exc()
                            try:
                                session.rollback()
                            except Exception as rb_e:
                                print(f"[SYNC ERROR] Rollback failed after batch commit error: {rb_e}")
                            if "database is locked" in str(e):
                                import time
                                time.sleep(0.2)
                except Exception as e:
                    import traceback
                    print(f"[SYNC ERROR] Failed to insert txn {txn.get('id')}: {e}")
                    traceback.print_exc()
                    try:
                        session.rollback()
                    except Exception as rb_e:
                        print(f"[SYNC ERROR] Rollback failed after insert error: {rb_e}")
                    if "database is locked" in str(e):
                        import time
                        time.sleep(0.2)
            # Commit any remaining transactions
            if txn_count % batch_size != 0:
                try:
                    session.commit()
                    print(f"[SYNC DEBUG] Committed remaining {txn_count % batch_size} transactions for account {acc['id']} (final commit).")
                except Exception as e:
                    import traceback
                    print(f"[SYNC ERROR] Commit failed for account {acc['id']} (final): {e}")
                    traceback.print_exc()
                    try:
                        session.rollback()
                    except Exception as rb_e:
                        print(f"[SYNC ERROR] Rollback failed after final commit error: {rb_e}")
                    if "database is locked" in str(e):
                        import time
                        time.sleep(0.2)
        print("[Incremental Sync] Incremental Monzo data sync complete.")
    except Exception as e:
        print(f"[Incremental Sync] Error during sync: {e}")
    finally:
        close_db_session(session)


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
            # Scheduled DB incremental sync every 6 hours
            scheduler.add_job(
                incremental_sync,
                'interval',
                id='scheduled_db_incremental_sync',
                hours=6,
                replace_existing=True
            )

    # Start the full sync in a background thread
    def run_startup_full_sync():
        with app.app_context():
            startup_full_sync()
    threading.Thread(target=run_startup_full_sync, daemon=True).start()

    # Start incremental sync in a background thread
    def run_incremental_sync():
        with app.app_context():
            incremental_sync()
    threading.Thread(target=run_incremental_sync, daemon=True).start()

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
