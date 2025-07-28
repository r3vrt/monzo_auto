"""
UI Blueprint Package

This package contains all UI-related blueprints for the Monzo application.
Each blueprint handles a specific area of functionality.
"""

from flask import Blueprint

# Create the main UI blueprint
ui_bp = Blueprint("ui", __name__)

# Import all route modules to register them
# These imports must happen after blueprint creation
from . import auth
from . import automation  
from . import dashboard
from . import logs
from . import pots
from . import sync

# Register monitoring routes to avoid circular import
from .monitoring import register_monitoring_routes
register_monitoring_routes(ui_bp)

# Manual route registration (temporary fix for deferred function issue)
def _register_all_routes():
    """Manually register all UI routes to fix deferred function issue."""
    # Dashboard routes
    from .dashboard import landing_page, debug_route, accounts_select_ui
    ui_bp.add_url_rule('/', 'landing_page', landing_page, methods=['GET'])
    ui_bp.add_url_rule('/debug', 'debug_route', debug_route, methods=['GET'])
    ui_bp.add_url_rule('/accounts/select-ui', 'accounts_select_ui', accounts_select_ui, methods=['GET', 'POST'])
    
    # Automation routes
    from .automation import automation_management
    ui_bp.add_url_rule('/automation/manage', 'automation_management', automation_management, methods=['GET'])
    
    # Pot management routes
    from .pots import pot_management
    ui_bp.add_url_rule('/pots/manage', 'pot_management', pot_management, methods=['GET'])
    
    # Logging routes
    from .logs import view_logs, logging_config
    ui_bp.add_url_rule('/logs', 'view_logs', view_logs, methods=['GET'])
    ui_bp.add_url_rule('/logs/config', 'logging_config', logging_config, methods=['GET'])
    
    # Auth routes
    from .auth import monzo_auth, auth_start, auth_callback, auth_client_info
    ui_bp.add_url_rule('/monzo_auth', 'monzo_auth', monzo_auth, methods=['GET'])
    ui_bp.add_url_rule('/auth/start', 'auth_start', auth_start, methods=['GET'])
    ui_bp.add_url_rule('/auth/callback', 'auth_callback', auth_callback, methods=['GET'])
    ui_bp.add_url_rule('/auth/client_info', 'auth_client_info', auth_client_info, methods=['POST'])

_register_all_routes()
