#!/bin/bash

# Development Environment Variables for Monzo App
# Source this file during development to enable debugging
# Usage: source dev-env.sh

# Flask Debug Mode
export FLASK_DEBUG=true

# Detailed Logging for Development
export LOG_ROOT_LEVEL=INFO
export LOG_APP_LEVEL=INFO
export LOG_MONZO_CLIENT_LEVEL=DEBUG      # Show API requests/responses
export LOG_MONZO_SYNC_LEVEL=DEBUG        # Show sync process details
export LOG_AUTOMATION_LEVEL=INFO
export LOG_SCHEDULER_LEVEL=INFO

# Keep external libraries quiet
export LOG_URLLIB3_LEVEL=WARNING
export LOG_REQUESTS_LEVEL=WARNING
export LOG_WERKZEUG_LEVEL=INFO
export LOG_SQLALCHEMY_LEVEL=WARNING

# Flask Secret Key (development only)
export FLASK_SECRET_KEY=dev-secret-key-change-in-production

echo "🔧 Development environment loaded!"
echo "   FLASK_DEBUG: $FLASK_DEBUG"
echo "   LOG_MONZO_SYNC_LEVEL: $LOG_MONZO_SYNC_LEVEL"
echo "   LOG_MONZO_CLIENT_LEVEL: $LOG_MONZO_CLIENT_LEVEL" 