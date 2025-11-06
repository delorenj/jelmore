"""WebSocket Connection Manager for Jelmore

Manages WebSocket connections for real-time session communication.
Provides connection pooling, message broadcasting, and automatic cleanup.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from jelmore.models.events import EventType
from jelmore.services.nats import publish_event

logger = structlog.get_logger(__name__)


@dataclass
class WebSocketConnection:
    """WebSocket connection metadata"""
    websocket: WebSocket
    session_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    user_id: Optional[str] = None
    last_ping: Optional[datetime] = None
    subscriptions: Set[str] = field(default_factory=set)


class WebSocketManager:
    """Manages WebSocket connections for session streaming"""
    
    def __init__(self):
        # session_id -> List[WebSocketConnection]
        self.connections: Dict[str, List[WebSocketConnection]] = {}
        # websocket -> WebSocketConnection  
        self.websocket_to_connection: Dict[WebSocket, WebSocketConnection] = {}
        self.total_connections = 0
        self.heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start WebSocket manager with heartbeat monitoring"""
        if self._running:
            return
            
        self._running = True
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("WebSocket manager started")
        
    async def stop(self):
        """Stop WebSocket manager and disconnect all clients"""
        self._running = False
        
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect all clients
        for connections in self.connections.values():
            for conn in connections[:]:  # Copy list to avoid modification during iteration
                await self._disconnect_websocket(conn.websocket, "Server shutdown")
        
        logger.info("WebSocket manager stopped")
    
    async def connect(
        self, 
        websocket: WebSocket, 
        session_id: str, 
        user_id: Optional[str] = None
    ) -> WebSocketConnection:
        """Accept WebSocket connection and add to management"""
        
        await websocket.accept()
        
        # Create connection metadata
        connection = WebSocketConnection(
            websocket=websocket,
            session_id=session_id,
            user_id=user_id,
            connected_at=datetime.utcnow()
        )
        
        # Add to tracking structures
        if session_id not in self.connections:
            self.connections[session_id] = []
        
        self.connections[session_id].append(connection)
        self.websocket_to_connection[websocket] = connection
        self.total_connections += 1
        
        logger.info("WebSocket connected",
                   session_id=session_id,
                   user_id=user_id,
                   total_connections=self.total_connections)
        
        # Send initial connection message
        await self.send_to_websocket(websocket, {
            "event": "connected",
            "session_id": session_id,
            "connection_id": id(connection),
            "server_time": datetime.utcnow().isoformat()
        })
        
        # Publish connection event
        await self._publish_connection_event(
            EventType.SESSION_RESUMED,  # Closest event type for connection
            session_id,
            {
                "event": "websocket_connected",
                "user_id": user_id,
                "connection_time": connection.connected_at.isoformat()
            }
        )
        
        return connection
    
    async def disconnect(self, websocket: WebSocket, reason: str = "Client disconnect"):
        """Disconnect WebSocket and cleanup"""
        await self._disconnect_websocket(websocket, reason)
    
    async def _disconnect_websocket(self, websocket: WebSocket, reason: str):
        """Internal disconnect with cleanup"""
        
        connection = self.websocket_to_connection.get(websocket)
        if not connection:
            return
        
        session_id = connection.session_id
        
        # Remove from tracking
        if session_id in self.connections:
            try:
                self.connections[session_id].remove(connection)
                if not self.connections[session_id]:
                    del self.connections[session_id]
            except ValueError:
                pass  # Connection already removed
        
        del self.websocket_to_connection[websocket]
        self.total_connections -= 1
        
        # Close WebSocket if still open
        try:
            await websocket.close(code=1000, reason=reason)
        except:
            pass  # Already closed
        
        logger.info("WebSocket disconnected",
                   session_id=session_id,
                   user_id=connection.user_id,
                   reason=reason,
                   duration_seconds=(datetime.utcnow() - connection.connected_at).total_seconds(),
                   total_connections=self.total_connections)
        
        # Publish disconnection event
        await self._publish_connection_event(
            EventType.SESSION_TERMINATED,  # Closest event type for disconnection
            session_id,
            {
                "event": "websocket_disconnected",
                "reason": reason,
                "duration_seconds": (datetime.utcnow() - connection.connected_at).total_seconds()
            }
        )
    
    async def send_to_session(self, session_id: str, message: Dict[str, Any]) -> int:
        """Send message to all WebSocket connections for a session"""
        
        if session_id not in self.connections:
            return 0
        
        connections = self.connections[session_id][:]  # Copy to avoid modification during iteration
        sent_count = 0
        failed_connections = []
        
        for connection in connections:
            try:
                await self.send_to_websocket(connection.websocket, message)
                sent_count += 1
            except Exception as e:
                logger.warning("Failed to send message to WebSocket",
                             session_id=session_id,
                             error=str(e))
                failed_connections.append(connection.websocket)
        
        # Clean up failed connections
        for websocket in failed_connections:
            await self._disconnect_websocket(websocket, "Send failed")
        
        return sent_count
    
    async def send_to_websocket(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific WebSocket connection"""
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        
        try:
            if isinstance(message, dict):
                await websocket.send_json(message)
            else:
                await websocket.send_text(str(message))
                
        except Exception as e:
            logger.error("WebSocket send error", error=str(e))
            raise
    
    async def broadcast_to_all(self, message: Dict[str, Any]) -> int:
        """Broadcast message to all connected WebSockets"""
        
        total_sent = 0
        for session_id in list(self.connections.keys()):
            sent = await self.send_to_session(session_id, message)
            total_sent += sent
        
        return total_sent
    
    async def handle_message(
        self, 
        websocket: WebSocket, 
        message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle incoming WebSocket message"""
        
        connection = self.websocket_to_connection.get(websocket)
        if not connection:
            return {"event": "error", "message": "Connection not found"}
        
        message_type = message.get("type", "unknown")
        
        try:
            if message_type == "ping":
                connection.last_ping = datetime.utcnow()
                return {
                    "event": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            elif message_type == "subscribe":
                # Subscribe to additional event types
                event_types = message.get("events", [])
                connection.subscriptions.update(event_types)
                return {
                    "event": "subscribed",
                    "events": list(connection.subscriptions)
                }
            
            elif message_type == "unsubscribe":
                # Unsubscribe from event types
                event_types = message.get("events", [])
                connection.subscriptions.difference_update(event_types)
                return {
                    "event": "unsubscribed", 
                    "events": list(connection.subscriptions)
                }
            
            elif message_type == "get_info":
                # Return connection info
                return {
                    "event": "connection_info",
                    "session_id": connection.session_id,
                    "connected_at": connection.connected_at.isoformat(),
                    "subscriptions": list(connection.subscriptions),
                    "server_time": datetime.utcnow().isoformat()
                }
            
            else:
                logger.warning("Unknown WebSocket message type",
                             session_id=connection.session_id,
                             message_type=message_type)
                return {
                    "event": "error",
                    "message": f"Unknown message type: {message_type}"
                }
        
        except Exception as e:
            logger.error("WebSocket message handling error",
                        session_id=connection.session_id,
                        message_type=message_type,
                        error=str(e))
            return {
                "event": "error",
                "message": f"Message handling failed: {str(e)}"
            }
    
    async def _heartbeat_loop(self):
        """Monitor WebSocket connections with periodic heartbeat"""
        
        while self._running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self._running:
                    break
                
                now = datetime.utcnow()
                stale_connections = []
                
                # Check for stale connections (no ping in 2 minutes)
                for websocket, connection in list(self.websocket_to_connection.items()):
                    if connection.last_ping:
                        time_since_ping = (now - connection.last_ping).total_seconds()
                        if time_since_ping > 120:  # 2 minutes
                            stale_connections.append(websocket)
                    else:
                        # No ping ever received, check connection age
                        connection_age = (now - connection.connected_at).total_seconds()
                        if connection_age > 300:  # 5 minutes without any ping
                            stale_connections.append(websocket)
                
                # Clean up stale connections
                for websocket in stale_connections:
                    await self._disconnect_websocket(websocket, "Heartbeat timeout")
                
                # Send ping to all connections to check health
                ping_message = {
                    "event": "ping",
                    "server_time": now.isoformat()
                }
                
                for websocket in list(self.websocket_to_connection.keys()):
                    try:
                        await self.send_to_websocket(websocket, ping_message)
                    except:
                        # Connection failed, will be cleaned up in next iteration
                        pass
                
                if stale_connections:
                    logger.info("Cleaned up stale WebSocket connections",
                               count=len(stale_connections),
                               total_connections=self.total_connections)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("WebSocket heartbeat error", error=str(e))
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get WebSocket connection statistics"""
        
        session_counts = {}
        user_counts = {}
        subscription_counts = {}
        
        for session_id, connections in self.connections.items():
            session_counts[session_id] = len(connections)
            
            for conn in connections:
                if conn.user_id:
                    user_counts[conn.user_id] = user_counts.get(conn.user_id, 0) + 1
                
                for sub in conn.subscriptions:
                    subscription_counts[sub] = subscription_counts.get(sub, 0) + 1
        
        return {
            "total_connections": self.total_connections,
            "sessions_with_connections": len(self.connections),
            "connections_per_session": session_counts,
            "connections_per_user": user_counts,
            "subscription_counts": subscription_counts,
            "manager_running": self._running
        }
    
    async def _publish_connection_event(
        self, 
        event_type: EventType, 
        session_id: str, 
        payload: Dict[str, Any]
    ):
        """Publish WebSocket connection events to NATS"""
        try:
            await publish_event(event_type.value, session_id, payload)
        except Exception as e:
            logger.warning("Failed to publish WebSocket event",
                         event_type=event_type.value,
                         session_id=session_id,
                         error=str(e))


# Global WebSocket manager instance
_websocket_manager: Optional[WebSocketManager] = None


async def get_websocket_manager() -> WebSocketManager:
    """Get or create WebSocket manager instance"""
    global _websocket_manager
    
    if _websocket_manager is None:
        _websocket_manager = WebSocketManager()
        await _websocket_manager.start()
    
    return _websocket_manager


async def cleanup_websocket_manager():
    """Cleanup WebSocket manager"""
    global _websocket_manager
    
    if _websocket_manager:
        await _websocket_manager.stop()
        _websocket_manager = None