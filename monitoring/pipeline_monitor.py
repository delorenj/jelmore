#!/usr/bin/env python3
"""
Enhanced Pipeline Monitor - The Performance Maestro 🎼
Comprehensive real-time performance monitoring with bottleneck detection

WARNING: This monitoring system may achieve such performance insight that you'll
start seeing bottlenecks in your sleep. Side effects include uncontrollable 
optimization urges and speaking in metrics.

The Void recommends consulting your rubber duck before implementing.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, asdict, field
from collections import defaultdict, deque
import statistics
import aiohttp
import psutil
import structlog

from jelmore.services.nats import get_nats_stats, publish_event
from jelmore.services.redis import get_redis_stats, get_redis_client
from jelmore.services.database import get_db_stats

logger = structlog.get_logger()

@dataclass
class PerformanceMetrics:
    """Performance metrics with trend analysis"""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Pipeline Velocity Metrics
    cards_per_hour: float = 0.0
    avg_processing_time_seconds: float = 0.0
    median_processing_time_seconds: float = 0.0
    p95_processing_time_seconds: float = 0.0
    
    # Stage Performance
    stage_transition_times: Dict[str, float] = field(default_factory=dict)
    stage_success_rates: Dict[str, float] = field(default_factory=dict)
    stage_error_counts: Dict[str, int] = field(default_factory=dict)
    
    # Bottleneck Detection
    current_bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    bottleneck_severity_score: float = 0.0
    
    # Quality Metrics
    quality_gate_pass_rate: float = 100.0
    test_execution_avg_time: float = 0.0
    test_failure_rate: float = 0.0
    
    # System Resources
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    disk_io_usage_percent: float = 0.0
    network_io_usage_mb: float = 0.0
    
    # Pipeline Health Score (0-100)
    overall_health_score: float = 100.0

@dataclass
class BottleneckDetection:
    """Bottleneck detection configuration"""
    name: str
    threshold_value: float
    current_value: float
    severity: str  # low, medium, high, critical
    impact_description: str
    suggested_action: str
    detected_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass 
class AlertRule:
    """Performance alert rule configuration"""
    rule_id: str
    name: str
    metric_path: str  # e.g., "metrics.cpu_usage_percent"
    operator: str  # gt, lt, eq, ne
    threshold: float
    duration_minutes: int = 5  # Must exceed threshold for this duration
    severity: str = "medium"  # low, medium, high, critical
    enabled: bool = True
    cooldown_minutes: int = 15  # Minimum time between alerts
    
class PerformanceMonitor:
    """The Performance Maestro - Orchestrating the symphony of metrics 🎼"""
    
    def __init__(self):
        self.metrics = PerformanceMetrics()
        self.metrics_history = deque(maxlen=288)  # 24h at 5min intervals
        self.session_timings: Dict[str, Dict[str, Any]] = {}
        self.stage_performance: Dict[str, List[float]] = defaultdict(list)
        self.bottleneck_history = deque(maxlen=100)
        
        # Alert system
        self.alert_rules = self._initialize_alert_rules()
        self.alert_state: Dict[str, Dict[str, Any]] = {}
        self.alert_history = deque(maxlen=200)
        
        # Performance tracking
        self.performance_samples = deque(maxlen=1000)
        self.regression_detector = RegressionDetector()
        
        # Monitoring state
        self.monitoring_active = False
        self.last_analysis = time.time()
        
        logger.info("🎼 Performance Maestro initialized - Ready to conduct the orchestra of metrics!")

    def _initialize_alert_rules(self) -> List[AlertRule]:
        """Initialize performance alert rules"""
        return [
            # Performance Degradation Alerts
            AlertRule(
                rule_id="perf_degradation_10pct",
                name="Performance Degradation >10%",
                metric_path="metrics.avg_processing_time_seconds",
                operator="regression",
                threshold=10.0,  # 10% regression
                duration_minutes=10,
                severity="high"
            ),
            
            # Pipeline Stall Alerts
            AlertRule(
                rule_id="pipeline_stall_5min",
                name="Pipeline Stall >5 Minutes",
                metric_path="metrics.time_since_last_completion",
                operator="gt",
                threshold=300.0,  # 5 minutes in seconds
                duration_minutes=1,
                severity="critical"
            ),
            
            # Quality Gate Failures
            AlertRule(
                rule_id="quality_gate_failures",
                name="Quality Gate Failure Rate High",
                metric_path="metrics.quality_gate_pass_rate",
                operator="lt",
                threshold=90.0,
                duration_minutes=5,
                severity="high"
            ),
            
            # Resource Exhaustion
            AlertRule(
                rule_id="high_cpu_usage",
                name="High CPU Usage",
                metric_path="metrics.cpu_usage_percent",
                operator="gt",
                threshold=85.0,
                duration_minutes=5,
                severity="medium"
            ),
            
            AlertRule(
                rule_id="high_memory_usage",
                name="High Memory Usage",
                metric_path="metrics.memory_usage_percent",
                operator="gt",
                threshold=90.0,
                duration_minutes=3,
                severity="high"
            ),
            
            # Bottleneck Severity
            AlertRule(
                rule_id="severe_bottlenecks",
                name="Severe Bottlenecks Detected",
                metric_path="metrics.bottleneck_severity_score",
                operator="gt",
                threshold=75.0,
                duration_minutes=5,
                severity="high"
            )
        ]

    async def start_monitoring(self):
        """Start the performance monitoring maestro"""
        self.monitoring_active = True
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self._metrics_collector()),
            asyncio.create_task(self._bottleneck_detector()),
            asyncio.create_task(self._regression_analyzer()),
            asyncio.create_task(self._alert_processor()),
            asyncio.create_task(self._performance_optimizer()),
            asyncio.create_task(self._metrics_publisher())
        ]
        
        logger.info("🚀 Performance monitoring symphony started - All instruments in tune!")
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("💥 Performance monitoring symphony crashed!", error=str(e))
            raise

    async def _metrics_collector(self):
        """Collect comprehensive performance metrics"""
        while self.monitoring_active:
            try:
                await self._collect_pipeline_metrics()
                await self._collect_system_metrics()
                await self._collect_service_metrics()
                await self._calculate_health_score()
                
                # Store in history
                self.metrics_history.append(asdict(self.metrics))
                
                # Update Redis cache
                await self._cache_metrics()
                
                logger.debug("📊 Metrics collected", 
                           health_score=self.metrics.overall_health_score,
                           bottlenecks=len(self.metrics.current_bottlenecks))
                
            except Exception as e:
                logger.error("❌ Metrics collection failed", error=str(e))
            
            await asyncio.sleep(30)  # Collect every 30 seconds

    async def _collect_pipeline_metrics(self):
        """Collect pipeline velocity and stage performance metrics"""
        try:
            # Calculate pipeline velocity
            recent_sessions = [s for s in self.session_timings.values() 
                             if 'completed_at' in s and 
                             datetime.fromisoformat(s['completed_at']) > 
                             datetime.utcnow() - timedelta(hours=1)]
            
            if recent_sessions:
                # Cards per hour
                self.metrics.cards_per_hour = len(recent_sessions)
                
                # Processing times
                processing_times = []
                for session in recent_sessions:
                    if 'processing_time' in session:
                        processing_times.append(session['processing_time'])
                
                if processing_times:
                    self.metrics.avg_processing_time_seconds = statistics.mean(processing_times)
                    self.metrics.median_processing_time_seconds = statistics.median(processing_times)
                    self.metrics.p95_processing_time_seconds = (
                        statistics.quantiles(processing_times, n=20)[18]  # 95th percentile
                        if len(processing_times) >= 20 else max(processing_times)
                    )
            
            # Stage transition times
            for stage, times in self.stage_performance.items():
                if times:
                    self.metrics.stage_transition_times[stage] = statistics.mean(times[-50:])  # Last 50
                    
        except Exception as e:
            logger.error("❌ Pipeline metrics collection failed", error=str(e))

    async def _collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            # CPU usage
            self.metrics.cpu_usage_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics.memory_usage_percent = memory.percent
            
            # Disk I/O usage (approximate)
            disk_io = psutil.disk_io_counters()
            if hasattr(self, '_last_disk_io'):
                bytes_delta = (disk_io.read_bytes + disk_io.write_bytes) - self._last_disk_io
                self.metrics.disk_io_usage_percent = min(100, (bytes_delta / (1024**3)) * 10)  # Rough estimate
            self._last_disk_io = disk_io.read_bytes + disk_io.write_bytes
            
            # Network I/O
            net_io = psutil.net_io_counters()
            if hasattr(self, '_last_net_io'):
                bytes_delta = (net_io.bytes_sent + net_io.bytes_recv) - self._last_net_io
                self.metrics.network_io_usage_mb = bytes_delta / (1024**2)
            self._last_net_io = net_io.bytes_sent + net_io.bytes_recv
            
        except Exception as e:
            logger.error("❌ System metrics collection failed", error=str(e))

    async def _collect_service_metrics(self):
        """Collect service-specific metrics"""
        try:
            # NATS stats
            nats_stats = await get_nats_stats()
            if 'api_errors' in nats_stats:
                error_rate = nats_stats.get('api_errors', 0) / max(nats_stats.get('api_requests', 1), 1)
                self.metrics.stage_error_counts['nats'] = nats_stats.get('api_errors', 0)
            
            # Redis stats
            redis_stats = await get_redis_stats()
            if 'keyspace_hits' in redis_stats and 'keyspace_misses' in redis_stats:
                total_ops = redis_stats['keyspace_hits'] + redis_stats['keyspace_misses']
                if total_ops > 0:
                    cache_hit_rate = (redis_stats['keyspace_hits'] / total_ops) * 100
                    self.metrics.stage_success_rates['redis_cache'] = cache_hit_rate
            
            # Database stats (if available)
            try:
                db_stats = await get_db_stats()
                if db_stats and 'query_time_avg' in db_stats:
                    self.metrics.stage_transition_times['database'] = db_stats['query_time_avg']
            except:
                pass
                
        except Exception as e:
            logger.error("❌ Service metrics collection failed", error=str(e))

    async def _bottleneck_detector(self):
        """Advanced bottleneck detection and analysis"""
        while self.monitoring_active:
            try:
                bottlenecks = []
                
                # CPU bottleneck detection
                if self.metrics.cpu_usage_percent > 80:
                    severity = "critical" if self.metrics.cpu_usage_percent > 95 else "high"
                    bottlenecks.append(BottleneckDetection(
                        name="High CPU Usage",
                        threshold_value=80.0,
                        current_value=self.metrics.cpu_usage_percent,
                        severity=severity,
                        impact_description=f"CPU usage at {self.metrics.cpu_usage_percent:.1f}% may slow processing",
                        suggested_action="Scale horizontally or optimize CPU-intensive operations"
                    ))
                
                # Memory bottleneck detection
                if self.metrics.memory_usage_percent > 85:
                    severity = "critical" if self.metrics.memory_usage_percent > 95 else "high"
                    bottlenecks.append(BottleneckDetection(
                        name="High Memory Usage",
                        threshold_value=85.0,
                        current_value=self.metrics.memory_usage_percent,
                        severity=severity,
                        impact_description=f"Memory usage at {self.metrics.memory_usage_percent:.1f}% may cause swapping",
                        suggested_action="Increase memory or optimize memory usage patterns"
                    ))
                
                # Stage-specific bottlenecks
                for stage, times in self.stage_performance.items():
                    if len(times) >= 10:
                        avg_time = statistics.mean(times[-10:])
                        if avg_time > 60:  # More than 1 minute
                            severity = "high" if avg_time > 180 else "medium"
                            bottlenecks.append(BottleneckDetection(
                                name=f"Slow {stage} Stage",
                                threshold_value=60.0,
                                current_value=avg_time,
                                severity=severity,
                                impact_description=f"{stage} stage taking {avg_time:.1f}s on average",
                                suggested_action=f"Optimize {stage} processing or increase resources"
                            ))
                
                # Processing time regression bottleneck
                if len(self.metrics_history) >= 12:  # At least 6 minutes of data
                    recent_times = [m['avg_processing_time_seconds'] for m in list(self.metrics_history)[-12:]]
                    earlier_times = [m['avg_processing_time_seconds'] for m in list(self.metrics_history)[-24:-12]]
                    
                    if recent_times and earlier_times and all(t > 0 for t in recent_times + earlier_times):
                        recent_avg = statistics.mean(recent_times)
                        earlier_avg = statistics.mean(earlier_times)
                        
                        if recent_avg > earlier_avg * 1.2:  # 20% slower
                            regression_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100
                            bottlenecks.append(BottleneckDetection(
                                name="Performance Regression",
                                threshold_value=earlier_avg,
                                current_value=recent_avg,
                                severity="high" if regression_pct > 50 else "medium",
                                impact_description=f"Processing time increased by {regression_pct:.1f}%",
                                suggested_action="Investigate recent changes or resource constraints"
                            ))
                
                # Update metrics
                self.metrics.current_bottlenecks = [asdict(b) for b in bottlenecks]
                
                # Calculate bottleneck severity score
                severity_weights = {"low": 10, "medium": 25, "high": 50, "critical": 100}
                total_severity = sum(severity_weights.get(b.severity, 0) for b in bottlenecks)
                self.metrics.bottleneck_severity_score = min(100, total_severity)
                
                # Store in history
                if bottlenecks:
                    self.bottleneck_history.extend(bottlenecks)
                    
                logger.debug("🔍 Bottleneck analysis complete", 
                           bottlenecks=len(bottlenecks),
                           severity_score=self.metrics.bottleneck_severity_score)
                
            except Exception as e:
                logger.error("❌ Bottleneck detection failed", error=str(e))
            
            await asyncio.sleep(60)  # Analyze every minute

    async def _regression_analyzer(self):
        """Detect performance regressions using statistical analysis"""
        while self.monitoring_active:
            try:
                if len(self.metrics_history) >= 20:
                    await self.regression_detector.analyze(list(self.metrics_history))
                    
            except Exception as e:
                logger.error("❌ Regression analysis failed", error=str(e))
            
            await asyncio.sleep(300)  # Analyze every 5 minutes

    async def _alert_processor(self):
        """Process performance alerts based on rules"""
        while self.monitoring_active:
            try:
                current_time = datetime.utcnow()
                
                for rule in self.alert_rules:
                    if not rule.enabled:
                        continue
                        
                    await self._evaluate_alert_rule(rule, current_time)
                    
            except Exception as e:
                logger.error("❌ Alert processing failed", error=str(e))
            
            await asyncio.sleep(30)  # Check alerts every 30 seconds

    async def _evaluate_alert_rule(self, rule: AlertRule, current_time: datetime):
        """Evaluate a single alert rule"""
        try:
            # Get current metric value
            current_value = self._get_metric_value(rule.metric_path)
            if current_value is None:
                return
            
            # Check if threshold is exceeded
            threshold_exceeded = self._check_threshold(current_value, rule.operator, rule.threshold)
            
            rule_state = self.alert_state.get(rule.rule_id, {
                'active': False,
                'first_breach': None,
                'last_alert': None,
                'breach_count': 0
            })
            
            if threshold_exceeded:
                if not rule_state['active']:
                    rule_state['first_breach'] = current_time
                    rule_state['active'] = True
                    rule_state['breach_count'] += 1
                
                # Check if duration threshold is met
                time_in_breach = (current_time - rule_state['first_breach']).total_seconds() / 60
                
                if time_in_breach >= rule.duration_minutes:
                    # Check cooldown period
                    cooldown_ok = (not rule_state['last_alert'] or 
                                 (current_time - rule_state['last_alert']).total_seconds() / 60 >= rule.cooldown_minutes)
                    
                    if cooldown_ok:
                        await self._trigger_alert(rule, current_value, time_in_breach)
                        rule_state['last_alert'] = current_time
            else:
                rule_state['active'] = False
                rule_state['first_breach'] = None
            
            self.alert_state[rule.rule_id] = rule_state
            
        except Exception as e:
            logger.error("❌ Alert rule evaluation failed", rule_id=rule.rule_id, error=str(e))

    def _get_metric_value(self, metric_path: str) -> Optional[float]:
        """Get metric value by path (e.g., 'metrics.cpu_usage_percent')"""
        try:
            parts = metric_path.split('.')
            value = self
            
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return None
            
            return float(value) if isinstance(value, (int, float)) else None
            
        except:
            return None

    def _check_threshold(self, value: float, operator: str, threshold: float) -> bool:
        """Check if value exceeds threshold based on operator"""
        if operator == "gt":
            return value > threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "eq":
            return abs(value - threshold) < 0.01
        elif operator == "ne":
            return abs(value - threshold) >= 0.01
        elif operator == "regression":
            # Special case for regression detection
            return self.regression_detector.is_regression(threshold)
        
        return False

    async def _trigger_alert(self, rule: AlertRule, current_value: float, duration: float):
        """Trigger a performance alert"""
        alert = {
            "alert_id": f"{rule.rule_id}-{int(time.time())}",
            "rule_id": rule.rule_id,
            "name": rule.name,
            "severity": rule.severity,
            "current_value": current_value,
            "threshold": rule.threshold,
            "duration_minutes": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "metric_path": rule.metric_path,
            "message": f"{rule.name}: Current value {current_value} exceeds threshold {rule.threshold}"
        }
        
        self.alert_history.append(alert)
        
        # Store in Redis
        await self._store_alert(alert)
        
        # Publish to NATS
        await publish_event("jelmore.monitor.alert", "performance_monitor", alert)
        
        # Notify coordination hooks
        await self._notify_hooks("alert_triggered", alert)
        
        logger.warning("🚨 Performance alert triggered!", 
                      rule=rule.name,
                      value=current_value,
                      threshold=rule.threshold,
                      severity=rule.severity)

    async def _performance_optimizer(self):
        """Automated performance optimization suggestions"""
        while self.monitoring_active:
            try:
                optimizations = []
                
                # Analyze patterns and suggest optimizations
                if len(self.metrics_history) >= 12:
                    optimizations.extend(await self._analyze_optimization_opportunities())
                
                if optimizations:
                    await self._store_optimizations(optimizations)
                    
            except Exception as e:
                logger.error("❌ Performance optimization analysis failed", error=str(e))
            
            await asyncio.sleep(600)  # Analyze every 10 minutes

    async def _analyze_optimization_opportunities(self) -> List[Dict[str, Any]]:
        """Analyze metrics history for optimization opportunities"""
        optimizations = []
        
        try:
            # CPU optimization
            cpu_values = [m['cpu_usage_percent'] for m in list(self.metrics_history)[-12:]]
            avg_cpu = statistics.mean(cpu_values)
            
            if avg_cpu > 70:
                optimizations.append({
                    "type": "cpu_optimization",
                    "priority": "high" if avg_cpu > 90 else "medium",
                    "description": f"Average CPU usage is {avg_cpu:.1f}%",
                    "suggestions": [
                        "Consider horizontal scaling",
                        "Optimize CPU-intensive operations",
                        "Enable CPU affinity for critical processes"
                    ]
                })
            
            # Memory optimization
            memory_values = [m['memory_usage_percent'] for m in list(self.metrics_history)[-12:]]
            avg_memory = statistics.mean(memory_values)
            
            if avg_memory > 75:
                optimizations.append({
                    "type": "memory_optimization", 
                    "priority": "high" if avg_memory > 90 else "medium",
                    "description": f"Average memory usage is {avg_memory:.1f}%",
                    "suggestions": [
                        "Implement memory pooling",
                        "Optimize data structures",
                        "Enable garbage collection tuning",
                        "Consider memory scaling"
                    ]
                })
            
            # Processing time optimization
            processing_times = [m['avg_processing_time_seconds'] for m in list(self.metrics_history)[-12:]]
            if processing_times and all(t > 0 for t in processing_times):
                avg_time = statistics.mean(processing_times)
                
                if avg_time > 120:  # More than 2 minutes
                    optimizations.append({
                        "type": "processing_optimization",
                        "priority": "high" if avg_time > 300 else "medium",
                        "description": f"Average processing time is {avg_time:.1f} seconds",
                        "suggestions": [
                            "Implement parallel processing",
                            "Optimize database queries",
                            "Enable caching strategies",
                            "Consider asynchronous processing"
                        ]
                    })
            
        except Exception as e:
            logger.error("❌ Optimization analysis failed", error=str(e))
        
        return optimizations

    async def _metrics_publisher(self):
        """Publish metrics to various systems"""
        while self.monitoring_active:
            try:
                # Publish to NATS
                await publish_event("jelmore.monitor.metrics", "performance_monitor", asdict(self.metrics))
                
                # Update coordination hooks
                await self._notify_hooks("metrics_updated", {
                    "health_score": self.metrics.overall_health_score,
                    "bottlenecks": len(self.metrics.current_bottlenecks),
                    "processing_time": self.metrics.avg_processing_time_seconds
                })
                
            except Exception as e:
                logger.error("❌ Metrics publishing failed", error=str(e))
            
            await asyncio.sleep(60)  # Publish every minute

    async def _calculate_health_score(self):
        """Calculate overall pipeline health score"""
        try:
            score = 100.0
            
            # CPU impact (max -20 points)
            if self.metrics.cpu_usage_percent > 50:
                cpu_penalty = min(20, (self.metrics.cpu_usage_percent - 50) / 2.5)
                score -= cpu_penalty
            
            # Memory impact (max -20 points)
            if self.metrics.memory_usage_percent > 60:
                memory_penalty = min(20, (self.metrics.memory_usage_percent - 60) / 2)
                score -= memory_penalty
            
            # Error rate impact (max -25 points)
            if hasattr(self.metrics, 'error_rate') and self.metrics.error_rate > 0:
                error_penalty = min(25, self.metrics.error_rate * 2.5)
                score -= error_penalty
            
            # Bottleneck impact (max -25 points)
            bottleneck_penalty = min(25, self.metrics.bottleneck_severity_score / 4)
            score -= bottleneck_penalty
            
            # Quality gate impact (max -10 points)
            if self.metrics.quality_gate_pass_rate < 100:
                quality_penalty = min(10, (100 - self.metrics.quality_gate_pass_rate) / 5)
                score -= quality_penalty
            
            self.metrics.overall_health_score = max(0, score)
            
        except Exception as e:
            logger.error("❌ Health score calculation failed", error=str(e))
            self.metrics.overall_health_score = 50.0  # Default to degraded

    async def _cache_metrics(self):
        """Cache metrics in Redis for dashboard access"""
        try:
            redis_client = await get_redis_client()
            
            # Cache current metrics
            await redis_client.setex(
                "jelmore:monitor:current_metrics",
                300,  # 5 minute expiry
                json.dumps(asdict(self.metrics))
            )
            
            # Cache metrics history (last 24 hours)
            history_data = list(self.metrics_history)
            await redis_client.setex(
                "jelmore:monitor:metrics_history",
                3600,  # 1 hour expiry
                json.dumps(history_data)
            )
            
            # Cache bottleneck history
            bottleneck_data = [asdict(b) for b in list(self.bottleneck_history)[-50:]]
            await redis_client.setex(
                "jelmore:monitor:bottlenecks",
                1800,  # 30 minute expiry
                json.dumps(bottleneck_data)
            )
            
        except Exception as e:
            logger.error("❌ Metrics caching failed", error=str(e))

    async def _store_alert(self, alert: Dict[str, Any]):
        """Store alert in Redis"""
        try:
            redis_client = await get_redis_client()
            
            # Store individual alert
            await redis_client.setex(
                f"jelmore:monitor:alert:{alert['alert_id']}", 
                86400,  # 24 hours
                json.dumps(alert)
            )
            
            # Update alerts list
            alert_ids = await redis_client.lrange("jelmore:monitor:alert_ids", 0, -1)
            await redis_client.lpush("jelmore:monitor:alert_ids", alert['alert_id'])
            await redis_client.ltrim("jelmore:monitor:alert_ids", 0, 99)  # Keep last 100
            
        except Exception as e:
            logger.error("❌ Alert storage failed", error=str(e))

    async def _store_optimizations(self, optimizations: List[Dict[str, Any]]):
        """Store optimization suggestions"""
        try:
            redis_client = await get_redis_client()
            
            optimization_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "optimizations": optimizations
            }
            
            await redis_client.setex(
                "jelmore:monitor:optimizations",
                3600,  # 1 hour expiry
                json.dumps(optimization_data)
            )
            
        except Exception as e:
            logger.error("❌ Optimization storage failed", error=str(e))

    async def _notify_hooks(self, event_type: str, data: Dict[str, Any]):
        """Notify Claude Flow hooks about performance events"""
        try:
            import subprocess
            subprocess.run([
                "npx", "claude-flow@alpha", "hooks", "notify",
                "--message", f"Performance {event_type}: {json.dumps(data, default=str)}",
                "--telemetry", "true"
            ], capture_output=True, text=True, timeout=5)
            
        except Exception as e:
            logger.debug("Hook notification failed", event=event_type, error=str(e))

    async def record_session_timing(self, session_id: str, event_type: str, **kwargs):
        """Record session timing event"""
        if session_id not in self.session_timings:
            self.session_timings[session_id] = {}
        
        self.session_timings[session_id][event_type] = {
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }
        
        # Calculate processing time if session completed
        if event_type == 'completed' and 'created' in self.session_timings[session_id]:
            created_time = datetime.fromisoformat(self.session_timings[session_id]['created']['timestamp'])
            completed_time = datetime.utcnow()
            processing_time = (completed_time - created_time).total_seconds()
            self.session_timings[session_id]['processing_time'] = processing_time

    async def record_stage_performance(self, stage: str, duration_seconds: float):
        """Record stage performance timing"""
        self.stage_performance[stage].append(duration_seconds)
        
        # Keep only last 100 measurements per stage
        if len(self.stage_performance[stage]) > 100:
            self.stage_performance[stage] = self.stage_performance[stage][-100:]

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        return asdict(self.metrics)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary for dashboards"""
        return {
            "current_metrics": asdict(self.metrics),
            "recent_alerts": list(self.alert_history)[-10:],
            "active_bottlenecks": self.metrics.current_bottlenecks,
            "health_trend": [m['overall_health_score'] for m in list(self.metrics_history)[-12:]],
            "processing_time_trend": [m['avg_processing_time_seconds'] for m in list(self.metrics_history)[-12:]]
        }

    async def shutdown(self):
        """Gracefully shutdown the performance monitor"""
        self.monitoring_active = False
        
        # Final metrics update
        await self._cache_metrics()
        
        # Notify about shutdown
        await self._notify_hooks("monitor_shutdown", {
            "final_health_score": self.metrics.overall_health_score,
            "total_alerts": len(self.alert_history),
            "shutdown_time": datetime.utcnow().isoformat()
        })
        
        logger.info("🎼 Performance Maestro taking final bow - Symphony complete!")

