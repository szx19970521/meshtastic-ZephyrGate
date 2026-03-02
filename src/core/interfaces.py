"""
Meshtastic Interface Management for ZephyrGate

Handles serial, TCP, and BLE connections to Meshtastic devices with
automatic reconnection and multiple simultaneous interface support.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
import uuid

try:
    from ..models.message import Message, MessageType, InterfaceConfig
except ImportError:
    from models.message import Message, MessageType, InterfaceConfig
from .logging import get_logger


class InterfaceStatus(Enum):
    """Interface connection status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ConnectionAttempt:
    """Connection attempt tracking"""
    timestamp: datetime
    success: bool
    error: Optional[str] = None


@dataclass
class InterfaceStats:
    """Interface statistics"""
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connection_attempts: int = 0
    successful_connections: int = 0
    last_message_time: Optional[datetime] = None
    uptime_start: Optional[datetime] = None
    
    def get_uptime(self) -> Optional[timedelta]:
        """Get interface uptime"""
        if self.uptime_start:
            return datetime.utcnow() - self.uptime_start
        return None


class MeshtasticInterface(ABC):
    """Abstract base class for Meshtastic interfaces"""
    
    def __init__(self, config: InterfaceConfig, message_callback: Callable[[Message, str], None]):
        self.config = config
        self.message_callback = message_callback
        self.logger = get_logger(f'interface_{config.id}')
        
        self.status = InterfaceStatus.DISCONNECTED
        self.connection = None
        self.stats = InterfaceStats()
        self.connection_history: List[ConnectionAttempt] = []
        
        # Reconnection management
        self.retry_count = 0
        self.next_retry_time: Optional[datetime] = None
        self.backoff_multiplier = 2
        self.max_backoff = 300  # 5 minutes
        
        # Message processing
        self.receive_task: Optional[asyncio.Task] = None
        self.send_queue = asyncio.Queue()
        self.send_task: Optional[asyncio.Task] = None
        
        self.logger.info(f"Initialized {self.config.type} interface: {self.config.id}")
    
    @abstractmethod
    async def _connect(self) -> bool:
        """Establish connection to Meshtastic device"""
        pass
    
    @abstractmethod
    async def _disconnect(self):
        """Close connection to Meshtastic device"""
        pass
    
    @abstractmethod
    async def _send_message(self, message: Message) -> bool:
        """Send message through the interface"""
        pass
    
    @abstractmethod
    async def _receive_messages(self):
        """Receive messages from the interface"""
        pass
    
    async def start(self):
        """Start the interface"""
        if not self.config.enabled:
            self.status = InterfaceStatus.DISABLED
            self.logger.info(f"Interface {self.config.id} is disabled")
            return
        
        self.logger.info(f"Starting interface {self.config.id}")
        
        # Start connection task
        asyncio.create_task(self._connection_manager())
        
        # Start send task
        self.send_task = asyncio.create_task(self._send_worker())
    
    async def stop(self):
        """Stop the interface"""
        self.logger.info(f"Stopping interface {self.config.id}")
        
        # Cancel tasks
        if self.receive_task:
            self.receive_task.cancel()
        if self.send_task:
            self.send_task.cancel()
        
        # Disconnect
        await self._disconnect()
        self.status = InterfaceStatus.DISCONNECTED
        
        self.logger.info(f"Interface {self.config.id} stopped")
    
    async def send_message(self, message: Message) -> bool:
        """Queue message for sending"""
        if self.status != InterfaceStatus.CONNECTED:
            self.logger.warning(f"Cannot send message - interface {self.config.id} not connected")
            return False
        
        try:
            await self.send_queue.put(message)
            return True
        except Exception as e:
            self.logger.error(f"Failed to queue message: {e}")
            return False
    
    async def _connection_manager(self):
        """Manage connection lifecycle with automatic reconnection"""
        while self.config.enabled:
            try:
                if self.status in [InterfaceStatus.DISCONNECTED, InterfaceStatus.FAILED]:
                    # Check if we should retry
                    if self.next_retry_time and datetime.utcnow() < self.next_retry_time:
                        await asyncio.sleep(1)
                        continue
                    
                    # Attempt connection
                    await self._attempt_connection()
                
                elif self.status == InterfaceStatus.CONNECTED:
                    # Monitor connection health
                    await self._monitor_connection()
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in connection manager: {e}")
                await asyncio.sleep(5)
    
    async def _attempt_connection(self):
        """Attempt to connect to the device"""
        self.status = InterfaceStatus.CONNECTING
        self.stats.connection_attempts += 1
        
        self.logger.info(f"Attempting to connect to {self.config.connection_string}")
        
        try:
            success = await self._connect()
            
            if success:
                self.status = InterfaceStatus.CONNECTED
                self.stats.successful_connections += 1
                self.stats.uptime_start = datetime.utcnow()
                self.retry_count = 0
                self.next_retry_time = None
                
                # Record successful connection
                self.connection_history.append(
                    ConnectionAttempt(datetime.utcnow(), True)
                )
                
                # Start receiving messages
                self.receive_task = asyncio.create_task(self._receive_messages())
                
                self.logger.info(f"Successfully connected to {self.config.id}")
                
            else:
                await self._handle_connection_failure("Connection failed")
                
        except Exception as e:
            await self._handle_connection_failure(str(e))
    
    async def _handle_connection_failure(self, error: str):
        """Handle connection failure with backoff"""
        self.status = InterfaceStatus.FAILED
        self.retry_count += 1
        
        # Record failed connection
        self.connection_history.append(
            ConnectionAttempt(datetime.utcnow(), False, error)
        )
        
        # Calculate backoff delay
        if self.retry_count <= self.config.max_retries:
            delay = min(
                self.config.retry_interval * (self.backoff_multiplier ** (self.retry_count - 1)),
                self.max_backoff
            )
            self.next_retry_time = datetime.utcnow() + timedelta(seconds=delay)
            
            self.logger.warning(
                f"Connection failed for {self.config.id}: {error}. "
                f"Retry {self.retry_count}/{self.config.max_retries} in {delay}s"
            )
        else:
            self.logger.error(
                f"Max retries exceeded for {self.config.id}. Giving up."
            )
            self.config.enabled = False
    
    async def _monitor_connection(self):
        """Monitor connection health"""
        # Check if receive task is still running
        if self.receive_task and self.receive_task.done():
            exception = self.receive_task.exception()
            if exception:
                self.logger.error(f"Receive task failed: {exception}")
                await self._disconnect()
                self.status = InterfaceStatus.DISCONNECTED
    
    async def _send_worker(self):
        """Worker task for sending messages"""
        while True:
            try:
                # Wait for message to send
                message = await self.send_queue.get()
                
                if self.status == InterfaceStatus.CONNECTED:
                    success = await self._send_message(message)
                    
                    if success:
                        self.stats.messages_sent += 1
                        self.stats.bytes_sent += len(message.content.encode('utf-8'))
                        self.logger.debug(f"Sent message via {self.config.id}")
                    else:
                        self.logger.error(f"Failed to send message via {self.config.id}")
                else:
                    self.logger.warning(f"Dropped message - interface {self.config.id} not connected")
                
            except Exception as e:
                self.logger.error(f"Error in send worker: {e}")
                await asyncio.sleep(1)
    
    def _handle_received_message(self, message: Message):
        """Handle received message"""
        message.interface_id = self.config.id
        self.stats.messages_received += 1
        self.stats.bytes_received += len(message.content.encode('utf-8'))
        self.stats.last_message_time = datetime.utcnow()
        
        # Call the message callback
        try:
            self.message_callback(message, self.config.id)
        except Exception as e:
            self.logger.error(f"Error in message callback: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get interface status information"""
        return {
            'id': self.config.id,
            'type': self.config.type,
            'status': self.status.value,
            'enabled': self.config.enabled,
            'connection_string': self.config.connection_string,
            'retry_count': self.retry_count,
            'next_retry': self.next_retry_time.isoformat() if self.next_retry_time else None,
            'stats': {
                'messages_sent': self.stats.messages_sent,
                'messages_received': self.stats.messages_received,
                'bytes_sent': self.stats.bytes_sent,
                'bytes_received': self.stats.bytes_received,
                'connection_attempts': self.stats.connection_attempts,
                'successful_connections': self.stats.successful_connections,
                'last_message_time': self.stats.last_message_time.isoformat() if self.stats.last_message_time else None,
                'uptime_seconds': self.stats.get_uptime().total_seconds() if self.stats.get_uptime() else 0
            },
            'recent_connections': [
                {
                    'timestamp': attempt.timestamp.isoformat(),
                    'success': attempt.success,
                    'error': attempt.error
                }
                for attempt in self.connection_history[-10:]  # Last 10 attempts
            ]
        }


class SerialInterface(MeshtasticInterface):
    """Serial interface for Meshtastic devices"""
    
    def __init__(self, config, message_callback):
        super().__init__(config, message_callback)
        self._pubsub_callback = None  # Store reference to prevent garbage collection
    
    async def _connect(self) -> bool:
        """Connect to serial device"""
        try:
            # Import meshtastic library
            import meshtastic.serial_interface
            from pubsub import pub
            
            params = self.config.get_connection_params()
            
            # Ensure any existing connection is closed first
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                self.connection = None
            
            # Create serial connection
            # Note: meshtastic library uses 'devPath' not 'port', and no baudRate parameter
            self.connection = meshtastic.serial_interface.SerialInterface(
                devPath=params['port'],
                connectNow=True
            )
            
            # Create wrapper functions for different packet types
            def text_message_handler(packet, interface=None):
                self._on_meshtastic_text(packet, interface)
            
            def user_handler(packet, interface=None):
                self._on_meshtastic_user(packet, interface)
            
            def position_handler(packet, interface=None):
                self._on_meshtastic_position(packet, interface)
            
            def telemetry_handler(packet, interface=None):
                self._on_meshtastic_telemetry(packet, interface)
            
            # Store references to prevent garbage collection
            self._text_callback = text_message_handler
            self._user_callback = user_handler
            self._position_callback = position_handler
            self._telemetry_callback = telemetry_handler
            self._routing_callback = lambda packet, interface: self._on_meshtastic_routing(packet, interface)
            
            # Subscribe to all relevant packet types
            pub.subscribe(self._text_callback, "meshtastic.receive.text")
            pub.subscribe(self._user_callback, "meshtastic.receive.user")
            pub.subscribe(self._position_callback, "meshtastic.receive.position")
            pub.subscribe(self._telemetry_callback, "meshtastic.receive.telemetry")
            pub.subscribe(self._routing_callback, "meshtastic.receive.routing")
            
            self.logger.info("Subscribed to meshtastic packet types: text, user, position, telemetry, routing")
            
            # DISABLED: Don't import node database on startup
            # This was importing all nodes the device has ever heard (including distant/unreachable ones)
            # Now we only track nodes that are actively heard via radio
            # self._import_node_database_sync()
            
            # Test connection
            if self.connection.myInfo:
                return True
            else:
                return False
                
        except ImportError as e:
            self.logger.error(f"Meshtastic library not available: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Serial connection failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Ensure connection is cleaned up on error
            if self.connection:
                try:
                    self.connection.close()
                except:
                    pass
                self.connection = None
            return False
    
    def _on_meshtastic_text(self, packet, interface=None):
        """Handle incoming text message from Meshtastic"""
        try:
            self.logger.debug(f"📨 Received text message from {packet.get('fromId', 'unknown')}: {packet.get('decoded', {}).get('text', '')}")
            
            # Continue with existing text message handling...
            node_id = packet.get('fromId', '')
            if not node_id:
                return
            
            decoded = packet.get('decoded', {})
            text = decoded.get('text', '')
            
            # Update node tracking
            self._update_node_from_packet(packet)
            
            # Create Message object and route to message router
            from models.message import Message, MessageType, MessagePriority
            message = Message(
                sender_id=node_id,
                recipient_id=packet.get('toId', 'broadcast'),
                channel=packet.get('channel', 0),
                content=text,
                message_type=MessageType.TEXT,
                priority=MessagePriority.NORMAL,
                hop_count=max(0, packet.get('hopStart', 0) - packet.get('hopLimit', 0)),
                snr=packet.get('rxSnr'),
                rssi=packet.get('rxRssi'),
                metadata={'raw_packet': packet}
            )
            self._handle_received_message(message)
            
        except Exception as e:
            self.logger.error(f"Error processing text message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _import_node_database_sync(self):
        """Import existing node information from Meshtastic device"""
        try:
            if not self.connection:
                return
            
            self.logger.info("Importing node database from Meshtastic device...")
            
            # Access the node database from the Meshtastic connection
            nodes = getattr(self.connection, 'nodes', {})
            
            if not nodes:
                self.logger.warning("No nodes found in Meshtastic device database")
                return
            
            imported_count = 0
            for node_id, node_info in nodes.items():
                try:
                    # Get user info from node
                    user = node_info.get('user', {})
                    
                    if not user:
                        continue
                    
                    # Create a synthetic packet to update the database
                    synthetic_packet = {
                        'fromId': node_id,
                        'toId': 'broadcast',
                        'channel': 0,
                        'decoded': {
                            'user': {
                                'shortName': user.get('shortName', node_id[-4:]),
                                'longName': user.get('longName', 'Unknown'),
                                'hwModel': user.get('hwModel', ''),
                                'role': user.get('role', 'CLIENT')
                            }
                        },
                        'rxSnr': node_info.get('snr'),
                        'rxRssi': node_info.get('rssi'),
                        'hopStart': 0,
                        'hopLimit': 0
                    }
                    
                    # Update database with this node's info
                    self._update_node_from_packet(synthetic_packet, user_info=synthetic_packet['decoded']['user'])
                    imported_count += 1
                    
                    self.logger.debug(
                        f"Imported node {node_id}: "
                        f"{user.get('shortName', 'unknown')} / {user.get('longName', 'Unknown')}"
                    )
                    
                except Exception as e:
                    self.logger.error(f"Error importing node {node_id}: {e}")
                    continue
            
            self.logger.info(f"Successfully imported {imported_count} nodes from Meshtastic device")
            
        except Exception as e:
            self.logger.error(f"Error importing node database: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            
            # Convert Meshtastic packet to our Message format
            try:
                from ..models.message import Message, MessageType
            except ImportError:
                from models.message import Message, MessageType
            
            message = Message(
                sender_id=packet.get('fromId', ''),
                recipient_id=packet.get('toId'),
                channel=packet.get('channel', 0),
                content=packet.get('decoded', {}).get('text', ''),
                message_type=MessageType.TEXT,
                interface_id=self.config.id,
                hop_count=max(0, packet.get('hopStart', 0) - packet.get('hopLimit', 0)),
                snr=packet.get('rxSnr'),
                rssi=packet.get('rxRssi')
            )
            
            self.logger.info(f"✓ Converted to Message object, routing to message router")
            
            # Call the message callback
            self._handle_received_message(message)
            
            # Also update node tracking
            self._update_node_from_packet(packet)
            
        except Exception as e:
            self.logger.error(f"Error processing text message: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _on_meshtastic_user(self, packet, interface=None):
        """Handle incoming user info packet from Meshtastic (nodeinfo)"""
        try:
            node_id = packet.get('fromId', '')
            
            # Skip if no valid sender
            if not node_id:
                self.logger.debug(f"Received USER packet without sender ID, skipping")
                return
            
            decoded = packet.get('decoded', {})
            user_info = decoded.get('user', {})
            
            self.logger.debug(
                f"📡 User info from {node_id}: "
                f"{user_info.get('shortName', 'unknown')} / "
                f"{user_info.get('longName', 'unknown')} "
                f"({user_info.get('hwModel', 'unknown')})"
            )
            
            # Update node tracking with hardware info
            self._update_node_from_packet(packet, user_info=user_info)
            
            # Create Message object and route to message router
            from models.message import Message, MessageType, MessagePriority
            message = Message(
                sender_id=node_id,
                recipient_id=packet.get('toId', 'broadcast'),
                channel=packet.get('channel', 0),
                content="",  # USER has no text content
                message_type=MessageType.NODEINFO,
                priority=MessagePriority.NORMAL,
                metadata={'raw_packet': packet}
            )
            self._handle_received_message(message)
            
        except Exception as e:
            self.logger.error(f"Error processing user packet: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _on_meshtastic_position(self, packet, interface=None):
        """Handle incoming position packet from Meshtastic"""
        try:
            node_id = packet.get('fromId', '')
            
            # Skip if no valid sender
            if not node_id:
                self.logger.debug(f"Received POSITION packet without sender ID, skipping")
                return
            
            decoded = packet.get('decoded', {})
            position = decoded.get('position', {})
            
            if position:
                lat = position.get('latitude')
                lon = position.get('longitude')
                alt = position.get('altitude')
                
                self.logger.debug(f"Position from {node_id}: lat={lat}, lon={lon}, alt={alt}")
                
                # Update node tracking with position
                self._update_node_from_packet(packet, position=position)
                
                # Create Message object and route to message router
                from models.message import Message, MessageType, MessagePriority
                message = Message(
                    sender_id=node_id,
                    recipient_id=packet.get('toId', 'broadcast'),
                    channel=packet.get('channel', 0),
                    content="",  # POSITION has no text content
                    message_type=MessageType.POSITION,
                    priority=MessagePriority.NORMAL,
                    metadata={'raw_packet': packet, 'position': position}
                )
                self._handle_received_message(message)
            
        except Exception as e:
            self.logger.error(f"Error processing position packet: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _on_meshtastic_telemetry(self, packet, interface=None):
        """Handle incoming telemetry packet from Meshtastic"""
        try:
            node_id = packet.get('fromId', '')
            
            # Skip if no valid sender
            if not node_id:
                self.logger.debug(f"Received TELEMETRY packet without sender ID, skipping")
                return
            
            decoded = packet.get('decoded', {})
            telemetry = decoded.get('telemetry', {})
            
            device_metrics = telemetry.get('deviceMetrics', {})
            if device_metrics:
                battery = device_metrics.get('batteryLevel')
                voltage = device_metrics.get('voltage')
                
                self.logger.debug(f"Telemetry from {node_id}: battery={battery}%, voltage={voltage}V")
                
                # Update node tracking with telemetry
                self._update_node_from_packet(packet, telemetry=device_metrics)
                
                # Create Message object and route to message router
                from models.message import Message, MessageType, MessagePriority
                message = Message(
                    sender_id=node_id,
                    recipient_id=packet.get('toId', 'broadcast'),
                    channel=packet.get('channel', 0),
                    content="",  # TELEMETRY has no text content
                    message_type=MessageType.TELEMETRY,
                    priority=MessagePriority.NORMAL,
                    metadata={'raw_packet': packet, 'telemetry': device_metrics}
                )
                self._handle_received_message(message)
            
        except Exception as e:
            self.logger.error(f"Error processing telemetry packet: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _on_meshtastic_routing(self, packet, interface=None):
        """Handle incoming routing packet from Meshtastic (traceroute, neighbor_info)"""
        try:
            node_id = packet.get('fromId', '')
            
            # Skip if no valid sender
            if not node_id:
                self.logger.debug(f"Received ROUTING packet without sender ID, skipping")
                return
            
            decoded = packet.get('decoded', {})
            routing = decoded.get('routing', {})
            
            # Check if there's a 'payload' field that might contain the RouteDiscovery protobuf
            if 'payload' in decoded:
                payload = decoded.get('payload')
                if payload:
                    # Try to decode as RouteDiscovery protobuf
                    try:
                        from meshtastic.protobuf import mesh_pb2
                        route_discovery = mesh_pb2.RouteDiscovery()
                        route_discovery.ParseFromString(payload)
                        route_list = list(route_discovery.route)
                        route_back_list = list(route_discovery.route_back)
                        
                        # Add the decoded route to routing dict
                        if not routing:
                            routing = {}
                        
                        # Check if this has actual route data
                        if route_list or route_back_list:
                            routing['route'] = route_list
                            routing['route_back'] = route_back_list
                            # Only log actual traceroute responses with data
                            self.logger.info(f"🗺️  Traceroute response from {node_id}: route={route_list}, route_back={route_back_list}")
                        else:
                            # Empty route - likely an ACK
                            routing['route'] = route_list
                            routing['route_back'] = route_back_list
                            
                    except Exception as e:
                        self.logger.debug(f"Failed to decode RouteDiscovery: {e}")
            
            if routing:
                # Determine if this is a traceroute or neighbor_info
                if 'route' in routing or 'routeReply' in routing:
                    # This is a traceroute message
                    route = routing.get('route') or routing.get('routeReply', [])
                    route_back = routing.get('route_back', [])
                    error_reason = routing.get('errorReason', 'UNKNOWN')
                    to_id = packet.get('toId', '')
                    
                    if route or route_back:
                        # Has route data - definitely a traceroute response
                        message_type_val = MessageType.TRACEROUTE
                        metadata = {
                            'raw_packet': packet,
                            'routing': routing,
                            'traceroute': True,
                            'route': route,
                            'route_back': route_back,
                            'request_id': decoded.get('requestId'),
                            'error_reason': error_reason
                        }
                    elif error_reason == 'NONE' and to_id and to_id != 'broadcast' and node_id != to_id:
                        # Empty route but no error - likely a direct node (0 hops)
                        self.logger.info(f"🗺️  Traceroute response from {node_id}: DIRECT NODE (0 hops)")
                        message_type_val = MessageType.TRACEROUTE
                        metadata = {
                            'raw_packet': packet,
                            'routing': routing,
                            'traceroute': True,
                            'route': route,
                            'route_back': route_back,
                            'request_id': decoded.get('requestId'),
                            'error_reason': error_reason,
                            'direct_node': True
                        }
                    else:
                        # ACK or error - use DEBUG level
                        self.logger.debug(f"Routing ACK/ERROR from {node_id}: errorReason={error_reason}")
                        message_type_val = MessageType.ROUTING
                        metadata = {
                            'raw_packet': packet,
                            'routing': routing,
                            'traceroute_ack': True,
                            'error_reason': error_reason,
                            'request_id': decoded.get('requestId')
                        }
                elif 'neighbors' in routing or 'neighborInfo' in routing:
                    # This is a neighbor info message
                    neighbors = routing.get('neighbors') or routing.get('neighborInfo', [])
                    self.logger.info(f"👥 Neighbor info from {node_id}: {len(neighbors)} neighbors")
                    message_type_val = MessageType.NEIGHBOR_INFO
                    metadata = {
                        'raw_packet': packet,
                        'routing': routing,
                        'neighbors': neighbors
                    }
                else:
                    # Generic routing message - DEBUG level
                    self.logger.debug(f"Generic routing from {node_id}")
                    message_type_val = MessageType.ROUTING
                    metadata = {'raw_packet': packet, 'routing': routing}
                
                # Create Message object and route to message router
                from models.message import Message, MessagePriority
                message = Message(
                    sender_id=node_id,
                    recipient_id=packet.get('toId', 'broadcast'),
                    channel=packet.get('channel', 0),
                    content="",  # ROUTING has no text content
                    message_type=message_type_val,
                    priority=MessagePriority.NORMAL,
                    metadata=metadata
                )
                self._handle_received_message(message)
            
        except Exception as e:
            self.logger.error(f"Error processing routing packet: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _update_node_from_packet(self, packet, user_info=None, position=None, telemetry=None):
        """Update node information in database from packet data"""
        try:
            from core.database import get_database
            from datetime import datetime
            
            node_id = packet.get('fromId', '')
            if not node_id:
                return
            
            # Filter out invalid/special node IDs
            # Valid node IDs start with '!' followed by 8 hex characters
            if not node_id.startswith('!') or len(node_id) != 9:
                self.logger.debug(f"Skipping invalid node ID: {node_id}")
                return
            
            # Filter out special broadcast addresses
            if node_id in ['!ffffffff', '^all', 'broadcast']:
                self.logger.debug(f"Skipping broadcast address: {node_id}")
                return
            
            db = get_database()
            
            # Prepare user data
            user_data = {
                'node_id': node_id,
                'last_seen': datetime.utcnow().isoformat()
            }
            
            # Add user info if available
            if user_info:
                user_data['short_name'] = user_info.get('shortName', node_id[-4:])
                user_data['long_name'] = user_info.get('longName')
            else:
                # Get existing user or use default
                existing = db.get_user(node_id)
                if existing:
                    user_data['short_name'] = existing.get('short_name', node_id[-4:])
                else:
                    user_data['short_name'] = node_id[-4:]
            
            # Add position if available
            if position:
                user_data['location_lat'] = position.get('latitude')
                user_data['location_lon'] = position.get('longitude')
                user_data['altitude'] = position.get('altitude')
            
            # Add signal quality
            user_data['snr'] = packet.get('rxSnr')
            user_data['rssi'] = packet.get('rxRssi')
            user_data['hop_count'] = max(0, packet.get('hopStart', 0) - packet.get('hopLimit', 0))
            
            # Add telemetry if available
            if telemetry:
                user_data['battery_level'] = telemetry.get('batteryLevel')
                user_data['voltage'] = telemetry.get('voltage')
            
            # Upsert user record
            db.upsert_user(user_data)
            
            # Update node_hardware table if we have hardware info
            if user_info or telemetry:
                hardware_data = {
                    'node_id': node_id,
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                if user_info:
                    hardware_data['hardware_model'] = user_info.get('hwModel', '')
                    hardware_data['role'] = user_info.get('role', 'CLIENT')
                
                if telemetry:
                    hardware_data['battery_level'] = telemetry.get('batteryLevel')
                    hardware_data['voltage'] = telemetry.get('voltage')
                    hardware_data['channel_utilization'] = telemetry.get('channelUtilization')
                    hardware_data['air_util_tx'] = telemetry.get('airUtilTx')
                    hardware_data['uptime_seconds'] = telemetry.get('uptimeSeconds')
                
                # Build update query
                columns = list(hardware_data.keys())
                placeholders = ', '.join(['?' for _ in columns])
                update_clause = ', '.join([f"{col} = excluded.{col}" for col in columns if col != 'node_id'])
                
                query = f"""
                    INSERT INTO node_hardware ({', '.join(columns)})
                    VALUES ({placeholders})
                    ON CONFLICT(node_id) DO UPDATE SET {update_clause}
                """
                
                db.execute_update(query, tuple(hardware_data[col] for col in columns))
            
            self.logger.debug(f"Updated node tracking for {node_id}")
            
        except Exception as e:
            self.logger.error(f"Error updating node from packet: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    async def _disconnect(self):
        """Disconnect from serial device"""
        if self.connection:
            try:
                # Unsubscribe from all pubsub topics using stored callback references
                from pubsub import pub
                
                if hasattr(self, '_text_callback') and self._text_callback:
                    pub.unsubscribe(self._text_callback, "meshtastic.receive.text")
                    self._text_callback = None
                
                if hasattr(self, '_user_callback') and self._user_callback:
                    pub.unsubscribe(self._user_callback, "meshtastic.receive.user")
                    self._user_callback = None
                
                if hasattr(self, '_position_callback') and self._position_callback:
                    pub.unsubscribe(self._position_callback, "meshtastic.receive.position")
                    self._position_callback = None
                
                if hasattr(self, '_telemetry_callback') and self._telemetry_callback:
                    pub.unsubscribe(self._telemetry_callback, "meshtastic.receive.telemetry")
                    self._telemetry_callback = None
                
                if hasattr(self, '_routing_callback') and self._routing_callback:
                    pub.unsubscribe(self._routing_callback, "meshtastic.receive.routing")
                    self._routing_callback = None
                
                self.logger.info("Unsubscribed from all meshtastic packet types")
                
            except Exception as e:
                self.logger.debug(f"Error unsubscribing from pubsub: {e}")
            
            try:
                self.connection.close()
            except Exception as e:
                self.logger.error(f"Error closing serial connection: {e}")
            finally:
                self.connection = None
    
    async def _send_message(self, message: Message) -> bool:
        """Send message via serial interface"""
        if not self.connection:
            return False
        
        try:
            # For traceroute messages, use sendTraceRoute method
            if message.message_type == MessageType.ROUTING and message.metadata.get('traceroute'):
                hop_limit = message.hop_limit if message.hop_limit is not None else 7
                self.logger.info(f"Sending traceroute to {message.recipient_id} (hop_limit={hop_limit})")
                
                # Use the proper sendTraceRoute method which handles the protocol correctly
                self.connection.sendTraceRoute(
                    dest=message.recipient_id,
                    hopLimit=hop_limit,
                    channelIndex=message.channel
                )
                
                # Note: The Meshtastic library prints traceroute results to stdout
                # but doesn't publish them through pubsub in a parseable way.
                # The actual route data appears in the console output like:
                # "Route traced towards destination: nodeA --> nodeB --> nodeC"
                # We would need to capture stdout or parse the node database to get this data.
                # For now, the traceroute IS working (you can see it in logs), but we can't
                # programmatically capture the route for processing.
                
                return True
            
            # For regular text messages, use sendText
            self.logger.info(f"Calling sendText with content='{message.content[:50] if message.content else ''}...', destinationId={message.recipient_id}, channelIndex={message.channel}")
            
            # Prepare sendText parameters
            send_params = {
                'text': message.content,
                'destinationId': message.recipient_id,
                'channelIndex': message.channel
            }
            
            # Note: sendText doesn't support hopLimit parameter
            # Hop limit must be set via device config or will use default (3)
            if message.hop_limit is not None:
                self.logger.warning(f"Hop limit {message.hop_limit} requested but sendText doesn't support hopLimit parameter - using device default")
            
            self.connection.sendText(**send_params)
            self.logger.info(f"sendText completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send serial message: {e}", exc_info=True)
            return False
    
    async def _receive_messages(self):
        """Receive messages from serial interface"""
        while self.status == InterfaceStatus.CONNECTED:
            try:
                # This is a simplified implementation
                # In reality, we'd need to set up proper message callbacks
                # with the meshtastic library
                
                await asyncio.sleep(0.1)  # Prevent busy loop
                
            except Exception as e:
                self.logger.error(f"Error receiving serial messages: {e}")
                break


class TCPInterface(MeshtasticInterface):
    """TCP interface for Meshtastic devices"""
    
    async def _connect(self) -> bool:
        """Connect to TCP device"""
        try:
            # Import meshtastic library
            import meshtastic.tcp_interface
            
            params = self.config.get_connection_params()
            
            # Create TCP connection
            self.connection = meshtastic.tcp_interface.TCPInterface(
                hostname=params['host'],
                portNumber=params.get('port', 4403),
                connectNow=True
            )
            
            # Test connection
            if self.connection.myInfo:
                return True
            else:
                return False
                
        except ImportError:
            self.logger.error("Meshtastic library not available")
            return False
        except Exception as e:
            self.logger.error(f"TCP connection failed: {e}")
            return False
    
    async def _disconnect(self):
        """Disconnect from TCP device"""
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                self.logger.error(f"Error closing TCP connection: {e}")
            finally:
                self.connection = None
    
    async def _send_message(self, message: Message) -> bool:
        """Send message via TCP interface"""
        if not self.connection:
            return False
        
        try:
            # For traceroute messages, use sendData with TRACEROUTE_APP port
            if message.message_type == MessageType.ROUTING and message.metadata.get('traceroute'):
                self.logger.info(f"Sending traceroute request to {message.recipient_id} with hop_limit={message.hop_limit}")
                
                # Import protobuf definitions
                from meshtastic.protobuf import portnums_pb2, mesh_pb2
                
                # Create RouteDiscovery protobuf message
                route_discovery = mesh_pb2.RouteDiscovery()
                
                # Serialize the protobuf
                payload = route_discovery.SerializeToString()
                
                # Send using sendData with TRACEROUTE_APP port
                self.connection.sendData(
                    payload,
                    destinationId=message.recipient_id,
                    portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                    wantAck=True,
                    wantResponse=True,
                    channelIndex=message.channel
                )
                self.logger.info(f"Traceroute request sent successfully")
                return True
            
            # For regular text messages, use sendText
            send_params = {
                'text': message.content,
                'destinationId': message.recipient_id,
                'channelIndex': message.channel
            }
            
            # Note: sendText doesn't support hopLimit parameter
            if message.hop_limit is not None:
                self.logger.warning(f"Hop limit {message.hop_limit} requested but sendText doesn't support hopLimit parameter - using device default")
            
            self.connection.sendText(**send_params)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send TCP message: {e}")
            return False
    
    async def _receive_messages(self):
        """Receive messages from TCP interface"""
        while self.status == InterfaceStatus.CONNECTED:
            try:
                # This is a simplified implementation
                # In reality, we'd need to set up proper message callbacks
                # with the meshtastic library
                
                await asyncio.sleep(0.1)  # Prevent busy loop
                
            except Exception as e:
                self.logger.error(f"Error receiving TCP messages: {e}")
                break


class BLEInterface(MeshtasticInterface):
    """BLE interface for Meshtastic devices"""
    
    async def _connect(self) -> bool:
        """Connect to BLE device"""
        try:
            # Import meshtastic library
            import meshtastic.ble_interface
            
            params = self.config.get_connection_params()
            
            # Create BLE connection
            self.connection = meshtastic.ble_interface.BLEInterface(
                address=params['address'],
                connectNow=True
            )
            
            # Test connection
            if self.connection.myInfo:
                return True
            else:
                return False
                
        except ImportError:
            self.logger.error("Meshtastic BLE library not available")
            return False
        except Exception as e:
            self.logger.error(f"BLE connection failed: {e}")
            return False
    
    async def _disconnect(self):
        """Disconnect from BLE device"""
        if self.connection:
            try:
                self.connection.close()
            except Exception as e:
                self.logger.error(f"Error closing BLE connection: {e}")
            finally:
                self.connection = None
    
    async def _send_message(self, message: Message) -> bool:
        """Send message via BLE interface"""
        if not self.connection:
            return False
        
        try:
            # For traceroute messages, use sendData with TRACEROUTE_APP port
            if message.message_type == MessageType.ROUTING and message.metadata.get('traceroute'):
                self.logger.info(f"Sending traceroute request to {message.recipient_id} with hop_limit={message.hop_limit}")
                
                # Import protobuf definitions
                from meshtastic.protobuf import portnums_pb2, mesh_pb2
                
                # Create RouteDiscovery protobuf message
                route_discovery = mesh_pb2.RouteDiscovery()
                
                # Serialize the protobuf
                payload = route_discovery.SerializeToString()
                
                # Send using sendData with TRACEROUTE_APP port
                self.connection.sendData(
                    payload,
                    destinationId=message.recipient_id,
                    portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
                    wantAck=True,
                    wantResponse=True,
                    channelIndex=message.channel
                )
                self.logger.info(f"Traceroute request sent successfully")
                return True
            
            # For regular text messages, use sendText
            send_params = {
                'text': message.content,
                'destinationId': message.recipient_id,
                'channelIndex': message.channel
            }
            
            # Note: sendText doesn't support hopLimit parameter
            if message.hop_limit is not None:
                self.logger.warning(f"Hop limit {message.hop_limit} requested but sendText doesn't support hopLimit parameter - using device default")
            
            self.connection.sendText(**send_params)
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send BLE message: {e}")
            return False
    
    async def _receive_messages(self):
        """Receive messages from BLE interface"""
        while self.status == InterfaceStatus.CONNECTED:
            try:
                # This is a simplified implementation
                # In reality, we'd need to set up proper message callbacks
                # with the meshtastic library
                
                await asyncio.sleep(0.1)  # Prevent busy loop
                
            except Exception as e:
                self.logger.error(f"Error receiving BLE messages: {e}")
                break


class InterfaceFactory:
    """Factory for creating Meshtastic interfaces"""
    
    @staticmethod
    def create_interface(config: InterfaceConfig, message_callback: Callable[[Message, str], None]) -> MeshtasticInterface:
        """Create interface based on configuration"""
        if config.type == 'serial':
            return SerialInterface(config, message_callback)
        elif config.type == 'tcp':
            return TCPInterface(config, message_callback)
        elif config.type == 'ble':
            return BLEInterface(config, message_callback)
        else:
            raise ValueError(f"Unsupported interface type: {config.type}")


class InterfaceManager:
    """Manages multiple Meshtastic interfaces"""
    
    def __init__(self, message_callback: Callable[[Message, str], None]):
        self.message_callback = message_callback
        self.interfaces: Dict[str, MeshtasticInterface] = {}
        self.logger = get_logger('interface_manager')
        
        self.logger.info("Interface manager initialized")
    
    async def add_interface(self, config: InterfaceConfig):
        """Add and start a new interface"""
        if config.id in self.interfaces:
            self.logger.warning(f"Interface {config.id} already exists")
            return
        
        try:
            interface = InterfaceFactory.create_interface(config, self.message_callback)
            self.interfaces[config.id] = interface
            
            await interface.start()
            
            self.logger.info(f"Added interface {config.id} ({config.type})")
            
        except Exception as e:
            self.logger.error(f"Failed to add interface {config.id}: {e}")
    
    async def remove_interface(self, interface_id: str):
        """Remove and stop an interface"""
        if interface_id not in self.interfaces:
            self.logger.warning(f"Interface {interface_id} not found")
            return
        
        interface = self.interfaces[interface_id]
        
        try:
            await interface.stop()
            del self.interfaces[interface_id]
            
            self.logger.info(f"Removed interface {interface_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to remove interface {interface_id}: {e}")
    
    async def send_message(self, message: Message, interface_id: Optional[str] = None) -> bool:
        """Send message through specified interface or all interfaces"""
        if interface_id:
            # Send through specific interface
            if interface_id in self.interfaces:
                return await self.interfaces[interface_id].send_message(message)
            else:
                self.logger.error(f"Interface {interface_id} not found")
                return False
        else:
            # Send through all connected interfaces
            success = False
            for interface in self.interfaces.values():
                if await interface.send_message(message):
                    success = True
            return success
    
    def get_interface_status(self, interface_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of interfaces"""
        if interface_id:
            if interface_id in self.interfaces:
                return self.interfaces[interface_id].get_status()
            else:
                return {}
        else:
            return {
                iface_id: interface.get_status()
                for iface_id, interface in self.interfaces.items()
            }
    
    def get_connected_interfaces(self) -> List[str]:
        """Get list of connected interface IDs"""
        return [
            iface_id for iface_id, interface in self.interfaces.items()
            if interface.status == InterfaceStatus.CONNECTED
        ]
    
    async def stop_all(self):
        """Stop all interfaces"""
        self.logger.info("Stopping all interfaces")
        
        for interface in self.interfaces.values():
            try:
                await interface.stop()
            except Exception as e:
                self.logger.error(f"Error stopping interface: {e}")
        
        self.interfaces.clear()
        self.logger.info("All interfaces stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get overall interface statistics"""
        total_stats = {
            'total_interfaces': len(self.interfaces),
            'connected_interfaces': len(self.get_connected_interfaces()),
            'total_messages_sent': 0,
            'total_messages_received': 0,
            'total_bytes_sent': 0,
            'total_bytes_received': 0,
            'interfaces': {}
        }
        
        for iface_id, interface in self.interfaces.items():
            status = interface.get_status()
            stats = status['stats']
            
            total_stats['total_messages_sent'] += stats['messages_sent']
            total_stats['total_messages_received'] += stats['messages_received']
            total_stats['total_bytes_sent'] += stats['bytes_sent']
            total_stats['total_bytes_received'] += stats['bytes_received']
            total_stats['interfaces'][iface_id] = status
        
        return total_stats