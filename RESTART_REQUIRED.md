# Application Restart Required

## Summary

The traceroute_mapper plugin has been updated to version 1.2.0 with native meshtastic library support, but the application needs to be restarted for the changes to take effect.

## Current Status

- ✅ Plugin code updated with native `sendTraceRoute()` method
- ✅ Plugin version updated to 1.2.0
- ✅ Plugin is in the `enabled_plugins` list in config.yaml
- ✅ Plugin is being discovered by the plugin manager
- ❌ Application is running with old code (needs restart)

## What to Do

1. **Stop the current ZephyrGate process:**
   ```bash
   # Find the process
   ps aux | grep "python.*main.py" | grep -v grep
   
   # Kill it (use the PID from above)
   kill <PID>
   
   # Or use Ctrl+C if running in terminal
   ```

2. **Start ZephyrGate again:**
   ```bash
   python3 src/main.py
   ```

3. **Verify the plugin loaded:**
   - Check logs for "Network Traceroute Mapper plugin initialized"
   - Check logs for "Subscribed to meshtastic.receive.traceroute pubsub topic"
   - Check the web dashboard for traceroute data

## Expected Log Messages

After restart, you should see:
```
INFO - Initializing Network Traceroute Mapper plugin
INFO - Configuration validated successfully
INFO - Initializing NodeStateTracker...
INFO - Initializing PriorityQueue...
INFO - Initializing RateLimiter...
INFO - Initializing TracerouteManager...
INFO - Network Traceroute Mapper plugin initialized successfully
INFO - Starting Network Traceroute Mapper plugin
INFO - Subscribed to meshtastic.receive.traceroute pubsub topic
INFO - Started queue processing loop
INFO - Network Traceroute Mapper plugin started successfully
```

## Troubleshooting

If the plugin still doesn't load:

1. **Check if plugin is enabled in config:**
   ```bash
   grep -A5 "enabled_plugins:" config/config.yaml
   ```
   Should include `- traceroute_mapper`

2. **Check plugin configuration:**
   ```bash
   grep -A5 "traceroute_mapper:" config/config.yaml
   ```
   Should have `enabled: true`

3. **Check for errors in logs:**
   ```bash
   tail -100 logs/zephyrgate.log | grep -i "traceroute\|error"
   ```

4. **Verify meshtastic interface is connected:**
   The plugin needs a working meshtastic interface to send traceroutes.
   Check logs for interface connection status.

## Session Validation Issue

The "Session validation failed" warnings are a separate issue related to web authentication. This happens when:
- Session cookies expire
- Application restarts (sessions are in-memory)
- Browser cache has old session tokens

**To fix:** Simply log out and log back in to the web dashboard.
