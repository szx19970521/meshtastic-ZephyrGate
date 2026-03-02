"""
Network Traceroute Mapper Plugin for ZephyrGate

Automatically discovers and maps mesh network topology by performing intelligent
traceroutes to nodes. Prioritizes important network changes, respects network
health constraints, and publishes results to MQTT for visualization by mapping tools.

Author: ZephyrGate Team
Version: 1.2.0
License: GPL-3.0
"""

import sys
import asyncio
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

# Add src directory to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core.enhanced_plugin import EnhancedPlugin
from core.plugin_manager import PluginMetadata
from models.message import Message, MessageType

# Import component modules
from .node_state_tracker import NodeStateTracker
from .priority_queue import PriorityQueue
from .rate_limiter import RateLimiter
from .traceroute_manager import TracerouteManager
from .state_persistence import StatePersistence
from .network_health_monitor import NetworkHealthMonitor


class TracerouteMapperPlugin(EnhancedPlugin):
    """
    Network Traceroute Mapper Plugin
    
    Automatically discovers and maps mesh network topology by performing
    intelligent traceroutes to nodes. Features:
    - Intelligent priority queue for traceroute requests
    - Rate limiting to protect network health
    - Direct node filtering (skip single-hop nodes)
    - Periodic rechecks for topology changes
    - Network health monitoring and emergency stop
    - State persistence across restarts
    - MQTT integration for visualization
    """
    
    def __init__(self, name: str, config: Dict[str, Any], plugin_manager):
        """
        Initialize the Traceroute Mapper plugin.
        
        Args:
            name: Plugin name
            config: Plugin configuration dictionary
            plugin_manager: Reference to the plugin manager
        """
        super().__init__(name, config, plugin_manager)
        
        # Plugin state
        self.enabled = False
        self.initialized = False
        
        # Component references (will be initialized in initialize())
        self.node_tracker = None
        self.priority_queue = None
        self.rate_limiter = None
        self.traceroute_manager = None
        self.state_persistence = None
        self.health_monitor = None
        
        # Configuration cache
        self._config_cache = {}
        
        # Statistics
        self.stats = {
            'nodes_discovered': 0,
            'traceroutes_sent': 0,
            'traceroutes_successful': 0,
            'traceroutes_failed': 0,
            'traceroutes_timeout': 0,
            'queue_size': 0,
            'direct_nodes_skipped': 0,
            'filtered_nodes_skipped': 0,
            'last_traceroute_time': None,
            'avg_response_time_ms': 0.0
        }
        
        # Background tasks
        self._background_tasks = []
        
    async def initialize(self) -> bool:
        """
        Initialize the plugin with configuration.
        
        This method:
        1. Loads and validates configuration
        2. Initializes sub-components (node tracker, queue, rate limiter, etc.)
        3. Registers with the message router
        
        Returns:
            True if initialization successful, False otherwise
            
        Requirements: 1.1, 1.3, 1.4, 3.3, 6.2, 10.2, 11.2, 11.5
        """
        self.logger.info("Initializing Network Traceroute Mapper plugin")
        
        try:
            # Load configuration - access directly from self.config
            self.enabled = self.config.get("enabled", False)
            
            if not self.enabled:
                self.logger.info("Network Traceroute Mapper is disabled in configuration")
                return False
            
            # Validate and cache configuration
            if not self._load_and_validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            self.logger.info("Configuration validated successfully")
            self.logger.debug(f"Configuration: {json.dumps(self._config_cache, indent=2)}")
            
            # Initialize NodeStateTracker
            self.logger.info("Initializing NodeStateTracker...")
            self.node_tracker = NodeStateTracker(self._config_cache)
            
            # Initialize PriorityQueue
            self.logger.info("Initializing PriorityQueue...")
            self.priority_queue = PriorityQueue(
                max_size=self._config_cache['queue_max_size'],
                overflow_strategy=self._config_cache['queue_overflow_strategy']
            )
            
            # Initialize RateLimiter
            self.logger.info("Initializing RateLimiter...")
            self.rate_limiter = RateLimiter(
                traceroutes_per_minute=self._config_cache['traceroutes_per_minute'],
                burst_multiplier=self._config_cache['burst_multiplier'],
                logger=self.logger
            )
            
            # Initialize TracerouteManager
            self.logger.info("Initializing TracerouteManager...")
            self.traceroute_manager = TracerouteManager(
                max_hops=self._config_cache['max_hops'],
                timeout_seconds=self._config_cache['timeout_seconds'],
                max_retries=self._config_cache['max_retries'],
                retry_backoff_multiplier=self._config_cache['retry_backoff_multiplier'],
                logger=self.logger
            )
            
            # Initialize StatePersistence
            self.logger.info("Initializing StatePersistence...")
            self.state_persistence = StatePersistence(
                state_file_path=self._config_cache['state_file_path'],
                history_per_node=self._config_cache['history_per_node']
            )
            
            # Initialize NetworkHealthMonitor
            self.logger.info("Initializing NetworkHealthMonitor...")
            quiet_hours = self._config_cache['quiet_hours']
            congestion = self._config_cache['congestion_detection']
            emergency = self._config_cache['emergency_stop']
            
            self.health_monitor = NetworkHealthMonitor(
                success_rate_threshold=congestion['success_rate_threshold'],
                failure_threshold=emergency['failure_threshold'],
                consecutive_failures_threshold=emergency['consecutive_failures'],
                auto_recovery_minutes=emergency['auto_recovery_minutes'],
                quiet_hours_enabled=quiet_hours['enabled'],
                quiet_hours_start=quiet_hours['start_time'],
                quiet_hours_end=quiet_hours['end_time'],
                congestion_enabled=congestion['enabled'],
                throttle_multiplier=congestion['throttle_multiplier']
            )
            
            # Register message handler to receive all mesh messages
            self.register_message_handler(self._handle_mesh_message, priority=50)
            self.logger.info("Registered message handler with message router")
            
            self.initialized = True
            self.logger.info("Network Traceroute Mapper plugin initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Network Traceroute Mapper plugin: {e}", exc_info=True)
            return False
    
    def _load_and_validate_config(self) -> bool:
        """
        Load and validate plugin configuration.
        
        Validates all configuration parameters against the schema and caches
        them for efficient access during runtime.
        
        Returns:
            True if configuration is valid, False otherwise
            
        Requirements: 1.3, 3.3, 6.2, 10.2, 11.2, 11.5
        """
        try:
            # Load configuration schema
            schema_path = Path(__file__).parent / "config_schema.json"
            with open(schema_path, 'r') as f:
                schema = json.load(f)
            
            # Extract and validate each configuration parameter
            config_params = {
                # Rate limiting - support both old and new parameter names
                'seconds_between_traceroutes': ('number', 120, 1, 3600),  # 1 second to 1 hour
                'burst_multiplier': ('number', 2, 1, 10),
                
                # Traceroute scheduling
                'traceroute_interval_minutes': ('number', 180, 10, 10080),  # 10 minutes to 1 week
                'traceroute_retry_minutes': ('number', 30, 5, 1440),  # 5 minutes to 1 day
                'active_node_hours': ('number', 24, 1, 168),  # 1 hour to 1 week
                
                # Queue management
                'queue_max_size': ('integer', 500, 10, 10000),
                'queue_overflow_strategy': ('enum', 'drop_lowest_priority', 
                                           ['drop_lowest_priority', 'drop_oldest', 'drop_new'], None),
                'clear_queue_on_startup': ('boolean', False, None, None),
                
                # Periodic rechecks (deprecated - use traceroute_interval_minutes)
                'recheck_interval_hours': ('number', 6, 0, 168),
                'recheck_enabled': ('boolean', True, None, None),
                
                # Traceroute parameters
                'max_hops': ('integer', 7, 1, 15),
                'timeout_seconds': ('number', 60, 10, 300),
                'max_retries': ('integer', 3, 0, 10),
                'retry_backoff_multiplier': ('number', 2.0, 1.0, 10.0),
                
                # Startup behavior
                'initial_discovery_enabled': ('boolean', False, None, None),
                'startup_delay_seconds': ('number', 60, 0, 600),
                
                # Node filtering
                'skip_direct_nodes': ('boolean', True, None, None),
                'blacklist': ('list', [], None, None),
                'whitelist': ('list', [], None, None),
                'exclude_roles': ('list', ['CLIENT'], None, None),
                'min_snr_threshold': ('number_or_null', None, -30, 20),
                
                # State persistence
                'state_persistence_enabled': ('boolean', True, None, None),
                'state_file_path': ('string', 'data/traceroute_state.json', None, None),
                'auto_save_interval_minutes': ('number', 5, 1, 60),
                'history_per_node': ('integer', 10, 1, 100),
                
                # MQTT integration
                'forward_to_mqtt': ('boolean', True, None, None),
                
                # Logging
                'log_level': ('enum', 'INFO', 
                            ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], None),
                'log_traceroute_requests': ('boolean', True, None, None),
                'log_traceroute_responses': ('boolean', True, None, None),
            }
            
            # Validate and cache each parameter
            for param_name, param_spec in config_params.items():
                param_type = param_spec[0]
                default_value = param_spec[1]
                
                value = self.config.get(param_name, default_value)
                
                # Type validation
                if param_type == 'boolean':
                    if not isinstance(value, bool):
                        self.logger.error(f"Invalid type for {param_name}: expected boolean, got {type(value)}")
                        return False
                        
                elif param_type == 'integer':
                    min_val, max_val = param_spec[2], param_spec[3]
                    if not isinstance(value, int):
                        self.logger.error(f"Invalid type for {param_name}: expected integer, got {type(value)}")
                        return False
                    if min_val is not None and value < min_val:
                        self.logger.error(f"Invalid value for {param_name}: {value} < {min_val}")
                        return False
                    if max_val is not None and value > max_val:
                        self.logger.error(f"Invalid value for {param_name}: {value} > {max_val}")
                        return False
                        
                elif param_type == 'number':
                    min_val, max_val = param_spec[2], param_spec[3]
                    if not isinstance(value, (int, float)):
                        self.logger.error(f"Invalid type for {param_name}: expected number, got {type(value)}")
                        return False
                    if min_val is not None and value < min_val:
                        self.logger.error(f"Invalid value for {param_name}: {value} < {min_val}")
                        return False
                    if max_val is not None and value > max_val:
                        self.logger.error(f"Invalid value for {param_name}: {value} > {max_val}")
                        return False
                        
                elif param_type == 'number_or_null':
                    min_val, max_val = param_spec[2], param_spec[3]
                    if value is not None:
                        if not isinstance(value, (int, float)):
                            self.logger.error(f"Invalid type for {param_name}: expected number or null, got {type(value)}")
                            return False
                        if min_val is not None and value < min_val:
                            self.logger.error(f"Invalid value for {param_name}: {value} < {min_val}")
                            return False
                        if max_val is not None and value > max_val:
                            self.logger.error(f"Invalid value for {param_name}: {value} > {max_val}")
                            return False
                            
                elif param_type == 'string':
                    if not isinstance(value, str):
                        self.logger.error(f"Invalid type for {param_name}: expected string, got {type(value)}")
                        return False
                        
                elif param_type == 'enum':
                    valid_values = param_spec[2]
                    if not isinstance(value, str):
                        self.logger.error(f"Invalid type for {param_name}: expected string, got {type(value)}")
                        return False
                    if value not in valid_values:
                        self.logger.error(f"Invalid value for {param_name}: {value} not in {valid_values}")
                        return False
                        
                elif param_type == 'list':
                    if not isinstance(value, list):
                        self.logger.error(f"Invalid type for {param_name}: expected list, got {type(value)}")
                        return False
                
                # Cache the validated value
                self._config_cache[param_name] = value
            
            # Validate nested objects: quiet_hours
            quiet_hours = self.config.get('quiet_hours', {})
            if not isinstance(quiet_hours, dict):
                self.logger.error(f"Invalid type for quiet_hours: expected dict, got {type(quiet_hours)}")
                return False
            
            quiet_hours_config = {
                'enabled': quiet_hours.get('enabled', False),
                'start_time': quiet_hours.get('start_time', '22:00'),
                'end_time': quiet_hours.get('end_time', '06:00'),
                'timezone': quiet_hours.get('timezone', 'UTC')
            }
            
            # Validate quiet hours types
            if not isinstance(quiet_hours_config['enabled'], bool):
                self.logger.error("Invalid type for quiet_hours.enabled: expected boolean")
                return False
            if not isinstance(quiet_hours_config['start_time'], str):
                self.logger.error("Invalid type for quiet_hours.start_time: expected string")
                return False
            if not isinstance(quiet_hours_config['end_time'], str):
                self.logger.error("Invalid type for quiet_hours.end_time: expected string")
                return False
            if not isinstance(quiet_hours_config['timezone'], str):
                self.logger.error("Invalid type for quiet_hours.timezone: expected string")
                return False
            
            self._config_cache['quiet_hours'] = quiet_hours_config
            
            # Validate nested objects: congestion_detection
            congestion = self.config.get('congestion_detection', {})
            if not isinstance(congestion, dict):
                self.logger.error(f"Invalid type for congestion_detection: expected dict, got {type(congestion)}")
                return False
            
            congestion_config = {
                'enabled': congestion.get('enabled', True),
                'success_rate_threshold': congestion.get('success_rate_threshold', 0.5),
                'throttle_multiplier': congestion.get('throttle_multiplier', 0.5)
            }
            
            # Validate congestion detection types and ranges
            if not isinstance(congestion_config['enabled'], bool):
                self.logger.error("Invalid type for congestion_detection.enabled: expected boolean")
                return False
            if not isinstance(congestion_config['success_rate_threshold'], (int, float)):
                self.logger.error("Invalid type for congestion_detection.success_rate_threshold: expected number")
                return False
            if not (0.0 <= congestion_config['success_rate_threshold'] <= 1.0):
                self.logger.error("Invalid value for congestion_detection.success_rate_threshold: must be 0.0-1.0")
                return False
            if not isinstance(congestion_config['throttle_multiplier'], (int, float)):
                self.logger.error("Invalid type for congestion_detection.throttle_multiplier: expected number")
                return False
            if not (0.1 <= congestion_config['throttle_multiplier'] <= 1.0):
                self.logger.error("Invalid value for congestion_detection.throttle_multiplier: must be 0.1-1.0")
                return False
            
            self._config_cache['congestion_detection'] = congestion_config
            
            # Validate nested objects: emergency_stop
            emergency = self.config.get('emergency_stop', {})
            if not isinstance(emergency, dict):
                self.logger.error(f"Invalid type for emergency_stop: expected dict, got {type(emergency)}")
                return False
            
            emergency_config = {
                'enabled': emergency.get('enabled', True),
                'failure_threshold': emergency.get('failure_threshold', 0.2),
                'consecutive_failures': emergency.get('consecutive_failures', 10),
                'auto_recovery_minutes': emergency.get('auto_recovery_minutes', 30)
            }
            
            # Validate emergency stop types and ranges
            if not isinstance(emergency_config['enabled'], bool):
                self.logger.error("Invalid type for emergency_stop.enabled: expected boolean")
                return False
            if not isinstance(emergency_config['failure_threshold'], (int, float)):
                self.logger.error("Invalid type for emergency_stop.failure_threshold: expected number")
                return False
            if not (0.0 <= emergency_config['failure_threshold'] <= 1.0):
                self.logger.error("Invalid value for emergency_stop.failure_threshold: must be 0.0-1.0")
                return False
            if not isinstance(emergency_config['consecutive_failures'], int):
                self.logger.error("Invalid type for emergency_stop.consecutive_failures: expected integer")
                return False
            if not (1 <= emergency_config['consecutive_failures'] <= 100):
                self.logger.error("Invalid value for emergency_stop.consecutive_failures: must be 1-100")
                return False
            if not isinstance(emergency_config['auto_recovery_minutes'], (int, float)):
                self.logger.error("Invalid type for emergency_stop.auto_recovery_minutes: expected number")
                return False
            if not (1 <= emergency_config['auto_recovery_minutes'] <= 1440):
                self.logger.error("Invalid value for emergency_stop.auto_recovery_minutes: must be 1-1440")
                return False
            
            self._config_cache['emergency_stop'] = emergency_config
            
            # Convert seconds_between_traceroutes to traceroutes_per_minute for rate limiter
            seconds_between = self._config_cache['seconds_between_traceroutes']
            traceroutes_per_minute = 60.0 / seconds_between
            self._config_cache['traceroutes_per_minute'] = traceroutes_per_minute
            
            self.logger.info(
                f"Rate limit: {seconds_between} seconds between traceroutes "
                f"= {traceroutes_per_minute:.2f} traceroutes/minute"
            )
            
            # Special validation: rate limit of 0 disables operations
            if traceroutes_per_minute == 0:
                self.logger.warning("traceroutes_per_minute is 0, all traceroute operations will be disabled")
            
            # Special validation: recheck interval of 0 disables periodic rechecks
            if self._config_cache['recheck_interval_hours'] == 0:
                self.logger.info("recheck_interval_hours is 0, periodic rechecks are disabled")
            
            return True
            
        except FileNotFoundError:
            self.logger.error(f"Configuration schema file not found: {schema_path}")
            return False
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse configuration schema: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during configuration validation: {e}", exc_info=True)
            return False
    
    async def start(self) -> bool:
        """
        Start the plugin.
        
        This method:
        1. Loads persisted state (if enabled)
        2. Subscribes to traceroute response pubsub topic
        3. Starts background tasks (queue processing, periodic rechecks, state persistence)
        4. Runs initial discovery scan (if enabled)
        
        Returns:
            True if start successful, False otherwise
            
        Requirements: 1.1, 1.2, 8.1, 8.2, 8.3, 8.5
        """
        if not self.initialized:
            self.logger.error("Cannot start plugin: not initialized")
            return False
        
        self.logger.info("Starting Network Traceroute Mapper plugin")
        
        try:
            # Load persisted state if enabled
            if self._config_cache.get('state_persistence_enabled', False):
                self.logger.info("Loading persisted state...")
                try:
                    node_states = await self.state_persistence.load_state()
                    if node_states:
                        self.node_tracker.load_state(node_states)
                        self.logger.info(f"Loaded state for {len(node_states)} nodes")
                    else:
                        self.logger.info("No persisted state found, starting fresh")
                except Exception as e:
                    self.logger.error(f"Failed to load persisted state: {e}", exc_info=True)
                    self.logger.info("Continuing with empty state")
            
            # Subscribe to traceroute responses via pubsub
            try:
                from pubsub import pub
                pub.subscribe(self._on_traceroute_response, "meshtastic.receive.traceroute")
                self.logger.info("Subscribed to meshtastic.receive.traceroute pubsub topic")
            except Exception as e:
                self.logger.warning(f"Failed to subscribe to traceroute pubsub topic: {e}")
            
            # Clear queue on startup if configured
            if self._config_cache.get('clear_queue_on_startup', False):
                self.logger.info("Clearing queue on startup...")
                self.priority_queue.clear()
            
            # Start background tasks
            self.logger.info("Starting background tasks...")
            
            # Queue processing loop
            queue_task = asyncio.create_task(self._process_queue_loop())
            self._background_tasks.append(queue_task)
            self.logger.info("Started queue processing loop")
            
            # Periodic recheck loop (if enabled)
            if self._config_cache.get('recheck_enabled', True) and self._config_cache.get('recheck_interval_hours', 0) > 0:
                recheck_task = asyncio.create_task(self._periodic_recheck_loop())
                self._background_tasks.append(recheck_task)
                self.logger.info("Started periodic recheck loop")
            
            # State persistence loop (if enabled)
            if self._config_cache.get('state_persistence_enabled', False):
                persistence_task = asyncio.create_task(self._state_persistence_loop())
                self._background_tasks.append(persistence_task)
                self.logger.info("Started state persistence loop")
            
            # Timeout check loop
            timeout_task = asyncio.create_task(self._timeout_check_loop())
            self._background_tasks.append(timeout_task)
            self.logger.info("Started timeout check loop")
            
            # Run initial discovery scan if enabled
            if self._config_cache.get('initial_discovery_enabled', False):
                self.logger.info("Running initial discovery scan...")
                asyncio.create_task(self._run_initial_discovery())
            
            # Mark plugin as running
            self.is_running = True
            
            self.logger.info("Network Traceroute Mapper plugin started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start Network Traceroute Mapper plugin: {e}", exc_info=True)
            return False
    
    async def stop(self) -> bool:
        """
        Stop the plugin.
        
        This method:
        1. Unsubscribes from pubsub topics
        2. Stops background tasks
        3. Saves final state to disk
        4. Clears queue (if configured)
        5. Cleans up resources
        
        Returns:
            True if stop successful, False otherwise
            
        Requirements: 1.5
        """
        self.logger.info("Stopping Network Traceroute Mapper plugin")
        
        # Mark plugin as not running
        self.is_running = False
        
        try:
            # Unsubscribe from pubsub
            try:
                from pubsub import pub
                pub.unsubscribe(self._on_traceroute_response, "meshtastic.receive.traceroute")
                self.logger.info("Unsubscribed from traceroute pubsub topic")
            except Exception as e:
                self.logger.warning(f"Failed to unsubscribe from pubsub: {e}")
            
            # Stop background tasks
            self.logger.info("Stopping background tasks...")
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self._background_tasks.clear()
            self.logger.info("All background tasks stopped")
            
            # Save final state if persistence is enabled
            if self._config_cache.get('state_persistence_enabled', False) and self.node_tracker:
                self.logger.info("Saving final state...")
                try:
                    node_states = self.node_tracker.get_all_nodes()
                    await self.state_persistence.save_state(node_states)
                    self.logger.info(f"Saved state for {len(node_states)} nodes")
                except Exception as e:
                    self.logger.error(f"Failed to save final state: {e}", exc_info=True)
            
            # Clear queue if configured
            if self._config_cache.get('clear_queue_on_startup', False) and self.priority_queue:
                self.logger.info("Clearing queue...")
                self.priority_queue.clear()
            
            self.logger.info("Network Traceroute Mapper plugin stopped successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to stop Network Traceroute Mapper plugin: {e}", exc_info=True)
            return False
    
    async def handle_message(self, message: Message, user: Optional[Any] = None) -> Optional[Any]:
        """
        Handle incoming message from mesh.
        
        This is the public interface method that delegates to _handle_mesh_message().
        All message handling logic is implemented in _handle_mesh_message().
        
        Args:
            message: The incoming message
            user: Optional user profile (not used by this plugin)
            
        Returns:
            None (messages are forwarded to other plugins)
            
        Requirements: 2.1, 4.1, 4.2, 16.2, 16.3, 16.4
        """
        if not self.enabled or not self.initialized:
            return None
        
        try:
            # Create context dict for internal use
            context = {
                'timestamp': datetime.now(),
                'plugin_name': self.name
            }
            # Delegate to the actual message handler
            return await self._handle_mesh_message(message, context)
            
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)
            return None
    
    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get plugin health status.
        
        Returns comprehensive health status including:
        - Plugin state (enabled, initialized, emergency_stop)
        - Queue metrics (size, pending traceroutes)
        - Node metrics (tracked, direct, indirect)
        - Statistics (sent, successful, failed, success rate)
        - Network health (throttled, quiet hours)
        
        Returns:
            Dictionary with health status information
            
        Requirements: 15.5, 15.6
        """
        try:
            # Get component statistics
            queue_size = self.priority_queue.size() if self.priority_queue else 0
            pending_traceroutes = self.traceroute_manager.get_pending_count() if self.traceroute_manager else 0
            
            # Get node statistics
            node_stats = self.node_tracker.get_statistics() if self.node_tracker else {}
            nodes_tracked = node_stats.get('total_nodes', 0)
            direct_nodes = node_stats.get('direct_nodes', 0)
            indirect_nodes = node_stats.get('indirect_nodes', 0)
            
            # Get health monitor status
            is_emergency_stop = self.health_monitor.is_emergency_stop if self.health_monitor else False
            is_throttled = self.health_monitor.should_throttle() if self.health_monitor else False
            is_quiet_hours = self.health_monitor.is_quiet_hours() if self.health_monitor else False
            
            # Calculate success rate
            success_rate = 0.0
            if self.stats['traceroutes_sent'] > 0:
                success_rate = self.stats['traceroutes_successful'] / self.stats['traceroutes_sent']
            
            # Get current rate (may be throttled)
            base_rate = self._config_cache.get('traceroutes_per_minute', 1)
            current_rate = base_rate
            if self.health_monitor:
                current_rate = self.health_monitor.get_recommended_rate(base_rate)
            
            return {
                'healthy': self.enabled and self.initialized and not is_emergency_stop,
                'enabled': self.enabled,
                'initialized': self.initialized,
                'emergency_stop': is_emergency_stop,
                'queue_size': queue_size,
                'pending_traceroutes': pending_traceroutes,
                'nodes_tracked': nodes_tracked,
                'direct_nodes': direct_nodes,
                'indirect_nodes': indirect_nodes,
                'traceroutes_sent': self.stats['traceroutes_sent'],
                'traceroutes_successful': self.stats['traceroutes_successful'],
                'traceroutes_failed': self.stats['traceroutes_failed'],
                'traceroutes_timeout': self.stats['traceroutes_timeout'],
                'success_rate': success_rate,
                'last_traceroute_time': self.stats.get('last_traceroute_time'),
                'current_rate': current_rate,
                'base_rate': base_rate,
                'is_throttled': is_throttled,
                'is_quiet_hours': is_quiet_hours,
                'direct_nodes_skipped': self.stats['direct_nodes_skipped'],
                'filtered_nodes_skipped': self.stats['filtered_nodes_skipped']
            }
            
        except Exception as e:
            self.logger.error(f"Error getting health status: {e}", exc_info=True)
            return {
                'healthy': False,
                'error': str(e)
            }
    
    async def _process_queue_loop(self) -> None:
        """
        Background task to process the traceroute queue.
        
        This loop:
        1. Checks if we should process (not in quiet hours, not emergency stop)
        2. Dequeues the next request
        3. Waits for rate limiter
        4. Sends the traceroute request
        """
        self.logger.info("Queue processing loop started")
        
        # Wait for startup delay
        startup_delay = self._config_cache.get('startup_delay_seconds', 60)
        if startup_delay > 0:
            self.logger.info(f"Waiting {startup_delay}s before processing queue (startup delay)")
            await asyncio.sleep(startup_delay)
        
        while True:
            try:
                # Check if we should process queue
                if not self._should_process_queue():
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
                # Check if queue has requests
                if self.priority_queue.is_empty():
                    await asyncio.sleep(10)  # Check again in 10 seconds
                    continue
                
                # Dequeue next request
                request = self.priority_queue.dequeue()
                if not request:
                    continue
                
                self.logger.debug(
                    f"Dequeued traceroute request: node={request.node_id}, "
                    f"priority={request.priority}, reason={request.reason}, "
                    f"queue_size={self.priority_queue.size()}"
                )
                
                # Wait for rate limiter
                await self.rate_limiter.acquire()
                
                # Send traceroute
                await self._send_traceroute_request(request)
                
                # Update queue size stat
                self.stats['queue_size'] = self.priority_queue.size()
                
            except asyncio.CancelledError:
                self.logger.info("Queue processing loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in queue processing loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _periodic_recheck_loop(self) -> None:
        """
        Background task to schedule periodic rechecks for nodes.
        
        This loop checks the database for nodes that are past due for traceroute
        and queues them with appropriate priority.
        """
        self.logger.info("Periodic recheck loop started")
        
        check_interval_seconds = 60  # Check every 1 minute for faster queuing
        
        while True:
            try:
                await asyncio.sleep(check_interval_seconds)
                
                # Get configuration
                active_hours = self._config_cache.get('active_node_hours', 24)
                skip_direct = self._config_cache.get('skip_direct_nodes', True)
                
                # Get nodes from database that need traceroute
                try:
                    from core.database import get_database
                    db = get_database()
                    
                    # Find nodes that are:
                    # - Active (seen recently)
                    # - Past due for traceroute
                    # - Not already in queue
                    query = """
                        SELECT node_id, hop_count, snr, last_traceroute_success, next_traceroute_time
                        FROM users 
                        WHERE last_seen > datetime('now', '-{} hours')
                        AND (next_traceroute_time IS NULL OR next_traceroute_time <= datetime('now'))
                    """.format(active_hours)
                    
                    rows = db.execute_query(query)
                    
                    queued_count = 0
                    skipped_in_queue = 0
                    skipped_direct = 0
                    skipped_should_not_trace = 0
                    
                    for row in rows:
                        node_id = row[0]
                        hop_count = row[1]
                        snr = row[2]
                        last_success = row[3]
                        next_time = row[4]
                        
                        # Skip if already in queue
                        if self.priority_queue.contains(node_id):
                            skipped_in_queue += 1
                            self.logger.debug(f"Skipping {node_id} - already in queue")
                            continue
                        
                        # Check node_tracker for current state (more accurate than database)
                        node_state = self.node_tracker.get_node_state(node_id)
                        
                        # Determine if node is direct using both database and tracker
                        is_direct = False
                        
                        # First check tracker (most accurate, real-time)
                        if node_state and node_state.is_direct:
                            is_direct = True
                        # Fall back to database values if no tracker state
                        else:
                            # Check hop_count first (most reliable indicator)
                            if hop_count is not None and hop_count < 1:
                                is_direct = True
                            # For nodes with successful traceroutes, also check SNR
                            elif last_success is True and snr is not None and snr > 5.0:
                                is_direct = True
                        
                        # Skip direct nodes if configured
                        # BUT: Never skip nodes that have failed traceroutes - we need to retry them
                        if is_direct and skip_direct and last_success is not False:
                            skipped_direct += 1
                            self.logger.debug(f"Skipping direct node {node_id} in periodic recheck")
                            continue
                        
                        # Ensure node is in tracker before checking if it should be traced
                        # This is important for nodes that haven't sent messages recently
                        if not node_state:
                            self.node_tracker.update_node(
                                node_id=node_id,
                                is_direct=is_direct,
                                snr=snr,
                                rssi=None,
                                hop_count=hop_count
                            )
                        
                        # Check if node should be traced (filters, blacklist, etc.)
                        if not self.node_tracker.should_trace_node(node_id):
                            skipped_should_not_trace += 1
                            self.logger.debug(f"Skipping {node_id} - should_trace_node returned False")
                            continue
                        
                        # Determine priority
                        if last_success is False:
                            priority = 5  # RETRY priority
                            reason = "retry_failed"
                        else:
                            priority = 8  # PERIODIC_RECHECK priority
                            reason = "periodic_recheck"
                        
                        # Queue the traceroute
                        if self.priority_queue.enqueue(
                            node_id=node_id,
                            priority=priority,
                            reason=reason
                        ):
                            queued_count += 1
                            self.logger.debug(
                                f"Queued periodic recheck for node {node_id}: "
                                f"hop_count={hop_count}, snr={snr}, is_direct={is_direct}, "
                                f"priority={priority}, reason={reason}"
                            )
                            
                            # Set next_traceroute_time to now if it's NULL
                            # This prevents nodes from showing as "pending" in the dashboard
                            if next_time is None:  # next_traceroute_time is NULL
                                try:
                                    db.execute_update("""
                                        UPDATE users 
                                        SET next_traceroute_time = datetime('now')
                                        WHERE node_id = ?
                                    """, (node_id,))
                                except Exception as e:
                                    self.logger.error(f"Error setting next_traceroute_time for {node_id}: {e}")
                    
                    if queued_count > 0:
                        self.logger.info(
                            f"Periodic recheck: queued {queued_count} nodes "
                            f"(skipped: {skipped_in_queue} in queue, {skipped_direct} direct, "
                            f"{skipped_should_not_trace} filtered)"
                        )
                    else:
                        self.logger.debug(
                            f"Periodic recheck: no nodes queued from {len(rows)} candidates "
                            f"(skipped: {skipped_in_queue} in queue, {skipped_direct} direct, "
                            f"{skipped_should_not_trace} filtered)"
                        )
                        
                except Exception as e:
                    self.logger.error(f"Error in periodic recheck database query: {e}", exc_info=True)
                
            except asyncio.CancelledError:
                self.logger.info("Periodic recheck loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in periodic recheck loop: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _state_persistence_loop(self) -> None:
        """
        Background task to periodically save state to disk.
        """
        self.logger.info("State persistence loop started")
        
        auto_save_interval = self._config_cache.get('auto_save_interval_minutes', 5)
        save_interval_seconds = auto_save_interval * 60
        
        while True:
            try:
                await asyncio.sleep(save_interval_seconds)
                
                # Save state
                node_states = self.node_tracker.get_all_nodes()
                success = await self.state_persistence.save_state(node_states)
                
                if success:
                    self.logger.debug(f"Auto-saved state for {len(node_states)} nodes")
                else:
                    self.logger.warning("Failed to auto-save state")
                
            except asyncio.CancelledError:
                self.logger.info("State persistence loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in state persistence loop: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _timeout_check_loop(self) -> None:
        """
        Background task to check for timed out traceroute requests.
        """
        self.logger.info("Timeout check loop started")
        
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                # Check for timeouts
                timed_out = self.traceroute_manager.check_timeouts()
                
                # Handle timed out requests
                for pending in timed_out:
                    self.logger.warning(
                        f"Traceroute to {pending.node_id} timed out "
                        f"(request_id={pending.request_id})"
                    )
                    
                    # Record failure
                    self.health_monitor.record_failure(is_timeout=True)
                    self.stats['traceroutes_failed'] += 1
                    self.stats['traceroutes_timeout'] += 1
                    
                    # Mark node as traced (failed)
                    self.node_tracker.mark_node_traced(pending.node_id, success=False)
                    
                    # Update database schedule for retry
                    await self._update_traceroute_schedule(pending.node_id, success=False)
                    
                    # Schedule retry if retries remain
                    if pending.retry_count < pending.max_retries:
                        await self.traceroute_manager.schedule_retry(pending)
                        # Re-queue the request
                        self.priority_queue.enqueue(
                            node_id=pending.node_id,
                            priority=pending.priority,
                            reason=f"retry_{pending.retry_count}"
                        )
                
            except asyncio.CancelledError:
                self.logger.info("Timeout check loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in timeout check loop: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _run_initial_discovery(self) -> None:
        """
        Run initial discovery scan for nodes that are due for traceroute.
        Only queues nodes that:
        - Are active (seen recently)
        - Are indirect (not direct connection)
        - Are past due for traceroute (next_traceroute_time is in the past or NULL)
        """
        try:
            self.logger.info("Running initial discovery scan...")
            
            # Get configuration
            active_hours = self._config_cache.get('active_node_hours', 24)
            skip_direct = self._config_cache.get('skip_direct_nodes', True)
            
            # Get nodes from database that need traceroute
            try:
                from core.database import get_database
                db = get_database()
                
                # Build query to find nodes needing traceroute
                query = """
                    SELECT node_id, hop_count, snr, last_seen, 
                           next_traceroute_time, last_traceroute_success
                    FROM users 
                    WHERE last_seen > datetime('now', '-{} hours')
                    AND (next_traceroute_time IS NULL OR next_traceroute_time <= datetime('now'))
                """.format(active_hours)
                
                rows = db.execute_query(query)
                
                self.logger.info(f"Found {len(rows)} nodes due for traceroute from last {active_hours} hours")
                
                # Process each node
                queued_count = 0
                skipped_direct = 0
                skipped_filtered = 0
                
                for row in rows:
                    node_id = row[0]
                    hop_count = row[1]
                    snr = row[2]
                    last_seen = row[3]
                    next_traceroute_time = row[4]
                    last_success = row[5]
                    
                    # Determine if node is direct based on hop count and SNR (0 hops = direct)
                    is_direct = False
                    if hop_count is not None and hop_count < 1:
                        is_direct = True
                    elif snr is not None and snr > 5.0:
                        is_direct = True
                    
                    # Skip direct nodes if configured
                    if is_direct and skip_direct:
                        skipped_direct += 1
                        continue
                    
                    # Update node tracker
                    self.node_tracker.update_node(
                        node_id=node_id,
                        is_direct=is_direct,
                        snr=snr,
                        rssi=None,
                        hop_count=hop_count
                    )
                    
                    # Check if node should be traced (filters, blacklist, etc.)
                    if not self.node_tracker.should_trace_node(node_id):
                        skipped_filtered += 1
                        continue
                    
                    # Determine priority based on status
                    priority = 1  # NEW_NODE priority (highest)
                    reason = "initial_discovery"
                    
                    if next_traceroute_time is not None:
                        # Node has been traced before
                        if last_success is False:
                            priority = 5  # RETRY priority
                            reason = "retry_failed"
                        else:
                            priority = 8  # PERIODIC_RECHECK priority
                            reason = "periodic_recheck"
                    
                    # Queue traceroute for indirect nodes
                    if self.priority_queue.enqueue(
                        node_id=node_id,
                        priority=priority,
                        reason=reason
                    ):
                        queued_count += 1
                
                self.logger.info(
                    f"Initial discovery complete: queued {queued_count} nodes "
                    f"(skipped {skipped_direct} direct, {skipped_filtered} filtered)"
                )
                
            except Exception as e:
                self.logger.error(f"Error loading nodes from database: {e}", exc_info=True)
                self.logger.info("Initial discovery failed")
            
        except Exception as e:
            self.logger.error(f"Error in initial discovery scan: {e}", exc_info=True)
    
    def _should_process_queue(self) -> bool:
        """
        Check if we should process the queue based on network health.
        
        Returns:
            True if we should process, False otherwise
        """
        # Check if rate is zero (disabled)
        rate = self._config_cache.get('traceroutes_per_minute', 1)
        if rate == 0:
            self.logger.warning("Queue processing disabled: rate limit is 0")
            return False
        
        # Check for emergency stop
        if self.health_monitor.is_emergency_stop:
            self.logger.warning(
                f"Queue processing paused: emergency stop active - "
                f"reason={self.health_monitor.emergency_stop_reason}"
            )
            return False
        
        # Check for quiet hours
        if self.health_monitor.is_quiet_hours():
            self.logger.info("Queue processing paused: quiet hours active")
            return False
        
        # Check network health
        if not self.health_monitor.is_healthy():
            success_rate = self.health_monitor.get_success_rate()
            self.logger.warning(
                f"Queue processing paused: network unhealthy - "
                f"success_rate={success_rate:.2%}, "
                f"threshold={self.health_monitor.failure_threshold:.2%}, "
                f"emergency_stop={self.health_monitor.is_emergency_stop}"
            )
            return False
        
        self.logger.debug(
            f"Queue processing active: rate={rate}/min, "
            f"queue_size={self.priority_queue.size()}, "
            f"success_rate={self.health_monitor.get_success_rate():.2%}"
        )
        return True
    
    async def _send_traceroute_request(self, request) -> None:
        """
        Send a traceroute request using the native meshtastic library method.
        
        Args:
            request: TracerouteRequest object from the queue
            
        Requirements:
            - 7.1: Use native meshtastic sendTraceRoute method
            - 7.3: Proper protocol compliance via library
            - 14.1: Responses handled via pubsub subscription
        """
        try:
            # Get the meshtastic interface from the message router
            meshtastic_interface = None
            if self.plugin_manager and hasattr(self.plugin_manager, 'message_router'):
                message_router = self.plugin_manager.message_router
                if hasattr(message_router, 'interfaces') and message_router.interfaces:
                    # Get the first available interface
                    interface_id = list(message_router.interfaces.keys())[0]
                    interface_wrapper = message_router.interfaces[interface_id]
                    
                    # Get the actual meshtastic connection object
                    if hasattr(interface_wrapper, 'connection'):
                        meshtastic_interface = interface_wrapper.connection
                        self.logger.debug(f"Got meshtastic interface connection from {interface_id}")
            
            if not meshtastic_interface:
                self.logger.error("No meshtastic interface available for traceroute")
                self.health_monitor.record_failure()
                self.stats['traceroutes_failed'] += 1
                return
            
            # Send traceroute via manager with native method
            request_id = await self.traceroute_manager.send_traceroute(
                node_id=request.node_id,
                priority=request.priority,
                meshtastic_interface=meshtastic_interface
            )
            
            if self._config_cache.get('log_traceroute_requests', True):
                self.logger.info(
                    f"Traceroute request sent to {request.node_id} "
                    f"(request_id={request_id}, priority={request.priority}, "
                    f"reason={request.reason})"
                )
            
            # Update statistics
            self.stats['traceroutes_sent'] += 1
            self.stats['last_traceroute_time'] = datetime.now()
            
        except Exception as e:
            self.logger.error(
                f"Error sending traceroute to {request.node_id}: {e}",
                exc_info=True
            )
            # Record failure
            self.health_monitor.record_failure()
            self.stats['traceroutes_failed'] += 1
    
    def _on_traceroute_response(self, packet: dict, interface: Any):
        """
        Handle traceroute response from pubsub.
        
        This is called by the meshtastic library's pubsub system when a
        traceroute response is received on the "meshtastic.receive.traceroute" topic.
        
        Args:
            packet: The packet dictionary from meshtastic
            interface: The meshtastic interface that received the packet
        """
        try:
            self.logger.debug(f"Received traceroute response via pubsub: {packet}")
            
            # Convert the meshtastic packet to our Message format
            from models.message import Message, MessageType, MessagePriority
            
            # Extract route data from the decoded traceroute protobuf
            decoded = packet.get('decoded', {})
            traceroute_data = decoded.get('traceroute', {})
            
            # Parse route information
            route = traceroute_data.get('route', [])
            route_back = traceroute_data.get('routeBack', [])
            snr_towards = traceroute_data.get('snrTowards', [])
            snr_back = traceroute_data.get('snrBack', [])
            
            # Convert SNR values from quarter-dB to dB (divide by 4)
            snr_towards_db = [snr / 4.0 for snr in snr_towards] if snr_towards else []
            snr_back_db = [snr / 4.0 for snr in snr_back] if snr_back else []
            
            # Create Message object
            message = Message(
                id=str(packet.get('id', '')),
                sender_id=packet.get('fromId', ''),
                recipient_id=packet.get('toId', ''),
                channel=packet.get('channel', 0),
                content="",  # Traceroute responses have no text content
                message_type=MessageType.ROUTING,
                priority=MessagePriority.NORMAL,
                hop_count=len(route),
                snr=packet.get('rxSnr'),
                rssi=packet.get('rxRssi'),
                metadata={
                    'traceroute': True,
                    'route': route,
                    'route_back': route_back,
                    'snr_values': snr_towards_db,
                    'snr_back_values': snr_back_db,
                    'raw_packet': packet
                }
            )
            
            # Schedule async handling
            if self.is_running:
                asyncio.create_task(self._handle_traceroute_response(message))
            
        except Exception as e:
            self.logger.error(f"Error handling traceroute response from pubsub: {e}", exc_info=True)
    
    async def _handle_mesh_message(self, message: Message, context: Dict[str, Any]) -> Optional[Any]:
        """
        Handle incoming mesh message.
        
        This method:
        - Updates node state tracker
        - Detects traceroute responses
        - Detects new node discoveries
        - Queues traceroute requests as needed
        
        Args:
            message: The incoming message
            context: Message context
            
        Returns:
            None (messages are forwarded to other plugins)
            
        Requirements: 2.1, 4.1, 4.2, 16.2, 16.3, 16.4
        """
        try:
            # Extract node information from message
            sender_id = message.sender_id
            if not sender_id:
                return None
            
            # Determine if node is direct based on hop count and signal strength
            is_direct = self._is_direct_node(message)
            
            # Get previous node state before updating
            previous_state = self.node_tracker.get_node_state(sender_id)
            was_previously_indirect = previous_state and not previous_state.is_direct if previous_state else False
            was_offline = previous_state.was_offline if previous_state else False
            
            # Update node state tracker
            self.node_tracker.update_node(
                node_id=sender_id,
                is_direct=is_direct,
                snr=message.snr,
                rssi=message.rssi
            )
            
            # Check if this is a traceroute response
            if self._is_traceroute_response(message):
                await self._handle_traceroute_response(message)
                return None
            
            # Get updated node state
            node_state = self.node_tracker.get_node_state(sender_id)
            if not node_state:
                return None
            
            # Check for direct node transition (was indirect, now direct)
            if was_previously_indirect and is_direct:
                self.logger.debug(f"Node {sender_id} transitioned from indirect to direct")
                await self._handle_direct_node_transition(sender_id)
                return None
            
            # Skip direct nodes (don't queue traceroutes for them)
            if is_direct:
                self.logger.debug(f"Skipping direct node {sender_id}")
                return None
            
            # Check for node coming back online
            if was_offline:
                self.logger.debug(f"Node {sender_id} came back online")
                await self._handle_node_back_online(sender_id)
                return None
            
            # Check if this is a newly discovered indirect node
            if not is_direct and node_state.trace_count == 0 and not was_previously_indirect:
                self.logger.debug(f"Discovered new indirect node {sender_id}")
                await self._handle_new_indirect_node(sender_id)
                return None
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error handling mesh message: {e}", exc_info=True)
            return None
    
    def _is_direct_node(self, message: Message) -> bool:
        """
        Determine if a node is directly heard based on message properties.
        
        Args:
            message: The message to analyze
            
        Returns:
            True if node is direct, False otherwise
        """
        # Check hop count (0 indicates direct connection)
        if message.hop_count is not None and message.hop_count < 1:
            return True
        
        # Check signal strength (strong signal indicates direct)
        if message.snr is not None and message.snr > 5.0:
            return True
        
        # Check if in neighbor list (from metadata)
        if message.metadata.get('is_neighbor', False):
            return True
        
        return False
    
    def _is_traceroute_response(self, message: Message) -> bool:
        """
        Check if message is a traceroute response.
        
        Args:
            message: The message to check
            
        Returns:
            True if traceroute response, False otherwise
        """
        # Check message type
        if message.message_type != MessageType.ROUTING and message.message_type != MessageType.TRACEROUTE:
            return False
        
        # Skip ACKs (marked explicitly as ACKs)
        if message.metadata.get('traceroute_ack'):
            self.logger.debug(f"Skipping traceroute ACK from {message.sender_id}")
            return False
        
        # Check for traceroute flag in metadata
        if not message.metadata.get('traceroute', False):
            return False
        
        # Accept responses with route data OR direct node responses (empty route but valid)
        route = message.metadata.get('route', [])
        route_back = message.metadata.get('route_back', [])
        is_direct = message.metadata.get('direct_node', False)
        
        # Valid if: has route data OR is marked as direct node response
        if route or route_back or is_direct:
            return True
        
        self.logger.debug(f"Skipping ROUTING message - not a valid traceroute response from {message.sender_id}")
        return False
    
    async def _handle_traceroute_response(self, message: Message) -> None:
        """
        Handle a traceroute response message.
        
        Args:
            message: The traceroute response message
            
        Requirements:
            - 7.2: Forward traceroute responses to message router
            - 14.4: Preserve all message fields including route array
            - 14.5: Forward responses from other nodes as well
        """
        try:
            # Forward to message router FIRST (before processing)
            # This ensures ALL traceroute messages are forwarded, not just our requests
            # Requirements: 7.2, 14.1, 14.4, 14.5
            if self.plugin_manager and hasattr(self.plugin_manager, 'message_router'):
                try:
                    # Forward the message to message router for MQTT publishing
                    # This will forward responses from other nodes as well, not just our requests
                    await self.plugin_manager.message_router.send_message(message)
                    
                    if self._config_cache.get('log_traceroute_responses', True):
                        self.logger.debug(
                            f"Forwarded traceroute response from {message.sender_id} to message router"
                        )
                except Exception as e:
                    self.logger.error(
                        f"Error forwarding traceroute response to message router: {e}",
                        exc_info=True
                    )
            
            # Check if this was one of our pending requests
            # Match by node ID since Meshtastic responses don't include our internal request_id
            request_id = message.metadata.get('request_id')
            pending = None
            
            # First try to match by request_id if available
            if request_id:
                pending = self.traceroute_manager.get_pending_traceroute(request_id)
            
            # If no match by request_id, try to match by node ID
            # This handles cases where the response doesn't have our internal request_id
            if not pending:
                # The response is FROM a node, but we need to find which node we were TRACING
                # Check all pending requests to see if any match this sender
                pending = self.traceroute_manager.get_pending_for_node(message.sender_id)
                
                if pending:
                    self.logger.info(
                        f"Matched traceroute response from {message.sender_id} to pending request "
                        f"for node {pending.node_id} (matched by node ID)"
                    )
            
            # Forward to traceroute manager (this will remove it from pending)
            result = await self.traceroute_manager.handle_traceroute_response(message)
            
            # If this was one of our pending requests and it was successful
            if pending and result:
                # Get the actual hop count from the traceroute result
                actual_hop_count = result.hop_count
                
                # Update database with the actual hop count from traceroute
                try:
                    from core.database import get_database
                    db = get_database()
                    db.execute_update("""
                        UPDATE users 
                        SET hop_count = ?
                        WHERE node_id = ?
                    """, (actual_hop_count, pending.node_id))
                    
                    self.logger.debug(
                        f"Updated database hop_count={actual_hop_count} for node {pending.node_id}"
                    )
                except Exception as e:
                    self.logger.error(f"Error updating hop_count in database: {e}")
                
                # Determine if node is actually direct based on traceroute result
                is_actually_direct = actual_hop_count < 1
                
                # Ensure node exists in tracker with correct direct status
                if not self.node_tracker.get_node_state(pending.node_id):
                    # Add the node to tracker
                    self.node_tracker.update_node(
                        node_id=pending.node_id,
                        is_direct=is_actually_direct,
                        snr=message.snr,
                        rssi=message.rssi
                    )
                else:
                    # Update existing node with correct direct status
                    self.node_tracker.update_node(
                        node_id=pending.node_id,
                        is_direct=is_actually_direct,
                        snr=message.snr,
                        rssi=message.rssi
                    )
                
                # If node turned out to be direct, handle the transition
                if is_actually_direct:
                    self.logger.info(
                        f"Traceroute revealed {pending.node_id} is actually a direct node (0 hops)"
                    )
                    await self._handle_direct_node_transition(pending.node_id)
                    # Don't schedule next traceroute for direct nodes
                    return
                
                # Record success
                self.health_monitor.record_success()
                self.stats['traceroutes_successful'] += 1
                
                # Mark node as traced
                self.node_tracker.mark_node_traced(pending.node_id, success=True)
                
                # Update database schedule for next traceroute
                await self._update_traceroute_schedule(pending.node_id, success=True)
                
                # Save traceroute history
                if self._config_cache.get('state_persistence_enabled', False):
                    route = message.metadata.get('route', [])
                    snr_values = message.metadata.get('snr_values', [])
                    rssi_values = message.metadata.get('rssi_values', [])
                    
                    result_data = {
                        'timestamp': datetime.now(),
                        'success': True,
                        'hop_count': len(route),
                        'route': route,
                        'snr_values': snr_values,
                        'rssi_values': rssi_values,
                        'duration_ms': (datetime.now() - pending.sent_at).total_seconds() * 1000
                    }
                    
                    await self.state_persistence.save_traceroute_history(
                        pending.node_id,
                        result_data
                    )
            
        except Exception as e:
            self.logger.error(f"Error handling traceroute response: {e}", exc_info=True)
    
    async def _handle_new_indirect_node(self, node_id: str) -> None:
        """
        Handle discovery of a new indirect node.
        
        Args:
            node_id: The node ID
            
        Requirements: 4.1
        """
        try:
            # Check if node should be traced
            if not self.node_tracker.should_trace_node(node_id):
                self.stats['filtered_nodes_skipped'] += 1
                self.logger.debug(f"Skipping filtered node {node_id}")
                return
            
            # Set initial next_traceroute_time to now so it gets queued immediately
            # This prevents the node from showing as "pending" in the dashboard
            try:
                from core.database import get_database
                db = get_database()
                now = datetime.utcnow()
                
                db.execute_update("""
                    UPDATE users 
                    SET next_traceroute_time = ?
                    WHERE node_id = ? AND next_traceroute_time IS NULL
                """, (now, node_id))
                
                self.logger.debug(f"Set initial next_traceroute_time for new node {node_id}")
            except Exception as e:
                self.logger.error(f"Error setting initial traceroute time for {node_id}: {e}")
            
            # Queue traceroute with NEW_NODE priority (1 = highest)
            if self.priority_queue.enqueue(
                node_id=node_id,
                priority=1,
                reason="new_indirect_node"
            ):
                self.stats['nodes_discovered'] += 1
                self.logger.info(f"Queued traceroute for new indirect node {node_id} (priority=1)")
            else:
                self.logger.warning(f"Failed to queue traceroute for new node {node_id} (queue full)")
            
        except Exception as e:
            self.logger.error(f"Error handling new indirect node {node_id}: {e}", exc_info=True)
    
    async def _handle_node_back_online(self, node_id: str) -> None:
        """
        Handle a node coming back online.
        Only queue traceroute if node is past due.
        
        Args:
            node_id: The node ID
            
        Requirements: 4.2
        """
        try:
            # Check if node should be traced
            if not self.node_tracker.should_trace_node(node_id):
                return
            
            # Check if node is past due for traceroute
            try:
                from core.database import get_database
                db = get_database()
                
                rows = db.execute_query("""
                    SELECT next_traceroute_time 
                    FROM users 
                    WHERE node_id = ?
                """, (node_id,))
                
                if rows and rows[0][0]:
                    next_time_str = rows[0][0]
                    next_time = datetime.fromisoformat(next_time_str)
                    
                    # Only queue if past due
                    if next_time > datetime.utcnow():
                        self.logger.debug(
                            f"Node {node_id} back online but not due for traceroute until {next_time}"
                        )
                        # Clear the was_offline flag
                        node_state = self.node_tracker.get_node_state(node_id)
                        if node_state:
                            node_state.was_offline = False
                        return
                
            except Exception as e:
                self.logger.error(f"Error checking traceroute schedule for {node_id}: {e}")
                # Continue with queueing on error
            
            # Queue traceroute with NODE_BACK_ONLINE priority (4)
            if self.priority_queue.enqueue(
                node_id=node_id,
                priority=4,
                reason="node_back_online"
            ):
                self.logger.info(f"Queued traceroute for node back online {node_id} (priority=4)")
            
            # Clear the was_offline flag
            node_state = self.node_tracker.get_node_state(node_id)
            if node_state:
                node_state.was_offline = False
            
        except Exception as e:
            self.logger.error(f"Error handling node back online {node_id}: {e}", exc_info=True)
    
    async def _handle_direct_node_transition(self, node_id: str) -> None:
        """
        Handle a node transitioning from indirect to direct.
        
        Args:
            node_id: The node ID
            
        Requirements: 2.2
        """
        try:
            # Remove any pending traceroute requests for this node
            if self.priority_queue.contains(node_id):
                self.priority_queue.remove(node_id)
                self.stats['direct_nodes_skipped'] += 1
                self.logger.info(
                    f"Node {node_id} became direct, removed pending traceroute request"
                )
            
            # Cancel any pending traceroute in the manager
            # (This will be handled by the manager's timeout check)
            
        except Exception as e:
            self.logger.error(f"Error handling direct node transition {node_id}: {e}", exc_info=True)
    
    async def _update_traceroute_schedule(self, node_id: str, success: bool) -> None:
        """
        Update the traceroute schedule in the database after a traceroute attempt.
        
        Args:
            node_id: The node ID
            success: Whether the traceroute was successful
        """
        try:
            from core.database import get_database
            from datetime import timedelta
            
            db = get_database()
            now = datetime.utcnow()
            
            # Get configuration
            if success:
                # Schedule next traceroute based on interval
                interval_minutes = self._config_cache.get('traceroute_interval_minutes', 180)
                next_time = now + timedelta(minutes=interval_minutes)
                failure_count = 0
            else:
                # Schedule retry based on retry interval
                retry_minutes = self._config_cache.get('traceroute_retry_minutes', 30)
                next_time = now + timedelta(minutes=retry_minutes)
                # Increment failure count
                failure_count = None  # Will be incremented in SQL
            
            # Update database
            if success:
                db.execute_update("""
                    UPDATE users 
                    SET last_traceroute_time = ?,
                        last_traceroute_success = ?,
                        next_traceroute_time = ?,
                        traceroute_failure_count = 0
                    WHERE node_id = ?
                """, (now, True, next_time, node_id))
                
                self.logger.debug(
                    f"Scheduled next traceroute for {node_id} at {next_time} "
                    f"({interval_minutes} minutes from now)"
                )
            else:
                db.execute_update("""
                    UPDATE users 
                    SET last_traceroute_time = ?,
                        last_traceroute_success = ?,
                        next_traceroute_time = ?,
                        traceroute_failure_count = traceroute_failure_count + 1
                    WHERE node_id = ?
                """, (now, False, next_time, node_id))
                
                self.logger.debug(
                    f"Scheduled retry traceroute for {node_id} at {next_time} "
                    f"({retry_minutes} minutes from now)"
                )
                
        except Exception as e:
            self.logger.error(f"Error updating traceroute schedule for {node_id}: {e}", exc_info=True)
    
    async def _check_node_active(self, node_id: str) -> bool:
        """
        Check if a node is still active (seen recently).
        
        Args:
            node_id: The node ID
            
        Returns:
            True if node is active, False otherwise
        """
        try:
            from core.database import get_database
            
            db = get_database()
            active_hours = self._config_cache.get('active_node_hours', 24)
            
            rows = db.execute_query("""
                SELECT COUNT(*) 
                FROM users 
                WHERE node_id = ? 
                AND last_seen > datetime('now', '-{} hours')
            """.format(active_hours), (node_id,))
            
            return rows[0][0] > 0 if rows else False
            
        except Exception as e:
            self.logger.error(f"Error checking if node {node_id} is active: {e}", exc_info=True)
            return False
    
    def get_metadata(self) -> PluginMetadata:
        """
        Get plugin metadata.
        
        Returns:
            Plugin metadata object
        """
        return PluginMetadata(
            name=self.name,
            version="1.2.0",
            description="Network Traceroute Mapper for automated mesh network topology discovery",
            author="ZephyrGate Team"
        )
