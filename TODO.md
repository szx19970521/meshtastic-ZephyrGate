# ZephyrGate TODO

This document tracks pending tasks, bugs, and planned features for ZephyrGate.

---

## 🧪 Tests to Run

### Asset Service
- [ ] Test asset tracking functionality
- [ ] Test geofencing alerts
- [ ] Test asset location updates
- [ ] Test asset movement detection
- [ ] Test asset database persistence
- [ ] Test asset scheduling service
- [ ] Integration tests with mesh network
- [ ] Property-based tests for asset state management

### Email Service
- [ ] Test SMTP connection and authentication
- [ ] Test IMAP connection and email retrieval
- [ ] Test email-to-mesh forwarding
- [ ] Test mesh-to-email sending
- [ ] Test email parsing and formatting
- [ ] Test attachment handling
- [ ] Test email rate limiting
- [ ] Integration tests with email providers
- [ ] Error handling for connection failures

### Emergency Service
- [ ] Test emergency keyword detection
- [ ] Test alert escalation logic
- [ ] Test notification delivery (mesh, email, etc.)
- [ ] Test emergency response tracking
- [ ] Test false positive handling
- [ ] Test multi-channel monitoring
- [ ] Test emergency contact management
- [ ] Integration tests with notification systems
- [ ] Property-based tests for keyword matching

### Games
- [ ] Test trivia game functionality
- [ ] Test word game mechanics
- [ ] Test game state persistence
- [ ] Test multiplayer game coordination
- [ ] Test game scoring and leaderboards
- [ ] Test game timeout handling
- [ ] Test concurrent game sessions
- [ ] Integration tests with BBS system
- [ ] Property-based tests for game logic

---

## 🐛 Bugs

### Known Issues
- [ ] None currently tracked

### To Investigate
- [ ] Traceroute responses from direct nodes (0 hops) - verify empty route handling
- [ ] MQTT reconnection behavior under poor network conditions
- [ ] Web dashboard WebSocket connection stability
- [ ] Database migration edge cases for large node counts

### Performance Issues
- [ ] Database query optimization for large message history
- [ ] Memory usage with many concurrent plugin operations
- [ ] Web interface responsiveness with 100+ nodes

---

## 🚀 New Features

### Discord Integration
**Priority:** High  
**Status:** Planned

Bridge Meshtastic mesh network to Discord channels.

**Features:**
- Bidirectional message forwarding (mesh ↔ Discord)
- Discord bot for mesh network control
- Channel mapping configuration
- User identity mapping
- Rich embeds for mesh messages (location, telemetry, etc.)
- Discord slash commands for mesh operations
- Message formatting and emoji support
- Rate limiting and flood protection
- Discord webhook support
- Thread support for conversations

**Configuration:**
```yaml
discord_bridge:
  enabled: true
  bot_token: "your-discord-bot-token"
  guild_id: "your-server-id"
  channel_mappings:
    - mesh_channel: 0
      discord_channel_id: "123456789"
      bidirectional: true
  user_mapping_enabled: true
  rich_embeds: true
  forward_telemetry: true
  forward_position: true
```

**Technical Requirements:**
- Discord.py library integration
- Async message handling
- Message queue for rate limiting
- User permission management
- Error handling and reconnection logic

---

### Slack Integration
**Priority:** Medium  
**Status:** Planned

Bridge Meshtastic mesh network to Slack workspaces.

**Features:**
- Bidirectional message forwarding (mesh ↔ Slack)
- Slack app for mesh network control
- Channel mapping configuration
- User identity mapping
- Rich message formatting with blocks
- Slack slash commands for mesh operations
- Thread support for conversations
- Emoji reactions and custom emoji
- File sharing support
- Rate limiting and flood protection

**Configuration:**
```yaml
slack_bridge:
  enabled: true
  bot_token: "xoxb-your-bot-token"
  app_token: "xapp-your-app-token"
  workspace_id: "your-workspace-id"
  channel_mappings:
    - mesh_channel: 0
      slack_channel_id: "C123456789"
      bidirectional: true
  user_mapping_enabled: true
  rich_formatting: true
  forward_telemetry: true
  forward_position: true
```

