#!/usr/bin/env python3
"""
Quick diagnostic script to check traceroute plugin status
"""
import sqlite3
from datetime import datetime

# Connect to database
conn = sqlite3.connect('data/zephyrgate_dev.db')
cursor = conn.cursor()

print("=" * 80)
print("TRACEROUTE STATUS DIAGNOSTIC")
print("=" * 80)
print(f"Current time: {datetime.utcnow()}")
print()

# Check nodes with hop_count >= 1
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN next_traceroute_time IS NULL THEN 1 ELSE 0 END) as null_schedule,
           SUM(CASE WHEN next_traceroute_time <= datetime('now') THEN 1 ELSE 0 END) as overdue,
           SUM(CASE WHEN next_traceroute_time > datetime('now') THEN 1 ELSE 0 END) as scheduled
    FROM users 
    WHERE hop_count >= 1
""")
row = cursor.fetchone()
print(f"Indirect Nodes (hop_count >= 1):")
print(f"  Total: {row[0]}")
print(f"  NULL schedule: {row[1]}")
print(f"  Overdue: {row[2]}")
print(f"  Scheduled (future): {row[3]}")
print()

# Show some overdue nodes
print("Sample of overdue nodes:")
cursor.execute("""
    SELECT node_id, short_name, hop_count, next_traceroute_time, last_traceroute_time
    FROM users
    WHERE hop_count >= 1 AND next_traceroute_time <= datetime('now')
    ORDER BY next_traceroute_time
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"  {row[0]} ({row[1]}): hop={row[2]}, next={row[3]}, last={row[4]}")
print()

# Check traceroute hop counts
cursor.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN traceroute_hop_count IS NULL THEN 1 ELSE 0 END) as never_attempted,
           SUM(CASE WHEN traceroute_hop_count = 0 THEN 1 ELSE 0 END) as failed,
           SUM(CASE WHEN traceroute_hop_count > 0 THEN 1 ELSE 0 END) as successful
    FROM users
    WHERE hop_count >= 1
""")
row = cursor.fetchone()
print(f"Traceroute Results:")
print(f"  Total indirect nodes: {row[0]}")
print(f"  Never attempted: {row[1]}")
print(f"  Failed (hop=0): {row[2]}")
print(f"  Successful (hop>0): {row[3]}")
print()

conn.close()

print("=" * 80)
print("RECOMMENDATION:")
print("If you see many overdue nodes, the periodic recheck may not be running.")
print("Check if the application is running and check logs for errors.")
print("=" * 80)
