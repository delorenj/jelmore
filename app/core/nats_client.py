"""
NATS Event Publisher
Publishes session events to NATS bus
"""
import json
from typing import Optional, Dict, Any
from datetime import datetime
import nats
from nats.js import JetStreamContext
import structlog

from app.config import settings

logger = structlog.get_logger()

# Global NATS client
nc: Optional[nats.NATS] = None
js: Optional[JetStreamContext] = None


async def init_nats():
    """Initialize NATS connection"""
    global nc, js
    
    try:
        nc = await nats.connect(settings.nats_url)
        js = nc.jetstream()
        
        # Create stream for Tonzies events
        try:
            await js.add_stream(
                name="TONZIES",
                subjects=[f"{settings.nats_subject_prefix}.>"],
                retention="limits",
                max_msgs=10000,
            )
        except Exception as e:
            # Stream might already exist
            logger.debug("Stream creation", error=str(e))
        
        logger.info("NATS connected", url=settings.nats_url)
    except Exception as e:
        logger.error("Failed to connect to NATS", error=str(e))
        raise


async def close_nats():
    """Close NATS connection"""
    global nc
    if nc:
        await nc.close()
        logger.info("NATS connection closed")


async def publish_event(
    event_type: str,
    session_id: str,
    payload: Dict[str, Any]
) -> None:
    """Publish an event to NATS"""
    if not nc or not js:
        logger.warning("NATS not connected, skipping event publish")
        return
    
    try:
        subject = f"{settings.nats_subject_prefix}.{event_type}"
        
        event_data = {
            "event_type": event_type,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload
        }
        
        await js.publish(
            subject,
            json.dumps(event_data).encode(),
        )
        
        logger.debug("Event published", 
                    event_type=event_type, 
                    session_id=session_id)
    except Exception as e:
        logger.error("Failed to publish event", 
                    event_type=event_type,
                    error=str(e))
