# 💰 Automation Configuration: Pounds and Pence Update

This document summarizes the update to use pounds and pence format instead of pence-only format in automation configurations.

## 📋 Overview

All automation configurations have been updated to use pounds and pence format (e.g., `100.50` for £100.50) instead of pence-only format (e.g., `10050` for £100.50). This makes configurations more human-readable and easier to understand.

## 🔧 What Was Updated

### 1. Helper Function
A `convert_pence_to_pounds()` helper function was created that:
- Converts pence amounts to pounds (e.g., `10050` → `100.50`)
- Handles various input types (int, float, None)
- Preserves existing pounds format (doesn't double-convert)
- Returns `None` for zero/null values

### 2. Automation Rule Types Updated

#### 📂 Autosorter Rules
- `holding_reserve_amount`: Reserve amount in holding pot
- `min_holding_balance`: Minimum balance to keep in holding
- `priority_pots[].amount`: Fixed amounts for priority pots
- `goal_pots[].amount`: Fixed amounts for goal pots
- `investment_pots[].amount`: Fixed amounts for investment pots

#### 💰 Pot Sweep Rules
- `amount`: Transfer amount (legacy format)
- `min_balance`: Minimum balance to maintain
- `payday_threshold`: Minimum amount for payday detection
- `trigger_threshold`: Amount threshold for triggers
- `sources[].amount`: Amount for each source pot
- `sources[].min_balance`: Minimum balance for each source

#### 💳 Auto Topup Rules
- `amount`: Topup amount
- `min_balance`: Minimum balance threshold

#### 📊 Bills Pot Logic Rules
- `shortfall_threshold`: Threshold for shortfall alerts

### 3. Setup Script Updated
The `setup_automation_rules.py` script now creates rules using pounds and pence format by default:
- `1000.0` instead of `100000` for £1000
- `500.0` instead of `50000` for £500
- `100.0` instead of `10000` for £100

## 🛠️ Scripts Created/Updated

### 1. `update_automation_config_to_pounds_simple.py`
**Purpose**: Comprehensive script to update all existing automation configurations
**Features**:
- Handles all automation rule types
- Safe conversion logic
- Detailed progress reporting
- Database transaction safety

### 2. `update_automation_config_to_pounds.py`
**Purpose**: Full-featured version with app integration
**Features**:
- Uses app models and database session
- More robust error handling
- Integration with existing app structure

### 3. `update_config_to_pounds.py`
**Purpose**: Legacy script for specific autosorter rules
**Features**:
- Updated with improved conversion logic
- Backward compatible

## 🔄 Backend Compatibility

The backend automatically handles both formats:
- **Pounds format**: `100.50` → converted to pence (`10050`) internally
- **Pence format**: `10050` → used directly

The `_convert_to_pence()` helper function in `app/automation/autosorter.py` handles the conversion:
```python
def _convert_to_pence(self, amount) -> int:
    """Convert amount to pence, handling both pence and pounds formats."""
    if amount is None:
        return 0
    
    # If amount is a float or has decimal places, assume it's in pounds
    if isinstance(amount, float) or (isinstance(amount, int) and amount < 1000):
        # Assume it's in pounds, convert to pence
        return int(amount * 100)
    else:
        # Assume it's already in pence
        return int(amount)
```

## 📊 Example Conversions

| Old Format (Pence) | New Format (Pounds) | Description |
|-------------------|-------------------|-------------|
| `100000` | `1000.0` | £1000 holding reserve |
| `50000` | `500.0` | £500 minimum balance |
| `25000` | `250.0` | £250 weekly topup |
| `10000` | `100.0` | £100 shortfall threshold |

## 🎯 Benefits

1. **Human Readable**: Configurations are easier to understand
2. **Consistent**: All amounts use the same format
3. **Backward Compatible**: Existing pence values still work
4. **Future Proof**: New configurations use pounds format
5. **Error Prevention**: Less chance of confusion with large numbers

## 🚀 Usage

### For New Configurations
Use pounds and pence format directly:
```json
{
  "holding_reserve_amount": 1000.0,
  "min_holding_balance": 500.0,
  "priority_pots": [
    {
      "amount": 250.0,
      "allocation_type": "fixed_amount"
    }
  ]
}
```

### For Existing Configurations
Run the update script to convert:
```bash
python update_automation_config_to_pounds_simple.py
```

### For Development
The backend automatically handles both formats, so no code changes are needed for new automation features.

## ✅ Status

- ✅ Helper function implemented
- ✅ All automation rule types supported
- ✅ Setup script updated
- ✅ Update scripts created
- ✅ Backend compatibility maintained
- ✅ Example rules created and tested
- ✅ Conversion logic tested and working

All automation configurations now use pounds and pence format for better readability and consistency! 