#!/usr/bin/env python3
"""NATS Test Utilities
Utilities for testing event publishing, subscribing, and replay functionality
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import click
import nats
from nats.js import JetStreamContext

# Event simulation data
SAMPLE_EVENTS = [
    {
        "type": "session.created",
        "payload": {"provider": "claude", "timeout": 7200}
    },
    {
        "type": "session.output", 
        "payload": {"content": "Hello from Claude Code!", "tokens": 15}
    },
    {
        "type": "session.file_modified",
        "payload": {"file": "/home/user/test.py", "action": "modified"}
    },
    {
        "type": "session.git_activity", 
        "payload": {"action": "commit", "files": ["test.py"], "message": "Update test"}
    },
    {
        "type": "session.completed",
        "payload": {"duration": 300, "exit_code": 0}
    }
]


class NATSTestClient:
    """Test client for NATS operations"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None
        
    async def connect(self):
        """Connect to NATS"""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            print(f"✅ Connected to NATS at {self.nats_url}")
        except Exception as e:
            print(f"❌ Failed to connect to NATS: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from NATS"""
        if self.nc:
            await self.nc.close()
            print("👋 Disconnected from NATS")
    
    async def publish_test_event(self, event_type: str, session_id: str = None, custom_payload: Dict = None):
        """Publish a test event"""
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")
        
        session_id = session_id or str(uuid.uuid4())
        
        # Find matching sample event or use custom
        payload = custom_payload
        if not payload:
            for sample in SAMPLE_EVENTS:
                if sample["type"] == event_type:
                    payload = sample["payload"]
                    break
            
            if not payload:
                payload = {"test": True, "timestamp": datetime.utcnow().isoformat()}
        
        event_data = {\n            "event_type": event_type,\n            "session_id": session_id,\n            "timestamp": datetime.utcnow().isoformat(),\n            "payload": payload,\n            "message_id": f"{session_id}-{event_type}-{datetime.utcnow().timestamp()}"\n        }\n        \n        subject = f"jelmore.{event_type}"\n        \n        try:\n            ack = await self.js.publish(\n                subject,\n                json.dumps(event_data).encode(),\n                headers={\"Event-Type\": event_type, \"Session-Id\": session_id}\n            )\n            \n            print(f"📤 Published event: {event_type}")
            print(f"   Session: {session_id}")
            print(f"   Subject: {subject}")
            print(f"   Sequence: {ack.seq}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to publish event: {e}")
            return False
    
    async def subscribe_to_events(self, subjects: List[str], duration: int = 30):
        """Subscribe to events for testing"""
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")
        
        print(f"🔔 Subscribing to: {', '.join(subjects)}")
        print(f"   Duration: {duration}s")
        print("-" * 50)
        
        try:
            sub = await self.js.subscribe(subjects, stream="JELMORE")
            
            start_time = datetime.utcnow()
            event_count = 0
            
            async for msg in sub.messages:
                if (datetime.utcnow() - start_time).seconds >= duration:
                    break
                
                try:
                    event = json.loads(msg.data.decode())
                    event_count += 1
                    
                    print(f"\n📨 Event #{event_count}: {event['event_type']}")
                    print(f"   Session: {event['session_id']}")
                    print(f"   Time: {event['timestamp']}")
                    print(f"   Subject: {msg.subject}")
                    print(f"   Payload: {json.dumps(event['payload'], indent=2)}")
                    
                    await msg.ack()
                    
                except Exception as e:
                    print(f"❌ Error parsing message: {e}")
            
            print(f"\n✅ Received {event_count} events in {duration}s")
            
        except Exception as e:
            print(f"❌ Subscription failed: {e}")
    
    async def replay_events(self, subjects: List[str], hours_back: int = 1):
        """Replay events from the past"""
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")
        
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        
        print(f"🔄 Replaying events from {hours_back} hours ago")
        print(f"   Subjects: {', '.join(subjects)}")
        print(f"   Start time: {start_time.isoformat()}")
        print("-" * 50)
        
        try:
            from nats.js import api
            
            # Create temporary consumer for replay
            config = api.ConsumerConfig(
                deliver_policy=api.DeliverPolicy.BY_START_TIME,
                opt_start_time=start_time,
                filter_subjects=subjects,
                ack_policy=api.AckPolicy.NONE
            )
            
            consumer = await self.js.add_consumer("JELMORE", config)
            
            # Fetch messages
            msgs = await self.js.fetch("JELMORE", consumer.name, batch=100, timeout=5.0)
            
            print(f"📥 Found {len(msgs)} events to replay")
            
            for i, msg in enumerate(msgs, 1):
                try:
                    event = json.loads(msg.data.decode())
                    
                    print(f"\n🔄 Replay #{i}: {event['event_type']}")
                    print(f"   Original time: {event['timestamp']}")
                    print(f"   Session: {event['session_id']}")
                    print(f"   Subject: {msg.subject}")
                    
                except Exception as e:
                    print(f"❌ Error parsing replayed message: {e}")
            
            # Clean up temporary consumer
            await self.js.delete_consumer("JELMORE", consumer.name)
            
            print(f"\n✅ Replay completed: {len(msgs)} events")
            
        except Exception as e:
            print(f"❌ Replay failed: {e}")
    
    async def check_stream_health(self):
        """Check stream health and info"""
        if not self.js:
            raise RuntimeError("Not connected to NATS JetStream")
        
        try:
            # Main stream info
            main_info = await self.js.stream_info("JELMORE")
            print("🏥 Stream Health Check")
            print("-" * 50)
            print(f"📊 JELMORE Stream:")
            print(f"   Messages: {main_info.state.messages:,}")
            print(f"   Bytes: {main_info.state.bytes:,}")
            print(f"   Subjects: {main_info.config.subjects}")
            print(f"   Storage: {main_info.config.storage}")
            
            # DLQ stream info
            try:
                dlq_info = await self.js.stream_info("JELMORE_DLQ")
                print(f"\n💀 DLQ Stream:")
                print(f"   Messages: {dlq_info.state.messages:,}")
                print(f"   Bytes: {dlq_info.state.bytes:,}")
            except:
                print(f"\n💀 DLQ Stream: Not found")
            
            # Consumer info
            consumers = []
            consumer_names = ["session_handlers", "file_watchers", "git_monitors", "system_monitors"]
            
            print(f"\n👥 Consumers:")
            for name in consumer_names:
                try:
                    consumer_info = await self.js.consumer_info("JELMORE", name)
                    print(f"   {name}:")
                    print(f"      Delivered: {consumer_info.delivered.consumer_seq:,}")
                    print(f"      Pending: {consumer_info.num_pending:,}")
                    print(f"      Ack Pending: {consumer_info.num_ack_pending:,}")
                except:
                    print(f"   {name}: Not found")
            
            print("\n✅ Health check completed")
            
        except Exception as e:
            print(f"❌ Health check failed: {e}")
    
    async def simulate_load(self, events_per_second: int = 10, duration: int = 60):
        """Simulate event load for testing"""
        print(f"🚀 Starting load simulation")
        print(f"   Rate: {events_per_second} events/sec")
        print(f"   Duration: {duration}s")
        print(f"   Total events: {events_per_second * duration}")
        print("-" * 50)
        
        start_time = datetime.utcnow()
        total_sent = 0
        total_failed = 0
        
        try:
            while (datetime.utcnow() - start_time).seconds < duration:
                batch_start = datetime.utcnow()
                
                # Send events for this second
                for i in range(events_per_second):
                    event_type = SAMPLE_EVENTS[i % len(SAMPLE_EVENTS)]["type"]
                    success = await self.publish_test_event(event_type)
                    
                    if success:
                        total_sent += 1
                    else:
                        total_failed += 1
                
                # Wait for next second
                elapsed = (datetime.utcnow() - batch_start).total_seconds()
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
                
                # Progress update
                if total_sent % 50 == 0:
                    print(f"📈 Progress: {total_sent} sent, {total_failed} failed")
        
        except KeyboardInterrupt:
            print("\n⏹️  Load simulation interrupted")
        
        total_time = (datetime.utcnow() - start_time).total_seconds()
        actual_rate = total_sent / total_time if total_time > 0 else 0
        
        print(f"\n📊 Load simulation completed:")
        print(f"   Duration: {total_time:.1f}s")
        print(f"   Events sent: {total_sent:,}")
        print(f"   Events failed: {total_failed:,}")
        print(f"   Actual rate: {actual_rate:.1f} events/sec")


# CLI Interface
@click.group()
def cli():
    """NATS Test Utilities for Jelmore"""
    pass


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--event-type", required=True, help="Event type to publish")
@click.option("--session-id", help="Session ID (auto-generated if not provided)")
@click.option("--payload", help="JSON payload (uses sample if not provided)")
def publish(nats_url, event_type, session_id, payload):
    """Publish a test event"""
    
    async def run():
        client = NATSTestClient(nats_url)
        await client.connect()
        
        custom_payload = None
        if payload:
            try:
                custom_payload = json.loads(payload)
            except Exception as e:
                print(f"❌ Invalid JSON payload: {e}")
                return
        
        await client.publish_test_event(event_type, session_id, custom_payload)
        await client.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--subjects", default="jelmore.>", help="Subjects to subscribe to (comma-separated)")
@click.option("--duration", default=30, help="Subscription duration in seconds")
def subscribe(nats_url, subjects, duration):
    """Subscribe to events"""
    
    async def run():
        client = NATSTestClient(nats_url)
        await client.connect()
        
        subject_list = [s.strip() for s in subjects.split(",")]
        await client.subscribe_to_events(subject_list, duration)
        await client.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--subjects", default="jelmore.>", help="Subjects to replay (comma-separated)")
@click.option("--hours", default=1, help="Hours back to replay from")
def replay(nats_url, subjects, hours):
    """Replay events from the past"""
    
    async def run():
        client = NATSTestClient(nats_url)
        await client.connect()
        
        subject_list = [s.strip() for s in subjects.split(",")]
        await client.replay_events(subject_list, hours)
        await client.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
def health(nats_url):
    """Check stream health"""
    
    async def run():
        client = NATSTestClient(nats_url)
        await client.connect()
        await client.check_stream_health()
        await client.disconnect()
    
    asyncio.run(run())


@cli.command()
@click.option("--nats-url", default="nats://localhost:4222", help="NATS server URL")
@click.option("--rate", default=10, help="Events per second")
@click.option("--duration", default=60, help="Duration in seconds")
def load(nats_url, rate, duration):
    """Simulate event load"""
    
    async def run():
        client = NATSTestClient(nats_url)
        await client.connect()
        await client.simulate_load(rate, duration)
        await client.disconnect()
    
    asyncio.run(run())


if __name__ == "__main__":
    cli()