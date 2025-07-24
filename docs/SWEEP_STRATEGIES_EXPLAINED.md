# Sweep Strategies Explained

## Overview

The pot sweep automation supports four different strategies for determining how much money to move from a source (pot or main account) to a target pot. Each strategy serves different use cases and provides different levels of control.

## The Four Strategies

### 1. Fixed Amount (`FIXED_AMOUNT`)
**What it does**: Moves a specific, predetermined amount.

**Code Logic**:
```python
return min(source.amount, current_balance)
```

**Example**: 
- Set amount: £500
- Current balance: £1,000
- Result: Moves £500
- Current balance: £800  
- Result: Moves £500 (even if it would leave £300)

**Use case**: When you want to move exactly the same amount every time, regardless of the source balance.

---

### 2. Percentage (`PERCENTAGE`)
**What it does**: Moves a percentage of the current balance.

**Code Logic**:
```python
return int(current_balance * source.percentage)
```

**Example**:
- Set percentage: 50% (0.5)
- Current balance: £1,000
- Result: Moves £500
- Current balance: £800
- Result: Moves £400

**Use case**: When you want to move a proportional amount that scales with the source balance.

---

### 3. Remaining Balance (`REMAINING_BALANCE`) ⭐
**What it does**: Moves everything except a specified minimum balance.

**Code Logic**:
```python
if source.min_balance is None:
    return current_balance  # If no min_balance set, moves everything
return max(0, current_balance - source.min_balance)
```

**Example**:
- Set minimum balance: £100
- Current balance: £1,000
- Result: Moves £900 (keeps £100)
- Current balance: £150
- Result: Moves £50 (keeps £100)
- Current balance: £80
- Result: Moves £0 (keeps £80, doesn't go below £100)

**Use case**: When you want to maintain a safety buffer in the source while moving excess funds.

---

### 4. All Available (`ALL_AVAILABLE`) ⭐
**What it does**: Moves the entire current balance.

**Code Logic**:
```python
return current_balance
```

**Example**:
- Current balance: £1,000
- Result: Moves £1,000 (empties completely)
- Current balance: £500
- Result: Moves £500 (empties completely)
- Current balance: £0
- Result: Moves £0

**Use case**: When you want to completely empty the source pot/account.

---

## Key Differences: REMAINING_BALANCE vs ALL_AVAILABLE

### **REMAINING_BALANCE**
- **Keeps a minimum**: Always leaves the specified amount behind
- **Safety buffer**: Protects against completely emptying the source
- **Configurable**: You set the minimum amount to keep
- **Smart**: Won't move money if it would leave less than the minimum

### **ALL_AVAILABLE**  
- **Empties completely**: Moves every penny available
- **No safety net**: Can leave the source with £0
- **Simple**: No configuration needed
- **Aggressive**: Always moves the maximum possible amount

## Practical Examples

### Scenario: Bills Pot with £1,000

#### Using REMAINING_BALANCE (min_balance: £100)
```
Current balance: £1,000
Moves: £900
Leaves: £100 ✅

Current balance: £150  
Moves: £50
Leaves: £100 ✅

Current balance: £80
Moves: £0
Leaves: £80 ✅ (protects the £80)
```

#### Using ALL_AVAILABLE
```
Current balance: £1,000
Moves: £1,000
Leaves: £0 ⚠️

Current balance: £150
Moves: £150  
Leaves: £0 ⚠️

Current balance: £80
Moves: £80
Leaves: £0 ⚠️
```

## When to Use Each

### Use REMAINING_BALANCE when:
- You want to maintain a safety buffer
- The source pot/account needs some money for emergencies
- You're sweeping from main account but want to keep some spending money
- You want to ensure the source never goes below a certain amount

### Use ALL_AVAILABLE when:
- You want to completely empty the source
- The source is a temporary holding pot
- You're doing a "clean sweep" operation
- You don't need to maintain any balance in the source

## Edge Cases

### REMAINING_BALANCE with no min_balance set:
```python
if source.min_balance is None:
    return current_balance  # Behaves like ALL_AVAILABLE
```

### Both strategies with £0 balance:
- Both return 0 (no money to move)

### Both strategies with negative balance:
- Both return 0 (can't move negative money)

## Summary

| Strategy | Moves | Leaves Behind | Safety Buffer | Use Case |
|----------|-------|---------------|---------------|----------|
| **REMAINING_BALANCE** | Everything except minimum | Specified minimum | ✅ Yes | Maintain safety buffer |
| **ALL_AVAILABLE** | Everything | Nothing (£0) | ❌ No | Complete emptying |

The key difference is that **REMAINING_BALANCE** is protective and maintains a safety net, while **ALL_AVAILABLE** is aggressive and empties completely. 