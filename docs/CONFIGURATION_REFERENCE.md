# ZephyrGate Configuration Reference

Complete reference guide for all configuration options in `config.yaml`.

## Table of Contents

- [Core System Configuration](#core-system-configuration)
- [Meshtastic Interfaces](#meshtastic-interfaces)
- [Plugin Configuration](#plugin-configuration)
  - [Traceroute Mapper](#traceroute-mapper)
  - [MQTT Gateway](#mqtt-gateway)
  - [Web Service](#web-service)
  - [Bot Service](#bot-service)
  - [Emergency Service](#emergency-service)
  - [Email Service](#email-service)
  - [Weather Service](#weather-service)
  - [Asset Service](#asset-service)
  - [BBS Service](#bbs-service)
  - [Villages Events Service](#villages-events-service)
  - [Ping Responder](#ping-responder)

---

## Core System Configuration

### System Settings

```yaml
system:
  debug: false                    # Enable debug mode (verbose logging)
  log_level: "INFO"              # Global log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  data_directory: "data"         # Directory for database and state files
  timezone: "UTC"                # System timezone for scheduling
```

**Options:**
- `debug`: Boolean - Enables detailed debug logging across all components
- `log_level`: String - Sets minimum log level for all loggers
- `data_directory`: String - Path to store database and persistent data
- `timezone`: String - IANA timezone identifier (e.g., "America/New_York")

### Database Configuration

```yaml
database:
  path: "data/zephyrgate.db"    # SQLite database file location
  backup_enabled: true           # Enable automatic backups
  backup_interval_hours: 24      # Hours between backups
  backup_retention_days: 7       # Days to keep old backups
```

---

## Meshtastic Interfaces

Configure connections to Meshtastic devices.

### Serial Interface

```yaml
interfaces:
  - id: "primary"
    type: "serial"
    enabled: true
    port: "/dev/ttyUSB0"         # Serial port path
    reconnect: true              # Auto-reconnect on disconnect
    reconnect_delay: 5           # Seconds between reconnect attempts
```

**Options:**
- `id`: String - Unique identifier for this interface
- `type`: String - Interface type: "serial", "tcp", or "ble"
- `enabled`: Boolean - Enable/disable this interface
- `port`: String - Serial device path (Linux/Mac: `/dev/tty*`, Windows: `COM*`)
- `reconnect`: Boolean - Automatically reconnect on connection loss
- `reconnect_delay`: Integer - Seconds to wait before reconnecting

### TCP Interface

```yaml
interfaces:
  - id: "remote"
    type: "tcp"
    enabled: false
    host: "192.168.1.100"        # IP address of Meshtastic device
    port: 4403                   # TCP port (default: 4403)
    reconnect: true
    reconnect_delay: 5
```

### BLE Interface

```yaml
interfaces:
  - id: "bluetooth"
    type: "ble"
    enabled: false
    address: "AA:BB:CC:DD:EE:FF" # Bluetooth MAC address
    reconnect: true
    reconnect_delay: 10
```

---

## Plugin Configuration

### Traceroute Mapper

Automatically discovers and maps mesh network topology.

```yaml
traceroute_mapper:
  enabled: true
```

#### Rate Limiting

```yaml
  seconds_between_traceroutes: 120  # Minimum seconds between sending traceroutes
  burst_multiplier: 2               # Allow bursts (capacity = rate × multiplier)
```

**Purpose:** Prevents overwhelming the mesh network with too many traceroute requests.

**Options:**
- `seconds_between_traceroutes`: Integer (1-3600) - Minimum time between traceroutes
- `burst_multiplier`: Float (1.0-10.0) - Allows short bursts of activity

#### Traceroute Scheduling (Database-backed)

```yaml
  traceroute_interval_minutes: 180  # Minutes between successful traceroutes (same node)
  traceroute_retry_minutes: 30      # Minutes before retrying failed traceroutes
  active_node_hours: 24             # Only trace nodes seen in last N hours
```

**Purpose:** Controls when nodes are re-traced using database timestamps.

**Options:**
- `traceroute_interval_minutes`: Integer (10-10080) - Wait time between successful traces
- `traceroute_retry_minutes`: Integer (5-1440) - Wait time before retrying failures
- `active_node_hours`: Integer (1-168) - Only trace recently active nodes

**How it works:**
- Each node has `next_traceroute_time` stored in database
- After successful traceroute: next time = now + `traceroute_interval_minutes`
- After failed traceroute: next time = now + `traceroute_retry_minutes`
- Nodes not seen in `active_node_hours` are skipped

#### Priority Queue

```yaml
  queue_max_size: 500                        # Maximum queued requests
  queue_overflow_strategy: "drop_lowest_priority"  # Overflow handling
  clear_queue_on_startup: false              # Clear queue on restart
```

**Priority Levels:**
- Priority 1: New indirect nodes discovered (highest)
- Priority 4: Nodes coming back online
- Priority 8: Periodic rechecks (lowest)

**Options:**
- `queue_max_size`: Integer (10-10000) - Maximum pending traceroutes
- `queue_overflow_strategy`: String - How to handle full queue:
  - `drop_lowest_priority`: Remove lowest priority items
  - `drop_oldest`: Remove oldest items
  - `drop_new`: Reject new items
- `clear_queue_on_startup`: Boolean - Clear pending requests on restart

#### Traceroute Parameters

```yaml
  max_hops: 7                      # Maximum hops to trace
  timeout_seconds: 60              # Response timeout
  max_retries: 3                   # Retry attempts for failures
  retry_backoff_multiplier: 2.0    # Exponential backoff multiplier
```

**Options:**
- `max_hops`: Integer (1-15) - Maximum mesh hops to trace
- `timeout_seconds`: Integer (10-300) - Seconds to wait for response
- `max_retries`: Integer (0-10) - Number of retry attempts
- `retry_backoff_multiplier`: Float (1.0-10.0) - Delay multiplier for retries
  - Retry 1: base delay
  - Retry 2: base delay × multiplier
  - Retry 3: base delay × multiplier²

#### Startup Behavior

```yaml
  initial_discovery_enabled: true  # Scan existing nodes on startup
  startup_delay_seconds: 60        # Wait before first traceroute
```

**Options:**
- `initial_discovery_enabled`: Boolean - Queue traceroutes for all known nodes at startup
- `startup_delay_seconds`: Integer (0-600) - Delay before processing queue

#### Node Filtering

```yaml
  skip_direct_nodes: true          # Skip nodes at 0 hops (directly heard)
  blacklist: []                    # Node IDs to never trace
  whitelist: []                    # If set, only trace these nodes
  exclude_roles: ["CLIENT"]        # Skip nodes with these roles
  min_snr_threshold: null          # Minimum SNR to trace (null = no limit)
```

**Options:**
- `skip_direct_nodes`: Boolean - Skip direct nodes (0 hops away)
  - `true`: Only trace multi-hop nodes (recommended)
  - `false`: Trace all nodes including direct
- `blacklist`: List of Strings - Node IDs to never trace (e.g., `["!a1b2c3d4"]`)
- `whitelist`: List of Strings - If set, only trace these nodes (overrides blacklist)
- `exclude_roles`: List of Strings - Skip nodes with these roles:
  - `CLIENT`: Client devices
  - `ROUTER`: Router nodes
  - `REPEATER`: Repeater nodes
- `min_snr_threshold`: Float or null - Minimum signal-to-noise ratio (-30 to 20)

#### Network Health Protection

##### Quiet Hours

```yaml
  quiet_hours:
    enabled: false                 # Enable quiet hours
    start_time: "22:00"           # Start time (24-hour format)
    end_time: "06:00"             # End time (24-hour format)
    timezone: "UTC"               # Timezone for quiet hours
```

**Purpose:** Pause traceroutes during specific time windows (e.g., nighttime).

**Options:**
- `enabled`: Boolean - Enable quiet hours feature
- `start_time`: String - Start time in HH:MM format (24-hour)
- `end_time`: String - End time in HH:MM format (24-hour)
- `timezone`: String - IANA timezone identifier

##### Congestion Detection

```yaml
  congestion_detection:
    enabled: true                  # Enable congestion detection
    success_rate_threshold: 0.5    # Throttle if success rate < 50%
    throttle_multiplier: 0.5       # Reduce rate by 50% when congested
```

**Purpose:** Automatically reduce traceroute rate when network is congested.

**How it works:**
- Monitors traceroute success rate
- If success rate < threshold: reduce rate by throttle_multiplier
- Automatically recovers when success rate improves

**Options:**
- `enabled`: Boolean - Enable automatic throttling
- `success_rate_threshold`: Float (0.0-1.0) - Success rate trigger (0.5 = 50%)
- `throttle_multiplier`: Float (0.1-1.0) - Rate reduction factor (0.5 = 50% slower)

##### Emergency Stop

```yaml
  emergency_stop:
    enabled: true                  # Enable emergency stop
    failure_threshold: 0.2         # Stop if success rate < 20%
    consecutive_failures: 10       # Stop after N consecutive failures
    auto_recovery_minutes: 30      # Auto-resume after N minutes
```

**Purpose:** Completely stop traceroutes if network health is critical.

**How it works:**
- Monitors success rate and consecutive failures
- Stops all traceroutes if either threshold is exceeded
- Automatically resumes after recovery period

**Options:**
- `enabled`: Boolean - Enable emergency stop feature
- `failure_threshold`: Float (0.0-1.0) - Success rate trigger (0.2 = 20%)
- `consecutive_failures`: Integer - Number of consecutive failures to trigger
- `auto_recovery_minutes`: Integer - Minutes before auto-resume

#### State Persistence

```yaml
  state_persistence_enabled: true
  state_file_path: "data/traceroute_state.json"
  auto_save_interval_minutes: 5
  history_per_node: 10
```

**Options:**
- `state_persistence_enabled`: Boolean - Save state to disk
- `state_file_path`: String - Path to state file
- `auto_save_interval_minutes`: Integer - Minutes between auto-saves
- `history_per_node`: Integer - Number of historical traceroutes to keep per node

#### MQTT Integration

```yaml
  forward_to_mqtt: true            # Forward traceroute messages to MQTT
```

**Options:**
- `forward_to_mqtt`: Boolean - Publish traceroute requests/responses to MQTT
  - Requires `mqtt_gateway` plugin to be enabled

#### Logging

```yaml
  log_level: "INFO"                # Plugin log level
  log_traceroute_requests: true    # Log each request
  log_traceroute_responses: true   # Log each response
```

---

### MQTT Gateway

Bridges Meshtastic mesh to MQTT broker.

```yaml
mqtt_gateway:
  enabled: true
  broker_address: "mqtt.example.com"  # MQTT broker hostname/IP
  broker_port: 1883                   # MQTT broker port
  root_topic: "msh/US/2/json"        # Base MQTT topic
  region: "US"                        # Meshtastic region
  format: "json"                      # Message format: json or protobuf
  max_messages_per_second: 10         # Rate limit for MQTT publishing
  reconnect_enabled: true             # Auto-reconnect to broker
  log_level: "INFO"                   # Plugin log level
```

**Options:**
- `broker_address`: String - MQTT broker hostname or IP address
- `broker_port`: Integer - MQTT broker port (default: 1883, TLS: 8883)
- `root_topic`: String - Base topic for all messages
- `region`: String - Meshtastic region code (US, EU, etc.)
- `format`: String - Message format:
  - `json`: JSON format (human-readable)
  - `protobuf`: Binary protobuf format (compact)
- `max_messages_per_second`: Integer - Maximum MQTT publish rate
- `reconnect_enabled`: Boolean - Automatically reconnect on disconnect

**Topic Structure:**
- Outgoing: `{root_topic}/{channel}/json/{gateway_id}/{node_id}`
- Incoming: `{root_topic}/#` (subscribes to all)

---

### Web Service

Web-based administration interface.

```yaml
web_service:
  enabled: true
  host: "0.0.0.0"                    # Listen address (0.0.0.0 = all interfaces)
  port: 8080                         # HTTP port
  admin_username: "admin"            # Admin username
  admin_password: "changeme"         # Admin password (change this!)
  session_timeout_minutes: 60        # Session timeout
  enable_api: true                   # Enable REST API
  enable_websocket: true             # Enable WebSocket for real-time updates
```

**Security Notes:**
- Always change default password
- Use HTTPS in production (configure reverse proxy)
- Restrict `host` to specific interface if needed

---

### Bot Service

AI-powered conversational bot for mesh network.

```yaml
bot_service:
  enabled: true
  bot_name: "ZephyrBot"              # Bot display name
  trigger_keywords: ["bot", "help"]  # Keywords that trigger bot
  ai_provider: "openai"              # AI provider: openai, anthropic, local
  api_key: "your-api-key"           # API key for AI provider
  model: "gpt-4"                     # AI model to use
  max_response_length: 200           # Maximum response characters
  response_timeout: 30               # Seconds to wait for AI response
```

---

### Emergency Service

Emergency keyword detection and alerting.

```yaml
emergency_service:
  enabled: true
  keywords: ["emergency", "help", "911"]  # Emergency trigger words
  alert_channels: [0]                     # Channels to monitor
  escalation_delay: 300                   # Seconds before escalation
  notification_methods: ["mesh", "email"] # How to send alerts
```

---

### Email Service

Send/receive emails via mesh network.

```yaml
email_service:
  enabled: false
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  smtp_username: "your-email@gmail.com"
  smtp_password: "your-app-password"
  imap_server: "imap.gmail.com"
  imap_port: 993
  check_interval_minutes: 5
```

---

### Weather Service

Weather forecasts and alerts for mesh network.

```yaml
weather_service:
  enabled: true
  api_key: "your-weather-api-key"
  provider: "openweathermap"
  default_location: "Miami, FL"
  update_interval_minutes: 30
  alert_enabled: true
```

---

### Asset Service

Track and manage assets via mesh network.

```yaml
asset_service:
  enabled: true
  tracking_interval_minutes: 15
  geofence_enabled: true
  alert_on_movement: true
```

---

### BBS Service

Bulletin Board System for mesh network.

```yaml
bbs_service:
  enabled: true
  max_messages: 100
  message_retention_days: 30
  allow_anonymous: false
```

---

### Villages Events Service

Event scheduling and notifications.

```yaml
villages_events_service:
  enabled: true
  calendar_url: "https://example.com/calendar.ics"
  update_interval_hours: 6
  reminder_hours_before: 24
```

---

### Ping Responder

Automatic ping/pong responses.

```yaml
ping_responder:
  enabled: true
  response_message: "Pong! 🏓"
  cooldown_seconds: 60
```

---

## Scheduled Broadcasts

Configure automated broadcast messages.

```yaml
scheduled_broadcasts:
  - name: "Morning Greeting"
    schedule: "0 8 * * *"           # Cron expression (8 AM daily)
    message: "Good morning mesh network!"
    channel: 0
    priority: "normal"
    hop_limit: 3                    # Optional: limit broadcast range
    enabled: true
```

**Cron Expression Format:**
```
* * * * *
│ │ │ │ │
│ │ │ │ └─ Day of week (0-7, 0 and 7 = Sunday)
│ │ │ └─── Month (1-12)
│ │ └───── Day of month (1-31)
│ └─────── Hour (0-23)
└───────── Minute (0-59)
```

**Examples:**
- `0 8 * * *` - Every day at 8:00 AM
- `*/15 * * * *` - Every 15 minutes
- `0 */6 * * *` - Every 6 hours
- `0 12 * * 1-5` - Weekdays at noon
- `30 18 * * 0` - Sundays at 6:30 PM

---

## Environment Variables

Override configuration with environment variables:

```bash
ZEPHYRGATE_DEBUG=true
ZEPHYRGATE_LOG_LEVEL=DEBUG
ZEPHYRGATE_DB_PATH=/custom/path/db.sqlite
ZEPHYRGATE_WEB_PORT=8080
```

---

## Configuration Best Practices

### Security
1. Change all default passwords
2. Use strong API keys
3. Restrict web interface to trusted networks
4. Enable HTTPS in production
5. Regularly rotate credentials

### Performance
1. Adjust `seconds_between_traceroutes` based on network size
2. Enable `skip_direct_nodes` to reduce unnecessary traceroutes
3. Use `active_node_hours` to focus on active nodes
4. Configure `quiet_hours` to avoid peak usage times
5. Monitor `success_rate` and adjust throttling thresholds

### Reliability
1. Enable `state_persistence` for all plugins
2. Configure `auto_recovery` for emergency stop
3. Set appropriate `timeout_seconds` for your network
4. Use `reconnect` for all interfaces
5. Regular database backups

### Network Health
1. Start with conservative rate limits
2. Enable `congestion_detection` and `emergency_stop`
3. Monitor success rates in web dashboard
4. Adjust thresholds based on network behavior
5. Use `blacklist` for problematic nodes

---

## Troubleshooting

### Traceroutes Not Working
1. Check `enabled: true` in traceroute_mapper
2. Verify `skip_direct_nodes` setting matches your needs
3. Check `active_node_hours` - nodes may be considered inactive
4. Review `blacklist` and `whitelist` settings
5. Check logs for timeout or error messages
6. Verify Meshtastic firmware version (2.0.8+ required)

### High Network Congestion
1. Increase `seconds_between_traceroutes`
2. Lower `success_rate_threshold` for earlier throttling
3. Enable `quiet_hours` during peak times
4. Reduce `max_hops` to limit traceroute scope
5. Increase `traceroute_interval_minutes`

### Database Issues
1. Check `data_directory` permissions
2. Verify disk space availability
3. Enable `backup_enabled` for safety
4. Check database file corruption
5. Review migration logs

---

## See Also

- [Admin Guide](ADMIN_GUIDE.md) - Administration and operation
- [Features Overview](FEATURES_OVERVIEW.md) - Feature descriptions
- [Plugin Development](../plugins/README.md) - Creating custom plugins
- [API Documentation](API_REFERENCE.md) - REST API reference
