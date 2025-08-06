#!/usr/bin/env python3
"""
NATS Event Subscriber
Test script to monitor events from Tonzies
"""
import asyncio
import json
import sys
from nats import connect


async def main():
    """Subscribe to Tonzies events"""
    
    # Connect to NATS
    nc = await connect("nats://localhost:4222")
    js = nc.jetstream()
    
    print("📡 Listening for Tonzies events...")
    print("-" * 50)
    
    # Subscribe to all Tonzies events
    sub = await js.subscribe("tonzies.>", stream="TONZIES")
    
    try:
        async for msg in sub.messages:
            # Parse and display event
            try:
                event = json.loads(msg.data.decode())
                print(f"\n🔔 Event: {event['event_type']}")
                print(f"   Session: {event['session_id']}")
                print(f"   Time: {event['timestamp']}")
                print(f"   Payload: {json.dumps(event['payload'], indent=2)}")
                print("-" * 50)
            except Exception as e:
                print(f"Error parsing message: {e}")
            
            await msg.ack()
            
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        await nc.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
