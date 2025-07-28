from app import create_app
from app.db import Base, engine, get_db_session
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import User, Account
from app.monzo.sync import sync_account_data
from app.monzo.client import MonzoClient
from app.services.auth_service import get_authenticated_monzo_client
from app.automation.integration import AutomationIntegration
from datetime import datetime
import os
from app.logging_config import get_logging_manager

# Configure logging using the logging manager
logging_manager = get_logging_manager()

# Auto-create tables if they do not exist
Base.metadata.create_all(engine)

app = create_app()

# Individual automation rule schedulers
def create_rule_scheduler(rule_id: str, user_id: str, account_id: str, trigger_type: str, trigger_interval: int = None):
    """Create a scheduler for a specific automation rule."""
    def execute_single_rule():
        logging.info(f"[RULE-SCHEDULER] Executing specific rule {rule_id} for user {user_id}")
        with next(get_db_session()) as db:
            try:
                # Create authenticated Monzo client for this user
                monzo = get_authenticated_monzo_client(db, user_id)
                if not monzo:
                    logging.warning(f"[RULE-SCHEDULER] No valid credentials for user {user_id}, skipping rule {rule_id}")
                    return
                
                # Execute only this specific rule, not all automation
                from app.automation.rules import RulesManager
                rules_manager = RulesManager(db)
                rule = rules_manager.get_rule_by_id(rule_id)
                
                if not rule or not rule.enabled:
                    logging.info(f"[RULE-SCHEDULER] Rule {rule_id} not found or disabled, skipping")
                    return
                
                # Create automation integration
                automation = AutomationIntegration(db, monzo)
                
                # Execute only this specific rule
                results = automation.execute_single_rule(rule, user_id, account_id)
                logging.info(f"[RULE-SCHEDULER] Rule {rule_id} results: {results}")
                
            except Exception as e:
                logging.error(f"[RULE-SCHEDULER] Error executing rule {rule_id}: {e}")
    
    return execute_single_rule

def add_rule_scheduler(rule_id: str, user_id: str, account_id: str, rule_config: dict):
    """Add a scheduler for a new automation rule."""
    try:
        trigger_type = rule_config.get('trigger_type')
        
        # Only create individual schedulers for rules that need specific timing
        # Skip rules that are triggered by other conditions (payday_date, automation_trigger, etc.)
        if trigger_type in ['payday_date', 'time_of_day', 'transaction_based', 'date_range', 'automation_trigger', 'manual_only']:
            logging.info(f"[SCHEDULER] Skipping individual scheduler for new rule {rule_id} - trigger type '{trigger_type}' handled by global automation")
            return
        
        trigger_interval = rule_config.get('trigger_interval', 5)
        
        # Determine schedule based on trigger type
        schedule_interval = None
        if trigger_type == 'minute':
            schedule_interval = trigger_interval
        elif trigger_type == 'hourly':
            schedule_interval = 60
        elif trigger_type == 'daily':
            schedule_interval = 1440
        elif trigger_type == 'weekly':
            schedule_interval = 10080
        elif trigger_type == 'monthly':
            schedule_interval = 43200
        elif trigger_type == 'balance_threshold':
            schedule_interval = 5
        else:
            # Skip unknown trigger types
            logging.warning(f"[SCHEDULER] Unknown trigger type '{trigger_type}' for new rule {rule_id}, skipping individual scheduler")
            return
        
        # Create scheduler for this rule
        rule_job = create_rule_scheduler(rule_id, user_id, account_id, trigger_type, schedule_interval)
        
        # Add job to scheduler
        job_name = f"rule_{rule_id}"
        scheduler.add_job(
            rule_job, 
            'interval', 
            minutes=schedule_interval, 
            next_run_time=datetime.now(),
            id=job_name,
            replace_existing=True
        )
        
        logging.info(f"[SCHEDULER] Added individual scheduler for new rule {rule_id}: every {schedule_interval} minutes")
        
    except Exception as e:
        logging.error(f"[SCHEDULER] Error adding rule scheduler for {rule_id}: {e}")

