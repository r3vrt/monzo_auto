# Database Migrations

This directory contains Alembic database migrations for the Monzo app.

## Setup

The migration system is configured to work with our existing database setup:

- Uses environment variables from `.env` file
- Connects to PostgreSQL database
- Automatically detects our SQLAlchemy models

## Commands

### Create a new migration
```bash
alembic revision -m "Description of changes"
```

### Apply migrations
```bash
alembic upgrade head
```

### Check current migration state
```bash
alembic current
```

### Rollback migrations
```bash
alembic downgrade -1  # Rollback one migration
alembic downgrade base  # Rollback all migrations
```

### Generate migration from model changes
```bash
alembic revision --autogenerate -m "Description"
```

## Migration History

1. **7d15f4015bfd** - Add user_pot_categories table
   - Creates table for storing pot category assignments
   - Adds indexes for user_id and pot_id columns
   - Enables structured pot management instead of fuzzy matching

2. **3585abcf6cc3** - Remove deprecated sync_meta table
   - Drops the sync_meta table which is no longer needed
   - Sync status now uses latest transaction timestamp directly
   - Simplifies the data model and removes deprecated code

## Notes

- Always review auto-generated migrations before applying
- Test migrations on a copy of production data first
- Keep migrations small and focused on single changes 