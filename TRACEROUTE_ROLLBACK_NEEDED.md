# Traceroute Plugin Rollback Required

## Issue

The traceroute_mapper plugin changes caused application instability:
- Web interface freezing
- Application not responding to Ctrl+C
- General instability after implementing native meshtastic traceroute method

## Immediate Action Taken

1. ✅ Force-killed the application process
2. ✅ Disabled traceroute_mapper plugin in config.yaml
3. ✅ Added to disabled_plugins list

## What Changed (Causing Issues)

The following changes were made to implement native meshtastic traceroute:

### Modified Files:
1. **plugins/traceroute_mapper/traceroute_manager.py**
   - Changed `send_traceroute()` to use native meshtastic `sendTraceRoute()` method
   - Removed `get_pending_traceroute_message()` method
   - Added `meshtastic_interface` parameter

2. **plugins/traceroute_mapper/plugin.py**
   - Modified `_send_traceroute_request()` to get meshtastic interface from message router
   - Added pubsub subscription in `start()` method
   - Added `_on_traceroute_response()` pubsub callback handler
   - Modified `stop()` to unsubscribe from pubsub

3. **plugins/traceroute_mapper/manifest.yaml**
   - Updated version from 1.0.0 to 1.2.0

## Potential Issues

1. **Pubsub Import**: The plugin tries to import `from pubsub import pub` which may not be available or may conflict
2. **Interface Access**: Getting the meshtastic interface from `plugin_manager.message_router.interfaces` may fail
3. **Async Handling**: The pubsub callback creates async tasks which may cause deadlocks
4. **Missing Error Handling**: Not enough error handling for missing interfaces

## Recommended Next Steps

### Option 1: Revert to Working Version (Recommended)
```bash
git diff plugins/traceroute_mapper/ > traceroute_changes.patch
git checkout HEAD -- plugins/traceroute_mapper/
```

### Option 2: Fix the Issues
1. Add proper error handling for missing pubsub library
2. Add fallback if meshtastic interface not available
3. Test in isolation before enabling
4. Add timeout protection for pubsub callbacks

### Option 3: Keep Disabled
- Leave the plugin disabled until proper testing can be done
- The old manual message construction method was working
- Native method is nice-to-have, not critical

## Current State

- Plugin is DISABLED in config
- Application can be restarted safely
- Other plugins should work normally

## To Restart Application

```bash
python3 src/main.py
```

The application should start normally with traceroute_mapper disabled.

## Testing Before Re-enabling

If you want to test the traceroute plugin:

1. Start with ONLY traceroute_mapper enabled
2. Disable all other plugins
3. Watch logs carefully for errors
4. Test for 5-10 minutes
5. Check for memory leaks, freezes, etc.

## Apology

I apologize for the instability. The changes were made too quickly without proper testing. The native meshtastic method implementation needs more careful integration and error handling before it's production-ready.
