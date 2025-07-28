# Main Account Sweep Feature

## Overview

The pot sweep automation now supports sweeping money from the main account balance in addition to pots. This allows users to automatically move money from their main account to target pots based on various strategies.

## Features

### Main Account as Source
- **Source Type**: Users can now select "Main Account" as a source in pot sweep rules
- **Real-time Balance**: Uses Monzo API to get current main account balance
- **All Strategies Supported**: Works with all existing sweep strategies

### Supported Strategies for Main Account

1. **Fixed Amount** (`FIXED_AMOUNT`)
   - Move a specific amount from main account
   - Example: Move exactly £500

2. **Percentage** (`PERCENTAGE`)
   - Move a percentage of main account balance
   - Example: Move 50% of available balance

3. **Remaining Balance** (`REMAINING_BALANCE`)
   - Move everything except a minimum balance
   - Example: Keep £100 minimum, move the rest

4. **All Available** (`ALL_AVAILABLE`)
   - Move entire main account balance
   - Example: Empty the account completely

## Implementation Details

### Backend Changes

#### SweepSource Enhancement
- Added `is_main_account` property to detect main account sources
- Supports multiple naming conventions: "main_account", "main account", "account", "main"

#### New Methods in PotSweeps Class
- `_get_main_account_balance()`: Retrieves current balance from Monzo API
- `_transfer_from_main_account()`: Handles transfers from main account to pots
- Updated `_process_sweep_source()`: Handles main account transfers differently

#### Transfer Logic
- Main account transfers use `deposit_into_pot()` API call
- Includes deduplication ID to prevent duplicate transfers
- Proper error handling and logging

### UI Changes

#### Automation Management Template
- Added "Main Account" option to source pot dropdowns
- Available in both create and edit modes
- Maintains existing pot options alongside main account

#### JavaScript Functions
- `addSourcePot()`: Includes main account option
- `editSourcePot()`: Includes main account option for editing
- All existing functionality preserved

## Usage Examples

### Example 1: Keep £100 Minimum
```json
{
  "name": "Sweep Main Account",
  "sources": [
    {
      "pot_name": "main_account",
      "strategy": "remaining_balance",
      "min_balance": 10000
    }
  ],
  "target_pot_name": "Held"
}
```

### Example 2: Move 50% of Balance
```json
{
  "name": "Half Main Account",
  "sources": [
    {
      "pot_name": "main_account",
      "strategy": "percentage",
      "percentage": 0.5
    }
  ],
  "target_pot_name": "Savings"
}
```

### Example 3: Fixed Amount Transfer
```json
{
  "name": "Monthly Transfer",
  "sources": [
    {
      "pot_name": "main_account",
      "strategy": "fixed_amount",
      "amount": 50000
    }
  ],
  "target_pot_name": "Bills"
}
```

## Benefits

1. **Complete Money Management**: Can now sweep from main account, not just pots
2. **Flexible Strategies**: All existing sweep strategies work with main account
3. **Real-time Balance**: Uses live Monzo API data for accurate balances
4. **Seamless Integration**: Works alongside existing pot sweep functionality
5. **User-Friendly**: Simple dropdown selection in UI

## Technical Notes

- Main account balance is retrieved in real-time from Monzo API
- Transfers use proper deduplication to prevent duplicates
- Error handling includes account not found scenarios
- Logging provides clear feedback on transfer success/failure
- Compatible with all existing trigger types (manual, payday, etc.)

## Testing

The feature has been tested with:
- ✅ Main account source detection
- ✅ All sweep strategies
- ✅ UI integration
- ✅ Error handling
- ✅ Database compatibility

## Future Enhancements

Potential future improvements:
- Multiple account support (if user has multiple Monzo accounts)
- Balance threshold triggers for main account
- Scheduled main account sweeps
- Main account balance monitoring 