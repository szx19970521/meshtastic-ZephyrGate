# MQTT Gateway Plugin Testing Plan

## Test Environment Setup

### Option 1: Public Meshtastic MQTT Broker (Recommended for Quick Test)
- **Broker**: mqtt.meshtastic.org
- **Port**: 1883 (no auth required)
- **Pros**: No setup needed, see real mesh traffic
- **Cons**: Public data, can't control test messages

### Option 2: Local Mosquitto Broker (Recommended for Development)
- **Install**: `brew install mosquitto` (macOS) or `apt-get install mosquitto` (Linux)
- **Start**: `mosquitto -v` (verbose mode for debugging)
- **Pros**: Full control, private, see all messages
- **Cons**: Requires installation

### Option 3: MQTT Explorer Tool
- **Download**: http://mqtt-explorer.com/
- **Purpose**: Visual MQTT client to monitor messages
- **Use**: Connect to broker and subscribe to `msh/US/#` to see all messages

## Testing Steps

### Phase 1: Basic Connection Test

1. **Enable the plugin** in config.yaml:
   ```yaml
   mqtt_gateway:
     enabled: true
     broker_address: mqtt.meshtastic.org  # or localhost for local broker
     broker_port: 1883
     log_level: DEBUG  # Enable detailed logging
   ```

2. **Restart ZephyrGate**

3. **Check logs** for connection success:
   ```
   INFO: MQTT Gateway plugin initialized
   INFO: Connecting to MQTT broker mqtt.meshtastic.org:1883
   INFO: Successfully connected to MQTT broker
   ```

4. **Verify health status** via web dashboard or API:
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" \
        http://localhost:8080/api/plugins
   ```

### Phase 2: Message Forwarding Test

1. **Configure channel forwarding**:
   ```yaml
   mqtt_gateway:
     enabled: true
     channels:
       - name: "LongFast"
         uplink_enabled: true
         message_types: ["text", "position", "nodeinfo", "telemetry"]
   ```

2. **Send a test message** via Meshtastic device or simulator

3. **Monitor MQTT broker** using MQTT Explorer or mosquitto_sub:
   ```bash
   # Subscribe to all topics
   mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/#" -v
   
   # Or specific channel
   mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/2/json/LongFast/#" -v
   ```

4. **Verify message appears** in MQTT with correct format:
   ```json
   {
     "sender": "!a4ee2753",
     "channel": 0,
     "type": "text",
     "payload": {
       "text": "Test message"
     },
     "timestamp": 1234567890,
     "snr": 8.5,
     "rssi": -95
   }
   ```

### Phase 3: Rate Limiting Test

1. **Configure low rate limit**:
   ```yaml
   mqtt_gateway:
     max_messages_per_second: 2
   ```

2. **Send burst of messages** (5+ messages quickly)

3. **Check logs** for rate limiting:
   ```
   DEBUG: Rate limit reached, queuing message
   INFO: Queue size: 3 messages
   ```

4. **Verify messages are queued** and published gradually

### Phase 4: Reconnection Test

1. **Stop MQTT broker** (if using local broker):
   ```bash
   # Kill mosquitto process
   pkill mosquitto
   ```

2. **Check logs** for reconnection attempts:
   ```
   WARNING: MQTT connection lost
   INFO: Attempting reconnection (attempt 1/infinite)
   INFO: Reconnection attempt 1 failed, waiting 1.0 seconds
   INFO: Attempting reconnection (attempt 2/infinite)
   ```

3. **Restart broker**:
   ```bash
   mosquitto -v
   ```

4. **Verify reconnection**:
   ```
   INFO: Successfully reconnected to MQTT broker
   INFO: Processing queued messages (5 messages)
   ```

### Phase 5: Message Filtering Test

1. **Configure selective forwarding**:
   ```yaml
   mqtt_gateway:
     channels:
       - name: "LongFast"
         uplink_enabled: true
         message_types: ["text"]  # Only text messages
   ```

2. **Send different message types**:
   - Text message (should forward)
   - Position update (should NOT forward)
   - Telemetry (should NOT forward)

3. **Verify filtering** in logs:
   ```
   DEBUG: Forwarding text message from !a4ee2753
   DEBUG: Message type 'position' not in allowed types, skipping
   DEBUG: Message type 'telemetry' not in allowed types, skipping
   ```

### Phase 6: Error Handling Test

1. **Test invalid broker**:
   ```yaml
   mqtt_gateway:
     broker_address: invalid.broker.example.com
   ```

2. **Check error handling**:
   ```
   ERROR: Failed to connect to MQTT broker: Name or service not known
   INFO: Entering recovery mode, will retry connection
   ```

3. **Test authentication failure** (if using authenticated broker):
   ```yaml
   mqtt_gateway:
     username: "wrong_user"
     password: "wrong_pass"
   ```

4. **Verify graceful degradation**:
   ```
   ERROR: Authentication failed
   INFO: ZephyrGate continues operating normally
   ```

## Test Checklist

- [ ] Plugin loads successfully
- [ ] Connects to MQTT broker
- [ ] Publishes messages in correct format
- [ ] Follows Meshtastic MQTT topic structure
- [ ] Rate limiting works correctly
- [ ] Message queue functions properly
- [ ] Reconnection works after disconnect
- [ ] Channel filtering works
- [ ] Message type filtering works
- [ ] Handles connection errors gracefully
- [ ] Health status reports correctly
- [ ] Logs are informative and not excessive
- [ ] No memory leaks during long-running test
- [ ] ZephyrGate works normally when MQTT is down

## Expected MQTT Topics

### JSON Format (Default)
```
msh/US/2/json/LongFast/!a4ee2753
msh/US/2/json/0/!a4ee2753
```

### Protobuf Format (Encrypted)
```
msh/US/2/e/LongFast/!a4ee2753
```

## Monitoring Commands

### Using mosquitto_sub (command line)
```bash
# Monitor all messages
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/#" -v

