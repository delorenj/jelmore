"""NATS Monitoring and Metrics Service"""
import json
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import structlog
from dataclasses import dataclass, asdict

from .nats import js, publish_event, get_stream_info

logger = structlog.get_logger()


@dataclass
class EventMetrics:
    """Event metrics data structure"""
    topic: str
    count: int
    rate_per_minute: float
    avg_processing_time_ms: float
    error_rate: float
    last_event_time: Optional[datetime] = None


@dataclass  
class SystemHealth:
    """System health metrics"""
    stream_health: str  # healthy, degraded, critical
    consumer_lag: int
    dlq_message_count: int
    connection_status: str
    uptime_seconds: float
    memory_usage_mb: float


class NATSMonitor:
    """NATS monitoring and metrics collection"""
    
    def __init__(self):
        self.metrics: Dict[str, EventMetrics] = {}
        self.start_time = datetime.utcnow()
        self.monitoring_active = False
        
    async def start_monitoring(self):
        """Start continuous monitoring"""
        self.monitoring_active = True
        
        # Start metrics collection task
        asyncio.create_task(self._collect_metrics_loop())
        asyncio.create_task(self._health_check_loop())
        
        logger.info("NATS monitoring started")
    
    async def stop_monitoring(self):
        """Stop monitoring"""
        self.monitoring_active = False
        logger.info("NATS monitoring stopped")
    
    async def _collect_metrics_loop(self):
        """Collect metrics periodically"""
        while self.monitoring_active:
            try:
                await self._collect_current_metrics()
                await asyncio.sleep(60)  # Collect every minute
            except Exception as e:
                logger.error("Error collecting metrics", error=str(e))
                await asyncio.sleep(30)  # Retry after 30s on error
    
    async def _health_check_loop(self):
        """Perform health checks periodically"""
        while self.monitoring_active:
            try:
                health = await self.get_system_health()
                
                # Publish health metrics
                await publish_event(
                    "system.health",
                    "monitoring",
                    {
                        "health_status": health.stream_health,
                        "consumer_lag": health.consumer_lag,
                        "dlq_count": health.dlq_message_count,
                        "uptime_seconds": health.uptime_seconds
                    }
                )
                
                # Alert on critical issues
                if health.stream_health == "critical":
                    await self._send_alert("Critical NATS health detected", health)
                
                await asyncio.sleep(300)  # Health check every 5 minutes
            except Exception as e:
                logger.error("Error in health check", error=str(e))
                await asyncio.sleep(60)
    
    async def _collect_current_metrics(self):
        """Collect current metrics from streams"""
        try:
            info = await get_stream_info()
            
            # Update metrics based on stream info
            for consumer in info.get("consumers", []):
                consumer_name = consumer["name"]
                lag = consumer["num_pending"]
                
                # Calculate processing rate (simplified)
                delivered = consumer.get("delivered", 0)
                
                # Store consumer metrics
                self.metrics[f"consumer_{consumer_name}"] = EventMetrics(
                    topic=consumer_name,
                    count=delivered,
                    rate_per_minute=0.0,  # Would need historical data
                    avg_processing_time_ms=0.0,  # Would need timing data
                    error_rate=0.0,  # Would need error tracking
                    last_event_time=datetime.utcnow()
                )
            
            logger.debug("Metrics collected", consumers=len(info.get("consumers", [])))
            
        except Exception as e:
            logger.error("Failed to collect metrics", error=str(e))
    
    async def get_system_health(self) -> SystemHealth:
        """Get current system health status"""
        try:
            info = await get_stream_info()
            
            # Determine health status
            stream_health = "healthy"
            consumer_lag = 0
            
            # Check consumer lag
            for consumer in info.get("consumers", []):
                lag = consumer.get("num_pending", 0)
                consumer_lag = max(consumer_lag, lag)
                
                if lag > 1000:
                    stream_health = "critical"
                elif lag > 100:
                    stream_health = "degraded"
            
            # Check DLQ message count
            dlq_count = info.get("dlq_stream", {}).get("messages", 0)
            if dlq_count > 100:
                stream_health = "critical"
            elif dlq_count > 10:
                stream_health = "degraded"
            
            uptime = (datetime.utcnow() - self.start_time).total_seconds()
            
            return SystemHealth(
                stream_health=stream_health,
                consumer_lag=consumer_lag,
                dlq_message_count=dlq_count,
                connection_status="connected",  # Would check actual connection
                uptime_seconds=uptime,
                memory_usage_mb=0.0  # Would implement actual memory tracking
            )
            
        except Exception as e:
            logger.error("Failed to get system health", error=str(e))
            return SystemHealth(
                stream_health="critical",
                consumer_lag=-1,
                dlq_message_count=-1,
                connection_status="error",
                uptime_seconds=0.0,
                memory_usage_mb=0.0
            )
    
    async def _send_alert(self, message: str, health: SystemHealth):
        """Send alert for critical issues"""
        await publish_event(
            "system.alert",
            "monitoring", 
            {
                "alert_level": "critical",
                "message": message,
                "health_data": asdict(health),
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        logger.critical("NATS alert sent", message=message, health=asdict(health))
    
    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        try:
            info = await get_stream_info()
            health = await self.get_system_health()
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
                "health": asdict(health),
                "streams": {
                    "main": info.get("main_stream", {}),
                    "dlq": info.get("dlq_stream", {})
                },
                "consumers": info.get("consumers", []),
                "event_metrics": {k: asdict(v) for k, v in self.metrics.items()}
            }
            
        except Exception as e:
            logger.error("Failed to get metrics summary", error=str(e))
            return {"error": str(e)}
    
    async def get_consumer_performance(self, consumer_name: str) -> Dict[str, Any]:
        """Get detailed performance metrics for a consumer"""
        try:
            info = await get_stream_info()
            
            consumer_data = None
            for consumer in info.get("consumers", []):
                if consumer["name"] == consumer_name:
                    consumer_data = consumer
                    break
            
            if not consumer_data:
                return {"error": f"Consumer {consumer_name} not found"}
            
            return {
                "consumer": consumer_name,
                "delivered_count": consumer_data.get("delivered", 0),
                "pending_count": consumer_data.get("num_pending", 0),
                "ack_pending": consumer_data.get("ack_pending", 0),
                "processing_rate": self._calculate_processing_rate(consumer_name),
                "health_status": self._get_consumer_health(consumer_data)
            }
            
        except Exception as e:
            logger.error("Failed to get consumer performance", error=str(e))
            return {"error": str(e)}
    
    def _calculate_processing_rate(self, consumer_name: str) -> float:
        """Calculate processing rate for consumer (simplified)"""
        # This would require historical data tracking
        return 0.0
    
    def _get_consumer_health(self, consumer_data: Dict) -> str:
        """Determine consumer health status"""
        pending = consumer_data.get("num_pending", 0)
        ack_pending = consumer_data.get("ack_pending", 0)
        
        if pending > 1000 or ack_pending > 500:
            return "critical"
        elif pending > 100 or ack_pending > 50:
            return "degraded"
        else:
            return "healthy"


# Global monitor instance
monitor = NATSMonitor()


async def start_monitoring():
    """Start NATS monitoring"""
    await monitor.start_monitoring()


async def stop_monitoring():
    """Stop NATS monitoring"""
    await monitor.stop_monitoring()


async def get_health_status() -> Dict[str, Any]:
    """Get current health status"""
    health = await monitor.get_system_health()
    return asdict(health)


async def get_performance_metrics() -> Dict[str, Any]:
    """Get performance metrics summary"""
    return await monitor.get_metrics_summary()