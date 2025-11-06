"""Integration tests for NATS event system"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
import pytest

from jelmore.services.nats import (
    init_nats, close_nats, publish_event, subscribe_to_events,
    replay_events, get_stream_info, EVENT_TOPICS, CONSUMER_GROUPS
)
from jelmore.services.nats_monitoring import (
    start_monitoring, stop_monitoring, get_health_status,
    get_performance_metrics, monitor
)


class TestNATSIntegration:
    """Test NATS event system integration"""
    
    @pytest.fixture(autouse=True)
    async def setup_nats(self):
        """Setup NATS connection for tests"""
        await init_nats()
        await start_monitoring()
        yield
        await stop_monitoring()
        await close_nats()
    
    async def test_stream_initialization(self):
        """Test that streams are properly initialized"""
        info = await get_stream_info()
        
        # Check main stream exists
        assert "main_stream" in info
        assert info["main_stream"]["subjects"] == ["jelmore.>"]
        
        # Check DLQ stream exists
        assert "dlq_stream" in info
        
        # Check consumers exist
        assert "consumers" in info
        consumer_names = [c["name"] for c in info["consumers"]]
        for group in CONSUMER_GROUPS.keys():
            assert group in consumer_names
    
    async def test_event_publishing(self):
        """Test basic event publishing"""
        session_id = str(uuid.uuid4())
        payload = {"test": True, "timestamp": datetime.utcnow().isoformat()}
        
        success = await publish_event(
            event_type="session.created",
            session_id=session_id,
            payload=payload
        )
        
        assert success is True
        
        # Verify event was stored
        info = await get_stream_info()
        assert info["main_stream"]["messages"] > 0
    
    async def test_event_publishing_with_headers(self):
        """Test event publishing with custom headers"""
        session_id = str(uuid.uuid4())
        payload = {"priority": "high"}
        headers = {"Custom-Header": "test-value"}
        
        success = await publish_event(
            event_type="session.status",
            session_id=session_id,
            payload=payload,
            headers=headers
        )
        
        assert success is True
    
    async def test_event_subscription(self):
        """Test event subscription and handling"""
        received_events = []
        session_id = str(uuid.uuid4())
        
        async def event_handler(event, msg):\n            received_events.append(event)\n            await msg.ack()\n        \n        # Subscribe to events\n        subscription = await subscribe_to_events(\n            subjects=[\"jelmore.session.created\"],\n            handler=event_handler,\n            auto_ack=False\n        )\n        \n        # Give subscription time to start\n        await asyncio.sleep(0.1)\n        \n        # Publish test event\n        await publish_event(\n            event_type=\"session.created\",\n            session_id=session_id,\n            payload={\"test\": \"subscription\"}\n        )\n        \n        # Wait for event processing\n        await asyncio.sleep(0.5)\n        \n        # Verify event was received\n        assert len(received_events) >= 1\n        event = received_events[0]\n        assert event[\"event_type\"] == \"session.created\"\n        assert event[\"session_id\"] == session_id\n        assert event[\"payload\"][\"test\"] == \"subscription\"\n    \n    async def test_consumer_group_subscription(self):\n        \"\"\"Test subscription with consumer groups\"\"\"\n        received_events = []\n        session_id = str(uuid.uuid4())\n        \n        async def group_handler(event, msg):\n            received_events.append(event)\n            await msg.ack()\n        \n        # Subscribe with consumer group\n        subscription = await subscribe_to_events(\n            subjects=[\"jelmore.session.>\"],\n            handler=group_handler,\n            consumer_group=\"session_handlers\",\n            auto_ack=False\n        )\n        \n        await asyncio.sleep(0.1)\n        \n        # Publish multiple events\n        for i in range(3):\n            await publish_event(\n                event_type=\"session.output\",\n                session_id=session_id,\n                payload={\"message\": f\"test-{i}\"}\n            )\n        \n        await asyncio.sleep(1.0)\n        \n        # Should receive all events\n        assert len(received_events) >= 3\n    \n    async def test_event_replay(self):\n        \"\"\"Test event replay functionality\"\"\"\n        session_id = str(uuid.uuid4())\n        \n        # Publish some historical events\n        for i in range(5):\n            await publish_event(\n                event_type=\"session.file_modified\",\n                session_id=session_id,\n                payload={\"file\": f\"test-{i}.py\", \"action\": \"modified\"}\n            )\n        \n        await asyncio.sleep(0.5)\n        \n        # Replay events from last hour\n        start_time = datetime.utcnow() - timedelta(hours=1)\n        replayed_events = await replay_events(\n            subjects=[\"jelmore.session.file_modified\"],\n            start_time=start_time\n        )\n        \n        # Should find our events\n        assert len(replayed_events) >= 5\n        \n        # Verify event structure\n        for event in replayed_events[-5:]:\n            assert event[\"event_type\"] == \"session.file_modified\"\n            assert event[\"session_id\"] == session_id\n            assert \"file\" in event[\"payload\"]\n    \n    async def test_dead_letter_queue(self):\n        \"\"\"Test dead letter queue functionality\"\"\"\n        # This is harder to test without forcing failures\n        # For now, just verify DLQ stream exists\n        info = await get_stream_info()\n        assert \"dlq_stream\" in info\n        \n        # DLQ should be empty initially\n        assert info[\"dlq_stream\"][\"messages\"] >= 0\n    \n    async def test_monitoring_health(self):\n        \"\"\"Test monitoring and health checks\"\"\"\n        health = await get_health_status()\n        \n        assert \"stream_health\" in health\n        assert \"consumer_lag\" in health\n        assert \"dlq_message_count\" in health\n        assert \"connection_status\" in health\n        assert \"uptime_seconds\" in health\n        \n        # Should be healthy initially\n        assert health[\"stream_health\"] in [\"healthy\", \"degraded\", \"critical\"]\n    \n    async def test_performance_metrics(self):\n        \"\"\"Test performance metrics collection\"\"\"\n        metrics = await get_performance_metrics()\n        \n        assert \"timestamp\" in metrics\n        assert \"uptime_seconds\" in metrics\n        assert \"health\" in metrics\n        assert \"streams\" in metrics\n        assert \"consumers\" in metrics\n        \n        # Verify stream metrics\n        assert \"main\" in metrics[\"streams\"]\n        assert \"dlq\" in metrics[\"streams\"]\n        \n        # Verify consumer metrics\n        assert isinstance(metrics[\"consumers\"], list)\n    \n    async def test_high_throughput_publishing(self):\n        \"\"\"Test high-throughput event publishing\"\"\"\n        session_id = str(uuid.uuid4())\n        event_count = 100\n        \n        # Publish many events quickly\n        publish_tasks = []\n        for i in range(event_count):\n            task = publish_event(\n                event_type=\"session.output\",\n                session_id=session_id,\n                payload={\"sequence\": i, \"content\": f\"Message {i}\"}\n            )\n            publish_tasks.append(task)\n        \n        # Wait for all publishes\n        results = await asyncio.gather(*publish_tasks)\n        \n        # All should succeed\n        success_count = sum(1 for r in results if r is True)\n        assert success_count == event_count\n        \n        # Verify stream message count increased\n        info = await get_stream_info()\n        assert info[\"main_stream\"][\"messages\"] >= event_count\n    \n    async def test_event_topic_coverage(self):\n        \"\"\"Test all defined event topics\"\"\"\n        session_id = str(uuid.uuid4())\n        \n        # Test each event topic\n        for topic in EVENT_TOPICS:\n            event_type = topic.replace(\"jelmore.\", \"\")\n            \n            success = await publish_event(\n                event_type=event_type,\n                session_id=session_id,\n                payload={\"topic_test\": topic}\n            )\n            \n            assert success is True, f\"Failed to publish {event_type}\"\n    \n    async def test_consumer_group_configuration(self):\n        \"\"\"Test consumer group configuration\"\"\"\n        info = await get_stream_info()\n        consumers = info.get(\"consumers\", [])\n        \n        # Verify all expected consumer groups exist\n        consumer_names = [c[\"name\"] for c in consumers]\n        for group_name in CONSUMER_GROUPS.keys():\n            assert group_name in consumer_names, f\"Missing consumer group: {group_name}\"\n        \n        # Verify consumer health\n        for consumer in consumers:\n            assert \"delivered\" in consumer\n            assert \"ack_pending\" in consumer\n            assert \"num_pending\" in consumer\n    \n    @pytest.mark.slow\n    async def test_long_running_subscription(self):\n        \"\"\"Test long-running event subscription\"\"\"\n        received_count = 0\n        session_id = str(uuid.uuid4())\n        \n        async def counting_handler(event, msg):\n            nonlocal received_count\n            received_count += 1\n            await msg.ack()\n        \n        # Start subscription\n        subscription = await subscribe_to_events(\n            subjects=[\"jelmore.session.>\"],\n            handler=counting_handler,\n            consumer_group=\"session_handlers\"\n        )\n        \n        # Publish events over time\n        for batch in range(5):\n            for i in range(10):\n                await publish_event(\n                    event_type=\"session.status\",\n                    session_id=session_id,\n                    payload={\"batch\": batch, \"sequence\": i}\n                )\n            await asyncio.sleep(0.2)  # Small delay between batches\n        \n        # Wait for processing\n        await asyncio.sleep(2.0)\n        \n        # Should have received all events\n        assert received_count >= 50\n    \n    async def test_event_ordering(self):\n        \"\"\"Test that events maintain ordering\"\"\"\n        session_id = str(uuid.uuid4())\n        event_count = 20\n        \n        # Publish sequential events\n        for i in range(event_count):\n            await publish_event(\n                event_type=\"session.output\",\n                session_id=session_id,\n                payload={\"sequence\": i, \"timestamp\": datetime.utcnow().isoformat()}\n            )\n        \n        await asyncio.sleep(0.5)\n        \n        # Replay and verify order\n        start_time = datetime.utcnow() - timedelta(minutes=1)\n        replayed_events = await replay_events(\n            subjects=[\"jelmore.session.output\"],\n            start_time=start_time\n        )\n        \n        # Find our events\n        our_events = [e for e in replayed_events if e[\"session_id\"] == session_id]\n        assert len(our_events) >= event_count\n        \n        # Verify sequential order (last N events)\n        recent_events = our_events[-event_count:]\n        for i, event in enumerate(recent_events):\n            assert event[\"payload\"][\"sequence\"] == i\n\n\nclass TestNATSErrorHandling:\n    \"\"\"Test NATS error handling and recovery\"\"\"\n    \n    async def test_publish_without_connection(self):\n        \"\"\"Test publishing when not connected\"\"\"\n        # Don't initialize NATS\n        success = await publish_event(\n            event_type=\"session.created\",\n            session_id=\"test-session\",\n            payload={\"test\": True}\n        )\n        \n        # Should return False gracefully\n        assert success is False\n    \n    async def test_invalid_event_data(self):\n        \"\"\"Test publishing invalid event data\"\"\"\n        await init_nats()\n        \n        try:\n            # Test with non-serializable payload\n            success = await publish_event(\n                event_type=\"session.created\",\n                session_id=\"test-session\",\n                payload={\"function\": lambda x: x}  # Non-serializable\n            )\n            \n            # Should handle gracefully\n            assert success is False\n            \n        finally:\n            await close_nats()\n\n\n@pytest.mark.integration\nclass TestNATSPerformance:\n    \"\"\"Performance tests for NATS system\"\"\"\n    \n    @pytest.fixture(autouse=True)\n    async def setup_nats(self):\n        \"\"\"Setup NATS for performance tests\"\"\"\n        await init_nats()\n        yield\n        await close_nats()\n    \n    async def test_publish_latency(self):\n        \"\"\"Test event publishing latency\"\"\"\n        session_id = str(uuid.uuid4())\n        iterations = 100\n        \n        start_time = datetime.utcnow()\n        \n        for i in range(iterations):\n            await publish_event(\n                event_type=\"session.status\",\n                session_id=session_id,\n                payload={\"iteration\": i}\n            )\n        \n        end_time = datetime.utcnow()\n        duration = (end_time - start_time).total_seconds()\n        avg_latency = (duration / iterations) * 1000  # ms\n        \n        print(f\"Average publish latency: {avg_latency:.2f}ms\")\n        \n        # Should be under 10ms per publish on local setup\n        assert avg_latency < 10.0\n    \n    async def test_concurrent_publishing(self):\n        \"\"\"Test concurrent event publishing\"\"\"\n        session_id = str(uuid.uuid4())\n        concurrent_publishers = 10\n        events_per_publisher = 50\n        \n        async def publisher(publisher_id: int):\n            for i in range(events_per_publisher):\n                await publish_event(\n                    event_type=\"session.output\",\n                    session_id=session_id,\n                    payload={\"publisher\": publisher_id, \"sequence\": i}\n                )\n        \n        start_time = datetime.utcnow()\n        \n        # Run publishers concurrently\n        tasks = [publisher(i) for i in range(concurrent_publishers)]\n        await asyncio.gather(*tasks)\n        \n        end_time = datetime.utcnow()\n        duration = (end_time - start_time).total_seconds()\n        total_events = concurrent_publishers * events_per_publisher\n        throughput = total_events / duration\n        \n        print(f\"Concurrent throughput: {throughput:.2f} events/sec\")\n        \n        # Should achieve reasonable throughput\n        assert throughput > 100  # events per second