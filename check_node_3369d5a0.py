#!/usr/bin/env python3
"""Check the database state for node !3369d5a0"""

import sqlite3
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from core.database import initialize_database, get_database

def main():
    # Initialize database
    import asyncio
    asyncio.run(initialize_database({'database': {'path': 'data/zephyrgate_dev.db'}}))
    
    db = get_database()
    
    node_id = "!3369d5a0"
    
    print(f"\n=== Database state for {node_id} ===\n")
    
    rows = db.execute_query("""
        SELECT 
            node_id,
            short_name,
            hop_count,
            traceroute_hop_count,
            last_traceroute_time,
            last_traceroute_success,
            next_traceroute_time,
            traceroute_failure_count
        FROM users
        WHERE node_id = ?
    """, (node_id,))
    
    if not rows:
        print(f"Node {node_id} not found in database")
        return
    
    row = rows[0]
    print(f"Node ID: {row[0]}")
    print(f"Short Name: {row[1]}")
    print(f"hop_count: {row[2]}")
    print(f"traceroute_hop_count: {row[3]}")
    print(f"last_traceroute_time: {row[4]}")
    print(f"last_traceroute_success: {row[5]}")
    print(f"next_traceroute_time: {row[6]}")
    print(f"traceroute_failure_count: {row[7]}")
    print()
    
    # Check if it would appear in upcoming traceroutes
    if row[2] is not None and row[2] >= 1:
        print("✅ Would appear in UPCOMING traceroutes (hop_count >= 1)")
    else:
        print("❌ Would NOT appear in upcoming traceroutes (hop_count < 1 or NULL)")
    
    # Check if it would appear in recent traceroutes
    if row[4] is not None:
        print("✅ Would appear in RECENT traceroutes (last_traceroute_time IS NOT NULL)")
    else:
        print("❌ Would NOT appear in recent traceroutes (last_traceroute_time IS NULL)")
    print()

if __name__ == "__main__":
    main()
