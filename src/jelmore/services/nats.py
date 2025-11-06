"""NATS Event Bus Service
Comprehensive event streaming and inter-service communication
"""
import json
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timedelta
import asyncio
import nats
from nats.js import JetStreamContext, api
from nats.js.errors import BadRequestError, NotFoundError
import structlog

from jelmore.config import get_settings

settings = get_settings()
logger = structlog.get_logger()

# Global NATS client
nc: Optional[nats.NATS] = None
js: Optional[JetStreamContext] = None


# Event topics configuration
EVENT_TOPICS = [
    "jelmore.session.created",
    "jelmore.session.output", 
    "jelmore.session.completed",
    "jelmore.session.failed",
    "jelmore.session.status",
    "jelmore.session.directory_changed",
    "jelmore.session.file_modified",
    "jelmore.session.git_activity"
]

# Consumer groups for horizontal scaling
CONSUMER_GROUPS = {
    "session_handlers": ["jelmore.session.>"],
    "file_watchers": ["jelmore.session.directory_changed", "jelmore.session.file_modified"],
    "git_monitors": ["jelmore.session.git_activity"],
    "system_monitors": ["jelmore.session.status", "jelmore.session.failed"]
}


async def init_nats():
    """Initialize NATS connection with comprehensive stream configuration"""
    global nc, js
    
    try:
        nc = await nats.connect(
            settings.nats_url,
            reconnect_time_wait=2.0,
            max_reconnect_attempts=10,
            reconnected_cb=_on_reconnect,
            error_cb=_on_error
        )
        js = nc.jetstream()
        
        # Create main Jelmore stream with persistent storage
        await _create_main_stream()
        
        # Create dead letter queue stream
        await _create_dlq_stream()
        
        # Setup consumer groups
        await _setup_consumer_groups()
        
        logger.info(
            "NATS connected with JetStream configuration", 
            url=settings.nats_url,
            stream="JELMORE",
            dlq="JELMORE_DLQ",
            consumer_groups=list(CONSUMER_GROUPS.keys())
        )
    except Exception as e:
        logger.error("Failed to connect to NATS", error=str(e))
        raise


async def _create_main_stream():
    """Create main stream for persistent event storage"""
    try:
        config = api.StreamConfig(
            name="JELMORE",
            subjects=[f"{settings.nats_subject_prefix}.>"],
            retention=api.RetentionPolicy.LIMITS,
            storage=api.StorageType.FILE,  # Persistent storage
            max_msgs=100_000,  # Store up to 100k messages
            max_bytes=10 * 1024 * 1024 * 1024,  # 10GB max
            max_age=7 * 24 * 60 * 60,  # 7 days retention
            max_msg_size=1024 * 1024,  # 1MB max message size
            discard=api.DiscardPolicy.OLD,  # Discard old messages when full
            duplicate_window=60,  # 60 second duplicate window
            allow_rollup_hdrs=True,  # Allow message rollups
            deny_delete=False,
            deny_purge=False
        )
        
        await js.add_stream(config)
        logger.info("Created JELMORE stream with persistent storage")
        
    except BadRequestError as e:
        if "already exists" in str(e).lower():
            logger.debug("JELMORE stream already exists")
        else:
            raise


async def _create_dlq_stream():
    """Create dead letter queue stream for failed events"""
    try:
        config = api.StreamConfig(
            name="JELMORE_DLQ",
            subjects=[f"{settings.nats_subject_prefix}.dlq.>"],
            retention=api.RetentionPolicy.LIMITS,
            storage=api.StorageType.FILE,
            max_msgs=10_000,
            max_bytes=1024 * 1024 * 1024,  # 1GB
            max_age=30 * 24 * 60 * 60,  # 30 days retention for failed events
            discard=api.DiscardPolicy.OLD
        )
        
        await js.add_stream(config)
        logger.info("Created JELMORE_DLQ stream for failed events")
        
    except BadRequestError as e:
        if "already exists" in str(e).lower():
            logger.debug("JELMORE_DLQ stream already exists")
        else:
            raise


