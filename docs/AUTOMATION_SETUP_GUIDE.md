# 🤖 Automation Rules Setup Guide

This guide will help you set up and configure automation rules for your Monzo account.

## 📋 Prerequisites

Before setting up automation rules, ensure you have:

1. ✅ **Authenticated with Monzo** - Visit `/auth/start` to connect your account
2. ✅ **Synced your data** - Run a sync to pull accounts, pots, and transactions
3. ✅ **Organized your pots** - Visit `/pots/manage` to categorize your pots

## 🚀 Quick Start

### Option 1: Use the Setup Script (Recommended)

Run the automated setup script to create example rules:

```bash
python setup_automation_rules.py
```


This will create 5 practical automation rules:
- 💰 **Monthly Bills Sweep** - Automatically transfer £1000 to bills pot on the 1st of each month
- 📂 **Grocery Autosorter** - Automatically categorize Tesco transactions
- 💳 **Weekly Savings Topup** - Add £250 to savings every Monday
- 📊 **Bills Pot Analysis** - Monitor bills spending and shortfalls
- ☕ **Coffee Shop Autosorter** - Categorize Starbucks transactions (disabled by default)

### Option 2: Manual Setup via UI

1. Visit `/automation/manage` in your browser
2. Click "Create New Rule"
3. Choose a rule type and configure it
4. Save and enable the rule

## 🔧 Rule Types Explained

### 💰 Enhanced Pot Sweep Rules

Automatically transfer money from multiple sources to a target pot with advanced strategies.

**New Features:**
- **Multiple sources**: Move from multiple pots in one rule
- **Flexible strategies**: Different ways to calculate amounts
- **Smart triggers**: Payday detection, balance thresholds
- **Priority ordering**: Control execution order

**Use Cases:**
- Payday money management (your use case!)
- Monthly bills funding
- Regular savings contributions
- Emergency fund building

**Sweep Strategies:**
1. **fixed_amount**: Move a specific amount
2. **percentage**: Move a percentage of balance (0.0-1.0)
3. **remaining_balance**: Move everything except minimum
4. **all_available**: Move entire balance

**Trigger Types:**
1. **manual**: Manual execution only
2. **monthly**: Monthly on specific day
3. **weekly**: Weekly on specific day  
4. **payday_detection**: Based on salary deposits
5. **balance_threshold**: When source exceeds amount

**Payday Detection Details:**
The `payday_detection` trigger automatically detects when you receive salary by:
- Looking for **positive transactions** (income) in the last **3 days**
- Checking if the amount exceeds your configured `payday_threshold`
- Triggering the sweep once per detected payday

**Example thresholds:**
- `50000` = £500 (default)
- `100000` = £1000 (recommended for salary detection)
- `200000` = £2000 (for higher earners)

**Enhanced Configuration (Your Use Case):**
```json
{
  "trigger_type": "payday_detection",
  "payday_threshold": 100000,
  "target_pot_name": "Held",
  "sources": [
    {
      "pot_name": "Bills",
      "strategy": "remaining_balance",
      "min_balance": 50000,
      "priority": 1
    },
    {
      "pot_name": "Side",
      "strategy": "all_available", 
      "priority": 2
    }
  ]
}
```

**Legacy Configuration (Backward Compatible):**
```json
{
  "source_account_id": "acc_123",
  "target_pot_id": "pot_456",
  "amount": 100000,
  "trigger_type": "monthly",
  "trigger_day": 1,
  "min_balance": 50000
}
```

**Parameters:**
- `trigger_type`: Trigger type (see above)
- `payday_threshold`: Minimum amount for payday detection (in pence, e.g., 100000 = £1000)
- `target_pot_name`: The pot name to transfer money to (e.g., "Held", "Bills", "Side")
- `sources`: Array of source configurations
- `source.pot_name`: Source pot name (e.g., "Bills", "Side", "Emergency")
- `source.strategy`: Sweep strategy (see above)
- `source.amount`: For fixed_amount strategy
- `source.percentage`: For percentage strategy (0.0-1.0)
- `source.min_balance`: For remaining_balance strategy
- `source.priority`: Execution order (lower = higher priority)

### 💰 Autosorter Rules

Intelligent money distribution system that automatically distributes funds from a holding pot to other pots based on spending analysis, goals, and priorities.

**Use Cases:**
- Payday money management
- Automatic savings distribution
- Goal-based fund allocation
- Investment pot funding

**Configuration:**
```json
{
  "trigger_type": "payday_date",
  "holding_pot_id": "pot_123",
  "bills_pot_id": "pot_456",
  "priority_pots": [
    {
      "pot_id": "pot_789",
      "pot_name": "Emergency Fund",
      "amount": 50000,
      "allocation_type": "priority"
    }
  ],
  "goal_pots": [
    {
      "pot_id": "pot_101",
      "pot_name": "Holiday Fund",
      "percentage": 20,
      "allocation_type": "goal"
    }
  ],
  "investment_pots": [
    {
      "pot_id": "pot_202",
      "pot_name": "Investment",
      "percentage": 30,
      "allocation_type": "investment"
    }
  ]
}
```

**Parameters:**
- `trigger_type`: When to distribute (payday_date, time_of_day, transaction_based, etc.)
- `holding_pot_id`: Source pot containing funds to distribute
- `bills_pot_id`: Bills pot to replenish based on spending
- `priority_pots`: Fixed amounts for priority pots
- `goal_pots`: Percentage-based distribution to goal pots
- `investment_pots`: Remaining funds distributed to investment pots

