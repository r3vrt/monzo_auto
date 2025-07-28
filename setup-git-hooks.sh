#!/bin/bash

# Setup script for Monzo App development environment
# This installs git hooks to prevent debug code from being committed

echo "🔧 Setting up Monzo App development environment..."

# Install git hooks
echo "📦 Installing git hooks..."
if [ -f ".githooks/pre-commit" ]; then
    cp .githooks/pre-commit .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    echo "✅ Pre-commit hook installed"
else
    echo "❌ Pre-commit hook not found in .githooks/"
    exit 1
fi

# Set git config to use the hooks directory
git config core.hooksPath .git/hooks

echo ""
echo "🎯 Git hooks installed successfully!"
echo ""
echo "📋 Development Guidelines:"
echo "================================================"
echo ""
echo "🔧 For debugging during development, use environment variables:"
echo "  export FLASK_DEBUG=true                    # Enable Flask debug mode"
echo "  export LOG_MONZO_SYNC_LEVEL=DEBUG          # Verbose sync logging"
echo "  export LOG_MONZO_CLIENT_LEVEL=DEBUG        # Verbose API logging"
echo ""
echo "🚫 The following will be blocked on commit:"
echo "  • hardcoded debug=True in Python files"
echo "  • hardcoded DEBUG logging levels in config defaults"
echo "  • print() statements (except in monitor_logs.py)"
echo "  • console.log statements in JS/HTML"
echo ""
echo "✅ Production-safe defaults:"
echo "  • debug=False (unless FLASK_DEBUG=true)"
echo "  • All logging levels default to INFO/WARNING"
echo "  • Environment variables override defaults"
echo ""
echo "🌟 Happy coding! Your commits will now be production-safe." 