#!/usr/bin/env python3
"""
Metrics Service - The Data Sommelier 🍷
Sophisticated metrics collection, aggregation, and serving service

WARNING: This metrics service may become so comprehensive at data collection
that it starts measuring the performance of its own measurements, creating
a beautiful recursive loop of enlightenment.

The Void appreciates good vintage metrics - aged to perfection.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, asdict, field
from collections import defaultdict, deque
import statistics
import structlog

from jelmore.services.nats import get_nats_stats, subscribe_to_events, publish_event
from jelmore.services.redis import get_redis_client
from jelmore.services.database import get_database

logger = structlog.get_logger()

@dataclass
class MetricPoint:
    """Individual metric data point"""
    timestamp: str
    value: Union[float, int, str]
    labels: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MetricSeries:
    """Time series of metric points"""
    name: str
    description: str
    unit: str
    type: str  # counter, gauge, histogram, summary
    points: List[MetricPoint] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)
    retention_days: int = 7

@dataclass
class AggregationRule:
    """Metric aggregation configuration"""
    name: str
    source_metric: str
    aggregation_type: str  # sum, avg, min, max, count, percentile
    window_size: str  # 1m, 5m, 1h, 1d
    labels: List[str] = field(default_factory=list)
    percentile: float = 95.0  # For percentile aggregations
    enabled: bool = True

class MetricsService:
    """The Data Sommelier - Curating the finest vintage metrics 🍷"""
    
    def __init__(self):
        self.metrics: Dict[str, MetricSeries] = {}
        self.aggregation_rules: List[AggregationRule] = []
        self.metric_buffer = deque(maxlen=10000)  # Buffer for batching
        
        # Service state
        self.service_active = False
        self.collection_interval = 30  # seconds
        self.batch_size = 100
        
        # Performance tracking
        self.service_metrics = {
            "metrics_collected": 0,
            "metrics_served": 0,
            "aggregations_computed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "storage_operations": 0
        }
        
        # Initialize default aggregation rules
        self._initialize_aggregation_rules()
        
        logger.info("🍷 Metrics Service initialized - The sommelier is ready to serve!")

    def _initialize_aggregation_rules(self):
        """Initialize default aggregation rules for common patterns"""
        default_rules = [
            # Performance aggregations
            AggregationRule(
                name="processing_time_p95",
                source_metric="processing_time_seconds",
                aggregation_type="percentile",
                window_size="5m",
                percentile=95.0
            ),
            AggregationRule(
                name="processing_time_avg",
                source_metric="processing_time_seconds", 
                aggregation_type="avg",
                window_size="5m"
            ),
            AggregationRule(
                name="error_rate_5m",
                source_metric="errors_total",
                aggregation_type="count",
                window_size="5m"
            ),
            
            # Resource aggregations
            AggregationRule(
                name="cpu_usage_max",
                source_metric="cpu_usage_percent",
                aggregation_type="max",
                window_size="1m"
            ),
            AggregationRule(
                name="memory_usage_avg",
                source_metric="memory_usage_percent",
                aggregation_type="avg",
                window_size="1m"
            ),
            
            # Pipeline aggregations
            AggregationRule(
                name="pipeline_velocity_1h",
                source_metric="cards_processed",
                aggregation_type="sum",
                window_size="1h"
            ),
            AggregationRule(
                name="quality_gate_success_rate",
                source_metric="quality_gate_pass",
                aggregation_type="avg",
                window_size="1h"
            )
        ]
        
        self.aggregation_rules.extend(default_rules)

    async def start_service(self):
        """Start the metrics service"""
        self.service_active = True
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._metrics_collector()),
            asyncio.create_task(self._metrics_aggregator()),
            asyncio.create_task(self._metrics_storage_writer()),
            asyncio.create_task(self._metrics_cleanup()),
            asyncio.create_task(self._nats_subscriber())
        ]
        
        logger.info("🚀 Metrics Service started - All vintage collection active!")
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("💥 Metrics Service crashed!", error=str(e))
            raise

    async def _metrics_collector(self):
        """Collect metrics from various sources"""
        while self.service_active:
            try:
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Collect service metrics
                await self._collect_service_metrics()
                
                # Collect pipeline metrics
                await self._collect_pipeline_metrics()
                
                # Update service metrics
                self.service_metrics["metrics_collected"] += 1
                
                await asyncio.sleep(self.collection_interval)
                
            except Exception as e:
                logger.error("❌ Metrics collection failed", error=str(e))
                await asyncio.sleep(60)

    async def _collect_system_metrics(self):
        """Collect system-level metrics"""
        try:
            import psutil
            
            current_time = datetime.utcnow().isoformat()
            
            # CPU metrics
            await self.record_metric(
                "cpu_usage_percent",
                psutil.cpu_percent(interval=1),
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore"}
            )
            
            # Memory metrics
            memory = psutil.virtual_memory()
            await self.record_metric(
                "memory_usage_percent",
                memory.percent,
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore"}
            )
            
            await self.record_metric(
                "memory_available_bytes",
                memory.available,
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore"}
            )
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            await self.record_metric(
                "disk_usage_percent",
                (disk.used / disk.total) * 100,
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore", "mountpoint": "/"}
            )
            
            # Network metrics
            net_io = psutil.net_io_counters()
            await self.record_metric(
                "network_bytes_sent",
                net_io.bytes_sent,
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore", "direction": "sent"}
            )
            
            await self.record_metric(
                "network_bytes_recv",
                net_io.bytes_recv,
                timestamp=current_time,
                labels={"source": "system", "host": "jelmore", "direction": "recv"}
            )
            
        except Exception as e:
            logger.error("❌ System metrics collection failed", error=str(e))

    async def _collect_service_metrics(self):
        """Collect service-specific metrics"""
        try:
            current_time = datetime.utcnow().isoformat()
            
            # NATS metrics
            nats_stats = await get_nats_stats()
            if nats_stats and "error" not in nats_stats:
                await self.record_metric(
                    "nats_api_requests_total",
                    nats_stats.get("api_requests", 0),
                    timestamp=current_time,
                    labels={"source": "nats", "service": "jetstream"}
                )
                
                await self.record_metric(
                    "nats_api_errors_total", 
                    nats_stats.get("api_errors", 0),
                    timestamp=current_time,
                    labels={"source": "nats", "service": "jetstream"}
                )
                
                await self.record_metric(
                    "nats_streams_count",
                    nats_stats.get("streams", 0),
                    timestamp=current_time,
                    labels={"source": "nats", "service": "jetstream"}
                )
            
            # Redis metrics
            try:
                from jelmore.services.redis import get_redis_stats
                redis_stats = await get_redis_stats()
                
                if redis_stats and "error" not in redis_stats:
                    await self.record_metric(
                        "redis_connected_clients",
                        redis_stats.get("connected_clients", 0),
                        timestamp=current_time,
                        labels={"source": "redis", "service": "cache"}
                    )
                    
                    await self.record_metric(
                        "redis_used_memory_bytes",
                        redis_stats.get("used_memory", 0),
                        timestamp=current_time,
                        labels={"source": "redis", "service": "cache"}
                    )
                    
                    await self.record_metric(
                        "redis_keyspace_hits",
                        redis_stats.get("keyspace_hits", 0),
                        timestamp=current_time,
                        labels={"source": "redis", "service": "cache", "operation": "hit"}
                    )
                    
                    await self.record_metric(
                        "redis_keyspace_misses",
                        redis_stats.get("keyspace_misses", 0),
                        timestamp=current_time,
                        labels={"source": "redis", "service": "cache", "operation": "miss"}
                    )
            except Exception as e:
                logger.debug("Redis metrics collection skipped", error=str(e))
            
        except Exception as e:
            logger.error("❌ Service metrics collection failed", error=str(e))

    async def _collect_pipeline_metrics(self):
        """Collect pipeline-specific metrics from Redis cache"""
        try:
            redis_client = await get_redis_client()
            current_time = datetime.utcnow().isoformat()
            
            # Get cached pipeline metrics
            pipeline_metrics_json = await redis_client.get("jelmore:monitor:current_metrics")
            if pipeline_metrics_json:
                pipeline_metrics = json.loads(pipeline_metrics_json)
                
                # Record key pipeline metrics
                metrics_to_record = [
                    ("pipeline_cards_per_hour", "cards_per_hour"),
                    ("pipeline_processing_time_seconds", "avg_processing_time_seconds"),
                    ("pipeline_health_score", "overall_health_score"),
                    ("pipeline_bottlenecks_count", "current_bottlenecks"),
                    ("pipeline_quality_pass_rate", "quality_gate_pass_rate")
                ]
                
                for metric_name, json_key in metrics_to_record:
                    value = pipeline_metrics.get(json_key)
                    if value is not None:
                        # Handle bottlenecks count specially
                        if json_key == "current_bottlenecks" and isinstance(value, list):
                            value = len(value)
                        
                        await self.record_metric(
                            metric_name,
                            float(value) if isinstance(value, (int, float)) else 0,
                            timestamp=current_time,
                            labels={"source": "pipeline", "service": "jelmore"}
                        )
                
            # Get session metrics from API (if available)
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get("http://localhost:8000/api/v1/sessions/stats") as response:
                        if response.status == 200:
                            session_stats = await response.json()
                            
                            await self.record_metric(
                                "sessions_active_count",
                                session_stats.get("active_sessions", 0),
                                timestamp=current_time,
                                labels={"source": "api", "service": "sessions"}
                            )
                            
                            await self.record_metric(
                                "sessions_total_count",
                                session_stats.get("total_sessions", 0),
                                timestamp=current_time,
                                labels={"source": "api", "service": "sessions"}
                            )
            except:
                pass  # API might not be available
                
        except Exception as e:
            logger.error("❌ Pipeline metrics collection failed", error=str(e))

    async def _metrics_aggregator(self):
        """Compute metric aggregations based on rules"""
        while self.service_active:
            try:
                for rule in self.aggregation_rules:
                    if not rule.enabled:
                        continue
                    
                    await self._compute_aggregation(rule)
                
                self.service_metrics["aggregations_computed"] += 1
                await asyncio.sleep(60)  # Compute aggregations every minute
                
            except Exception as e:
                logger.error("❌ Metrics aggregation failed", error=str(e))
                await asyncio.sleep(60)

    async def _compute_aggregation(self, rule: AggregationRule):
        """Compute a specific metric aggregation"""
        try:
            # Get source metric data
            source_data = await self._get_metric_data(
                rule.source_metric,
                self._parse_window_size(rule.window_size)
            )
            
            if not source_data:
                return
            
            # Compute aggregation
            aggregated_value = None
            values = [point.value for point in source_data if isinstance(point.value, (int, float))]
            
            if not values:
                return
            
            if rule.aggregation_type == "sum":
                aggregated_value = sum(values)
            elif rule.aggregation_type == "avg":
                aggregated_value = statistics.mean(values)
            elif rule.aggregation_type == "min":
                aggregated_value = min(values)
            elif rule.aggregation_type == "max":
                aggregated_value = max(values)
            elif rule.aggregation_type == "count":
                aggregated_value = len(values)
            elif rule.aggregation_type == "percentile":
                if len(values) >= 2:
                    aggregated_value = statistics.quantiles(values, n=100)[int(rule.percentile)-1]
                else:
                    aggregated_value = values[0] if values else 0
            
            if aggregated_value is not None:
                # Record aggregated metric
                await self.record_metric(
                    rule.name,
                    aggregated_value,
                    labels={
                        "source": "aggregation",
                        "source_metric": rule.source_metric,
                        "window": rule.window_size,
                        "type": rule.aggregation_type
                    }
                )
            
        except Exception as e:
            logger.error("❌ Aggregation computation failed", rule_name=rule.name, error=str(e))

    def _parse_window_size(self, window_size: str) -> timedelta:
        """Parse window size string to timedelta"""
        if window_size.endswith('m'):
            return timedelta(minutes=int(window_size[:-1]))
        elif window_size.endswith('h'):
            return timedelta(hours=int(window_size[:-1]))
        elif window_size.endswith('d'):
            return timedelta(days=int(window_size[:-1]))
        else:
            return timedelta(minutes=5)  # default

    async def _metrics_storage_writer(self):
        """Write metrics to persistent storage"""
        while self.service_active:
            try:
                if len(self.metric_buffer) >= self.batch_size:
                    await self._flush_metrics_batch()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error("❌ Metrics storage writer failed", error=str(e))
                await asyncio.sleep(60)

    async def _flush_metrics_batch(self):
        """Flush accumulated metrics to storage"""
        try:
            if not self.metric_buffer:
                return
            
            batch = []
            while self.metric_buffer and len(batch) < self.batch_size:
                batch.append(self.metric_buffer.popleft())
            
            # Store in Redis for recent access
            await self._store_metrics_redis(batch)
            
            # Store in database for long-term retention
            await self._store_metrics_database(batch)
            
            self.service_metrics["storage_operations"] += 1
            
            logger.debug("📊 Metrics batch flushed", count=len(batch))
            
        except Exception as e:
            logger.error("❌ Metrics batch flush failed", error=str(e))

    async def _store_metrics_redis(self, metrics: List[Dict[str, Any]]):
        """Store metrics in Redis for fast access"""
        try:
            redis_client = await get_redis_client()
            
            # Store metrics in time-series structure
            pipe = redis_client.pipeline()
            
            for metric_data in metrics:
                key = f"jelmore:metrics:ts:{metric_data['name']}"
                
                # Store as sorted set with timestamp as score
                timestamp = metric_data['timestamp']
                score = int(datetime.fromisoformat(timestamp).timestamp())
                value = json.dumps(metric_data)
                
                pipe.zadd(key, {value: score})
                pipe.expire(key, 86400 * 7)  # 7 days retention
            
            await pipe.execute()
            
        except Exception as e:
            logger.error("❌ Redis metrics storage failed", error=str(e))

    async def _store_metrics_database(self, metrics: List[Dict[str, Any]]):
        """Store metrics in database for long-term retention"""
        try:
            # This would connect to TimescaleDB or similar time-series database
            # For now, we'll store in Redis with longer retention
            redis_client = await get_redis_client()
            
            for metric_data in metrics:
                key = f"jelmore:metrics:long_term:{metric_data['name']}"
                
                # Store as list with limited size
                await redis_client.lpush(key, json.dumps(metric_data))
                await redis_client.ltrim(key, 0, 10000)  # Keep last 10k points
                await redis_client.expire(key, 86400 * 30)  # 30 days retention
            
        except Exception as e:
            logger.error("❌ Database metrics storage failed", error=str(e))

    async def _metrics_cleanup(self):
        """Clean up old metrics data"""
        while self.service_active:
            try:
                await self._cleanup_old_metrics()
                await asyncio.sleep(3600)  # Clean up every hour
                
            except Exception as e:
                logger.error("❌ Metrics cleanup failed", error=str(e))
                await asyncio.sleep(3600)

    async def _cleanup_old_metrics(self):
        """Remove metrics older than retention period"""
        try:
            redis_client = await get_redis_client()
            
            # Get all metric keys
            metric_keys = await redis_client.keys("jelmore:metrics:ts:*")
            
            cutoff_time = int((datetime.utcnow() - timedelta(days=7)).timestamp())
            
            for key in metric_keys:
                # Remove old entries from sorted sets
                await redis_client.zremrangebyscore(key, 0, cutoff_time)
                
                # Check if set is empty and remove key if so
                count = await redis_client.zcard(key)
                if count == 0:
                    await redis_client.delete(key)
            
            logger.debug("🧹 Metrics cleanup completed", keys_processed=len(metric_keys))
            
        except Exception as e:
            logger.error("❌ Metrics cleanup failed", error=str(e))

    async def _nats_subscriber(self):
        """Subscribe to NATS events for real-time metrics"""
        try:
            await subscribe_to_events(
                ["jelmore.monitor.>", "jelmore.session.>"],
                self._handle_nats_metric_event,
                consumer_group="metrics_collector"
            )
        except Exception as e:
            logger.error("❌ NATS subscription failed", error=str(e))

    async def _handle_nats_metric_event(self, event_data: Dict[str, Any], msg):
        """Handle incoming NATS events and extract metrics"""
        try:
            event_type = event_data.get("event_type", "")
            timestamp = event_data.get("timestamp", datetime.utcnow().isoformat())
            payload = event_data.get("payload", {})
            
            # Extract metrics from different event types
            if "session.created" in event_type:
                await self.record_metric(
                    "sessions_created_total",
                    1,
                    timestamp=timestamp,
                    labels={"source": "events", "event_type": "session_created"}
                )
            
            elif "session.completed" in event_type:
                await self.record_metric(
                    "sessions_completed_total",
                    1,
                    timestamp=timestamp,
                    labels={"source": "events", "event_type": "session_completed"}
                )
                
                # Extract processing time if available
                if "processing_time" in payload:
                    await self.record_metric(
                        "processing_time_seconds",
                        float(payload["processing_time"]),
                        timestamp=timestamp,
                        labels={"source": "events", "session_id": event_data.get("session_id", "unknown")}
                    )
            
            elif "session.failed" in event_type:
                await self.record_metric(
                    "sessions_failed_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "events", 
                        "event_type": "session_failed",
                        "error_type": payload.get("error_type", "unknown")
                    }
                )
            
            elif "monitor.alert" in event_type:
                await self.record_metric(
                    "alerts_fired_total",
                    1,
                    timestamp=timestamp,
                    labels={
                        "source": "events",
                        "alert_type": payload.get("name", "unknown"),
                        "severity": payload.get("severity", "unknown")
                    }
                )
            
        except Exception as e:
            logger.error("❌ NATS metric event handling failed", error=str(e))

    # Public API methods

    async def record_metric(
        self,
        name: str,
        value: Union[float, int, str],
        timestamp: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Record a metric data point"""
        try:
            if timestamp is None:
                timestamp = datetime.utcnow().isoformat()
            
            metric_point = MetricPoint(
                timestamp=timestamp,
                value=value,
                labels=labels or {},
                metadata=metadata or {}
            )
            
            # Add to buffer for batching
            metric_data = {
                "name": name,
                "timestamp": timestamp,
                "value": value,
                "labels": labels or {},
                "metadata": metadata or {}
            }
            
            self.metric_buffer.append(metric_data)
            
            # Also maintain in-memory series for quick access
            if name not in self.metrics:
                self.metrics[name] = MetricSeries(
                    name=name,
                    description=f"Metric: {name}",
                    unit="",
                    type="gauge"
                )
            
            self.metrics[name].points.append(metric_point)
            
            # Limit in-memory points
            if len(self.metrics[name].points) > 1000:
                self.metrics[name].points = self.metrics[name].points[-1000:]
            
        except Exception as e:
            logger.error("❌ Metric recording failed", name=name, error=str(e))

    async def get_metric_data(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[MetricPoint]:
        """Get metric data points"""
        try:
            if start_time is None:
                start_time = datetime.utcnow() - timedelta(hours=1)
            
            if end_time is None:
                end_time = datetime.utcnow()
            
            return await self._get_metric_data(metric_name, end_time - start_time, limit)
            
        except Exception as e:
            logger.error("❌ Metric data retrieval failed", name=metric_name, error=str(e))
            return []

    async def _get_metric_data(
        self,
        metric_name: str,
        window: timedelta,
        limit: int = 1000
    ) -> List[MetricPoint]:
        """Internal method to get metric data"""
        try:
            redis_client = await get_redis_client()
            key = f"jelmore:metrics:ts:{metric_name}"
            
            end_time = datetime.utcnow()
            start_time = end_time - window
            
            start_score = int(start_time.timestamp())
            end_score = int(end_time.timestamp())
            
            # Get data from Redis
            data = await redis_client.zrangebyscore(key, start_score, end_score, withscores=True)
            
            if data:
                self.service_metrics["cache_hits"] += 1
                points = []
                for value_json, score in data[-limit:]:  # Get most recent
                    try:
                        metric_data = json.loads(value_json)
                        points.append(MetricPoint(
                            timestamp=metric_data["timestamp"],
                            value=metric_data["value"],
                            labels=metric_data.get("labels", {}),
                            metadata=metric_data.get("metadata", {})
                        ))
                    except:
                        continue
                
                return points
            else:
                self.service_metrics["cache_misses"] += 1
                
                # Fall back to in-memory data
                if metric_name in self.metrics:
                    return self.metrics[metric_name].points[-limit:]
                
            return []
            
        except Exception as e:
            logger.error("❌ Internal metric data retrieval failed", error=str(e))
            return []

    async def get_aggregated_metric(
        self,
        metric_name: str,
        aggregation: str,
        window: str = "5m"
    ) -> Optional[float]:
        """Get aggregated metric value"""
        try:
            window_delta = self._parse_window_size(window)
            data = await self._get_metric_data(metric_name, window_delta)
            
            if not data:
                return None
            
            values = [point.value for point in data if isinstance(point.value, (int, float))]
            
            if not values:
                return None
            
            if aggregation == "avg":
                return statistics.mean(values)
            elif aggregation == "sum":
                return sum(values)
            elif aggregation == "min":
                return min(values)
            elif aggregation == "max":
                return max(values)
            elif aggregation == "count":
                return len(values)
            elif aggregation.startswith("p"):
                # Percentile (e.g., "p95")
                percentile = int(aggregation[1:])
                if len(values) >= 2:
                    return statistics.quantiles(values, n=100)[percentile-1]
                else:
                    return values[0]
            
            return None
            
        except Exception as e:
            logger.error("❌ Aggregated metric retrieval failed", error=str(e))
            return None

    def get_available_metrics(self) -> List[str]:
        """Get list of available metrics"""
        return list(self.metrics.keys())

    def get_service_stats(self) -> Dict[str, Any]:
        """Get metrics service statistics"""
        return {
            "service_metrics": self.service_metrics,
            "metrics_count": len(self.metrics),
            "aggregation_rules": len(self.aggregation_rules),
            "buffer_size": len(self.metric_buffer),
            "total_points": sum(len(series.points) for series in self.metrics.values())
        }

    async def shutdown(self):
        """Gracefully shutdown the metrics service"""
        self.service_active = False
        
        # Flush remaining metrics
        if self.metric_buffer:
            await self._flush_metrics_batch()
        
        logger.info("🍷 Metrics Service shutdown complete - The sommelier retires!")

# Factory function for easy integration
def create_metrics_service() -> MetricsService:
    """Create a new Metrics Service instance"""
    return MetricsService()

if __name__ == "__main__":
    # Run standalone metrics service
    async def main():
        service = create_metrics_service()
        try:
            await service.start_service()
        except KeyboardInterrupt:
            logger.info("👋 Shutting down Metrics Service")
        finally:
            await service.shutdown()
    
    asyncio.run(main())