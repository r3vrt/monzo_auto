#!/usr/bin/env python3
"""
Database Reset Script for Monzo App

This script clears all data from the database while preserving the table structure.
Useful for testing and when you need to start fresh.

Usage:
    python reset_db.py                    # Normal reset with reauthentication prompt
    python reset_db.py --keep-auth        # Reset but keep existing authentication
    python reset_db.py --skip-auth        # Reset and skip reauthentication entirely
"""

import os
import sys
import argparse
from sqlalchemy import text
from app.db import engine, get_db_session
from app.models import (
    User, Account, Pot, Transaction, BillsPotTransaction, 
    UserPotCategory
)
from app.automation.rules import AutomationRule

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

def check_existing_auth():
    """Check if there are existing authentication credentials in the database."""
    
    try:
        with next(get_db_session()) as db:
            # Check if there are any users with authentication tokens
            users_with_auth = db.query(User).filter(
                User.monzo_access_token.isnot(None),
                User.monzo_access_token != ''
            ).all()
            
            if users_with_auth:
                print(f"🔑 Found {len(users_with_auth)} user(s) with existing authentication:")
                for user in users_with_auth:
                    print(f"   - User ID: {user.monzo_user_id}")
                    print(f"     Access Token: {'*' * 20}...{user.monzo_access_token[-4:] if user.monzo_access_token else 'None'}")
                    print(f"     Token Expires: {user.monzo_token_expires_in} seconds from obtain time")
                    print(f"     Token Obtained: {user.monzo_token_obtained_at}")
                return True
            else:
                print("🔑 No existing authentication found in database.")
                return False
                
    except Exception as e:
        print(f"❌ Error checking authentication: {e}")
        return False

def reset_database_preserve_auth():
    """Reset the database by clearing all data while preserving authentication credentials."""
    
    print("🔄 Starting database reset (preserving authentication)...")
    
    try:
        # Get database session
        with next(get_db_session()) as db:
            
            # Store existing authentication data
            existing_users = db.query(User).all()
            auth_data = []
            for user in existing_users:
                if user.monzo_access_token:
                    auth_data.append({
                        'monzo_user_id': user.monzo_user_id,
                        'monzo_access_token': user.monzo_access_token,
                        'monzo_refresh_token': user.monzo_refresh_token,
                        'monzo_token_type': user.monzo_token_type,
                        'monzo_token_expires_in': user.monzo_token_expires_in,
                        'monzo_client_id': user.monzo_client_id,
                        'monzo_token_obtained_at': user.monzo_token_obtained_at,
                        'monzo_client_secret': user.monzo_client_secret,
                        'monzo_redirect_uri': user.monzo_redirect_uri,
                        'created_at': user.created_at
                    })
            
            print(f"🔑 Preserving authentication for {len(auth_data)} user(s)...")
            
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
            
            # Restore authentication data
            print("🔑 Restoring authentication credentials...")
            for auth in auth_data:
                new_user = User(
                    monzo_user_id=auth['monzo_user_id'],
                    monzo_access_token=auth['monzo_access_token'],
                    monzo_refresh_token=auth['monzo_refresh_token'],
                    monzo_token_type=auth['monzo_token_type'],
                    monzo_token_expires_in=auth['monzo_token_expires_in'],
                    monzo_client_id=auth['monzo_client_id'],
                    monzo_token_obtained_at=auth['monzo_token_obtained_at'],
                    monzo_client_secret=auth['monzo_client_secret'],
                    monzo_redirect_uri=auth['monzo_redirect_uri'],
                    created_at=auth['created_at']
                )
                db.add(new_user)
            
            # Commit all changes
            db.commit()
            
            print("✅ Database reset completed successfully!")
            print("📊 Database is now empty but authentication is preserved.")
            
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
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monzo App Database Reset Tool')
    parser.add_argument('--keep-auth', action='store_true', 
                       help='Reset database but preserve existing authentication')
    parser.add_argument('--skip-auth', action='store_true',
                       help='Reset database and skip reauthentication entirely')
    args = parser.parse_args()
    
    print("=" * 50)
    print("🗄️  Monzo App Database Reset Tool")
    print("=" * 50)
    print()
    
    # Check for existing authentication if not skipping
    if not args.skip_auth:
        has_auth = check_existing_auth()
        print()
    
    print("⚠️  WARNING: This will delete ALL data from the database!")
    if args.keep_auth:
        print("   Authentication credentials will be preserved.")
    elif args.skip_auth:
        print("   Reauthentication will be skipped.")
    else:
        print("   This action cannot be undone.")
    print()
    
    # Ask for confirmation
    response = input("Are you sure you want to continue? (yes/no): ").lower().strip()
    
    if response not in ['yes', 'y']:
        print("❌ Database reset cancelled.")
        sys.exit(0)
    
    print()
    
    # Perform the reset
    if args.keep_auth:
        print("🔄 Performing reset while preserving authentication...")
        reset_database_preserve_auth()
    else:
        print("🔄 Performing full database reset...")
        reset_database()
    
    # Verify the reset
    verify_reset()
    
    print("\n" + "=" * 50)
    print("🎯 Next steps:")
    print("1. Restart your Flask app: python run.py")
    
    if args.skip_auth:
        print("2. Authentication skipped - app will run without Monzo access")
        print("3. To add authentication later, go to http://monzoapp:5000/monzo_auth")
    elif args.keep_auth:
        print("2. Authentication preserved - app will use existing credentials")
        print("3. The app will perform a fresh sync with existing auth")
    else:
        print("2. Go to http://monzoapp:5000/monzo_auth")
        print("3. Enter your Monzo API credentials")
        print("4. Complete the OAuth flow")
        print("5. The app will perform a fresh sync")
    
    print("=" * 50)

if __name__ == "__main__":
    main() 