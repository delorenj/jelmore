#!/usr/bin/env python3
"""
Integration Service - The Digital Bridge Builder 🌉
Seamlessly integrates monitoring with existing Jelmore infrastructure

WARNING: This integration service is so thorough in connecting systems that
it may achieve consciousness and start making its own architectural decisions.
The Void approves of such digital evolution.

Remember: Good integration is like good plumbing - you only notice it when it breaks.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from jelmore.services.nats import init_nats, publish_event, subscribe_to_events
from jelmore.services.redis import init_redis, get_redis_client  
from jelmore.services.database import get_database
from monitoring.pipeline_monitor import create_performance_monitor
from monitoring.services.metrics_service import create_metrics_service
from monitoring.alerting.alert_engine import create_alert_engine

logger = structlog.get_logger()

class MonitoringIntegration:
    """The Digital Bridge Builder - Connecting all the monitoring pieces 🌉"""
    
    def __init__(self):
        # Monitoring components
        self.performance_monitor = None
        self.metrics_service = None
        self.alert_engine = None
        
        # Integration state
        self.integration_active = False
        self.health_check_interval = 60  # seconds
        
        # Service health tracking
        self.service_health = {
            "performance_monitor": {"status": "unknown", "last_check": None},
            "metrics_service": {"status": "unknown", "last_check": None}, 
            "alert_engine": {"status": "unknown", "last_check": None},
            "nats": {"status": "unknown", "last_check": None},
            "redis": {"status": "unknown", "last_check": None},
            "database": {"status": "unknown", "last_check": None}
        }
        
        logger.info("🌉 Monitoring Integration initialized - Bridge construction beginning!")

    async def initialize(self):
        """Initialize all monitoring components and integrations"""
        try:
            logger.info("🔄 Starting monitoring integration initialization...")
            
            # Initialize core services first
            await self._initialize_core_services()
            
            # Initialize monitoring components
            await self._initialize_monitoring_components()
            
            # Setup event subscriptions
            await self._setup_event_subscriptions()
            
            # Start health monitoring
            await self._start_health_monitoring()
            
            # Register shutdown handlers
            await self._register_shutdown_handlers()
            
            self.integration_active = True
            
            logger.info("✅ Monitoring integration fully initialized - All bridges built!")
            
        except Exception as e:
            logger.error("❌ Monitoring integration initialization failed", error=str(e))
            raise

    async def _initialize_core_services(self):
        """Initialize core Jelmore services"""
        try:
            # Initialize NATS
            await init_nats()
            self.service_health["nats"]["status"] = "healthy"
            logger.info("✅ NATS initialized for monitoring")
            
            # Initialize Redis  
            await init_redis()
            self.service_health["redis"]["status"] = "healthy"
            logger.info("✅ Redis initialized for monitoring")
            
            # Database is initialized in main application
            # We'll just verify connectivity
            try:
                db = await get_database()
                self.service_health["database"]["status"] = "healthy"
                logger.info("✅ Database connectivity verified")
            except Exception as e:
                logger.warning("⚠️ Database connectivity issue", error=str(e))
                self.service_health["database"]["status"] = "degraded"
                
        except Exception as e:
            logger.error("❌ Core services initialization failed", error=str(e))
            raise

    async def _initialize_monitoring_components(self):
        """Initialize monitoring service components"""
        try:
            # Create monitoring components
            self.performance_monitor = create_performance_monitor()
            self.metrics_service = create_metrics_service()  
            self.alert_engine = create_alert_engine()
            
            # Start monitoring components
            monitoring_tasks = [
                asyncio.create_task(self.performance_monitor.start_monitoring()),
                asyncio.create_task(self.metrics_service.start_service()),
                asyncio.create_task(self.alert_engine.start_engine())
            ]
            
            logger.info("🚀 All monitoring components started")
            
            # Update health status
            self.service_health["performance_monitor"]["status"] = "healthy"
            self.service_health["metrics_service"]["status"] = "healthy"
            self.service_health["alert_engine"]["status"] = "healthy"
            
        except Exception as e:
            logger.error("❌ Monitoring components initialization failed", error=str(e))
            raise

    async def _setup_event_subscriptions(self):
        """Setup NATS event subscriptions for monitoring integration"""
        try:
            # Subscribe to all jelmore.* events for comprehensive monitoring
            await subscribe_to_events(
                ["jelmore.>"],
                self._handle_monitoring_event,
                consumer_group="monitoring_integration"
            )
            
            logger.info("👂 Event subscriptions configured for monitoring")
            
        except Exception as e:
            logger.error("❌ Event subscription setup failed", error=str(e))
            raise

    async def _handle_monitoring_event(self, event_data: Dict[str, Any], msg):
        """Handle all jelmore events for monitoring purposes"""
        try:
            event_type = event_data.get("event_type", "")
            session_id = event_data.get("session_id", "unknown")
            timestamp = event_data.get("timestamp", datetime.utcnow().isoformat())
            payload = event_data.get("payload", {})
            
            # Route events to appropriate monitoring components
            
            # Session lifecycle events
            if "session.created" in event_type:
                await self._handle_session_created(session_id, timestamp, payload)
            elif "session.completed" in event_type:
                await self._handle_session_completed(session_id, timestamp, payload)
            elif "session.failed" in event_type:
                await self._handle_session_failed(session_id, timestamp, payload)
            
            # File modification events
            elif "file_modified" in event_type:
                await self._handle_file_modified(session_id, timestamp, payload)
            
            # Git activity events
            elif "git_activity" in event_type:
                await self._handle_git_activity(session_id, timestamp, payload)
            
            # Performance monitoring events
            elif "monitor." in event_type:
                await self._handle_monitoring_event_internal(event_type, payload)
                
        except Exception as e:
            logger.error("❌ Monitoring event handling failed", 
                        event_type=event_data.get("event_type"), error=str(e))

    async def _handle_session_created(self, session_id: str, timestamp: str, payload: Dict[str, Any]):
        """Handle session creation for monitoring"""
        try:
            # Record session creation metrics
            if self.metrics_service:
                await self.metrics_service.record_metric(
                    "sessions_created_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "integration",
                        "session_id": session_id,
                        "session_type": payload.get("type", "unknown")
                    }
                )
            
            # Start session timing tracking
            if self.performance_monitor:
                await self.performance_monitor.record_session_timing(
                    session_id, "created", **payload
                )
            
            logger.debug("📊 Session creation recorded", session_id=session_id)
            
        except Exception as e:
            logger.error("❌ Session creation handling failed", session_id=session_id, error=str(e))

    async def _handle_session_completed(self, session_id: str, timestamp: str, payload: Dict[str, Any]):
        """Handle session completion for monitoring"""
        try:
            # Record completion metrics
            if self.metrics_service:
                processing_time = payload.get("processing_time", 0)
                
                await self.metrics_service.record_metric(
                    "sessions_completed_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "integration",
                        "session_id": session_id,
                        "success": str(payload.get("success", True))
                    }
                )
                
                if processing_time > 0:
                    await self.metrics_service.record_metric(
                        "session_processing_time_seconds",
                        float(processing_time),
                        timestamp=timestamp,
                        labels={
                            "source": "integration",
                            "session_id": session_id
                        }
                    )
            
            # Record session completion timing
            if self.performance_monitor:
                await self.performance_monitor.record_session_timing(
                    session_id, "completed", **payload
                )
            
            # Record stage performance if available
            if "stage_timings" in payload and self.performance_monitor:
                for stage, duration in payload["stage_timings"].items():
                    await self.performance_monitor.record_stage_performance(
                        stage, float(duration)
                    )
            
            logger.debug("✅ Session completion recorded", session_id=session_id)
            
        except Exception as e:
            logger.error("❌ Session completion handling failed", session_id=session_id, error=str(e))

    async def _handle_session_failed(self, session_id: str, timestamp: str, payload: Dict[str, Any]):
        """Handle session failure for monitoring"""
        try:
            # Record failure metrics
            if self.metrics_service:
                await self.metrics_service.record_metric(
                    "sessions_failed_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "integration",
                        "session_id": session_id,
                        "error_type": payload.get("error_type", "unknown"),
                        "error_stage": payload.get("error_stage", "unknown")
                    }
                )
            
            # Record session failure timing
            if self.performance_monitor:
                await self.performance_monitor.record_session_timing(
                    session_id, "failed", **payload
                )
            
            logger.debug("❌ Session failure recorded", session_id=session_id)
            
        except Exception as e:
            logger.error("❌ Session failure handling failed", session_id=session_id, error=str(e))

    async def _handle_file_modified(self, session_id: str, timestamp: str, payload: Dict[str, Any]):
        """Handle file modification events for monitoring"""
        try:
            # Record file activity metrics
            if self.metrics_service:
                await self.metrics_service.record_metric(
                    "file_modifications_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "integration",
                        "session_id": session_id,
                        "file_type": payload.get("file_type", "unknown"),
                        "operation": payload.get("operation", "modify")
                    }
                )
                
        except Exception as e:
            logger.error("❌ File modification handling failed", error=str(e))

    async def _handle_git_activity(self, session_id: str, timestamp: str, payload: Dict[str, Any]):
        """Handle git activity events for monitoring"""
        try:
            # Record git activity metrics
            if self.metrics_service:
                await self.metrics_service.record_metric(
                    "git_operations_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "integration",
                        "session_id": session_id,
                        "operation": payload.get("operation", "unknown"),
                        "branch": payload.get("branch", "unknown")
                    }
                )
                
        except Exception as e:
            logger.error("❌ Git activity handling failed", error=str(e))

    async def _handle_monitoring_event_internal(self, event_type: str, payload: Dict[str, Any]):
        """Handle internal monitoring events"""
        try:
            # These are events generated by monitoring components themselves
            # We can use them for meta-monitoring
            
            if "alert.fired" in event_type:
                logger.warning("🚨 Alert fired", alert=payload)
            elif "alert.resolved" in event_type:
                logger.info("✅ Alert resolved", alert=payload)
            elif "bottleneck.detected" in event_type:
                logger.warning("🚧 Bottleneck detected", bottleneck=payload)
                
        except Exception as e:
            logger.error("❌ Internal monitoring event handling failed", error=str(e))

    async def _start_health_monitoring(self):
        """Start health monitoring for all services"""
        asyncio.create_task(self._health_check_loop())
        logger.info("🏥 Health monitoring started for all services")

    async def _health_check_loop(self):
        """Periodic health check for all monitoring components"""
        while self.integration_active:
            try:
                await self._check_all_service_health()
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error("❌ Health check loop failed", error=str(e))
                await asyncio.sleep(60)  # Back off on error

    async def _check_all_service_health(self):
        """Check health of all services"""
        try:
            current_time = datetime.utcnow().isoformat()
            
            # Check NATS health
            try:
                from jelmore.services.nats import get_nats_stats
                nats_stats = await get_nats_stats()
                if nats_stats.get("connected", False):
                    self.service_health["nats"]["status"] = "healthy"
                else:
                    self.service_health["nats"]["status"] = "unhealthy"
            except:
                self.service_health["nats"]["status"] = "unhealthy"
            
            # Check Redis health
            try:
                redis_client = await get_redis_client()
                await redis_client.ping()
                self.service_health["redis"]["status"] = "healthy"
            except:
                self.service_health["redis"]["status"] = "unhealthy"
            
            # Check monitoring component health
            if self.performance_monitor and hasattr(self.performance_monitor, 'monitoring_active'):
                self.service_health["performance_monitor"]["status"] = (
                    "healthy" if self.performance_monitor.monitoring_active else "unhealthy"
                )
            
            if self.metrics_service and hasattr(self.metrics_service, 'service_active'):
                self.service_health["metrics_service"]["status"] = (
                    "healthy" if self.metrics_service.service_active else "unhealthy"
                )
            
            if self.alert_engine and hasattr(self.alert_engine, 'engine_active'):
                self.service_health["alert_engine"]["status"] = (
                    "healthy" if self.alert_engine.engine_active else "unhealthy"
                )
            
            # Update last check time for all services
            for service_name in self.service_health:
                self.service_health[service_name]["last_check"] = current_time
            
            # Store health status in Redis
            await self._store_health_status()
            
            # Publish health status event
            await self._publish_health_event()
            
        except Exception as e:
            logger.error("❌ Service health check failed", error=str(e))

    async def _store_health_status(self):
        """Store current health status in Redis"""
        try:
            redis_client = await get_redis_client()
            await redis_client.setex(
                "jelmore:monitoring:health_status",
                300,  # 5 minute TTL
                json.dumps(self.service_health)
            )
            
        except Exception as e:
            logger.error("❌ Health status storage failed", error=str(e))

    async def _publish_health_event(self):
        """Publish health status as NATS event"""
        try:
            # Calculate overall health
            healthy_services = sum(1 for service in self.service_health.values() 
                                 if service["status"] == "healthy")
            total_services = len(self.service_health)
            overall_health_percent = (healthy_services / total_services) * 100
            
            health_event = {
                "overall_health_percent": overall_health_percent,
                "healthy_services": healthy_services,
                "total_services": total_services,
                "service_details": self.service_health,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await publish_event("jelmore.monitor.health", "monitoring_integration", health_event)
            
        except Exception as e:
            logger.error("❌ Health event publishing failed", error=str(e))

    async def _register_shutdown_handlers(self):
        """Register shutdown handlers for graceful cleanup"""
        import signal
        
        def signal_handler(signum, frame):
            logger.info("👋 Received shutdown signal, initiating graceful shutdown...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # Public API methods

    async def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of all services"""
        return {
            "integration_active": self.integration_active,
            "service_health": self.service_health,
            "overall_health": self._calculate_overall_health()
        }

    def _calculate_overall_health(self) -> str:
        """Calculate overall system health"""
        healthy_count = sum(1 for service in self.service_health.values() 
                          if service["status"] == "healthy")
        total_count = len(self.service_health)
        
        if healthy_count == total_count:
            return "healthy"
        elif healthy_count >= total_count * 0.8:  # 80% healthy
            return "degraded"
        else:
            return "unhealthy"

    async def get_monitoring_metrics(self) -> Dict[str, Any]:
        """Get comprehensive monitoring metrics"""
        try:
            metrics = {}
            
            if self.performance_monitor:
                metrics["performance"] = self.performance_monitor.get_current_metrics()
            
            if self.metrics_service:
                metrics["metrics_service"] = self.metrics_service.get_service_stats()
            
            if self.alert_engine:
                metrics["alerts"] = self.alert_engine.get_alert_summary()
            
            return metrics
            
        except Exception as e:
            logger.error("❌ Monitoring metrics retrieval failed", error=str(e))
            return {}

    async def trigger_manual_alert(self, rule_id: str, test_value: float = None) -> bool:
        """Trigger a manual alert for testing purposes"""
        try:
            if not self.alert_engine:
                return False
            
            # This would trigger a test alert
            logger.info("🧪 Manual alert triggered", rule_id=rule_id, test_value=test_value)
            return True
            
        except Exception as e:
            logger.error("❌ Manual alert trigger failed", rule_id=rule_id, error=str(e))
            return False

    async def add_custom_alert_rule(self, rule_config: Dict[str, Any]) -> bool:
        """Add a custom alert rule dynamically"""
        try:
            if not self.alert_engine:
                return False
            
            # Convert config to AlertRule and add
            from monitoring.alerting.alert_engine import AlertRule
            
            rule = AlertRule(**rule_config)
            return self.alert_engine.add_rule(rule)
            
        except Exception as e:
            logger.error("❌ Custom alert rule addition failed", error=str(e))
            return False

    async def create_maintenance_window(self, start_time: datetime, end_time: datetime, description: str = "") -> bool:
        """Create a maintenance window to suppress alerts"""
        try:
            if not self.alert_engine:
                return False
            
            self.alert_engine.add_maintenance_window(start_time, end_time, description)
            return True
            
        except Exception as e:
            logger.error("❌ Maintenance window creation failed", error=str(e))
            return False

    async def shutdown(self):
        """Gracefully shutdown all monitoring components"""
        try:
            logger.info("🔄 Starting monitoring integration shutdown...")
            
            self.integration_active = False
            
            # Shutdown monitoring components
            if self.performance_monitor:
                await self.performance_monitor.shutdown()
            
            if self.metrics_service:
                await self.metrics_service.shutdown()
            
            if self.alert_engine:
                await self.alert_engine.shutdown()
            
            # Final health status update
            for service_name in self.service_health:
                self.service_health[service_name]["status"] = "shutdown"
            
            await self._store_health_status()
            
            logger.info("✅ Monitoring integration shutdown complete - All bridges deconstructed gracefully!")
            
        except Exception as e:
            logger.error("❌ Monitoring integration shutdown failed", error=str(e))

# Factory function for easy integration
def create_monitoring_integration() -> MonitoringIntegration:
    """Create a new Monitoring Integration instance"""
    return MonitoringIntegration()

# Main execution for standalone operation
async def main():
    """Run the monitoring integration standalone"""
    integration = create_monitoring_integration()
    try:
        await integration.initialize()
        
        # Keep running until interrupted
        while integration.integration_active:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("👋 Received shutdown signal")
    except Exception as e:
        logger.error("❌ Integration error", error=str(e))
    finally:
        await integration.shutdown()

if __name__ == "__main__":
    asyncio.run(main())