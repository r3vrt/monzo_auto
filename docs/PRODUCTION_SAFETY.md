# Production Safety & Debug Management

This document explains how the Monzo App ensures debug settings never reach production.

## 🎯 Overview

The codebase uses a multi-layered approach to prevent debug code from reaching production:

1. **Environment Variables** - Debug settings use env vars with production-safe defaults
2. **Git Pre-Commit Hooks** - Automatic checks before commits
3. **Development Tools** - Easy debugging setup for developers

## 🔧 Quick Setup

### For New Developers

```bash
# 1. Install git hooks (one-time setup)
./setup-git-hooks.sh

# 2. Enable debugging for development
source dev-env.sh

# 3. Start developing!
python run.py
```

## 📋 Environment Variables

### Debug Mode
```bash
export FLASK_DEBUG=true     # Enable Flask debug mode
```

### Logging Levels
```bash
export LOG_MONZO_SYNC_LEVEL=DEBUG    # Detailed sync logging
export LOG_MONZO_CLIENT_LEVEL=DEBUG  # API request/response logging
export LOG_APP_LEVEL=DEBUG           # General app debugging
```

### Production Defaults
All environment variables default to production-safe values:
- `FLASK_DEBUG` → `false`
- All `LOG_*_LEVEL` → `INFO` or `WARNING`

## 🚫 Git Pre-Commit Protection

The pre-commit hook automatically blocks commits containing:

### ❌ Blocked Patterns
- `debug=True` in Python files
- Hardcoded `DEBUG` logging levels in config defaults
- `print()` statements (except in `monitor_logs.py`)
- `console.log` statements in JS/HTML

### ✅ Example: Blocked Commit
```bash
$ git commit -m "Add debug feature"

🔍 Checking for debug settings...

🚫 COMMIT BLOCKED: Debug settings detected!
================================================
❌ Found hardcoded debug=True in Python files
⚠️  Found print() statements in: app/api/routes.py

💡 To fix:
  • Use FLASK_DEBUG=true environment variable instead of debug=True
  • Use LOG_*_LEVEL=DEBUG environment variables instead of hardcoded defaults
  • Remove print() statements (use logger instead)
  • Remove console.log statements
```

## 🔧 Development Workflow

### Enable Debugging
```bash
# Method 1: Use the provided script
source dev-env.sh

# Method 2: Set individual variables
export FLASK_DEBUG=true
export LOG_MONZO_SYNC_LEVEL=DEBUG
```

### Disable Debugging (Default)
No action needed - production defaults are automatic.

### Temporary Debugging
```bash
# Enable just for this session
FLASK_DEBUG=true python run.py

# Enable with specific logging
LOG_MONZO_SYNC_LEVEL=DEBUG python run.py
```

## 🛠 For Different Environments

### Development
```bash
source dev-env.sh
python run.py
```

### Testing
```bash
export LOG_ROOT_LEVEL=WARNING  # Reduce noise
python -m pytest
```

### Production
```bash
# No environment variables needed - uses safe defaults
python run.py
```

## 🚀 Deployment Safety

### What's Guaranteed
- Debug mode is **always** `false` unless explicitly enabled
- Logging levels default to `INFO`/`WARNING`
- No debug statements in committed code
- Environment variables override defaults

### Emergency Debug (Production)
If you need debugging in production (emergency only):
```bash
# Temporary enable for this process only
export FLASK_DEBUG=true
export LOG_MONZO_SYNC_LEVEL=DEBUG
python run.py
```

## 🔍 Troubleshooting

### Git Hook Not Working?
```bash
# Reinstall hooks
./setup-git-hooks.sh

# Check hook is installed
ls -la .git/hooks/pre-commit
```

### Can't Commit Code?
The git hook is protecting you! Fix the issues it reports:

```bash
# Instead of: debug=True
# Use environment variable approach (see run.py for example)

# Instead of: print("debug info")
# Use: logger.debug("debug info")

# Instead of: console.log("debug")
# Use: console.debug("debug") or remove entirely
```

### Environment Variables Not Working?
```bash
# Check current environment
env | grep -E "(FLASK_|LOG_)"

# Reload development environment
source dev-env.sh
```

## 📚 Technical Details

### File Structure
```
.githooks/pre-commit       # Git hook script
setup-git-hooks.sh         # Hook installation script
dev-env.sh                 # Development environment setup
run.py                     # Uses FLASK_DEBUG env var
app/logging_config.py      # Uses LOG_* env vars
```

### Code Changes Made

**run.py**:
```python
# Before
app.run(debug=False, host="0.0.0.0", port=5000)

# After
debug_mode = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")
app.run(debug=debug_mode, host="0.0.0.0", port=5000)
```

**logging_config.py**:
```python
# All defaults changed to INFO (production-safe)
# Environment variables can override for development
```

## 🎉 Benefits

✅ **Zero Risk** - Debug code cannot reach production  
✅ **Developer Friendly** - Easy debugging during development  
✅ **Automatic** - Git hooks work without thinking  
✅ **Flexible** - Environment variables for different needs  
✅ **Reversible** - Easy to enable/disable debugging  

---

**Remember**: The system defaults to production-safe settings. You must explicitly enable debugging for development. 