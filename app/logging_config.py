"""
Logging configuration for the Monzo app.

This module provides configurable logging levels that can be set via:
- Environment variables
- Runtime configuration via API
- Default fallback values
"""

import logging
import os
from typing import Dict, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class LoggingConfig:
    """Configuration for logging levels."""
    root_level: str = "INFO"
    app_level: str = "INFO"
    monzo_client_level: str = "INFO"
    monzo_sync_level: str = "INFO"
    automation_level: str = "INFO"
    scheduler_level: str = "INFO"
    urllib3_level: str = "WARNING"
    requests_level: str = "WARNING"
    werkzeug_level: str = "INFO"
    sqlalchemy_level: str = "WARNING"


class LoggingManager:
    """Manages logging configuration and provides runtime level changes."""
    
    def __init__(self):
        self.config = self._load_config()
        self._configure_logging()
    
    def _load_config(self) -> LoggingConfig:
        """Load logging configuration from environment variables with production-safe defaults."""
        return LoggingConfig(
            root_level=os.getenv("LOG_ROOT_LEVEL", "INFO"),
            app_level=os.getenv("LOG_APP_LEVEL", "INFO"),
            monzo_client_level=os.getenv("LOG_MONZO_CLIENT_LEVEL", "INFO"),
            monzo_sync_level=os.getenv("LOG_MONZO_SYNC_LEVEL", "INFO"),
            automation_level=os.getenv("LOG_AUTOMATION_LEVEL", "INFO"),
            scheduler_level=os.getenv("LOG_SCHEDULER_LEVEL", "INFO"),
            urllib3_level=os.getenv("LOG_URLLIB3_LEVEL", "WARNING"),
            requests_level=os.getenv("LOG_REQUESTS_LEVEL", "WARNING"),
            werkzeug_level=os.getenv("LOG_WERKZEUG_LEVEL", "INFO"),
            sqlalchemy_level=os.getenv("LOG_SQLALCHEMY_LEVEL", "WARNING"),
        )
    
    def _configure_logging(self):
        """Configure logging based on current configuration."""
        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, self.config.root_level),
            format='%(asctime)s %(name)s %(levelname)s %(message)s',
            handlers=[
                logging.FileHandler('monzo_app.log'),
                logging.StreamHandler()
            ]
        )
        
        # Configure specific loggers
        self._set_logger_level('app', self.config.app_level)
        self._set_logger_level('app.monzo.client', self.config.monzo_client_level)
        self._set_logger_level('app.monzo.sync', self.config.monzo_sync_level)
        self._set_logger_level('app.automation', self.config.automation_level)
        self._set_logger_level('scheduler', self.config.scheduler_level)
        self._set_logger_level('urllib3', self.config.urllib3_level)
        self._set_logger_level('requests', self.config.requests_level)
        self._set_logger_level('werkzeug', self.config.werkzeug_level)
        self._set_logger_level('sqlalchemy', self.config.sqlalchemy_level)
    
    def _set_logger_level(self, logger_name: str, level_name: str):
        """Set the level for a specific logger."""
        try:
            level = getattr(logging, level_name.upper())
            logging.getLogger(logger_name).setLevel(level)
        except AttributeError:
            logging.warning(f"Invalid logging level '{level_name}' for logger '{logger_name}'")
    
    def get_current_config(self) -> Dict:
        """Get current logging configuration as a dictionary."""
        return asdict(self.config)
    
    def update_config(self, new_config: Dict) -> Dict:
        """Update logging configuration and reconfigure logging."""
        # Update config with new values
        for key, value in new_config.items():
            if hasattr(self.config, key) and value is not None:
                setattr(self.config, key, value.upper())
        
        # Reconfigure logging
        self._configure_logging()
        
        return self.get_current_config()
    
    def set_logger_level(self, logger_name: str, level: str) -> bool:
        """Set the level for a specific logger."""
        try:
            level_upper = level.upper()
            if level_upper not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                return False
            
            self._set_logger_level(logger_name, level_upper)
            
            # Update config if it's a known logger
            if logger_name == 'app':
                self.config.app_level = level_upper
            elif logger_name == 'app.monzo.client':
                self.config.monzo_client_level = level_upper
            elif logger_name == 'app.monzo.sync':
                self.config.monzo_sync_level = level_upper
            elif logger_name == 'app.automation':
                self.config.automation_level = level_upper
            elif logger_name == 'scheduler':
                self.config.scheduler_level = level_upper
            elif logger_name == 'urllib3':
                self.config.urllib3_level = level_upper
            elif logger_name == 'requests':
                self.config.requests_level = level_upper
            elif logger_name == 'werkzeug':
                self.config.werkzeug_level = level_upper
            elif logger_name == 'sqlalchemy':
                self.config.sqlalchemy_level = level_upper
            
            return True
        except Exception:
            return False
    
    def get_available_loggers(self) -> Dict[str, str]:
        """Get list of available loggers and their current levels."""
        loggers = {
            'root': logging.getLogger().level,
            'app': logging.getLogger('app').level,
            'app.monzo.client': logging.getLogger('app.monzo.client').level,
            'app.monzo.sync': logging.getLogger('app.monzo.sync').level,
            'app.automation': logging.getLogger('app.automation').level,
            'scheduler': logging.getLogger('scheduler').level,
            'urllib3': logging.getLogger('urllib3').level,
            'requests': logging.getLogger('requests').level,
            'werkzeug': logging.getLogger('werkzeug').level,
            'sqlalchemy': logging.getLogger('sqlalchemy').level,
        }
        
        # Convert numeric levels to string names
        level_names = {logging.DEBUG: 'DEBUG', logging.INFO: 'INFO', 
                      logging.WARNING: 'WARNING', logging.ERROR: 'ERROR', 
                      logging.CRITICAL: 'CRITICAL'}
        
        return {name: level_names.get(level, 'UNKNOWN') for name, level in loggers.items()}


# Global logging manager instance
_logging_manager: Optional[LoggingManager] = None


def get_logging_manager() -> LoggingManager:
    """Get the global logging manager instance."""
    global _logging_manager
    if _logging_manager is None:
        _logging_manager = LoggingManager()
    return _logging_manager


def configure_logging():
    """Configure logging using the logging manager."""
    get_logging_manager() 