async def _setup_consumer_groups():
    """Setup consumer groups for horizontal scaling"""
    for group_name, subjects in CONSUMER_GROUPS.items():
        try:
            # Create durable consumer for each group
            config = api.ConsumerConfig(
                durable_name=group_name,
                filter_subjects=subjects,
                ack_policy=api.AckPolicy.EXPLICIT,
                replay_policy=api.ReplayPolicy.INSTANT,
                deliver_policy=api.DeliverPolicy.NEW,
                ack_wait=30,  # 30 second ack timeout
                max_deliver=3,  # Max 3 delivery attempts
                max_ack_pending=100,  # Max 100 unacked messages
                inactive_threshold=5 * 60,  # 5 minutes inactive threshold
                flow_control=True,
                heartbeat=30  # 30 second heartbeat
            )
            
            await js.add_consumer("JELMORE", config)
            logger.debug(f"Created consumer group: {group_name}", subjects=subjects)
            
        except BadRequestError as e:
            if "already exists" in str(e).lower():
                logger.debug(f"Consumer group {group_name} already exists")
            else:
                logger.error(f"Failed to create consumer group {group_name}", error=str(e))


async def _on_reconnect():
    """Handle NATS reconnection"""
    logger.info("NATS reconnected")


async def _on_error(error):
    """Handle NATS errors"""
    logger.error("NATS error", error=str(error))


async def close_nats():
    """Close NATS connection"""
    global nc
    if nc:
        await nc.close()
        logger.info("NATS connection closed")


async def get_nats_stats():
    """Get NATS connection statistics"""
    if not nc or not js:
        return {"error": "NATS not initialized"}
    
    try:
        stats = {
            "connected": nc.is_connected,
            "reconnected": nc.is_reconnecting,
            "jetstream_enabled": js is not None
        }
        
        if nc.is_connected:
            # Get server info
            stats.update({
                "server_id": nc.connected_server_version.get("server_id", "unknown") if nc.connected_server_version else "unknown",
                "server_version": nc.connected_server_version.get("version", "unknown") if nc.connected_server_version else "unknown",
                "max_payload": nc.max_payload
            })
            
        # Get JetStream stats if available
        if js:
            try:
                account_info = await js.account_info()
                stats.update({
                    "streams": account_info.streams,
                    "consumers": account_info.consumers,
                    "memory_used": account_info.memory,
                    "store_used": account_info.store,
                    "api_requests": account_info.api.total,
                    "api_errors": account_info.api.errors
                })
            except Exception as e:
                logger.warning("Failed to get JetStream account info", error=str(e))
                stats["jetstream_error"] = str(e)
        
        return stats
        
    except Exception as e:
        logger.error("Failed to get NATS stats", error=str(e))
        return {"error": str(e)}


