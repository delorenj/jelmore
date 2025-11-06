"""Core services for Jelmore"""

from .database import init_db, close_db, get_session, Base
from .redis import init_redis, close_redis, get_redis
from .nats import (
    init_nats, close_nats, publish_event, subscribe_to_events, 
    replay_events, get_stream_info, EVENT_TOPICS, CONSUMER_GROUPS
)
from .nats_monitoring import (
    start_monitoring, stop_monitoring, get_health_status, 
    get_performance_metrics, monitor
)
from .claude_code import session_manager, ClaudeCodeSession, SessionManager

__all__ = [
    "init_db", "close_db", "get_session", "Base",
    "init_redis", "close_redis", "get_redis",
    "init_nats", "close_nats", "publish_event", "subscribe_to_events",
    "replay_events", "get_stream_info", "EVENT_TOPICS", "CONSUMER_GROUPS",
    "start_monitoring", "stop_monitoring", "get_health_status",
    "get_performance_metrics", "monitor",
    "session_manager", "ClaudeCodeSession", "SessionManager",
]