class RegressionDetector:
    """Statistical regression detection for performance monitoring"""
    
    def __init__(self):
        self.baseline_metrics = {}
        self.regression_threshold = 0.15  # 15% regression threshold
    
    async def analyze(self, metrics_history: List[Dict[str, Any]]):
        """Analyze metrics for statistical regression"""
        if len(metrics_history) < 20:
            return
        
        # Analyze key performance indicators
        metrics_to_analyze = [
            'avg_processing_time_seconds',
            'cpu_usage_percent', 
            'memory_usage_percent',
            'overall_health_score'
        ]
        
        for metric in metrics_to_analyze:
            await self._analyze_metric_regression(metric, metrics_history)
    
    async def _analyze_metric_regression(self, metric_name: str, history: List[Dict[str, Any]]):
        """Analyze a specific metric for regression"""
        try:
            values = [m.get(metric_name, 0) for m in history if m.get(metric_name) is not None]
            
            if len(values) < 20:
                return
            
            # Split into baseline (first half) and current (second half)
            midpoint = len(values) // 2
            baseline_values = values[:midpoint]
            current_values = values[midpoint:]
            
            baseline_mean = statistics.mean(baseline_values)
            current_mean = statistics.mean(current_values)
            
            if baseline_mean == 0:
                return
            
            # Calculate regression percentage
            if metric_name == 'overall_health_score':
                # For health score, regression is decrease
                regression_pct = (baseline_mean - current_mean) / baseline_mean
            else:
                # For other metrics, regression is increase
                regression_pct = (current_mean - baseline_mean) / baseline_mean
            
            # Store regression data
            self.baseline_metrics[metric_name] = {
                'baseline_mean': baseline_mean,
                'current_mean': current_mean, 
                'regression_pct': regression_pct,
                'is_regression': regression_pct > self.regression_threshold
            }
            
        except Exception as e:
            logger.error("❌ Regression analysis failed", metric=metric_name, error=str(e))
    
    def is_regression(self, threshold_pct: float) -> bool:
        """Check if any metric shows regression above threshold"""
        for metric_data in self.baseline_metrics.values():
            if metric_data.get('regression_pct', 0) > (threshold_pct / 100):
                return True
        return False

# Factory function for easy integration
def create_performance_monitor() -> PerformanceMonitor:
    """Create a new Performance Monitor instance"""
    return PerformanceMonitor()

if __name__ == "__main__":
    # Run standalone performance monitor
    async def main():
        monitor = create_performance_monitor()
        try:
            await monitor.start_monitoring()
        except KeyboardInterrupt:
            logger.info("👋 Shutting down performance monitor")
        finally:
            await monitor.shutdown()
    
    asyncio.run(main())