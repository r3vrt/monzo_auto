# API Documentation

## Pot Category Management

The pot category management API allows users to organize their Monzo pots into structured categories for better automation and analysis.

### Base URL
All endpoints are prefixed with `/api`

### Authentication
All endpoints require user authentication. If no user is found in the session, the API will attempt to use the most recent user from the database.

---

## Get All Pot Categories

**GET** `/api/pots/categories`

Returns all pot categories and their associated pots for the authenticated user.

### Response
```json
{
  "categories": {
    "bills": [
      {
        "id": "pot_123",
        "name": "Bills Pot",
        "balance": 150000,
        "currency": "GBP",
        "style": "beach_ball"
      }
    ],
    "savings": [
      {
        "id": "pot_456",
        "name": "Emergency Fund",
        "balance": 500000,
        "currency": "GBP",
        "style": "rainbow"
      }
    ]
  },
  "uncategorized": [
    {
      "id": "pot_789",
      "name": "Uncategorized Pot",
      "balance": 25000,
      "currency": "GBP",
      "style": "default"
    }
  ],
  "available_categories": [
    "bills",
    "savings", 
    "holding",
    "spending",
    "emergency",
    "investment",
    "custom"
  ]
}
```

---

## Assign Pot to Category

**POST** `/api/pots/categories`

Assigns a pot to a specific category.

### Request Body
```json
{
  "pot_id": "pot_123",
  "category": "bills"
}
```

### Response
```json
{
  "success": true,
  "message": "Pot 'Bills Pot' assigned to category 'bills'"
}
```

### Error Responses
- `400` - Missing pot_id or category
- `400` - Invalid category
- `404` - Pot not found or doesn't belong to user

---

## Remove Pot from Category

**DELETE** `/api/pots/categories`

Removes a pot from a specific category.

### Request Body
```json
{
  "pot_id": "pot_123",
  "category": "bills"
}
```

### Response
```json
{
  "success": true,
  "message": "Pot 'Bills Pot' removed from category 'bills'"
}
```

### Error Responses
- `400` - Missing pot_id or category
- `404` - Pot not found in this category

---

## Get Pots by Category

**GET** `/api/pots/categories/{category}`

Returns all pots in a specific category.

### Path Parameters
- `category` - The category name (e.g., "bills", "savings")

### Response
```json
{
  "category": "bills",
  "pots": [
    {
      "id": "pot_123",
      "name": "Bills Pot",
      "balance": 150000,
      "currency": "GBP",
      "style": "beach_ball",
      "created": "2024-01-01T00:00:00Z",
      "updated": "2024-01-15T12:00:00Z"
    }
  ],
  "total_balance": 150000
}
```

### Error Responses
- `400` - Invalid category

---

## Get Pot Balances

**GET** `/api/pots/balances`

Returns pot balances aggregated by category with summary totals.

### Response
```json
{
  "category_balances": {
    "bills": {
      "pots": [
        {
          "id": "pot_123",
          "name": "Bills Pot",
          "balance": 150000,
          "currency": "GBP"
        }
      ],
      "total_balance": 150000
    },
    "savings": {
      "pots": [
        {
          "id": "pot_456",
          "name": "Emergency Fund",
          "balance": 500000,
          "currency": "GBP"
        }
      ],
      "total_balance": 500000
    }
  },
  "uncategorized": {
    "pots": [
      {
        "id": "pot_789",
        "name": "Uncategorized Pot",
        "balance": 25000,
        "currency": "GBP"
      }
    ],
    "total_balance": 25000
  },
  "summary": {
    "total_categorized": 650000,
    "total_uncategorized": 25000,
    "total_all": 675000
  }
}
```

---

## Available Categories

The following categories are available for pot assignment:

- `bills` - For bill payments and regular expenses
- `savings` - For long-term savings goals
- `holding` - For temporary fund holding
- `spending` - For discretionary spending
- `emergency` - For emergency funds
- `investment` - For investment pots
- `custom` - For custom categories

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (missing parameters, invalid data)
- `404` - Not Found (resource doesn't exist)
- `500` - Internal Server Error

Error responses include a JSON object with an `error` field:

```json
{
  "error": "Description of the error"
}
```

---

# Automation Management

The automation management API allows users to create, manage, and execute automation rules for their Monzo accounts.

## Get Automation Status

**GET** `/api/automation/status`

Returns the current automation status for the authenticated user.

### Response
```json
{
  "total_rules": 5,
  "enabled_rules": 3,
  "rule_counts": {
    "pot_sweep": {"total": 2, "enabled": 1},
    "autosorter": {"total": 2, "enabled": 1},
    "auto_topup": {"total": 1, "enabled": 1}
  },
  "last_execution": "2024-01-15T10:30:00Z"
}
```

---

## Execute Automation

**POST** `/api/automation/execute`

Manually trigger automation execution for a specific account.

### Request Body
```json
{
  "account_id": "acc_123"
}
```

### Response
```json
{
  "success": true,
  "message": "Automation executed successfully",
  "results": {
    "pot_sweeps": {"executed": 1, "success": 1, "errors": []},
    "autosorter": {"executed": 2, "success": 2, "errors": []},
    "auto_topup": {"executed": 0, "success": 0, "errors": []},
    "bills_pot_logic": {"executed": 1, "success": 1, "errors": []}
  }
}
```

---

## Get Automation Rules

**GET** `/api/automation/rules`

Returns all automation rules for the authenticated user.

### Response
```json
{
  "rules": [
    {
      "id": "rule_123",
      "name": "Monthly Bills Sweep",
      "rule_type": "pot_sweep",
      "enabled": true,
      "config": {
        "source_account_id": "acc_123",
        "target_pot_id": "pot_456",
        "amount": 100000,
        "trigger_type": "monthly",
        "trigger_day": 1
      },
      "last_executed": "2024-01-01T00:00:00Z",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

## Create Automation Rule

**POST** `/api/automation/rules`

Create a new automation rule.

### Request Body
```json
{
  "name": "Monthly Bills Sweep",
  "rule_type": "pot_sweep",
  "config": {
    "source_account_id": "acc_123",
    "target_pot_id": "pot_456",
    "amount": 100000,
    "trigger_type": "monthly",
    "trigger_day": 1
  },
  "enabled": true
}
```

### Response
```json
{
  "success": true,
  "message": "Automation rule created successfully",
  "rule_id": "rule_123"
}
```

---

## Update Automation Rule

**PUT** `/api/automation/rules/{rule_id}`

Update an existing automation rule.

### Request Body
```json
{
  "name": "Updated Rule Name",
  "config": {
    "amount": 150000
  }
}
```

### Response
```json
{
  "success": true,
  "message": "Automation rule updated successfully"
}
```

---

## Delete Automation Rule

**DELETE** `/api/automation/rules/{rule_id}`

Delete an automation rule.

### Response
```json
{
  "success": true,
  "message": "Automation rule deleted successfully"
}
```

---

## Toggle Automation Rule

**POST** `/api/automation/rules/{rule_id}/toggle`

Toggle the enabled state of an automation rule.

### Response
```json
{
  "success": true,
  "message": "Automation rule toggled successfully",
  "enabled": false
}
```

---

## Automation Rule Types

### Pot Sweep Rules
- **rule_type**: `"pot_sweep"`
- **config**: Contains source account, target pot, amount, and trigger settings

### Autosorter Rules
- **rule_type**: `"autosorter"`
- **config**: Contains intelligent money distribution settings including holding pot, bills pot, and allocation rules

### Auto Topup Rules
- **rule_type**: `"auto_topup"`
- **config**: Contains source account, target pot, amount, and trigger settings