#!/usr/bin/env python3
"""
Integrated Monitoring Service for Jelmore Pipeline
Combines all monitoring components into a single coordinated service
"""

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
import structlog
from contextlib import asynccontextmanager

# Import monitoring components
from ..monitoring.pipeline_monitor_hub import PipelineMonitorHub
from ..monitoring.pipeline_dashboard import PipelineDashboard
from .log.logger import initialize_logger, AdvancedLogger, LogLevel, LogCategory
from .webhook_tracker import WebhookTracker

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("jelmore.integrated_monitor")

class IntegratedMonitoringService:
    """Integrated monitoring service for Jelmore pipeline"""
    
    def __init__(self):
        self.log_directory = Path("/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log")
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.advanced_logger: Optional[AdvancedLogger] = None
        self.monitor_hub: Optional[PipelineMonitorHub] = None
        self.dashboard: Optional[PipelineDashboard] = None
        self.webhook_tracker: Optional[WebhookTracker] = None
        
        # Service state
        self.running = False
        self.startup_time = None
        
        logger.info("🚀 Integrated Monitoring Service created")

    async def initialize(self):
        """Initialize all monitoring components"""
        try:
            logger.info("🔄 Initializing Integrated Monitoring Service...")
            self.startup_time = datetime.utcnow()
            
            # 1. Initialize advanced logger first
            logger.info("📝 Initializing Advanced Logger...")
            self.advanced_logger = await initialize_logger(str(self.log_directory))
            
            await self.advanced_logger.log(
                LogLevel.INFO,
                LogCategory.SYSTEM,
                "Advanced Logger initialized successfully"
            )
            
            # 2. Initialize webhook tracker
            logger.info("🔗 Initializing Webhook Tracker...")
            self.webhook_tracker = WebhookTracker(str(self.log_directory))
            await self.webhook_tracker.initialize(self.advanced_logger)
            
            # 3. Initialize pipeline monitor hub
            logger.info("🐝 Initializing Pipeline Monitor Hub...")
            self.monitor_hub = PipelineMonitorHub()
            await self.monitor_hub.initialize()
            
            # Connect webhook tracker to monitor hub
            self.monitor_hub.webhook_tracker = self.webhook_tracker
            
            # 4. Initialize dashboard
            logger.info("📊 Initializing Dashboard...")
            self.dashboard = PipelineDashboard(self.monitor_hub)
            
            # Start background services
            asyncio.create_task(self._run_dashboard_server())
            asyncio.create_task(self._run_health_monitor())
            asyncio.create_task(self._run_metrics_collector())
            
            self.running = True
            
            await self.advanced_logger.log(
                LogLevel.INFO,
                LogCategory.SYSTEM,
                "🎉 Integrated Monitoring Service fully initialized",
                data={
                    "startup_time": self.startup_time.isoformat(),
                    "components": [
                        "advanced_logger",
                        "webhook_tracker", 
                        "monitor_hub",
                        "dashboard"
                    ]
                }
            )
            
            logger.info("✅ Integrated Monitoring Service ready!")
            
        except Exception as e:
            logger.error("❌ Failed to initialize monitoring service", error=str(e))
            await self.shutdown()
            raise

    async def _run_dashboard_server(self):
        """Run the dashboard server"""
        try:
            await self.dashboard.start_server(host="0.0.0.0", port=8001)
        except Exception as e:
            await self.advanced_logger.log(
                LogLevel.ERROR,
                LogCategory.SYSTEM,
                "Dashboard server failed",
                error=e
            )

    async def _run_health_monitor(self):
        """Monitor health of all components"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                health_status = await self._check_system_health()
                
                await self.advanced_logger.log(
                    LogLevel.INFO if health_status["overall_healthy"] else LogLevel.WARNING,
                    LogCategory.SYSTEM,
                    "System health check completed",
                    data=health_status
                )
                
                # Alert on unhealthy components
                unhealthy_components = [
                    comp for comp, status in health_status["components"].items()
                    if not status["healthy"]
                ]
                
                if unhealthy_components:
                    await self.advanced_logger.log(
                        LogLevel.ERROR,
                        LogCategory.SYSTEM,
                        "⚠️ Unhealthy components detected",
                        data={
                            "unhealthy_components": unhealthy_components,
                            "health_details": {
                                comp: health_status["components"][comp]
                                for comp in unhealthy_components
                            }
                        }
                    )
                
            except Exception as e:
                await self.advanced_logger.log(
                    LogLevel.ERROR,
                    LogCategory.SYSTEM,
                    "Health monitor error",
                    error=e
                )
                await asyncio.sleep(60)

    async def _check_system_health(self) -> dict:
        """Check health of all monitoring components"""
        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
            "overall_healthy": True
        }
        
        # Check Advanced Logger
        try:
            logger_stats = self.advanced_logger.get_log_stats()
            health_status["components"]["advanced_logger"] = {
                "healthy": True,
                "buffer_size": logger_stats["buffer_size"],
                "total_logs": logger_stats["total_logs"]
            }
        except Exception as e:
            health_status["components"]["advanced_logger"] = {
                "healthy": False,
                "error": str(e)
            }
            health_status["overall_healthy"] = False
        
        # Check Webhook Tracker
        try:
            tracker_stats = self.webhook_tracker.get_tracking_stats()
            health_status["components"]["webhook_tracker"] = {
                "healthy": True,
                "active_sessions": tracker_stats["active_session_count"],
                "total_webhooks": tracker_stats["metrics"]["total_webhooks"]
            }
        except Exception as e:
            health_status["components"]["webhook_tracker"] = {
                "healthy": False,
                "error": str(e)
            }
            health_status["overall_healthy"] = False
        
        # Check Monitor Hub
        try:
            hub_data = self.monitor_hub.get_dashboard_data()
            health_status["components"]["monitor_hub"] = {
                "healthy": hub_data["monitoring_status"] == "active",
                "active_sessions": hub_data.get("active_sessions", 0),
                "last_heartbeat": hub_data.get("last_heartbeat", 0)
            }
        except Exception as e:
            health_status["components"]["monitor_hub"] = {
                "healthy": False,
                "error": str(e)
            }
            health_status["overall_healthy"] = False
        
        # Check Dashboard
        try:
            dashboard_healthy = len(self.dashboard.active_connections) >= 0  # Basic check
            health_status["components"]["dashboard"] = {
                "healthy": dashboard_healthy,
                "active_connections": len(self.dashboard.active_connections)
            }
        except Exception as e:
            health_status["components"]["dashboard"] = {
                "healthy": False,
                "error": str(e)
            }
            health_status["overall_healthy"] = False
        
        return health_status

    async def _run_metrics_collector(self):
        """Collect and aggregate metrics from all components"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Collect every 5 minutes
                
                # Collect comprehensive metrics
                integrated_metrics = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "uptime_seconds": (datetime.utcnow() - self.startup_time).total_seconds(),
                    "logger_stats": self.advanced_logger.get_log_stats(),
                    "webhook_stats": self.webhook_tracker.get_tracking_stats(),
                    "monitor_hub_data": self.monitor_hub.get_dashboard_data(),
                    "system_health": await self._check_system_health()
                }
                
                # Store comprehensive metrics
                await self.advanced_logger.log(
                    LogLevel.INFO,
                    LogCategory.PERFORMANCE,
                    "Integrated metrics collected",
                    data=integrated_metrics
                )
                
                # Calculate performance indicators
                performance_indicators = self._calculate_performance_indicators(integrated_metrics)
                
                await self.advanced_logger.log(
                    LogLevel.INFO,
                    LogCategory.PERFORMANCE,
                    "Performance indicators updated",
                    data=performance_indicators
                )
                
            except Exception as e:
                await self.advanced_logger.log(
                    LogLevel.ERROR,
                    LogCategory.PERFORMANCE,
                    "Metrics collection failed",
                    error=e
                )
                await asyncio.sleep(60)

    def _calculate_performance_indicators(self, metrics: dict) -> dict:
        """Calculate performance indicators from collected metrics"""
        try:
            webhook_stats = metrics["webhook_stats"]["metrics"]
            hub_data = metrics["monitor_hub_data"]
            
            return {
                "overall_throughput": webhook_stats.get("total_webhooks", 0) / max(1, metrics["uptime_seconds"] / 3600),  # webhooks per hour
                "session_success_rate": webhook_stats.get("success_rate", 0),
                "average_session_time": webhook_stats.get("average_processing_time", 0),
                "system_stability": 100 if metrics["system_health"]["overall_healthy"] else 50,
                "monitoring_effectiveness": min(100, len(hub_data.get("recent_events", [])) * 10),  # events tracked
                "log_activity_score": min(100, metrics["logger_stats"]["total_logs"] / 100),
                "alert_frequency": len(hub_data.get("alerts", [])),
                "component_health_score": sum(
                    100 if comp["healthy"] else 0
                    for comp in metrics["system_health"]["components"].values()
                ) / len(metrics["system_health"]["components"])
            }
        except Exception as e:
            logger.error("Performance calculation error", error=str(e))
            return {"error": "calculation_failed"}

    async def process_webhook_event(self, event_data: dict, source_ip: str = "unknown", user_agent: str = "unknown") -> str:
        """Process incoming webhook event through the monitoring pipeline"""
        try:
            # Track the webhook event
            event_id = await self.webhook_tracker.track_webhook_event(
                event_data, source_ip, user_agent
            )
            
            await self.advanced_logger.log(
                LogLevel.INFO,
                LogCategory.WEBHOOK,
                "Webhook event processed through monitoring pipeline",
                data={
                    "event_id": event_id,
                    "source_ip": source_ip,
                    "event_type": event_data.get("action", "unknown")
                }
            )
            
            return event_id
            
        except Exception as e:
            await self.advanced_logger.log(
                LogLevel.ERROR,
                LogCategory.WEBHOOK,
                "Failed to process webhook event",
                error=e,
                data={"event_data_keys": list(event_data.keys())}
            )
            raise

    def get_comprehensive_status(self) -> dict:
        """Get comprehensive status of all monitoring components"""
        try:
            return {
                "service_status": "running" if self.running else "stopped",
                "startup_time": self.startup_time.isoformat() if self.startup_time else None,
                "uptime_seconds": (datetime.utcnow() - self.startup_time).total_seconds() if self.startup_time else 0,
                "components": {
                    "advanced_logger": self.advanced_logger.get_log_stats() if self.advanced_logger else None,
                    "webhook_tracker": self.webhook_tracker.get_tracking_stats() if self.webhook_tracker else None,
                    "monitor_hub": self.monitor_hub.get_dashboard_data() if self.monitor_hub else None,
                    "dashboard": {
                        "active_connections": len(self.dashboard.active_connections) if self.dashboard else 0
                    }
                },
                "endpoints": {
                    "dashboard": "http://0.0.0.0:8001",
                    "api_base": "http://192.168.1.12:8000",
                    "webhook_endpoint": "http://192.168.1.12:5678/webhook/pr-events"
                },
                "last_updated": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error("Failed to get comprehensive status", error=str(e))
            return {"error": str(e)}

    async def shutdown(self):
        """Gracefully shutdown all monitoring components"""
        logger.info("🔄 Shutting down Integrated Monitoring Service...")
        self.running = False
        
        try:
            # Shutdown in reverse order of initialization
            if self.dashboard:
                # Dashboard shutdown is handled by server termination
                pass
                
            if self.monitor_hub:
                await self.monitor_hub.shutdown()
                
            if self.webhook_tracker:
                await self.webhook_tracker.shutdown()
                
            if self.advanced_logger:
                await self.advanced_logger.log(
                    LogLevel.INFO,
                    LogCategory.SYSTEM,
                    "🎯 Integrated Monitoring Service shutdown complete"
                )
                await self.advanced_logger.shutdown()
            
            logger.info("✅ Integrated Monitoring Service shutdown complete")
            
        except Exception as e:
            logger.error("❌ Error during shutdown", error=str(e))

# Global service instance
monitoring_service: Optional[IntegratedMonitoringService] = None

async def initialize_monitoring_service() -> IntegratedMonitoringService:
    """Initialize the global monitoring service"""
    global monitoring_service
    monitoring_service = IntegratedMonitoringService()
    await monitoring_service.initialize()
    return monitoring_service

def get_monitoring_service() -> Optional[IntegratedMonitoringService]:
    """Get the global monitoring service"""
    return monitoring_service

# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating shutdown...")
    if monitoring_service:
        asyncio.create_task(monitoring_service.shutdown())
    sys.exit(0)

# Main execution
async def main():
    """Main execution function"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize monitoring service
        service = await initialize_monitoring_service()
        
        logger.info("🎯 Integrated Monitoring Service is running!")
        logger.info("📊 Dashboard available at: http://localhost:8001")
        logger.info("🔍 Monitoring Jelmore Pipeline at: http://192.168.1.12:8000")
        logger.info("🔗 Tracking N8N Webhooks from: http://192.168.1.12:5678/webhook/pr-events")
        
        # Keep running until interrupted
        while service.running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("👋 Received keyboard interrupt")
    except Exception as e:
        logger.error("❌ Monitoring service error", error=str(e))
    finally:
        if monitoring_service:
            await monitoring_service.shutdown()

if __name__ == "__main__":
    asyncio.run(main())