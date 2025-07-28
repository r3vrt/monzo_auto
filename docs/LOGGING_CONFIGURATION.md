# Logging Configuration

The Monzo app now supports configurable logging levels that can be adjusted at runtime without restarting the application.

## Overview

The logging system allows you to control the verbosity of different components:

- **Root Logger**: Controls the overall logging level
- **Application**: General application logs
- **Monzo Client**: API requests and responses
- **Monzo Sync**: Data synchronization operations
- **Automation**: Automation rule execution
- **Scheduler**: Background job scheduling
- **HTTP Libraries**: Network request logging (urllib3, requests)
- **Flask**: Web framework logs (Werkzeug)
- **Database**: SQLAlchemy query logging

## Available Logging Levels

- **DEBUG**: Most verbose, shows detailed information
- **INFO**: General information messages
- **WARNING**: Warning messages for potential issues
- **ERROR**: Error messages for actual problems
- **CRITICAL**: Critical errors that may cause application failure

## Configuration Methods

### 1. Web Interface

Visit `/logs/config` in your browser to access the logging configuration interface. This provides:

- A form to adjust all logging levels
- Real-time status of current logger levels
- Ability to reset to default values
- Visual feedback for changes

### 2. API Endpoints

#### Get Current Configuration
```bash
GET /api/logging/config
```

#### Update Configuration
```bash
PUT /api/logging/config
Content-Type: application/json

{
    "root_level": "INFO",
    "app_level": "DEBUG",
    "monzo_client_level": "WARNING",
    "automation_level": "INFO"
}
```

#### Set Specific Logger Level
```bash
PUT /api/logging/logger/app.automation/level/DEBUG
```

#### Reset to Defaults
```bash
POST /api/logging/reset
```

### 3. Environment Variables

You can set default logging levels using environment variables:

```bash
export LOG_ROOT_LEVEL=INFO
export LOG_APP_LEVEL=DEBUG
export LOG_MONZO_CLIENT_LEVEL=WARNING
export LOG_MONZO_SYNC_LEVEL=INFO
export LOG_AUTOMATION_LEVEL=INFO
export LOG_SCHEDULER_LEVEL=INFO
export LOG_URLLIB3_LEVEL=WARNING
export LOG_REQUESTS_LEVEL=WARNING
export LOG_WERKZEUG_LEVEL=INFO
export LOG_SQLALCHEMY_LEVEL=WARNING
```

## Use Cases

### Debugging Issues
Set relevant loggers to DEBUG level:
```bash
curl -X PUT http://localhost:5000/api/logging/config \
  -H "Content-Type: application/json" \
  -d '{"automation_level": "DEBUG", "monzo_sync_level": "DEBUG"}'
```

### Reducing Noise in Production
Set HTTP libraries to WARNING level:
```bash
curl -X PUT http://localhost:5000/api/logging/config \
  -H "Content-Type: application/json" \
  -d '{"urllib3_level": "WARNING", "requests_level": "WARNING", "werkzeug_level": "WARNING"}'
```

### Monitoring Specific Components
Focus on automation logs:
```bash
curl -X PUT http://localhost:5000/api/logging/logger/app.automation/level/INFO
```

## Default Configuration

The default logging configuration is:

- Root Logger: INFO
- Application: INFO
- Monzo Client: INFO
- Monzo Sync: INFO
- Automation: INFO
- Scheduler: INFO
- HTTP Libraries: WARNING
- Flask: INFO
- Database: WARNING

## Best Practices

1. **Start with INFO level** for most components
2. **Use DEBUG sparingly** as it generates significant output
3. **Set HTTP libraries to WARNING** in production to reduce noise
4. **Monitor automation logs** when troubleshooting rules
5. **Reset to defaults** when done debugging

## Troubleshooting

### Log File Location
Logs are written to `monzo_app.log` in the application root directory.

### Viewing Logs
- Web interface: `/logs`
- Direct file access: `tail -f monzo_app.log`

### Common Issues

**Too much logging output:**
- Set HTTP libraries to WARNING or ERROR
- Reduce automation level to INFO

**Not enough detail:**
- Set relevant components to DEBUG
- Check specific logger levels via API

**Configuration not taking effect:**
- Verify API responses for success
- Check web interface for current status
- Restart application if needed

## Integration with Existing Logging

The new configuration system integrates with the existing logging setup in `run.py` and maintains backward compatibility. All existing log statements will continue to work as expected. 