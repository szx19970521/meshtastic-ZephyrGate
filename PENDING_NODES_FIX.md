# Fix for "Pending and Not Scheduled" Nodes

## Problem
All nodes in the upcoming traceroutes list show as "Pending" with "Not Scheduled" even though they have `next_traceroute_time` set in the database.

## Root Cause
The periodic recheck loop (`_periodic_recheck_loop`) runs every 60 seconds and should queue nodes that are overdue, but it's not working properly. This could be due to:

1. The traceroute plugin not starting properly
2. The periodic recheck loop crashing silently
3. Logging not working so we can't see errors

## Immediate Fix (Applied)
Updated all overdue nodes to have `next_traceroute_time = NOW`:
```sql
UPDATE users SET next_traceroute_time = datetime('now') 
WHERE hop_count >= 1 AND next_traceroute_time < datetime('now', '-1 minute');
```

This should cause the periodic recheck to queue them within 60 seconds.

## Diagnostic Status
Current state (as of 2026-03-03 02:14):
- Total indirect nodes: 29
- Nodes with NULL schedule: 0
- Overdue nodes: 26 (just updated to NOW)
- Scheduled (future): 3
- Never attempted traceroute: 19
- Failed traceroutes: 10
- Successful traceroutes: 0

## Recommended Actions

### 1. Restart the Application
The application is running (PID 43240) but the traceroute plugin may not be working properly.

```bash
# Kill the current process
kill 43240

# Start fresh
python src/main.py
```

### 2. Monitor the Logs
Watch for these key messages:
```bash
tail -f logs/zephyrgate_dev.log | grep -i "traceroute\|recheck\|queue"
```

You should see:
- "Periodic recheck loop started" - confirms loop is running
- "Periodic check: found X pending nodes, queued Y" - confirms nodes are being queued
- "Sending traceroute to !XXXXXXXX" - confirms traceroutes are being sent

### 3. Check the Dashboard
After restart, within 60-120 seconds you should see:
- Nodes change from "Pending" to "Queued" or "Scheduled"
- The "Time Until" column should show actual times instead of "Not Scheduled"

### 4. Use the Diagnostic Script
Run this to check status:
```bash
python check_traceroute_status.py
```

## Why This Keeps Happening

The periodic recheck should automatically queue overdue nodes every 60 seconds. If nodes are stuck as "Pending", it means:

1. **The periodic recheck loop is not running** - Check logs for "Periodic recheck loop started"
2. **The loop is crashing** - Check logs for errors
3. **Nodes are being filtered out** - Check if `skip_direct_nodes` is filtering them
4. **The queue is full** - Check queue size (max 500)

## Long-Term Solution

The traceroute scheduling should be simple and database-driven:

1. **Database is the single source of truth** - No JSON files
2. **Trigger sets initial schedule** - When hop_count changes to >=1, set next_traceroute_time = NOW
3. **Periodic recheck queues overdue nodes** - Every 60 seconds, query for nodes where next_traceroute_time <= NOW
4. **After traceroute completes** - Set next_traceroute_time based on success (180 min) or failure (30 min)

This is already implemented, but something is preventing it from working.

## Debug Steps

If nodes are still stuck as "Pending" after restart:

1. Check if plugin is enabled:
```bash
grep -A 2 "traceroute_mapper:" config/config.yaml
```

2. Check if periodic recheck is enabled:
```bash
grep "recheck_enabled" config/config.yaml
```

3. Check database for overdue nodes:
```bash
sqlite3 data/zephyrgate_dev.db "SELECT COUNT(*) FROM users WHERE hop_count >= 1 AND next_traceroute_time <= datetime('now');"
```

4. Check if nodes are in queue (requires Python):
```python
# This would need to be run from within the application
# traceroute_plugin.priority_queue.size()
```

## Expected Behavior After Fix

1. Application starts
2. Within 60 seconds, periodic recheck runs
3. Finds 26 overdue nodes
4. Queues them all (or as many as fit in queue)
5. Processes queue at rate of 1 traceroute every 120 seconds
6. Dashboard shows nodes as "Queued" then "Scheduled"
7. After traceroute completes, next_traceroute_time is set to 30 min (failure) or 180 min (success)

## Files Involved

- `plugins/traceroute_mapper/plugin.py` - Main plugin with periodic recheck loop
- `config/config.yaml` - Configuration (recheck_enabled, seconds_between_traceroutes, etc.)
- `data/zephyrgate_dev.db` - Database with users table
- `plugins/web_service/web/web_admin_service.py` - API that returns upcoming traceroutes
- `plugins/web_service/web/static/js/dashboard.js` - Dashboard display

## Next Steps

1. **Restart the application** to ensure the periodic recheck loop starts fresh
2. **Wait 60-120 seconds** for the periodic recheck to run
3. **Refresh the dashboard** to see if nodes are now queued/scheduled
4. **Check logs** for any errors or warnings
5. **Run diagnostic script** to verify database state

If nodes are still stuck as "Pending" after these steps, there's a deeper issue with the periodic recheck loop that needs investigation.
