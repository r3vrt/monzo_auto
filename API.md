# API Documentation

This document provides comprehensive API documentation for the Monzo Automation App.

## Base URL

- **Development**: `http://localhost:5000`
- **Production**: `https://your-domain.com`

## Authentication

The application uses OAuth2 authentication with Monzo. All API endpoints require valid authentication unless otherwise specified.

### Authentication Flow

1. **Start OAuth Flow**: `GET /auth/login`
2. **OAuth Callback**: `GET /auth/callback`
3. **Check Status**: `GET /auth/status`
4. **Logout**: `POST /auth/logout`

## Response Format

All API responses follow a consistent format:

### Success Response
```json
{
  "status": "success",
  "data": { ... },
  "message": "Operation completed successfully"
}
```

### Error Response
```json
{
  "status": "error",
  "error": "Error description",
  "message": "Detailed error message"
}
```

## Endpoints

### Authentication

#### `GET /auth/login`
Start the OAuth authentication flow with Monzo.

**Response**: HTML page with authorization URL

#### `GET /auth/callback`
Handle OAuth callback from Monzo.

**Query Parameters**:
- `code` (string): Authorization code from Monzo
- `state` (string): State parameter for CSRF protection
- `error` (string): Error code if authorization failed

**Response**: HTML page with authentication result

#### `GET /auth/status`
Check current authentication status.

**Response**: HTML page with authentication status

#### `POST /auth/logout`
Logout and clear authentication tokens.

**Response**: Redirect to home page

### Task Management

#### `GET /tasks/`
List all available automation tasks.

**Response**: HTML page with available tasks

**Available Tasks**:
- `transaction_sync`: Sync recent transactions
- `auto_topup`: Automatically topup main account
- `sweep_pots`: Move balances between pots
- `autosorter`: Distribute funds to multiple pots

#### `GET /tasks/<task_id>/execute`
Execute a specific automation task.

**Path Parameters**:
- `task_id` (string): ID of the task to execute

**Response**: HTML page with execution results

#### `GET /tasks/accounts`
Get user accounts information.

**Response**: HTML page with account information

#### `GET /tasks/accounts/<account_id>/transactions`
Get transactions for a specific account.

**Path Parameters**:
- `account_id` (string): The account ID

**Query Parameters**:
- `limit` (integer, optional): Number of transactions to retrieve (default: 100)

**Response**: JSON response with transaction information

#### `GET /tasks/status`
Display task execution history.

**Response**: HTML page with task execution history

### Task-Specific Endpoints

#### Auto-Topup

##### `GET /tasks/auto_topup/execute`
Execute the auto-topup task.

**Response**: HTML page with execution results

##### `GET /tasks/auto_topup/status`
Get auto-topup execution history.

**Response**: HTML page with auto-topup history

#### Sweep Pots

##### `GET /tasks/sweep_pots/execute`
Execute the sweep pots task.

**Response**: HTML page with execution results

##### `GET /tasks/sweep_pots/dry_run`
Execute a dry run of the sweep pots task.

**Response**: HTML page with dry run results

##### `GET /tasks/sweep_pots/status`
Get sweep pots execution history.

**Response**: HTML page with sweep pots history

#### Autosorter

##### `GET /tasks/autosorter/execute`
Execute the autosorter task.

**Response**: HTML page with execution results

##### `GET /tasks/autosorter/dry_run`
Execute a dry run of the autosorter task.

**Response**: HTML page with dry run results

#### Combined Dry Run

##### `GET /tasks/combined/dry_run`
Execute a dry run of both sweep pots and autosorter tasks in sequence.

**Response**: HTML page with combined dry run results

### Configuration Management

#### `GET /configuration/`
Show configuration overview page.

**Response**: HTML page with current configuration

#### `GET /configuration/api`
Get current application configuration.

**Response**: JSON response with current configuration

#### `GET /configuration/auth`
Show authentication settings form.

**Response**: HTML form for authentication configuration

#### `POST /configuration/auth`
Update authentication settings.

**Form Data**:
- `client_id` (string): Monzo OAuth client ID
- `client_secret` (string): Monzo OAuth client secret
- `redirect_uri` (string): OAuth redirect URI

**Response**: HTML page with update result

#### `GET /configuration/general`
Show general settings form.

**Response**: HTML form for general configuration

#### `POST /configuration/general`
Update general settings.

**Form Data**:
- `debug_mode` (boolean): Enable debug mode
- `auto_sync` (boolean): Enable automatic transaction sync
- `sync_interval_minutes` (integer): Sync interval in minutes
- `log_level` (string): Logging level
- `max_retries` (integer): Maximum retry attempts
- `timeout_seconds` (integer): Request timeout in seconds

