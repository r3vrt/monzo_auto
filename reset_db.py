#!/usr/bin/env python3
"""
Database Reset Script for Monzo App

This script clears all data from the database while preserving the table structure.
Useful for testing and when you need to start fresh.

Usage:
    python reset_db.py
"""

import os
import sys
from sqlalchemy import text
from app.db import engine, get_db_session
from app.models import (
    User, Account, Pot, Transaction, BillsPotTransaction, 
    UserPotCategory, AutomationRule
)

def reset_database():
    """Reset the database by clearing all data while preserving table structure."""
    
    print("🔄 Starting database reset...")
    
    try:
        # Get database session
        with next(get_db_session()) as db:
            
            # Clear all data from tables in reverse dependency order
            print("🗑️  Clearing automation rules...")
            db.execute(text("DELETE FROM automation_rules"))
            
            print("🗑️  Clearing bills pot transactions...")
            db.execute(text("DELETE FROM bills_pot_transactions"))
            
            print("🗑️  Clearing transactions...")
            db.execute(text("DELETE FROM transactions"))
            
            print("🗑️  Clearing user pot categories...")
            db.execute(text("DELETE FROM user_pot_categories"))
            
            print("🗑️  Clearing pots...")
            db.execute(text("DELETE FROM pots"))
            
            print("🗑️  Clearing accounts...")
            db.execute(text("DELETE FROM accounts"))
            
            print("🗑️  Clearing users...")
            db.execute(text("DELETE FROM users"))
            
            # Reset auto-increment sequences
            print("🔄 Resetting auto-increment sequences...")
            db.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
            db.execute(text("ALTER SEQUENCE automation_rules_id_seq RESTART WITH 1"))
            db.execute(text("ALTER SEQUENCE user_pot_categories_id_seq RESTART WITH 1"))
            
            # Commit all changes
            db.commit()
            
            print("✅ Database reset completed successfully!")
            print("📊 Database is now empty and ready for fresh data.")
            
    except Exception as e:
        print(f"❌ Error during database reset: {e}")
        sys.exit(1)

def verify_reset():
    """Verify that the database has been reset by checking table counts."""
    
    print("\n🔍 Verifying database reset...")
    
    try:
        with next(get_db_session()) as db:
            
            # Check counts for each table
            tables = [
                ('users', User),
                ('accounts', Account), 
                ('pots', Pot),
                ('transactions', Transaction),
                ('bills_pot_transactions', BillsPotTransaction),
                ('user_pot_categories', UserPotCategory),
                ('automation_rules', AutomationRule)
            ]
            
            for table_name, model in tables:
                count = db.query(model).count()
                status = "✅" if count == 0 else "❌"
                print(f"{status} {table_name}: {count} records")
                
            print("\n🎉 Database reset verification complete!")
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")
        sys.exit(1)

def main():
    """Main function to run the database reset."""
    
    print("=" * 50)
    print("🗄️  Monzo App Database Reset Tool")
    print("=" * 50)
    print()
    print("⚠️  WARNING: This will delete ALL data from the database!")
    print("   This action cannot be undone.")
    print()
    
    # Ask for confirmation
    response = input("Are you sure you want to continue? (yes/no): ").lower().strip()
    
    if response not in ['yes', 'y']:
        print("❌ Database reset cancelled.")
        sys.exit(0)
    
    print()
    
    # Perform the reset
    reset_database()
    
    # Verify the reset
    verify_reset()
    
    print("\n" + "=" * 50)
    print("🎯 Next steps:")
    print("1. Restart your Flask app: python run.py")
    print("2. Go to http://monzoapp:5000/monzo_auth")
    print("3. Enter your Monzo API credentials")
    print("4. Complete the OAuth flow")
    print("5. The app will perform a fresh sync")
    print("=" * 50)

if __name__ == "__main__":
    main() 