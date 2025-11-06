#!/usr/bin/env python3
"""
NATS Event Subscriber
Advanced event monitoring with consumer group support
"""
import asyncio
import json
import sys
from datetime import datetime
from typing import Optional
import click
from nats import connect
from nats.js import JetStreamContext


class JelmoreEventSubscriber:
    """Advanced NATS event subscriber"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc = None
        self.js: Optional[JetStreamContext] = None
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "start_time": None
        }
    
    async def connect(self):
        """Connect to NATS"""
        try:
            self.nc = await connect(self.nats_url)
            self.js = self.nc.jetstream()
            self.stats["start_time"] = datetime.utcnow()
            print(f"✅ Connected to NATS at {self.nats_url}")
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from NATS"""
        if self.nc:
            await self.nc.close()
            print("\n👋 Disconnected from NATS")
    
    async def subscribe_all_events(self, consumer_group: Optional[str] = None):
        """Subscribe to all Jelmore events"""
        if not self.js:
            raise RuntimeError("Not connected to NATS")
        
        print("📡 Listening for Jelmore events...")
        if consumer_group:
            print(f"   Consumer Group: {consumer_group}")
        print("-" * 50)
        
        try:
            if consumer_group:
                sub = await self.js.subscribe(
                    "jelmore.>", 
                    stream="JELMORE",
                    durable=consumer_group
                )
            else:
                sub = await self.js.subscribe("jelmore.>", stream="JELMORE")
            
            async for msg in sub.messages:
                await self._handle_event(msg)
                
        except KeyboardInterrupt:
            await self._print_stats()
    
    async def subscribe_specific(self, subjects: list, consumer_group: Optional[str] = None):
        """Subscribe to specific subjects"""
        if not self.js:
            raise RuntimeError("Not connected to NATS")
        
        print(f"📡 Listening for events: {', '.join(subjects)}")
        if consumer_group:
            print(f"   Consumer Group: {consumer_group}")
        print("-" * 50)
        
        try:
            if consumer_group:
                sub = await self.js.subscribe(
                    subjects,
                    stream="JELMORE", 
                    durable=consumer_group
                )
            else:
                sub = await self.js.subscribe(subjects, stream="JELMORE")
            
            async for msg in sub.messages:
                await self._handle_event(msg)
                
        except KeyboardInterrupt:
            await self._print_stats()
    
    async def monitor_dlq(self):
        """Monitor dead letter queue"""
        if not self.js:
            raise RuntimeError("Not connected to NATS")
        
        print("💀 Monitoring Dead Letter Queue...")
        print("-" * 50)
        
        try:
            sub = await self.js.subscribe("jelmore.dlq.>", stream="JELMORE_DLQ")
            
            async for msg in sub.messages:
                await self._handle_dlq_event(msg)
                
        except KeyboardInterrupt:
            await self._print_stats()
    
    async def _handle_event(self, msg):
        """Handle incoming event message"""
        try:
            event = json.loads(msg.data.decode())
            event_type = event.get('event_type', 'unknown')
            
            # Update statistics
            self.stats["total_events"] += 1
            self.stats["events_by_type"][event_type] = self.stats["events_by_type"].get(event_type, 0) + 1
            
            # Display event
            print(f"\n🔔 Event #{self.stats['total_events']}: {event_type}")
            print(f"   Session: {event.get('session_id', 'N/A')}")
            print(f"   Time: {event.get('timestamp', 'N/A')}")
            print(f"   Subject: {msg.subject}")
            
            # Show headers if present
            if msg.headers:
                print(f"   Headers: {dict(msg.headers)}")
            
            # Show payload
            payload = event.get('payload', {})
            if payload:
                print(f"   Payload: {json.dumps(payload, indent=4)}")
            
            print("-" * 50)
            
            await msg.ack()
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            print(f"   Raw data: {msg.data.decode()[:200]}...")
            await msg.nak()  # Negative acknowledge
            
        except Exception as e:
            print(f"❌ Error processing message: {e}")
            await msg.nak()
    
    async def _handle_dlq_event(self, msg):
        """Handle dead letter queue event"""
        try:
            event = json.loads(msg.data.decode())
            
            print(f"\n💀 DLQ Event: {event.get('event_type', 'unknown')}")
            print(f"   Original Subject: {event.get('original_subject', 'N/A')}")
            print(f"   Failure Reason: {event.get('failure_reason', 'N/A')}")
            print(f"   DLQ Time: {event.get('dlq_timestamp', 'N/A')}")
            print(f"   Session: {event.get('session_id', 'N/A')}")
            
            if msg.headers:
                print(f"   Headers: {dict(msg.headers)}")
            
            print("-" * 50)
            
            await msg.ack()
            
        except Exception as e:
            print(f"❌ Error processing DLQ message: {e}")
            await msg.nak()
    
    async def _print_stats(self):
        """Print subscription statistics"""
        if not self.stats["start_time"]:
            return
        
        duration = (datetime.utcnow() - self.stats["start_time"]).total_seconds()
        rate = self.stats["total_events"] / duration if duration > 0 else 0
        
        print("\n📊 Subscription Statistics:")
        print(f"   Duration: {duration:.1f}s")
        print(f"   Total Events: {self.stats['total_events']}")
        print(f"   Rate: {rate:.2f} events/sec")
        
        if self.stats["events_by_type"]:
            print("   Events by Type:")
            for event_type, count in sorted(self.stats["events_by_type"].items()):
                percentage = (count / self.stats["total_events"]) * 100
                print(f"     {event_type}: {count} ({percentage:.1f}%)")


# CLI Interface
@click.group()
def cli():
    """Jelmore NATS Event Subscriber"""
    pass


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--consumer-group", help="Consumer group name for durable subscription")
def all(nats_url, consumer_group):
    """Subscribe to all events"""
    
    async def run():
        subscriber = JelmoreEventSubscriber(nats_url)
        try:
            await subscriber.connect()
            await subscriber.subscribe_all_events(consumer_group)
        except KeyboardInterrupt:
            pass
        finally:
            await subscriber.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--subjects", required=True, help="Comma-separated list of subjects")
@click.option("--consumer-group", help="Consumer group name")
def specific(nats_url, subjects, consumer_group):
    """Subscribe to specific subjects"""
    
    async def run():
        subscriber = JelmoreEventSubscriber(nats_url)
        subject_list = [s.strip() for s in subjects.split(",")]
        
        try:
            await subscriber.connect()
            await subscriber.subscribe_specific(subject_list, consumer_group)
        except KeyboardInterrupt:
            pass
        finally:
            await subscriber.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
def dlq(nats_url):
    """Monitor dead letter queue"""
    
    async def run():
        subscriber = JelmoreEventSubscriber(nats_url)
        try:
            await subscriber.connect()
            await subscriber.monitor_dlq()
        except KeyboardInterrupt:
            pass
        finally:
            await subscriber.disconnect()
    
    asyncio.run(run())


# Legacy main function for backward compatibility
async def main():
    """Legacy main function"""
    subscriber = JelmoreEventSubscriber()
    try:
        await subscriber.connect()
        await subscriber.subscribe_all_events()
    except KeyboardInterrupt:
        pass
    finally:
        await subscriber.disconnect()


if __name__ == "__main__":
    # Use CLI if arguments provided, otherwise legacy mode
    if len(sys.argv) > 1:
        cli()
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            sys.exit(0)