**Response**: HTML page with update result

#### Auto-Topup Configuration

##### `GET /configuration/auto-topup`
Show auto-topup configuration form.

**Response**: HTML form for auto-topup configuration

##### `POST /configuration/auto-topup`
Update auto-topup settings.

**Form Data**:
- `enabled` (boolean): Enable auto-topup
- `source_pot_name` (string): Source pot name
- `threshold_amount` (float): Threshold amount in pounds
- `target_amount` (float): Target amount in pounds
- `check_interval_minutes` (integer): Check interval in minutes

**Response**: HTML page with update result

#### Sweep Pots Configuration

##### `GET /configuration/sweep`
Show sweep pots configuration form.

**Response**: HTML form for sweep pots configuration

##### `POST /configuration/sweep`
Update sweep pots settings.

**Form Data**:
- `enabled` (boolean): Enable sweep pots
- `source_pot_names` (string): Comma-separated list of source pot names
- `target_pot_name` (string): Target pot name
- `minimum_amount` (float): Minimum amount to sweep

**Response**: HTML page with update result

#### Autosorter Configuration

##### `GET /configuration/autosorter`
Show autosorter configuration form.

**Response**: HTML form for autosorter configuration

##### `POST /configuration/autosorter`
Update autosorter settings.

**Form Data**:
- `source_pot` (string): Source pot name
- `allocation_strategy` (string): Allocation strategy (free_selection, all_goals, priority_goals)
- `destination_pots` (string): JSON string of destination pot configuration
- `priority_pots` (string): Comma-separated list of priority pot names
- `goal_allocation_method` (string): Goal allocation method (even, relative)
- `enable_bills_pot` (boolean): Enable bills pot integration
- `bills_pot_name` (string): Bills pot name
- `pay_cycle_payday` (string): Payday of the month
- `pay_cycle_frequency` (string): Pay cycle frequency (monthly, weekly)

**Response**: HTML page with update result

### Monitoring

#### `GET /monitoring/health`
Health check endpoint.

**Response**: HTML page with system health status

#### `GET /monitoring/status`
Get system status and metrics.

**Response**: HTML page with system status

#### `GET /monitoring/monzo`
Get detailed Monzo API status.

**Response**: HTML page with Monzo API status

#### `GET /monitoring/api/health`
API health check endpoint.

**Response**: JSON response with health status

#### `GET /monitoring/api/status`
API status endpoint.

**Response**: JSON response with system status

### Pages

#### `GET /`
Main dashboard page.

**Response**: HTML page with dashboard overview

#### `GET /accounts/`
Account overview page.

**Response**: HTML page with account information

#### `GET /accounts/<account_id>/transactions`
Account transactions page.

**Path Parameters**:
- `account_id` (string): The account ID

**Response**: HTML page with account transactions

#### `GET /analytics/`
Analytics and reporting page.

**Response**: HTML page with analytics data

#### `GET /transactions/sync`
Transaction sync interface.

**Response**: HTML page with transaction sync options

## Error Codes

### HTTP Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request parameters
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Access denied
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

### Common Error Messages

- `"No accounts selected"`: No accounts configured for automation
- `"Source pot not found"`: Specified pot does not exist
- `"Insufficient funds"`: Not enough money in source pot
- `"Configuration error"`: Invalid configuration settings
- `"Authentication failed"`: OAuth authentication error
- `"API rate limit exceeded"`: Monzo API rate limit reached

## Rate Limiting

The application respects Monzo API rate limits. If you encounter rate limiting:

1. Wait before making additional requests
2. Implement exponential backoff for retries
3. Consider using the dry run mode for testing

## Security Considerations

- All sensitive data (OAuth tokens, client secrets) is stored securely
- Input validation is performed on all user inputs
- Error messages are sanitized to prevent information leakage
- HTTPS is required in production environments
- OAuth state parameter is used for CSRF protection

## Examples

### Execute Auto-Topup Task
```bash
curl -X GET "http://localhost:5000/tasks/auto_topup/execute"
```

### Get Account Transactions
```bash
curl -X GET "http://localhost:5000/tasks/accounts/acc_1234567890/transactions?limit=50"
```

### Update Auto-Topup Configuration
```bash
curl -X POST "http://localhost:5000/configuration/auto-topup" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "enabled=true&source_pot_name=Savings&threshold_amount=30.0&target_amount=50.0"
```

## Support

For API-related issues or questions:

1. Check the error messages and status codes
2. Review the application logs
3. Ensure proper authentication
4. Verify configuration settings
5. Create an issue in the repository 