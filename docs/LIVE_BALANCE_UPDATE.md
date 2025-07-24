# Live Balance Updates for Automation System

## Overview

This document outlines the changes made to ensure all automation features (Sweep, Autosort, and Auto Topup) use live balance data from the Monzo API instead of potentially stale database data.

## Changes Made

### 1. Pot Balance Retrieval

All automation modules now use live Monzo API data for pot balances with database fallback:

#### Before:
- **Sweep & Autosort**: Used database-only balance data
- **Auto Topup**: Already used live API data with database fallback

#### After:
- **All modules**: Use live Monzo API data first, fall back to database if API fails

### 2. Account Sync Integration

All automation modules now trigger account sync before execution to ensure the database has the latest balance information:

#### New Methods Added:
- `_sync_account_data(user_id: str)` - Triggers sync for all active user accounts
- Integrated into `execute_sweep_rule()`, `execute_distribution()`, and `execute_topup_rule()`

### 3. Enhanced Logging

Added comprehensive logging to track balance retrieval:
- Live API balance retrieval with amounts in pounds
- Database fallback warnings when API fails
- Sync operation logging

### 4. Circular Import Resolution

Created `sync_utils.py` to avoid circular import dependencies:
- Isolated sync functionality from main sync module
- Simplified sync that updates account and pot data without triggering full automation integration
- Prevents circular dependency between automation modules and sync system

## Implementation Details

### Sync Utilities (`sync_utils.py`)

```python
def trigger_account_sync(db: Session, monzo_client: Any, user_id: str, module_name: str) -> None:
    """
    Trigger account sync to ensure database has latest balance information.
    
    This is a simplified sync that updates account and pot data without triggering
    the full automation integration to avoid circular imports.
    """
```

**Features:**
- Updates account details from Monzo API using `get_accounts()` method
- Updates pot balances and metadata using `get_pots()` method
- Handles new pots and deleted pots
- Comprehensive error handling and logging
- No circular import dependencies
- Uses correct MonzoClient API methods

### Sweep (`pot_sweeps.py`)

```python
def _get_pot_balance(self, pot_id: str) -> Optional[int]:
    """Get current balance for a pot from live Monzo API with database fallback."""
    # 1. Try to get live balance from Monzo API
    # 2. Fall back to database if API fails
    # 3. Log all operations with amounts in pounds
```

**Changes:**
- Updated `_get_pot_balance()` to use live API data
- Added `_sync_account_data()` method using `sync_utils`
- Integrated sync into `execute_sweep_rule()`

### Autosort (`autosorter.py`)

```python
def _get_pot_balance(self, pot_id: str) -> Optional[int]:
    """Get current balance of a pot from live Monzo API with database fallback."""
    # Same implementation as sweep
```

**Changes:**
- Updated `_get_pot_balance()` to use live API data
- Added `_sync_account_data()` method using `sync_utils`
- Integrated sync into `execute_distribution()`

### Auto Topup (`auto_topup.py`)

**Changes:**
- Added `_sync_account_data()` method using `sync_utils` for consistency
- Integrated sync into `execute_topup_rule()`
- Fixed `_get_account_balance()` method to use correct API methods
- Already had live API balance retrieval with proper fallbacks

## Benefits

### 1. Accuracy
- All automation decisions based on current, real-time balance data
- Eliminates issues caused by stale database data
- Reduces failed transfers due to insufficient funds

### 2. Consistency
- All automation modules now use the same balance retrieval strategy
- Unified approach across sweep, autosort, and topup features

### 3. Reliability
- Database fallback ensures operation continues even if API is temporarily unavailable
- Comprehensive error handling and logging

### 4. Data Freshness
- Account sync before execution ensures database is updated
- Pot balances reflect recent transactions and transfers

### 5. Architecture Stability
- Resolved circular import dependencies
- Clean separation of concerns
- Maintainable codebase structure

## Logging Examples

### Live Balance Retrieval
```
[SWEEP] Getting live pot balance for pot_123456
[SWEEP] Live pot balance for pot_123456: 50000 (500.00£)
```

### Database Fallback
```
[SWEEP] Pot pot_123456 not found in live data, falling back to database
[SWEEP] Using stale database balance for pot_123456: 45000 (450.00£)
```

### Account Sync
```
[SWEEP] Triggering account sync for user user_123
[SWEEP] Syncing account acc_456
[SWEEP] Successfully synced account acc_456
[SWEEP] Account sync completed for user user_123
```

## Error Handling

### API Failures
- Graceful fallback to database data
- Detailed error logging
- Operation continues with available data

### Sync Failures
- Individual account sync failures don't stop automation
- Comprehensive error logging per account
- Automation proceeds with available data

### Circular Import Prevention
- Isolated sync utilities prevent dependency cycles
- Clean module boundaries
- Maintainable import structure

## Performance Considerations

### API Calls
- Additional API calls for balance retrieval
- Account sync adds more API calls before execution
- Cached data used where possible

### Optimization
- Sync only active accounts
- Error handling prevents unnecessary retries
- Logging helps identify performance bottlenecks

## Testing Recommendations

### 1. Balance Accuracy
- Test with recent transactions
- Verify live vs database balance differences
- Check fallback behavior with API failures

### 2. Sync Integration
- Test sync before automation execution
- Verify database updates after sync
- Check error handling for sync failures

### 3. Transfer Accuracy
- Test transfers with live balance data
- Verify sufficient funds checks
- Test edge cases with minimal balances

### 4. Import Stability
- Test all automation module imports
- Verify no circular import errors
- Check integration with existing sync system

## Migration Notes

### Existing Rules
- No changes required to existing automation rules
- All rules automatically benefit from live balance data
- Backward compatibility maintained

### Configuration
- No new configuration options required
- Existing trigger conditions work unchanged
- Enhanced logging provides better visibility

## Future Enhancements

### 1. Caching
- Consider implementing balance caching with TTL
- Reduce API calls for frequent balance checks
- Cache invalidation on transfers

### 2. Real-time Updates
- Webhook integration for instant balance updates
- Push notifications for balance changes
- Real-time automation triggers

### 3. Performance Monitoring
- Track API call frequency and response times
- Monitor sync operation performance
- Alert on repeated API failures

### 4. Architecture Improvements
- Consider dependency injection for better testability
- Implement interface-based design for sync utilities
- Add configuration-driven sync strategies 