#!/bin/bash
# Diagnose what's causing the freeze

echo "=== Finding ZephyrGate process ==="
PID=$(ps aux | grep "python.*main.py" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "No ZephyrGate process found"
    exit 1
fi

echo "Found PID: $PID"
echo ""

echo "=== Thread dump (what each thread is doing) ==="
# Send SIGQUIT to get a thread dump (Python will print stack traces)
kill -QUIT $PID 2>/dev/null || echo "Could not send SIGQUIT"

echo ""
echo "=== Process info ==="
ps -p $PID -o pid,ppid,state,time,command

echo ""
echo "=== Open files/sockets ==="
lsof -p $PID 2>/dev/null | head -20

echo ""
echo "=== Last 30 log lines ==="
tail -30 logs/zephyrgate.log 2>/dev/null || echo "No log file found"

echo ""
echo "=== To kill the process, run: ==="
echo "kill -9 $PID"