**Technical Requirements:**
- Slack SDK integration
- Socket mode for real-time events
- Message queue for rate limiting
- User permission management
- Error handling and reconnection logic

---

### News Headlines Integration
**Priority:** Medium  
**Status:** Planned

Deliver news headlines to mesh network via scheduled broadcasts.

**Features:**
- Multiple news source support (RSS, APIs)
- Customizable news categories
- Scheduled headline broadcasts
- Keyword filtering and alerts
- Summary generation for bandwidth efficiency
- Breaking news alerts
- Local news prioritization
- Weather-related news integration
- Configurable update frequency
- News archive and history

**Configuration:**
```yaml
news_service:
  enabled: true
  sources:
    - name: "BBC News"
      type: "rss"
      url: "http://feeds.bbci.co.uk/news/rss.xml"
      categories: ["world", "technology"]
      enabled: true
    - name: "Associated Press"
      type: "api"
      api_key: "your-api-key"
      categories: ["breaking", "local"]
      enabled: true
  
  broadcast_schedule:
    - time: "08:00"
      max_headlines: 3
      categories: ["breaking", "local"]
    - time: "18:00"
      max_headlines: 5
      categories: ["world", "technology"]
  
  filtering:
    keywords: ["emergency", "weather", "local"]
    exclude_keywords: ["sports", "entertainment"]
  
  formatting:
    max_length: 200
    include_source: true
    include_timestamp: true
  
  alerts:
    breaking_news: true
    keywords: ["emergency", "evacuation", "warning"]
    priority: "high"
```

**Technical Requirements:**
- RSS feed parser
- News API integrations (NewsAPI, Google News, etc.)
- Text summarization (AI or extractive)
- Scheduled broadcast integration
- Keyword matching and filtering
- Caching to avoid duplicate headlines

**Supported News Sources:**
- RSS/Atom feeds
- NewsAPI.org
- Google News API
- Associated Press API
- Local news APIs
- Weather alert feeds
- Emergency broadcast systems

---

### Web Interface for Plugins
**Priority:** High  
**Status:** Planned

Enhanced web-based administration and control interface for all plugins.

**Features:**

- **Emergency Service Dashboard**
  - Active emergency alerts
  - Emergency contact management
  - Alert history and timeline
  - Response tracking
  - Escalation rule configuration

- **Asset Tracking Map**
  - Real-time asset location map
  - Geofence visualization and editing
  - Asset movement history
  - Alert configuration
  - Asset grouping and filtering

**Technical Requirements:**
- Modern web framework (React, Vue, or Svelte)
- WebSocket for real-time updates
- REST API for plugin control
- Interactive map library (Leaflet, Mapbox)
- Graph visualization (D3.js, Cytoscape.js)
- Form validation and error handling
- Responsive design for mobile
- Authentication and authorization
- Plugin API extensions for web UI

**UI Components:**
- Plugin card grid with status indicators
- Real-time log viewer with filtering
- Interactive network graph
- Configuration forms with validation
- Statistics dashboards with charts
- Map interface for location data
- Timeline for events and history
- Modal dialogs for actions
- Toast notifications for alerts

---

## 📋 Additional Planned Features

### Lower Priority
- [ ] **Mesh Chat Rooms** - Multi-user chat channels
- [ ] **Multi-Zephergate Connection** - Track node reliability

---

## 🔄 In Progress

Currently no features in active development. See completed features in [CHANGELOG.md](CHANGELOG.md).

---

## ✅ Completed

See [CHANGELOG.md](CHANGELOG.md) for completed features and releases.

---

## 📝 Notes

### Contributing
Want to work on any of these features? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Feature Requests
Have an idea for a new feature? Open an issue on GitHub with the `feature-request` label.

### Bug Reports
Found a bug? Open an issue on GitHub with the `bug` label and include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- System information
- Relevant logs

---

**Last Updated:** 2026-03-01  
**Version:** 1.0.0
