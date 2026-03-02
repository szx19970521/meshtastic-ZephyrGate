#!/usr/bin/env python3
"""
Simple MQTT monitor to test the mqtt_gateway plugin.
Subscribes to all topics and displays received messages.
"""

import paho.mqtt.client as mqtt
import json
import sys
from datetime import datetime

BROKER = "mqtt.villagesmesh.com"
PORT = 1883
TOPIC = "msh/US/#"  # Subscribe to all US region topics

def on_connect(client, userdata, flags, rc):
    """Callback when connected to broker"""
    if rc == 0:
        print(f"✅ Connected to {BROKER}:{PORT}")
        print(f"📡 Subscribing to: {TOPIC}")
        client.subscribe(TOPIC)
        print("=" * 80)
        print("Waiting for messages... (Press Ctrl+C to stop)")
        print("=" * 80)
    else:
        print(f"❌ Connection failed with code {rc}")
        sys.exit(1)

def on_message(client, userdata, message):
    """Callback when message received"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    topic = message.topic
    
    print(f"\n[{timestamp}] 📨 Message received")
    print(f"Topic: {topic}")
    
    try:
        # Try to parse as JSON
        payload = json.loads(message.payload.decode())
        print("Payload (JSON):")
        print(json.dumps(payload, indent=2))
    except:
        # If not JSON, show raw payload
        print(f"Payload (raw): {message.payload}")
    
    print("-" * 80)

def on_disconnect(client, userdata, rc):
    """Callback when disconnected"""
    if rc != 0:
        print(f"\n⚠️  Unexpected disconnection (code {rc})")
        print("Attempting to reconnect...")

def main():
    """Main function"""
    print("=" * 80)
    print("MQTT Gateway Test Monitor")
    print("=" * 80)
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Topic:  {TOPIC}")
    print("=" * 80)
    
    # Create MQTT client
    client = mqtt.Client(client_id="zephyrgate_test_monitor")
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect
    
    try:
        print(f"Connecting to {BROKER}:{PORT}...")
        client.connect(BROKER, PORT, 60)
        
        # Start the loop
        client.loop_forever()
        
    except KeyboardInterrupt:
        print("\n\n👋 Stopping monitor...")
        client.disconnect()
        print("✅ Disconnected cleanly")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
