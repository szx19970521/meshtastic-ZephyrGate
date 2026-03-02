# Traceroute Mapper Plugin Testing Guide

## Changes Made

1. **Enabled traceroute_mapper plugin** in `config/config.yaml`
2. **Changed rate limiting to seconds-based** - Now uses `seconds_between_traceroutes: 120` (2 minutes) instead of per-minute rate
3. **Fixed routing message metadata** in `src/core/interfaces.py` to include `traceroute: True` and `route` fields
4. **Added traceroute_mapper to message routing** in `src/core/message_router.py` so all messages are sent to the plugin
5. **Fixed handle_message signature** in `plugins/traceroute_mapper/plugin.py` to match message router expectations

## Configuration

Current settings in `config/config.yaml`:
- `enabled: true` - Plugin is active
- `seconds_between_traceroutes: 120` - Wait 2 minutes (120 seconds) between traceroutes
- `max_hops: 7` - Maximum hops to trace
- `timeout_seconds: 60` - Wait 60s for response
- `skip_direct_nodes: true` - Don't trace single-hop nodes
- `recheck_enabled: true` - Periodically re-trace nodes
- `recheck_interval_hours: 6` - Re-trace every 6 hours
- `forward_to_mqtt: true` - Publish results to MQTT broker
- `state_file_path: data/traceroute_state.json` - Persistent state

You can adjust `seconds_between_traceroutes` to any value:
- `30` = 30 seconds (2 per minute)
- `60` = 1 minute
- `120` = 2 minutes (default)
- `300` = 5 minutes
- `600` = 10 minutes

## Testing Steps

1. **Restart ZephyrGate** to load the plugin:
   ```bash
   # Stop current instance (Ctrl+C)
   python main.py
   ```

2. **Watch the logs** for plugin initialization and node discovery

3. **Wait for indirect nodes** - The plugin will automatically:
   - Detect nodes that are >1 hop away (indirect)
   - Queue traceroute requests for them
   - Send traceroutes at 1 per minute rate

4. **Check state file** after a few minutes:
   ```bash
   cat data/traceroute_state.json
   ```
   Should show discovered nodes and their trace status

5. **Monitor MQTT broker** for published traceroute results:
   ```bash
   python test_mqtt_monitor.py
   ```
   Look for messages on topic: `msh/US/FL/thevillages/2/json/traceroute/#`

## Expected Behavior

### For Direct Nodes (1 hop away)
- Plugin detects them as direct (good SNR/RSSI, hop_start=0)
- Logs "Skipping direct node !xxxxxxxx"
- No traceroute is queued

### For Indirect Nodes (2+ hops away)
- Plugin detects them as indirect (poor SNR/RSSI or hop_start>0)
- Logs "Discovered new indirect node !xxxxxxxx"
- Queues traceroute request with priority based on:
  - New discovery = HIGH priority
  - Recheck = MEDIUM priority
  - Retry = LOW priority
- Sends traceroute at rate limit (1/minute)
- Waits for response (60s timeout)
- Publishes result to MQTT if successful

### Traceroute Response Format
```json
{
  "sender": "!336908b8",
  "timestamp": 1772412651,
  "channel": 0,
  "type": "traceroute",
  "payload": {
    "route": ["!a1b2c3d4", "!e5f6g7h8", "!336908b8"],
    "snr_list": [8.5, 5.2, 3.1],
    "hops": 3
  }
}
```

## Troubleshooting

### No traceroutes being sent
- Check if any indirect nodes have been discovered
- Verify rate limiter isn't blocking (1/minute limit)
- Check network health monitor isn't in emergency stop

### Traceroute responses not detected
- Verify routing message handler is working
- Check metadata includes `traceroute: True` and `route` fields
- Look for errors in log

### State not persisting
- Check `data/` directory exists and is writable
- Verify `state_persistence_enabled: true` in config
- Look for "Saved state" messages every 5 minutes

## Manual Traceroute Test

To manually trigger a traceroute from the Meshtastic CLI:
```bash
meshtastic --traceroute !xxxxxxxx
```

This will send a traceroute request to node `!xxxxxxxx` and the plugin should detect the response.