### 💳 Auto Topup Rules

Automatically add money to pots when they fall below a threshold.

**Use Cases:**
- Maintaining minimum balances
- Regular savings contributions
- Emergency fund maintenance

**Configuration:**
```json
{
  "source_account_id": "acc_123",
  "target_pot_id": "pot_456",
  "amount": 50000,
  "trigger_type": "weekly",
  "trigger_day": 1,
  "min_balance": 10000
}
```

**Parameters:**
- Same as Pot Sweep rules, but triggered by pot balance thresholds

## 🎯 Practical Examples

### Example 1: Monthly Bills Management

**Goal:** Automatically fund your bills pot with £1200 on the 1st of each month.

**Setup:**
1. Create a "Bills" pot category in `/pots/manage`
2. Create a Pot Sweep rule:
   - Name: "Monthly Bills Funding"
   - Type: Pot Sweep
   - Amount: 120000 (pence)
   - Trigger: Monthly, Day 1
   - Min Balance: 50000

### Example 2: Payday Money Distribution

**Goal:** Automatically distribute your salary across different pots for bills, savings, and goals.

**Setup:**
1. Create a "Holding" pot to receive your salary
2. Create an Autosorter rule:
   - Name: "Payday Distribution"
   - Type: Autosorter
   - Trigger: Payday detection
   - Holding Pot: Your salary receiving pot
   - Bills Pot: Your bills pot
   - Priority Pots: Emergency fund (£500), Holiday fund (£200)
   - Goal Pots: House deposit (20% of remaining), Car fund (15% of remaining)
   - Investment Pots: Investment account (remaining funds)

### Example 3: Weekly Savings Topup

**Goal:** Add £250 to your savings pot every Monday.

**Setup:**
1. Create a "Savings" pot
2. Create an Auto Topup rule:
   - Name: "Weekly Savings"
   - Type: Auto Topup
   - Source: Main account
   - Target: Savings pot
   - Amount: £250
   - Trigger: Weekly, Day 1 (Monday)

## 🔍 Finding Your Account and Pot IDs

### Via API

```bash
# Get accounts
curl http://localhost:5000/api/accounts

# Get pots
curl http://localhost:5000/api/pots/categories
```

### Via Database

```python
from app.db import get_db_session
from app.models import Account, Pot

with next(get_db_session()) as db:
    accounts = db.query(Account).filter_by(is_active=True).all()
    pots = db.query(Pot).all()
    
    for acc in accounts:
        print(f"Account: {acc.description} (ID: {acc.id})")
    
    for pot in pots:
        print(f"Pot: {pot.name} (ID: {pot.id})")
```

## ⚙️ Automation Execution

### Automatic Execution

Automation rules run automatically after each successful sync:
1. New data is synced from Monzo
2. Automation integration triggers
3. Enabled rules are executed
4. Results are logged

### Manual Execution

You can manually trigger automation:
1. Visit `/automation/manage`
2. Click "Execute Automation"
3. View results in the console

### Execution Logs

Check execution logs:
```bash
# View application logs
tail -f logs/app.log | grep AUTOMATION
```

## 🛠️ Troubleshooting

### Common Issues

**"No accounts found"**
- Ensure you've synced your data
- Check that accounts are marked as active

**"No pots found"**
- Run a sync to pull pot data
- Verify pots exist in your Monzo account

**"Rule not executing"**
- Check if rule is enabled
- Verify account/pot IDs are correct
- Check execution logs for errors

**"Automation failed"**
- Verify Monzo API tokens are valid
- Check network connectivity
- Review error logs

### Debug Mode

Enable debug logging by setting the log level:

```python
import logging
logging.getLogger('app.automation').setLevel(logging.DEBUG)
```

## 📊 Monitoring and Management

### View Automation Status

Visit `/automation/manage` to see:
- Total rules and enabled count
- Last execution time
- Rule execution history

### API Endpoints

- `GET /api/automation/status` - Get automation status
- `GET /api/automation/rules` - List all rules
- `POST /api/automation/execute` - Manually execute automation
- `POST /api/automation/rules` - Create new rule
- `PUT /api/automation/rules/{id}` - Update rule
- `DELETE /api/automation/rules/{id}` - Delete rule

### Rule Management

- **Enable/Disable**: Toggle rules on/off without deleting
- **Edit**: Modify rule configuration
- **Delete**: Remove rules permanently
- **Duplicate**: Create similar rules with different parameters

## 🔒 Security Considerations

- Automation rules only execute after successful authentication
- Rules are user-specific and isolated
- Failed automation doesn't affect sync process
- All actions are logged for audit purposes

## 📈 Best Practices

1. **Start Small**: Begin with simple rules and gradually add complexity
2. **Test First**: Use small amounts when testing new rules
3. **Monitor Regularly**: Check automation status and logs
4. **Backup Rules**: Export rule configurations for backup
5. **Review Periodically**: Audit rules monthly to ensure they still meet your needs

## 🆘 Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review application logs
3. Verify your Monzo connection is active
4. Ensure you have sufficient funds for transfers
5. Check that pots are not deleted or renamed

---

**Happy Automating! 🤖✨** 