async def publish_event(
    event_type: str,
    session_id: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None
) -> bool:
    """Publish an event to NATS with error handling and retry logic"""
    if not nc or not js:
        logger.warning("NATS not connected, skipping event publish")
        return False
    
    subject = f"{settings.nats_subject_prefix}.{event_type}"
    
    event_data = {
        "event_type": event_type,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": payload,
        "message_id": f"{session_id}-{event_type}-{datetime.utcnow().timestamp()}",
        "retry_count": 0
    }
    
    # Add optional headers
    msg_headers = {
        "Nats-Msg-Id": event_data["message_id"],  # Deduplication
        "Event-Type": event_type,
        "Session-Id": session_id
    }
    if headers:
        msg_headers.update(headers)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ack = await js.publish(
                subject,
                json.dumps(event_data).encode(),
                headers=msg_headers,
                timeout=5.0  # 5 second timeout
            )
            
            logger.debug(
                "Event published", 
                event_type=event_type, 
                session_id=session_id,
                sequence=ack.seq
            )
            return True
            
        except Exception as e:
            attempt_num = attempt + 1
            if attempt_num < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(
                    f"Event publish failed, retrying in {wait_time}s",
                    event_type=event_type,
                    attempt=attempt_num,
                    error=str(e)
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(
                    "Failed to publish event after all retries", 
                    event_type=event_type,
                    session_id=session_id,
                    error=str(e)
                )
                # Send to DLQ
                await _send_to_dlq(event_data, str(e))
                return False
    
    return False


async def _send_to_dlq(event_data: Dict[str, Any], error_reason: str):
    """Send failed event to dead letter queue"""
    try:
        dlq_subject = f"{settings.nats_subject_prefix}.dlq.{event_data['event_type']}"
        
        dlq_event = {
            **event_data,
            "dlq_timestamp": datetime.utcnow().isoformat(),
            "failure_reason": error_reason,
            "original_subject": f"{settings.nats_subject_prefix}.{event_data['event_type']}"
        }
        
        await js.publish(
            dlq_subject,
            json.dumps(dlq_event).encode(),
            headers={"Error-Reason": error_reason}
        )
        
        logger.info("Event sent to DLQ", event_type=event_data["event_type"])
        
    except Exception as e:
        logger.error("Failed to send event to DLQ", error=str(e))


async def subscribe_to_events(
    subjects: List[str],
    handler: Callable,
    consumer_group: Optional[str] = None,
    auto_ack: bool = True
):
    """Subscribe to events with consumer group support"""
    if not nc or not js:
        raise RuntimeError("NATS not connected")
    
    try:
        if consumer_group and consumer_group in CONSUMER_GROUPS:
            # Use existing consumer group
            sub = await js.subscribe(
                subjects,
                stream="JELMORE",
                durable=consumer_group,
                manual_ack=not auto_ack
            )
        else:
            # Create ephemeral subscription
            sub = await js.subscribe(
                subjects,
                stream="JELMORE",
                manual_ack=not auto_ack
            )
        
        logger.info(
            "Subscribed to events",
            subjects=subjects,
            consumer_group=consumer_group
        )
        
        async def message_handler():
            async for msg in sub.messages:
                try:
                    event = json.loads(msg.data.decode())
                    await handler(event, msg)
                    
                    if not auto_ack:
                        await msg.ack()
                        
                except Exception as e:
                    logger.error(
                        "Error processing message",
                        subject=msg.subject,
                        error=str(e)
                    )
                    if not auto_ack:
                        await msg.nak()  # Negative acknowledge
        
        # Start message handler
        asyncio.create_task(message_handler())
        return sub
        
    except Exception as e:
        logger.error("Failed to subscribe to events", error=str(e))
        raise


async def replay_events(
    subjects: List[str],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    handler: Optional[Callable] = None
) -> List[Dict[str, Any]]:
    """Replay events from persistent storage"""
    if not nc or not js:
        raise RuntimeError("NATS not connected")
    
    try:
        # Create temporary consumer for replay
        config = api.ConsumerConfig(
            deliver_policy=api.DeliverPolicy.ALL if not start_time else api.DeliverPolicy.BY_START_TIME,
            opt_start_time=start_time,
            filter_subjects=subjects,
            ack_policy=api.AckPolicy.NONE,  # No acking needed for replay
            replay_policy=api.ReplayPolicy.INSTANT
        )
        
        consumer = await js.add_consumer("JELMORE", config)
        
        events = []
        msgs = await js.fetch("JELMORE", consumer.name, batch=1000, timeout=5.0)
        
        for msg in msgs:
            try:
                event = json.loads(msg.data.decode())
                event_time = datetime.fromisoformat(event["timestamp"])
                
                # Filter by end time if specified
                if end_time and event_time > end_time:
                    continue
                
                events.append(event)
                
                # Call handler if provided
                if handler:
                    await handler(event, msg)
                    
            except Exception as e:
                logger.warning("Error parsing replayed event", error=str(e))
        
        # Clean up temporary consumer
        await js.delete_consumer("JELMORE", consumer.name)
        
        logger.info(
            "Event replay completed",
            subjects=subjects,
            count=len(events),
            start_time=start_time,
            end_time=end_time
        )
        
        return events
        
    except Exception as e:
        logger.error("Failed to replay events", error=str(e))
        raise


async def get_stream_info() -> Dict[str, Any]:
    """Get stream information and metrics"""
    if not js:
        raise RuntimeError("NATS JetStream not connected")
    
    try:
        main_info = await js.stream_info("JELMORE")
        dlq_info = await js.stream_info("JELMORE_DLQ")
        
        consumers = []
        for group in CONSUMER_GROUPS.keys():
            try:
                consumer_info = await js.consumer_info("JELMORE", group)
                consumers.append({
                    "name": group,
                    "delivered": consumer_info.delivered.consumer_seq,
                    "ack_pending": consumer_info.num_ack_pending,
                    "num_pending": consumer_info.num_pending
                })
            except NotFoundError:
                pass
        
        return {
            "main_stream": {
                "messages": main_info.state.messages,
                "bytes": main_info.state.bytes,
                "first_seq": main_info.state.first_seq,
                "last_seq": main_info.state.last_seq,
                "subjects": main_info.config.subjects
            },
            "dlq_stream": {
                "messages": dlq_info.state.messages,
                "bytes": dlq_info.state.bytes,
                "first_seq": dlq_info.state.first_seq,
                "last_seq": dlq_info.state.last_seq
            },
            "consumers": consumers
        }
        
    except Exception as e:
        logger.error("Failed to get stream info", error=str(e))
        raise