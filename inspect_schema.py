# inspect_schema.py
# Run: python3 inspect_schema.py

import sqlite3

DB_PATH = 'data/funds.db'

def inspect_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all tables
    tables = cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
    """).fetchall()
    
    print("=" * 80)
    print("DATABASE SCHEMA INSPECTION")
    print("=" * 80)
    
    for (table_name,) in tables:
        print(f"\n{'─' * 80}")
        print(f"TABLE: {table_name}")
        print(f"{'─' * 80}")
        
        # Get CREATE TABLE statement
        create_stmt = cursor.execute(f"""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (table_name,)).fetchone()
        
        if create_stmt:
            print(create_stmt[0])
        
        # Get column details
        columns = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        print(f"\n  Columns ({len(columns)}):")
        for col in columns:
            print(f"    {col[1]:30s} {col[2]:15s} {'NOT NULL' if col[3] else 'NULL':10s} DEFAULT: {col[4]}")
        
        # Get row count
        row_count = cursor.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        print(f"\n  Row count: {row_count:,}")
        
        # Sample data (first 2 rows)
        sample = cursor.execute(f"SELECT * FROM {table_name} LIMIT 2").fetchall()
        if sample:
            print(f"\n  Sample data:")
            col_names = [c[1] for c in columns]
            for row in sample:
                print("    ", dict(zip(col_names, row)))
    
    conn.close()

if __name__ == '__main__':
    inspect_schema()