def update_rule_scheduler(rule_id: str, user_id: str, account_id: str, rule_config: dict, enabled: bool):
    """Update a scheduler for an existing automation rule."""
    try:
        job_name = f"rule_{rule_id}"
        
        if not enabled:
            # Remove the job if rule is disabled
            scheduler.remove_job(job_name)
            logging.info(f"[SCHEDULER] Removed job for disabled rule {rule_id}")
            return
        
        # Re-add the job with updated configuration
        add_rule_scheduler(rule_id, user_id, account_id, rule_config)
        
    except Exception as e:
        logging.error(f"[SCHEDULER] Error updating rule scheduler for {rule_id}: {e}")

def remove_rule_scheduler(rule_id: str):
    """Remove a scheduler for a deleted automation rule."""
    try:
        job_name = f"rule_{rule_id}"
        scheduler.remove_job(job_name)
        logging.info(f"[SCHEDULER] Removed job for deleted rule {rule_id}")
        
    except Exception as e:
        logging.error(f"[SCHEDULER] Error removing rule scheduler for {rule_id}: {e}")

# Make these functions available for import
__all__ = ['add_rule_scheduler', 'update_rule_scheduler', 'remove_rule_scheduler']

def setup_rule_schedulers():
    """Set up individual schedulers for automation rules that need specific timing."""
    logging.info("[SCHEDULER] Setting up individual rule schedulers...")
    
    with next(get_db_session()) as db:
        try:
            from app.automation.rules import RulesManager
            rules_manager = RulesManager(db)
            
            # Get all users and their rules
            users = db.query(User).all()
            for user in users:
                rules = rules_manager.get_rules_by_user(str(user.monzo_user_id))
                
                for rule in rules:
                    if not rule.enabled:
                        continue
                    
                    trigger_type = rule.config.get('trigger_type')
                    
                    # Only create individual schedulers for rules that need specific timing
                    # Skip rules that are triggered by other conditions (payday_date, automation_trigger, etc.)
                    if trigger_type in ['payday_date', 'time_of_day', 'transaction_based', 'date_range', 'automation_trigger', 'manual_only']:
                        logging.info(f"[SCHEDULER] Skipping individual scheduler for rule {rule.name} ({rule.rule_id}) - trigger type '{trigger_type}' handled by global automation")
                        continue
                    
                    # Determine schedule based on trigger type
                    schedule_interval = None
                    if trigger_type == 'minute':
                        schedule_interval = rule.config.get('trigger_interval', 5)  # Default to 5 minutes
                    elif trigger_type == 'hourly':
                        schedule_interval = 60  # 60 minutes
                    elif trigger_type == 'daily':
                        schedule_interval = 1440  # 24 hours
                    elif trigger_type == 'weekly':
                        schedule_interval = 10080  # 7 days
                    elif trigger_type == 'monthly':
                        schedule_interval = 43200  # 30 days
                    elif trigger_type == 'balance_threshold':
                        # For balance threshold, check every 5 minutes
                        schedule_interval = 5
                    else:
                        # Skip unknown trigger types
                        logging.warning(f"[SCHEDULER] Unknown trigger type '{trigger_type}' for rule {rule.name} ({rule.rule_id}), skipping individual scheduler")
                        continue
                    
                    # Get user's accounts
                    accounts = db.query(Account).filter_by(user_id=str(user.monzo_user_id), is_active=True).all()
                    if not accounts:
                        continue
                    
                    # Create scheduler for this rule
                    rule_job = create_rule_scheduler(
                        rule.rule_id, 
                        str(user.monzo_user_id), 
                        str(accounts[0].id),  # Use first account for now
                        trigger_type,
                        schedule_interval
                    )
                    
                    # Add job to scheduler
                    job_name = f"rule_{rule.rule_id}"
                    scheduler.add_job(
                        rule_job, 
                        'interval', 
                        minutes=schedule_interval, 
                        next_run_time=datetime.now(),
                        id=job_name,
                        replace_existing=True
                    )
                    
                    logging.info(f"[SCHEDULER] Added individual scheduler for rule {rule.name} ({rule.rule_id}): every {schedule_interval} minutes")
                    
        except Exception as e:
            logging.error(f"[SCHEDULER] Error setting up rule schedulers: {e}")