# Monitor specific channel
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/2/json/LongFast/#" -v

# Monitor specific node
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/2/json/+/!a4ee2753" -v

# Save to file
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/#" -v > mqtt_messages.log
```

### Using Python (programmatic)
```python
import paho.mqtt.client as mqtt

def on_message(client, userdata, message):
    print(f"Topic: {message.topic}")
    print(f"Payload: {message.payload.decode()}")
    print("---")

client = mqtt.Client()
client.on_message = on_message
client.connect("mqtt.meshtastic.org", 1883)
client.subscribe("msh/US/#")
client.loop_forever()
```

## Success Criteria

✅ **Plugin is working correctly if:**
1. Connects to broker without errors
2. Messages appear on MQTT with correct topic structure
3. JSON payload matches Meshtastic MQTT schema
4. Rate limiting prevents broker overload
5. Reconnects automatically after disconnection
6. Queue prevents message loss during outages
7. Health status shows `connected: true`
8. No errors in logs during normal operation

## Common Issues and Solutions

### Issue: "Connection refused"
- **Cause**: Broker not running or wrong address
- **Fix**: Verify broker is running, check address/port

### Issue: "Authentication failed"
- **Cause**: Wrong username/password
- **Fix**: Verify credentials, check broker config

### Issue: "Messages not appearing on MQTT"
- **Cause**: Channel not configured or uplink disabled
- **Fix**: Add channel to config with `uplink_enabled: true`

### Issue: "Queue growing indefinitely"
- **Cause**: Broker down or rate limit too low
- **Fix**: Check broker connection, increase rate limit

### Issue: "High CPU usage"
- **Cause**: Too many messages, inefficient serialization
- **Fix**: Reduce message types, increase rate limit delay

## Next Steps After Testing

1. **Production Configuration**:
   - Use TLS/SSL for security
   - Set appropriate rate limits
   - Configure only needed channels
   - Disable debug logging

2. **Monitoring**:
   - Set up health checks
   - Monitor queue size
   - Track message drop rate
   - Alert on connection failures

3. **Integration**:
   - Connect to Home Assistant
   - Set up Grafana dashboards
   - Configure alerting systems
   - Build custom MQTT consumers
