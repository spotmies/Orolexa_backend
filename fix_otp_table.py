#!/usr/bin/env python3
"""
Script to fix the otp_codes table schema
Drops and recreates the table with the correct schema
"""
import os
import sys
from sqlalchemy import create_engine, text, inspect

# Add the app directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def fix_otp_table():
    """
    Drop and recreate the otp_codes table with the correct schema
    """
    try:
        print("Connecting to database...")
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
        )
        
        with engine.connect() as conn:
            try:
                print("Checking otp_codes table...")
                
                # Check if table exists
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                
                if 'otp_codes' in tables:
                    print("Dropping existing otp_codes table...")
                    # Drop the old table
                    conn.execute(text("DROP TABLE IF EXISTS otp_codes"))
                    conn.commit()
                    print("[OK] Table dropped successfully")
                else:
                    print("Table otp_codes does not exist, will create new one")
                
                # Start new transaction for creating table
                trans = conn.begin()
                
                try:
                    # Create the new table with correct schema
                    print("Creating new otp_codes table with correct schema...")
                    create_table_sql = """
                    CREATE TABLE IF NOT EXISTS otp_codes (
                        id TEXT NOT NULL PRIMARY KEY,
                        phone TEXT NOT NULL,
                        otp TEXT,
                        flow TEXT NOT NULL,
                        session_id TEXT,
                        is_used BOOLEAN NOT NULL DEFAULT 0,
                        expires_at DATETIME NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                    conn.execute(text(create_table_sql))
                    
                    # Create index on phone for faster lookups
                    print("Creating index on phone column...")
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_otp_codes_phone ON otp_codes(phone)"))
                    
                    # Commit transaction
                    trans.commit()
                    print("\n[SUCCESS] otp_codes table created successfully with correct schema!")
                    print("\nSchema:")
                    print("  - id: TEXT PRIMARY KEY")
                    print("  - phone: TEXT (indexed)")
                    print("  - otp: TEXT (nullable)")
                    print("  - flow: TEXT")
                    print("  - session_id: TEXT (nullable, for backward compatibility)")
                    print("  - is_used: BOOLEAN")
                    print("  - expires_at: DATETIME")
                    print("  - created_at: DATETIME")
                    
                except Exception as e:
                    # Rollback on error
                    trans.rollback()
                    print(f"\n[ERROR] {e}")
                    raise
                    
            except Exception as e:
                print(f"\n[ERROR] {e}")
                raise
                
    except Exception as e:
        print(f"\n[ERROR] Failed to fix otp_codes table: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Fixing otp_codes table schema...")
    print("=" * 50)
    fix_otp_table()
    print("=" * 50)
    print("[SUCCESS] Done!")

