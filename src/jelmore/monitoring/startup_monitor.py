"""Startup Performance Monitoring and Health Checks

This module provides comprehensive startup monitoring, bottleneck identification,
and performance optimization tracking for the Infrastructure Parallelization Protocol.

Features that would make even the most hardened DevOps engineer weep tears of joy:
- Real-time startup time tracking with sub-second precision
- Service initialization bottleneck identification
- Composite health status aggregation
- Performance regression detection
- Startup optimization recommendations
- Circuit breaker status monitoring

WARNING: This module contains advanced monitoring patterns that may cause:
- Sudden awareness of all performance bottlenecks in your infrastructure
- Uncontrollable urge to optimize everything in parallel
- Spontaneous improvement in monitoring practices
- Ability to troubleshoot startup issues in record time
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

import structlog


logger = structlog.get_logger("jelmore.startup_monitor")


class HealthStatus(Enum):
    """Overall system health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Individual service health status"""
    name: str
    status: HealthStatus
    response_time_ms: float
    last_check: datetime
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class StartupPerformanceReport:
    """Comprehensive startup performance report"""
    total_startup_time_seconds: float
    parallel_efficiency_percent: float
    bottleneck_service: str
    bottleneck_time_seconds: float
    services_healthy: int
    services_failed: int
    startup_timestamp: datetime
    recommendations: List[str]
    performance_grade: str  # A, B, C, D, F


class StartupMonitor:
    """The Ultimate Startup Performance Monitor™
    
    This class monitors your startup performance with the dedication of a
    DevOps engineer on their first day and the precision of a Swiss atomic clock.
    """
    
    def __init__(self):
        self.startup_history: List[Dict[str, Any]] = []
        self.current_startup_start = None
        self.service_timings = {}
        self.performance_baseline = {
            "excellent": 15.0,  # < 15 seconds = A grade
            "good": 25.0,       # < 25 seconds = B grade  
            "acceptable": 40.0, # < 40 seconds = C grade
            "poor": 60.0,       # < 60 seconds = D grade
            # > 60 seconds = F grade (unacceptable)
        }
    
    def start_monitoring(self):
        """Start monitoring startup performance"""
        self.current_startup_start = time.time()
        self.service_timings = {}
        logger.info("📊 Startup performance monitoring initiated")
    
    def record_service_timing(self, service_name: str, duration_seconds: float):
        """Record timing for individual service initialization"""
        self.service_timings[service_name] = duration_seconds
        logger.debug("Service timing recorded",
                    service=service_name,
                    duration_seconds=round(duration_seconds, 3))
    
    def complete_monitoring(self, startup_metrics: Any) -> StartupPerformanceReport:
        """Complete monitoring and generate performance report"""
        if not self.current_startup_start:
            raise ValueError("Monitoring not started - call start_monitoring() first")
        
        total_time = time.time() - self.current_startup_start
        
        # Calculate parallel efficiency
        sequential_time = sum(result.startup_time for result in startup_metrics.service_results)
        parallel_efficiency = (sequential_time / total_time * 100) if total_time > 0 else 0
        
        # Identify bottleneck
        slowest_service = max(startup_metrics.service_results, 
                            key=lambda x: x.startup_time,
                            default=None)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(startup_metrics, total_time)
        
        # Calculate performance grade
        grade = self._calculate_performance_grade(total_time)
        
        report = StartupPerformanceReport(
            total_startup_time_seconds=total_time,
            parallel_efficiency_percent=parallel_efficiency,
            bottleneck_service=slowest_service.name if slowest_service else "unknown",
            bottleneck_time_seconds=slowest_service.startup_time if slowest_service else 0.0,
            services_healthy=startup_metrics.services_healthy,
            services_failed=startup_metrics.services_failed,
            startup_timestamp=datetime.utcnow(),
            recommendations=recommendations,
            performance_grade=grade
        )
        
        # Store in history
        self.startup_history.append(asdict(report))
        
        # Log comprehensive results
        logger.info("📊 Startup performance report generated",
                   grade=grade,
                   total_seconds=round(total_time, 3),
                   efficiency_percent=round(parallel_efficiency, 1),
                   bottleneck=slowest_service.name if slowest_service else "none",
                   recommendations_count=len(recommendations))
        
        return report
    
    def _generate_recommendations(self, 
                                startup_metrics: Any, 
                                total_time: float) -> List[str]:
        """Generate startup optimization recommendations"""
        recommendations = []
        
        # Time-based recommendations
        if total_time > 60:
            recommendations.append("🚨 CRITICAL: Startup time > 60s indicates severe bottlenecks")
            recommendations.append("🔧 Consider implementing connection pooling")
            recommendations.append("⚡ Review database initialization queries")
        elif total_time > 40:
            recommendations.append("⚠️ Startup time > 40s suggests optimization opportunities")
            recommendations.append("🔧 Review service health check intervals")
        elif total_time < 15:
            recommendations.append("🎉 EXCELLENT startup time - infrastructure is optimal!")
        
        # Service failure recommendations
        if startup_metrics.services_failed > 0:
            recommendations.append(f"🛠️ {startup_metrics.services_failed} services failed - check error logs")
            recommendations.append("🔄 Implement exponential backoff retry logic")
            recommendations.append("🏥 Consider circuit breaker patterns")
        
        # Efficiency recommendations
        parallel_efficiency = (sum(r.startup_time for r in startup_metrics.service_results) / total_time * 100) if total_time > 0 else 0
        if parallel_efficiency < 200:
            recommendations.append("📈 Low parallel efficiency - review asyncio.gather() usage")
            recommendations.append("⚙️ Consider increasing connection pool sizes")
        
        # Service-specific recommendations
        for result in startup_metrics.service_results:
            if result.startup_time > 20:
                recommendations.append(f"🐌 {result.name} taking {result.startup_time:.1f}s - needs optimization")
        
        return recommendations[:10]  # Limit to top 10 recommendations
    
    def _calculate_performance_grade(self, total_time: float) -> str:
        """Calculate startup performance grade"""
        if total_time <= self.performance_baseline["excellent"]:
            return "A"
        elif total_time <= self.performance_baseline["good"]:
            return "B"
        elif total_time <= self.performance_baseline["acceptable"]:
            return "C"
        elif total_time <= self.performance_baseline["poor"]:
            return "D"
        else:
            return "F"
    
    def get_performance_trends(self, limit: int = 10) -> Dict[str, Any]:
        """Get startup performance trends over time"""
        recent_startups = self.startup_history[-limit:]
        
        if not recent_startups:
            return {"status": "no_data", "message": "No startup history available"}
        
        # Calculate trends
        times = [s["total_startup_time_seconds"] for s in recent_startups]
        avg_time = sum(times) / len(times)
        
        # Performance trend (getting better/worse)
        if len(times) >= 2:
            trend = "improving" if times[-1] < times[0] else "degrading"
        else:
            trend = "stable"
        
        return {
            "average_startup_time": round(avg_time, 3),
            "latest_startup_time": round(times[-1], 3),
            "trend": trend,
            "startup_count": len(recent_startups),
            "performance_grades": [s["performance_grade"] for s in recent_startups]
        }


class HealthCheckManager:
    """Composite health check manager for all services"""
    
    def __init__(self):
        self.service_checks: Dict[str, ServiceHealth] = {}
        self.check_timeout = 5.0  # 5 second timeout for health checks
    
    async def check_service_health(self, 
                                 service_name: str,
                                 check_func: callable,
                                 timeout: Optional[float] = None) -> ServiceHealth:
        """Check health of individual service"""
        check_start = time.time()
        check_timeout = timeout or self.check_timeout
        
        try:
            # Run health check with timeout
            result = await asyncio.wait_for(
                check_func(),
                timeout=check_timeout
            )
            
            response_time = (time.time() - check_start) * 1000  # Convert to milliseconds
            
            health = ServiceHealth(
                name=service_name,
                status=HealthStatus.HEALTHY,
                response_time_ms=response_time,
                last_check=datetime.utcnow(),
                metadata={"result": str(result) if result else "healthy"}
            )
            
            self.service_checks[service_name] = health
            
            logger.debug("Service health check passed",
                        service=service_name,
                        response_time_ms=round(response_time, 1))
            
            return health
            
        except asyncio.TimeoutError:
            response_time = check_timeout * 1000
            health = ServiceHealth(
                name=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                last_check=datetime.utcnow(),
                error=f"Health check timeout after {check_timeout}s"
            )
            
            self.service_checks[service_name] = health
            logger.warning("Service health check timeout", service=service_name)
            return health
            
        except Exception as e:
            response_time = (time.time() - check_start) * 1000
            health = ServiceHealth(
                name=service_name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                last_check=datetime.utcnow(),
                error=str(e)
            )
            
            self.service_checks[service_name] = health
            logger.error("Service health check failed", service=service_name, error=str(e))
            return health
    
    async def run_all_health_checks(self, 
                                   health_check_configs: List[Tuple[str, callable]]) -> Dict[str, Any]:
        """Run all health checks in parallel"""
        logger.info("🏥 Running comprehensive health checks", 
                   total_checks=len(health_check_configs))
        
        # Create health check tasks
        tasks = []
        for service_name, check_func in health_check_configs:
            task = asyncio.create_task(
                self.check_service_health(service_name, check_func),
                name=f"health-{service_name}"
            )
            tasks.append(task)
        
        # Run all health checks in parallel
        try:
            health_results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.error("Critical error during health checks", error=str(e))
            health_results = []
        
        # Calculate composite health status
        composite_status = self._calculate_composite_health()
        
        # Generate health report
        report = {
            "overall_status": composite_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                service.name: {
                    "status": service.status.value,
                    "response_time_ms": service.response_time_ms,
                    "last_check": service.last_check.isoformat(),
                    "error": service.error
                }
                for service in self.service_checks.values()
            },
            "summary": {
                "total_services": len(self.service_checks),
                "healthy_services": sum(1 for s in self.service_checks.values() 
                                      if s.status == HealthStatus.HEALTHY),
                "unhealthy_services": sum(1 for s in self.service_checks.values() 
                                        if s.status == HealthStatus.UNHEALTHY),
                "average_response_time_ms": sum(s.response_time_ms for s in self.service_checks.values()) / len(self.service_checks) if self.service_checks else 0
            }
        }
        
        logger.info("🏥 Health checks complete",
                   overall_status=composite_status.value,
                   healthy_count=report["summary"]["healthy_services"],
                   unhealthy_count=report["summary"]["unhealthy_services"])
        
        return report
    
    def _calculate_composite_health(self) -> HealthStatus:
        """Calculate composite health status from all services"""
        if not self.service_checks:
            return HealthStatus.UNKNOWN
        
        statuses = [service.status for service in self.service_checks.values()]
        
        # If any service is unhealthy, overall status is degraded
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.DEGRADED
        
        # If all services are healthy, overall status is healthy
        if all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        
        # Otherwise, we're in a degraded state
        return HealthStatus.DEGRADED


# Global monitor instances
_startup_monitor = None
_health_check_manager = None


def get_startup_monitor() -> StartupMonitor:
    """Get global startup monitor instance"""
    global _startup_monitor
    if _startup_monitor is None:
        _startup_monitor = StartupMonitor()
    return _startup_monitor


def get_health_check_manager() -> HealthCheckManager:
    """Get global health check manager instance"""
    global _health_check_manager
    if _health_check_manager is None:
        _health_check_manager = HealthCheckManager()
    return _health_check_manager


async def create_startup_monitoring_report(startup_metrics: Any) -> Dict[str, Any]:
    """Create comprehensive startup monitoring report"""
    monitor = get_startup_monitor()
    
    if not hasattr(monitor, 'current_startup_start') or monitor.current_startup_start is None:
        return {"error": "Startup monitoring was not properly initialized"}
    
    # Generate performance report
    performance_report = monitor.complete_monitoring(startup_metrics)
    
    # Get performance trends
    trends = monitor.get_performance_trends()
    
    return {
        "startup_performance": asdict(performance_report),
        "performance_trends": trends,
        "optimization_status": {
            "target_startup_time": monitor.performance_baseline["excellent"],
            "current_performance_grade": performance_report.performance_grade,
            "efficiency_rating": "excellent" if performance_report.parallel_efficiency_percent > 300 else "good" if performance_report.parallel_efficiency_percent > 200 else "needs_improvement"
        }
    }