# Scheduled sync job
def scheduled_sync():
    logging.info("[SCHEDULER] Starting scheduled sync job...")
    with next(get_db_session()) as db:
        try:
            users = db.query(User).all()
            for user in users:
                # Create authenticated Monzo client for this user
                monzo = get_authenticated_monzo_client(db, user.monzo_user_id)
                if not monzo:
                    logging.warning(f"[SCHEDULER] No valid credentials for user {user.monzo_user_id}, skipping")
                    continue
                
                accounts = db.query(Account).filter_by(user_id=str(user.monzo_user_id), is_active=True).all()
                for acc in accounts:
                    try:
                        logging.info(f"[SCHEDULER] Syncing account {acc.id} for user {user.monzo_user_id}")
                        sync_account_data(db, user.id, str(acc.id), monzo)
                    except Exception as e:
                        logging.error(f"[SCHEDULER] Sync failed for account {acc.id}: {e}")
                        # Don't rollback the entire session, just log the error
            logging.info("[SCHEDULER] Scheduled sync job complete.")
        except Exception as e:
            logging.error(f"[SCHEDULER] Critical error in scheduled sync: {e}")
            db.rollback()
            # Don't raise the exception - just log it and continue
            # This prevents the app from exiting on sync failures

# Scheduled automation job (runs more frequently for time-sensitive triggers)
def scheduled_automation():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"[AUTOMATION] Starting scheduled automation job at {current_time}...")
    with next(get_db_session()) as db:
        try:
            users = db.query(User).all()
            logging.info(f"[AUTOMATION] Found {len(users)} users to check")
            
            for user in users:
                # Create authenticated Monzo client for this user
                monzo = get_authenticated_monzo_client(db, user.monzo_user_id)
                if not monzo:
                    logging.warning(f"[AUTOMATION] No valid credentials for user {user.monzo_user_id}, skipping")
                    continue
                
                # Create automation integration
                automation = AutomationIntegration(db, monzo)
                
                # Get user's accounts
                accounts = db.query(Account).filter_by(user_id=str(user.monzo_user_id), is_active=True).all()
                logging.info(f"[AUTOMATION] Found {len(accounts)} accounts for user {user.monzo_user_id}")
                
                for acc in accounts:
                    try:
                        logging.info(f"[AUTOMATION] Checking automation for account {acc.id} for user {user.monzo_user_id}")
                        # Execute automation without full sync (just check triggers)
                        results = automation.execute_post_sync_automation(str(user.monzo_user_id), str(acc.id))
                        logging.info(f"[AUTOMATION] Automation results for {acc.id}: {results}")
                    except Exception as e:
                        logging.error(f"[AUTOMATION] Automation failed for account {acc.id}: {e}")
                        # Don't rollback the entire session, just log the error
            logging.info(f"[AUTOMATION] Scheduled automation job complete at {current_time}")
        except Exception as e:
            logging.error(f"[AUTOMATION] Critical error in scheduled automation: {e}")
            db.rollback()
            # Don't raise the exception - just log it and continue
            # This prevents the app from exiting on automation failures

# Start the automation queue manager
from app.automation.queue_manager import get_queue_manager
queue_manager = get_queue_manager()
queue_manager.start()

scheduler = BackgroundScheduler()
# Sync every 10 minutes for more frequent transaction updates
scheduler.add_job(scheduled_sync, 'interval', minutes=10, next_run_time=datetime.now())
# Automation every 5 minutes for time-sensitive triggers
scheduler.add_job(scheduled_automation, 'interval', minutes=5, next_run_time=datetime.now())
scheduler.start()

# Set up individual rule schedulers for rules with specific timing requirements
setup_rule_schedulers()

# Log scheduler status
logging.info("[SCHEDULER] Scheduler started with jobs:")
for job in scheduler.get_jobs():
    logging.info(f"[SCHEDULER] - {job.name}: {job.trigger}")

if __name__ == "__main__":
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
    
    # Use environment variable for debug mode, default to False for production safety
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
    
    app.run(debug=debug_mode, host="0.0.0.0", port=5000) 