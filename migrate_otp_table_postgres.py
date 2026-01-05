#!/usr/bin/env python3
"""
Script to add session_id column to otp_codes table in PostgreSQL
Run this on your production database
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect

# Add the app directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def migrate_otp_table():
    """
    Add session_id column to otp_codes table if it doesn't exist
    """
    try:
        print("Connecting to database...")
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            
            try:
                print("Checking otp_codes table structure...")
                
                # Check if session_id column exists
                inspector = inspect(engine)
                columns = [col['name'] for col in inspector.get_columns('otp_codes')]
                
                print(f"Existing columns: {', '.join(columns)}")
                
                if 'session_id' not in columns:
                    print("Adding session_id column to otp_codes table...")
                    # Add session_id column (nullable, for backward compatibility)
                    conn.execute(text("""
                        ALTER TABLE otp_codes 
                        ADD COLUMN IF NOT EXISTS session_id VARCHAR(200)
                    """))
                    print("[OK] session_id column added successfully")
                else:
                    print("[OK] session_id column already exists")
                
                # Also ensure otp column is nullable (in case it's not)
                print("Ensuring otp column is nullable...")
                try:
                    conn.execute(text("""
                        ALTER TABLE otp_codes 
                        ALTER COLUMN otp DROP NOT NULL
                    """))
                    print("[OK] otp column is now nullable")
                except Exception as e:
                    # Column might already be nullable or error for other reason
                    print(f"[INFO] otp column nullable check: {str(e)}")
                
                # Commit transaction
                trans.commit()
                print("\n[SUCCESS] Migration completed successfully!")
                
                # Verify the changes
                print("\nVerifying table structure...")
                columns_after = [col['name'] for col in inspector.get_columns('otp_codes')]
                print(f"Columns after migration: {', '.join(columns_after)}")
                
            except Exception as e:
                # Rollback on error
                trans.rollback()
                print(f"\n[ERROR] {e}")
                raise
                
    except Exception as e:
        print(f"\n[ERROR] Failed to migrate otp_codes table: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    print("Migrating otp_codes table (PostgreSQL)...")
    print("=" * 50)
    migrate_otp_table()
    print("=" * 50)
    print("[SUCCESS] Done!")

