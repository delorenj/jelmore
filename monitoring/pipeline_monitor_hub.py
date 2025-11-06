#!/usr/bin/env python3
"""
Pipeline Monitor Hub - Central Nervous System of Jelmore Hive Mind
Real-time monitoring and coordination hub for all pipeline activities
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import aiohttp
import nats
from nats.js import JetStreamContext
import structlog

# Initialize logger
logger = structlog.get_logger()

@dataclass
class PipelineMetrics:
    """Real-time pipeline metrics"""
    active_sessions: int = 0
    total_sessions: int = 0
    average_processing_time: float = 0.0
    success_rate: float = 0.0
    error_rate: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    queue_backlog: int = 0
    agent_health_score: float = 100.0
    last_updated: str = ""

@dataclass
class AlertConfig:
    """Alert thresholds configuration"""
    session_timeout_minutes: int = 5
    high_cpu_threshold: float = 80.0
    memory_threshold_gb: float = 4.0
    error_rate_threshold: float = 10.0
    queue_backlog_threshold: int = 10

@dataclass
class PipelineEvent:
    """Pipeline event structure"""
    event_id: str
    event_type: str
    session_id: str
    timestamp: str
    payload: Dict[str, Any]
    source: str  # api, nats, webhook
    processed: bool = False

class PipelineMonitorHub:
    """Central monitoring hub for Jelmore pipeline"""
    
    def __init__(self):
        self.metrics = PipelineMetrics()
        self.alerts = AlertConfig()
        self.event_queue = deque(maxlen=1000)  # Last 1000 events
        self.session_registry: Dict[str, Dict[str, Any]] = {}
        self.agent_registry: Dict[str, Dict[str, Any]] = {}
        self.performance_history = deque(maxlen=144)  # 24h at 10min intervals
        
        # Monitoring endpoints
        self.jelmore_api = "http://192.168.1.12:8000/api/v1"
        self.n8n_webhook = "http://192.168.1.12:5678/webhook/pr-events"
        self.nats_monitor = "http://192.168.1.12:8222"
        self.nats_url = "nats://192.168.1.12:4222"
        
        # Connection objects
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Monitoring state
        self.monitoring_active = False
        self.last_heartbeat = time.time()
        self.error_counts = defaultdict(int)
        self.anomaly_detections = []
        
        logger.info("🐝 Pipeline Monitor Hub initialized", 
                   endpoints={
                       "jelmore_api": self.jelmore_api,
                       "nats_monitor": self.nats_monitor,
                       "n8n_webhook": self.n8n_webhook
                   })

    async def initialize(self):
        """Initialize all monitoring connections"""
        try:
            logger.info("🔄 Initializing Pipeline Monitor Hub connections...")
            
            # Initialize HTTP session
            self.http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
            
            # Initialize NATS connection
            await self._connect_nats()
            
            # Subscribe to all jelmore.* events
            await self._subscribe_to_events()
            
            # Start monitoring tasks
            await self._start_monitoring_tasks()
            
            self.monitoring_active = True
            logger.info("✅ Pipeline Monitor Hub fully initialized and monitoring")
            
        except Exception as e:
            logger.error("❌ Failed to initialize Pipeline Monitor Hub", error=str(e))
            raise

    async def _connect_nats(self):
        """Connect to NATS and JetStream"""
        try:
            self.nats_client = await nats.connect(
                self.nats_url,
                reconnect_time_wait=2.0,
                max_reconnect_attempts=5
            )
            self.jetstream = self.nats_client.jetstream()
            logger.info("📡 Connected to NATS JetStream")
            
        except Exception as e:
            logger.error("❌ Failed to connect to NATS", error=str(e))
            raise

    async def _subscribe_to_events(self):
        """Subscribe to all jelmore.* events for monitoring"""
        try:
            # Subscribe to all jelmore events
            await self.nats_client.subscribe(
                "jelmore.>", 
                cb=self._handle_nats_event
            )
            logger.info("👂 Subscribed to all jelmore.* NATS events")
            
        except Exception as e:
            logger.error("❌ Failed to subscribe to NATS events", error=str(e))
            raise

    async def _handle_nats_event(self, msg):
        """Handle incoming NATS events"""
        try:
            event_data = json.loads(msg.data.decode())
            event = PipelineEvent(
                event_id=event_data.get("message_id", f"evt_{int(time.time()*1000)}"),
                event_type=msg.subject,
                session_id=event_data.get("session_id", "unknown"),
                timestamp=event_data.get("timestamp", datetime.utcnow().isoformat()),
                payload=event_data.get("payload", {}),
                source="nats"
            )
            
            await self._process_pipeline_event(event)
            
            # Store event in memory
            await self._store_event_memory(event)
            
        except Exception as e:
            logger.error("❌ Error handling NATS event", 
                        subject=msg.subject, error=str(e))

    async def _process_pipeline_event(self, event: PipelineEvent):
        """Process and route pipeline events"""
        try:
            # Update session registry
            if event.session_id != "unknown":
                await self._update_session_registry(event)
            
            # Route events to appropriate handlers
            if "session.created" in event.event_type:
                await self._handle_session_created(event)
            elif "session.completed" in event.event_type:
                await self._handle_session_completed(event)
            elif "session.failed" in event.event_type:
                await self._handle_session_failed(event)
            elif "pr.comment" in event.event_type:
                await self._handle_pr_comment(event)
                
            # Check for anomalies
            await self._detect_anomalies(event)
            
            # Update metrics
            await self._update_metrics()
            
            logger.debug("📊 Processed pipeline event", 
                        event_type=event.event_type,
                        session_id=event.session_id)
            
        except Exception as e:
            logger.error("❌ Error processing pipeline event", 
                        event=event.event_type, error=str(e))

    async def _handle_session_created(self, event: PipelineEvent):
        """Handle new session creation"""
        session_id = event.session_id
        self.session_registry[session_id] = {
            "status": "active",
            "created_at": event.timestamp,
            "last_activity": event.timestamp,
            "events": []
        }
        
        # Notify Session Analyzer + Quality Gate
        await self._notify_agents("session_analyzer,quality_gate", {
            "action": "new_session",
            "session_id": session_id,
            "event": asdict(event)
        })
        
        logger.info("🆕 New session created", session_id=session_id)

    async def _handle_session_completed(self, event: PipelineEvent):
        """Handle session completion"""
        session_id = event.session_id
        if session_id in self.session_registry:
            self.session_registry[session_id]["status"] = "completed"
            self.session_registry[session_id]["completed_at"] = event.timestamp
            
        logger.info("✅ Session completed", session_id=session_id)

    async def _handle_session_failed(self, event: PipelineEvent):
        """Handle session failure"""
        session_id = event.session_id
        if session_id in self.session_registry:
            self.session_registry[session_id]["status"] = "failed"
            self.session_registry[session_id]["failed_at"] = event.timestamp
            
        # Trigger Error Recovery + Quality Gate
        await self._notify_agents("error_recovery,quality_gate", {
            "action": "session_failed",
            "session_id": session_id,
            "event": asdict(event)
        })
        
        logger.error("❌ Session failed", session_id=session_id)

    async def _handle_pr_comment(self, event: PipelineEvent):
        """Handle PR comment events from webhooks"""
        # Notify Session Analyzer + Integration Validator
        await self._notify_agents("session_analyzer,integration_validator", {
            "action": "pr_comment",
            "event": asdict(event)
        })
        
        logger.info("💬 PR comment received", payload=event.payload)

    async def _notify_agents(self, agent_list: str, message: Dict[str, Any]):
        """Notify specific agents via memory broadcast"""
        try:
            # Store in hive mind broadcast memory
            await self._store_memory(f"hive/pipeline/broadcast", {
                "timestamp": datetime.utcnow().isoformat(),
                "target_agents": agent_list.split(","),
                "message": message,
                "source": "pipeline_monitor_hub"
            })
            
            logger.debug("📢 Notified agents", agents=agent_list)
            
        except Exception as e:
            logger.error("❌ Failed to notify agents", agents=agent_list, error=str(e))

    async def _detect_anomalies(self, event: PipelineEvent):
        """Detect pipeline anomalies and alerts"""
        current_time = datetime.utcnow()
        
        # Check for session timeouts
        for session_id, session_data in self.session_registry.items():
            if session_data["status"] == "active":
                last_activity = datetime.fromisoformat(session_data["last_activity"])
                if current_time - last_activity > timedelta(minutes=self.alerts.session_timeout_minutes):
                    await self._trigger_alert("session_timeout", {
                        "session_id": session_id,
                        "timeout_minutes": self.alerts.session_timeout_minutes
                    })
        
        # Check error rate
        if self.metrics.error_rate > self.alerts.error_rate_threshold:
            await self._trigger_alert("high_error_rate", {
                "current_rate": self.metrics.error_rate,
                "threshold": self.alerts.error_rate_threshold
            })

    async def _trigger_alert(self, alert_type: str, details: Dict[str, Any]):
        """Trigger system alert"""
        alert = {
            "alert_type": alert_type,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
            "severity": "high" if alert_type in ["session_timeout", "high_error_rate"] else "medium"
        }
        
        self.anomaly_detections.append(alert)
        
        # Store alert in memory
        await self._store_memory("hive/monitor/alerts", alert)
        
        logger.warning("🚨 Alert triggered", alert_type=alert_type, details=details)

    async def _update_metrics(self):
        """Update real-time metrics"""
        try:
            # Get session stats from API
            await self._fetch_session_stats()
            
            # Get system resources
            await self._fetch_system_resources()
            
            # Calculate derived metrics
            self._calculate_derived_metrics()
            
            # Store metrics in memory
            await self._store_memory("hive/monitor/metrics", asdict(self.metrics))
            
            self.metrics.last_updated = datetime.utcnow().isoformat()
            
        except Exception as e:
            logger.error("❌ Failed to update metrics", error=str(e))

    async def _fetch_session_stats(self):
        """Fetch session statistics from Jelmore API"""
        try:
            if not self.http_session:
                return
                
            async with self.http_session.get(f"{self.jelmore_api}/sessions/stats") as response:
                if response.status == 200:
                    stats = await response.json()
                    self.metrics.active_sessions = stats.get("active_sessions", 0)
                    self.metrics.total_sessions = stats.get("total_sessions", 0)
                    
        except Exception as e:
            logger.debug("Session stats fetch failed", error=str(e))

    async def _fetch_system_resources(self):
        """Fetch system resource usage"""
        try:
            # Get CPU and memory from NATS monitoring
            if not self.http_session:
                return
                
            async with self.http_session.get(f"{self.nats_monitor}/varz") as response:
                if response.status == 200:
                    varz = await response.json()
                    self.metrics.cpu_usage = varz.get("cpu", 0.0)
                    self.metrics.memory_usage = varz.get("mem", 0) / (1024**3)  # Convert to GB
                    
        except Exception as e:
            logger.debug("System resources fetch failed", error=str(e))

    def _calculate_derived_metrics(self):
        """Calculate derived metrics from collected data"""
        # Success rate calculation
        total_events = len(self.event_queue)
        if total_events > 0:
            error_events = sum(1 for e in self.event_queue if "failed" in e.event_type or "error" in e.event_type)
            self.metrics.error_rate = (error_events / total_events) * 100
            self.metrics.success_rate = 100 - self.metrics.error_rate
        
        # Agent health score (based on error rate and performance)
        health_score = 100 - (self.metrics.error_rate * 2)  # Each error % reduces health by 2
        self.metrics.agent_health_score = max(0, min(100, health_score))

    async def _update_session_registry(self, event: PipelineEvent):
        """Update session registry with event"""
        session_id = event.session_id
        if session_id not in self.session_registry:
            self.session_registry[session_id] = {
                "status": "unknown",
                "created_at": event.timestamp,
                "events": []
            }
        
        self.session_registry[session_id]["last_activity"] = event.timestamp
        self.session_registry[session_id]["events"].append({
            "type": event.event_type,
            "timestamp": event.timestamp
        })

    async def _store_event_memory(self, event: PipelineEvent):
        """Store event in agent memory"""
        await self._store_memory(f"hive/events/{event.session_id}", asdict(event))

    async def _store_memory(self, key: str, value: Any):
        """Store data in agent memory system"""
        try:
            # Use claude-flow hooks to store in memory
            import subprocess
            memory_data = json.dumps(value) if not isinstance(value, str) else value
            
            subprocess.run([
                "npx", "claude-flow@alpha", "hooks", "notify",
                "--message", f"Memory update: {key}",
                "--memory-key", key,
                "--telemetry", "true"
            ], capture_output=True, text=True, timeout=5)
            
        except Exception as e:
            logger.debug("Memory store failed", key=key, error=str(e))

    async def _start_monitoring_tasks(self):
        """Start background monitoring tasks"""
        # Periodic metrics update
        asyncio.create_task(self._periodic_metrics_update())
        
        # Heartbeat monitoring
        asyncio.create_task(self._heartbeat_monitor())
        
        # Performance history tracking
        asyncio.create_task(self._performance_tracker())

    async def _periodic_metrics_update(self):
        """Periodically update metrics"""
        while self.monitoring_active:
            try:
                await self._update_metrics()
                await asyncio.sleep(30)  # Update every 30 seconds
            except Exception as e:
                logger.error("Metrics update error", error=str(e))
                await asyncio.sleep(60)

    async def _heartbeat_monitor(self):
        """Monitor system heartbeat"""
        while self.monitoring_active:
            try:
                self.last_heartbeat = time.time()
                
                # Check component health
                health_status = await self._check_component_health()
                await self._store_memory("hive/monitor/health", health_status)
                
                await asyncio.sleep(60)  # Heartbeat every minute
            except Exception as e:
                logger.error("Heartbeat monitor error", error=str(e))
                await asyncio.sleep(60)

    async def _performance_tracker(self):
        """Track performance history"""
        while self.monitoring_active:
            try:
                performance_snapshot = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "metrics": asdict(self.metrics),
                    "active_sessions": len([s for s in self.session_registry.values() if s["status"] == "active"]),
                    "error_count": sum(self.error_counts.values())
                }
                
                self.performance_history.append(performance_snapshot)
                await self._store_memory("hive/monitor/performance_history", list(self.performance_history))
                
                await asyncio.sleep(600)  # Track every 10 minutes
            except Exception as e:
                logger.error("Performance tracker error", error=str(e))
                await asyncio.sleep(600)

    async def _check_component_health(self) -> Dict[str, Any]:
        """Check health of all monitored components"""
        health = {
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "jelmore_api": await self._check_api_health(),
                "nats": await self._check_nats_health(),
                "n8n_webhook": await self._check_webhook_health()
            },
            "overall_status": "unknown"
        }
        
        # Determine overall status
        component_statuses = [comp["status"] for comp in health["components"].values()]
        if all(status == "healthy" for status in component_statuses):
            health["overall_status"] = "healthy"
        elif any(status == "unhealthy" for status in component_statuses):
            health["overall_status"] = "unhealthy"
        else:
            health["overall_status"] = "degraded"
        
        return health

    async def _check_api_health(self) -> Dict[str, Any]:
        """Check Jelmore API health"""
        try:
            if not self.http_session:
                return {"status": "unhealthy", "reason": "No HTTP session"}
                
            async with self.http_session.get(f"{self.jelmore_api}/sessions/stats", 
                                           timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return {"status": "healthy", "response_time_ms": 0}  # Could measure actual time
                else:
                    return {"status": "unhealthy", "reason": f"HTTP {response.status}"}
        except Exception as e:
            return {"status": "unhealthy", "reason": str(e)}

    async def _check_nats_health(self) -> Dict[str, Any]:
        """Check NATS health"""
        try:
            if not self.nats_client or not self.nats_client.is_connected:
                return {"status": "unhealthy", "reason": "Not connected"}
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "reason": str(e)}

    async def _check_webhook_health(self) -> Dict[str, Any]:
        """Check N8N webhook health"""
        try:
            if not self.http_session:
                return {"status": "unknown", "reason": "No HTTP session"}
                
            # Just check if the webhook endpoint is reachable
            async with self.http_session.get(self.n8n_webhook.replace("/webhook/", "/"),
                                           timeout=aiohttp.ClientTimeout(total=3)) as response:
                return {"status": "healthy" if response.status < 500 else "degraded"}
        except Exception:
            return {"status": "unknown", "reason": "Not reachable"}

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get current dashboard data"""
        return {
            "metrics": asdict(self.metrics),
            "session_count": len(self.session_registry),
            "active_sessions": len([s for s in self.session_registry.values() if s["status"] == "active"]),
            "recent_events": [asdict(e) for e in list(self.event_queue)[-10:]],
            "alerts": self.anomaly_detections[-5:],  # Last 5 alerts
            "monitoring_status": "active" if self.monitoring_active else "inactive",
            "last_heartbeat": self.last_heartbeat
        }

    async def shutdown(self):
        """Gracefully shutdown the monitoring hub"""
        logger.info("🔄 Shutting down Pipeline Monitor Hub...")
        
        self.monitoring_active = False
        
        if self.nats_client:
            await self.nats_client.close()
        
        if self.http_session:
            await self.http_session.close()
        
        # Final memory update
        await self._store_memory("hive/monitor/shutdown", {
            "timestamp": datetime.utcnow().isoformat(),
            "final_metrics": asdict(self.metrics)
        })
        
        logger.info("✅ Pipeline Monitor Hub shutdown complete")

# Main execution
async def main():
    """Main execution function"""
    monitor_hub = PipelineMonitorHub()
    
    try:
        await monitor_hub.initialize()
        
        # Keep running until interrupted
        while monitor_hub.monitoring_active:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("👋 Received shutdown signal")
    except Exception as e:
        logger.error("❌ Monitor hub error", error=str(e))
    finally:
        await monitor_hub.shutdown()

if __name__ == "__main__":
    asyncio.run(main())