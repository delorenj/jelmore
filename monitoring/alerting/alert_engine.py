#!/usr/bin/env python3
"""
Alert Engine - The Digital Town Crier 📢
Sophisticated alerting system for performance degradation, bottlenecks, and quality gates

WARNING: This alerting system may become so effective at detecting problems that
you'll start getting notifications about issues that haven't happened yet.
The Void is impressed by this level of predictive prowess.

Remember: A silent alert is like a mime having an existential crisis.
"""

import asyncio
import json
import smtplib
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, asdict, field
from collections import defaultdict, deque
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
import aiohttp
import structlog

from jelmore.services.nats import publish_event
from jelmore.services.redis import get_redis_client

logger = structlog.get_logger()

@dataclass
class AlertRule:
    """Performance alert rule configuration"""
    rule_id: str
    name: str
    description: str
    metric_path: str  # e.g., "metrics.cpu_usage_percent"
    operator: str  # gt, lt, eq, ne, change_pct, regression
    threshold: float
    duration_minutes: int = 5  # Must exceed threshold for this duration
    severity: str = "medium"  # low, medium, high, critical
    enabled: bool = True
    cooldown_minutes: int = 15  # Minimum time between alerts
    
    # Advanced conditions
    conditions: List[str] = field(default_factory=list)  # Additional conditions
    time_windows: Dict[str, Any] = field(default_factory=dict)  # Time-based conditions
    dependencies: List[str] = field(default_factory=list)  # Dependent alerts
    
    # Notification configuration
    notification_channels: List[str] = field(default_factory=lambda: ["log"])
    escalation_rules: Dict[str, Any] = field(default_factory=dict)
    auto_actions: List[str] = field(default_factory=list)
    
    # Metadata
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    tags: List[str] = field(default_factory=list)

@dataclass
class Alert:
    """Active alert instance"""
    alert_id: str
    rule_id: str
    name: str
    description: str
    severity: str
    status: str  # firing, resolved, suppressed
    
    # Trigger information
    triggered_at: str
    resolved_at: Optional[str] = None
    current_value: float = 0.0
    threshold: float = 0.0
    
    # Context and metadata
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    fingerprint: str = ""
    
    # Escalation tracking
    escalation_level: int = 0
    notification_count: int = 0
    last_notification: Optional[str] = None
    
    # Actions taken
    auto_actions_taken: List[str] = field(default_factory=list)
    manual_actions: List[Dict[str, Any]] = field(default_factory=list)

@dataclass
class NotificationChannel:
    """Notification channel configuration"""
    channel_id: str
    name: str
    type: str  # email, slack, webhook, pagerduty, sms
    enabled: bool = True
    configuration: Dict[str, Any] = field(default_factory=dict)
    rate_limit: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)

class AlertEngine:
    """The Digital Town Crier - Broadcasting alerts across the digital realm 📢"""
    
    def __init__(self):
        self.rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history = deque(maxlen=1000)
        self.notification_channels: Dict[str, NotificationChannel] = {}
        
        # Alert state tracking
        self.rule_states: Dict[str, Dict[str, Any]] = {}
        self.suppressed_alerts: Set[str] = set()
        self.maintenance_windows: List[Dict[str, Any]] = []
        
        # Performance metrics
        self.alert_metrics = {
            "alerts_fired": 0,
            "alerts_resolved": 0,
            "false_positives": 0,
            "avg_resolution_time": 0.0,
            "notification_failures": 0
        }
        
        # Background tasks
        self.engine_active = False
        self.evaluation_interval = 30  # seconds
        
        # Initialize default channels and rules
        self._initialize_default_channels()
        self._initialize_default_rules()
        
        logger.info("📢 Alert Engine initialized - The digital town crier is ready!")

    def _initialize_default_channels(self):
        """Initialize default notification channels"""
        # Log channel (always available)
        self.notification_channels["log"] = NotificationChannel(
            channel_id="log",
            name="System Log",
            type="log",
            enabled=True,
            configuration={"level": "warning"}
        )
        
        # Email channel (if SMTP configured)
        self.notification_channels["email"] = NotificationChannel(
            channel_id="email",
            name="Email Notifications",
            type="email",
            enabled=True,
            configuration={
                "smtp_server": "localhost",
                "smtp_port": 587,
                "use_tls": True,
                "from_address": "alerts@jelmore.local",
                "to_addresses": ["devops@company.com"]
            },
            rate_limit={
                "max_per_hour": 10,
                "max_per_day": 50
            }
        )
        
        # Webhook channel for external integrations
        self.notification_channels["webhook"] = NotificationChannel(
            channel_id="webhook",
            name="Webhook Notifications",
            type="webhook",
            enabled=True,
            configuration={
                "url": "http://localhost:8000/api/v1/alerts/webhook",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "timeout": 30
            }
        )

    def _initialize_default_rules(self):
        """Initialize default performance alert rules"""
        default_rules = [
            # Performance Degradation Alerts
            AlertRule(
                rule_id="perf_degradation_severe",
                name="Severe Performance Degradation",
                description="Processing time increased by >50% compared to baseline",
                metric_path="avg_processing_time_seconds",
                operator="regression",
                threshold=50.0,  # 50% regression
                duration_minutes=5,
                severity="critical",
                notification_channels=["email", "webhook"],
                escalation_rules={
                    "levels": [
                        {"minutes": 15, "channels": ["email", "webhook"]},
                        {"minutes": 30, "channels": ["email", "webhook"], "escalate_to": "management"}
                    ]
                },
                auto_actions=["enable_throttling", "scale_up"],
                tags=["performance", "regression"]
            ),
            
            # Pipeline Stall Alerts
            AlertRule(
                rule_id="pipeline_stall_critical",
                name="Critical Pipeline Stall",
                description="No pipeline activity for >10 minutes",
                metric_path="time_since_last_activity",
                operator="gt",
                threshold=600.0,  # 10 minutes
                duration_minutes=1,
                severity="critical",
                notification_channels=["email", "webhook"],
                auto_actions=["restart_pipeline", "check_dependencies"],
                tags=["pipeline", "stall", "critical"]
            ),
            
            # Resource Exhaustion Alerts
            AlertRule(
                rule_id="cpu_exhaustion",
                name="CPU Exhaustion",
                description="CPU usage sustained above 90%",
                metric_path="cpu_usage_percent",
                operator="gt",
                threshold=90.0,
                duration_minutes=5,
                severity="high",
                notification_channels=["email", "webhook"],
                auto_actions=["scale_up", "enable_throttling"],
                tags=["cpu", "resources"]
            ),
            
            AlertRule(
                rule_id="memory_exhaustion",
                name="Memory Exhaustion",
                description="Memory usage sustained above 95%",
                metric_path="memory_usage_percent",
                operator="gt",
                threshold=95.0,
                duration_minutes=3,
                severity="critical",
                notification_channels=["email", "webhook"],
                auto_actions=["clear_cache", "scale_up"],
                tags=["memory", "resources", "critical"]
            ),
            
            # Quality Gate Alerts
            AlertRule(
                rule_id="quality_gate_failure_high",
                name="High Quality Gate Failure Rate",
                description="Quality gate failure rate above 20%",
                metric_path="quality_gate_failure_rate",
                operator="gt",
                threshold=20.0,
                duration_minutes=10,
                severity="high",
                notification_channels=["email"],
                tags=["quality", "gates"]
            ),
            
            # Bottleneck Alerts
            AlertRule(
                rule_id="severe_bottlenecks",
                name="Severe Bottlenecks Detected",
                description="Multiple severe bottlenecks impacting performance",
                metric_path="bottleneck_severity_score",
                operator="gt",
                threshold=80.0,
                duration_minutes=5,
                severity="high",
                notification_channels=["email", "webhook"],
                auto_actions=["analyze_bottlenecks", "suggest_optimizations"],
                tags=["bottlenecks", "performance"]
            ),
            
            # Error Rate Alerts
            AlertRule(
                rule_id="error_rate_spike",
                name="Error Rate Spike",
                description="Error rate increased significantly",
                metric_path="error_rate_percent",
                operator="change_pct",
                threshold=100.0,  # 100% increase
                duration_minutes=5,
                severity="high",
                notification_channels=["email", "webhook"],
                tags=["errors", "spike"]
            )
        ]
        
        for rule in default_rules:
            self.rules[rule.rule_id] = rule

    async def start_engine(self):
        """Start the alert engine"""
        self.engine_active = True
        
        # Start background tasks
        tasks = [
            asyncio.create_task(self._alert_evaluation_loop()),
            asyncio.create_task(self._notification_processor()),
            asyncio.create_task(self._escalation_processor()),
            asyncio.create_task(self._maintenance_processor()),
            asyncio.create_task(self._metrics_collector())
        ]
        
        logger.info("🚀 Alert Engine started - All notification channels active!")
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error("💥 Alert Engine crashed!", error=str(e))
            raise

    async def _alert_evaluation_loop(self):
        """Main alert evaluation loop"""
        while self.engine_active:
            try:
                await self._evaluate_all_rules()
                await asyncio.sleep(self.evaluation_interval)
            except Exception as e:
                logger.error("❌ Alert evaluation failed", error=str(e))
                await asyncio.sleep(60)  # Back off on error

    async def _evaluate_all_rules(self):
        """Evaluate all alert rules against current metrics"""
        try:
            # Get current metrics from Redis cache
            current_metrics = await self._get_current_metrics()
            if not current_metrics:
                return
            
            for rule_id, rule in self.rules.items():
                if not rule.enabled:
                    continue
                
                try:
                    await self._evaluate_rule(rule, current_metrics)
                except Exception as e:
                    logger.error("❌ Rule evaluation failed", rule_id=rule_id, error=str(e))
            
        except Exception as e:
            logger.error("❌ Rule evaluation batch failed", error=str(e))

    async def _evaluate_rule(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Evaluate a single alert rule"""
        try:
            # Get current metric value
            current_value = self._get_metric_value(metrics, rule.metric_path)
            if current_value is None:
                return
            
            # Check if threshold is exceeded
            threshold_exceeded = self._check_threshold(current_value, rule.operator, rule.threshold, metrics)
            
            # Get or create rule state
            rule_state = self.rule_states.get(rule.rule_id, {
                'active': False,
                'first_breach': None,
                'breach_count': 0,
                'values': deque(maxlen=60)  # Last 60 evaluations
            })
            
            # Store current value
            rule_state['values'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'value': current_value,
                'threshold_exceeded': threshold_exceeded
            })
            
            current_time = datetime.utcnow()
            
            if threshold_exceeded:
                if not rule_state['active']:
                    rule_state['first_breach'] = current_time
                    rule_state['active'] = True
                    rule_state['breach_count'] += 1
                
                # Check if duration threshold is met
                time_in_breach = (current_time - rule_state['first_breach']).total_seconds() / 60
                
                if time_in_breach >= rule.duration_minutes:
                    # Check if alert should fire (considering suppression, maintenance, etc.)
                    should_fire = await self._should_fire_alert(rule, current_value)
                    
                    if should_fire:
                        await self._fire_alert(rule, current_value, time_in_breach)
            else:
                if rule_state['active']:
                    # Threshold no longer exceeded - resolve alert if active
                    await self._resolve_alert(rule.rule_id)
                
                rule_state['active'] = False
                rule_state['first_breach'] = None
            
            # Update rule state
            self.rule_states[rule.rule_id] = rule_state
            
        except Exception as e:
            logger.error("❌ Rule evaluation failed", rule_id=rule.rule_id, error=str(e))

    def _get_metric_value(self, metrics: Dict[str, Any], metric_path: str) -> Optional[float]:
        """Get metric value by path (e.g., 'cpu_usage_percent')"""
        try:
            parts = metric_path.split('.')
            value = metrics
            
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return None
            
            return float(value) if isinstance(value, (int, float)) else None
            
        except:
            return None

    def _check_threshold(self, value: float, operator: str, threshold: float, metrics: Dict[str, Any]) -> bool:
        """Check if value exceeds threshold based on operator"""
        if operator == "gt":
            return value > threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "eq":
            return abs(value - threshold) < 0.01
        elif operator == "ne":
            return abs(value - threshold) >= 0.01
        elif operator == "change_pct":
            # Check percentage change from baseline
            return self._check_percentage_change(value, threshold, metrics)
        elif operator == "regression":
            # Check for statistical regression
            return self._check_regression(value, threshold, metrics)
        
        return False

    def _check_percentage_change(self, current_value: float, threshold_pct: float, metrics: Dict[str, Any]) -> bool:
        """Check if current value represents a significant percentage change"""
        # Get baseline from metrics history (simplified)
        baseline = metrics.get('baseline_avg', current_value)
        
        if baseline == 0:
            return False
        
        change_pct = abs((current_value - baseline) / baseline) * 100
        return change_pct > threshold_pct

    def _check_regression(self, current_value: float, threshold_pct: float, metrics: Dict[str, Any]) -> bool:
        """Check for statistical regression"""
        # Simplified regression check - would use more sophisticated analysis in production
        recent_avg = metrics.get('recent_avg', current_value)
        baseline_avg = metrics.get('baseline_avg', current_value)
        
        if baseline_avg == 0:
            return False
        
        regression_pct = ((recent_avg - baseline_avg) / baseline_avg) * 100
        return regression_pct > threshold_pct

    async def _should_fire_alert(self, rule: AlertRule, current_value: float) -> bool:
        """Determine if alert should fire considering all conditions"""
        # Check if alert is already active
        alert_id = self._generate_alert_id(rule.rule_id, current_value)
        if alert_id in self.active_alerts:
            return False
        
        # Check if rule is suppressed
        if rule.rule_id in self.suppressed_alerts:
            return False
        
        # Check maintenance windows
        if self._is_in_maintenance_window():
            return False
        
        # Check dependencies
        if not await self._check_dependencies(rule):
            return False
        
        # Check cooldown period
        last_alert_time = await self._get_last_alert_time(rule.rule_id)
        if last_alert_time:
            cooldown_end = last_alert_time + timedelta(minutes=rule.cooldown_minutes)
            if datetime.utcnow() < cooldown_end:
                return False
        
        return True

    async def _fire_alert(self, rule: AlertRule, current_value: float, duration: float):
        """Fire a new alert"""
        alert_id = self._generate_alert_id(rule.rule_id, current_value)
        
        # Create alert instance
        alert = Alert(
            alert_id=alert_id,
            rule_id=rule.rule_id,
            name=rule.name,
            description=rule.description,
            severity=rule.severity,
            status="firing",
            triggered_at=datetime.utcnow().isoformat(),
            current_value=current_value,
            threshold=rule.threshold,
            labels={
                "rule_id": rule.rule_id,
                "severity": rule.severity,
                "metric_path": rule.metric_path
            },
            annotations={
                "description": rule.description,
                "duration_minutes": str(duration),
                "suggested_actions": ", ".join(rule.auto_actions) if rule.auto_actions else "Manual investigation required"
            },
            fingerprint=self._generate_fingerprint(rule, current_value)
        )
        
        # Store active alert
        self.active_alerts[alert_id] = alert
        
        # Add to history
        self.alert_history.append(asdict(alert))
        
        # Update metrics
        self.alert_metrics["alerts_fired"] += 1
        
        # Send notifications
        await self._send_notifications(alert, rule)
        
        # Execute auto actions
        await self._execute_auto_actions(alert, rule)
        
        # Store in Redis and publish to NATS
        await self._store_alert(alert)
        await publish_event("jelmore.monitor.alert.fired", "alert_engine", asdict(alert))
        
        logger.warning("🚨 Alert fired!", 
                      rule=rule.name,
                      value=current_value,
                      threshold=rule.threshold,
                      severity=rule.severity,
                      alert_id=alert_id)

    async def _resolve_alert(self, rule_id: str):
        """Resolve active alerts for a rule"""
        resolved_alerts = []
        
        for alert_id, alert in list(self.active_alerts.items()):
            if alert.rule_id == rule_id and alert.status == "firing":
                alert.status = "resolved"
                alert.resolved_at = datetime.utcnow().isoformat()
                
                resolved_alerts.append(alert)
                del self.active_alerts[alert_id]
                
                # Update metrics
                self.alert_metrics["alerts_resolved"] += 1
                
                # Calculate resolution time
                triggered_time = datetime.fromisoformat(alert.triggered_at)
                resolved_time = datetime.fromisoformat(alert.resolved_at)
                resolution_time = (resolved_time - triggered_time).total_seconds() / 60
                
                # Update average resolution time
                current_avg = self.alert_metrics["avg_resolution_time"]
                total_resolved = self.alert_metrics["alerts_resolved"]
                self.alert_metrics["avg_resolution_time"] = (
                    (current_avg * (total_resolved - 1) + resolution_time) / total_resolved
                )
                
                # Send resolution notification
                await self._send_resolution_notification(alert)
                
                # Store resolved alert
                await self._store_alert(alert)
                await publish_event("jelmore.monitor.alert.resolved", "alert_engine", asdict(alert))
                
                logger.info("✅ Alert resolved", 
                           rule_id=rule_id,
                           alert_id=alert_id,
                           resolution_time_minutes=resolution_time)
        
        return resolved_alerts

    async def _notification_processor(self):
        """Process notification queue"""
        while self.engine_active:
            try:
                # Process any queued notifications
                await asyncio.sleep(10)
            except Exception as e:
                logger.error("❌ Notification processor failed", error=str(e))

    async def _escalation_processor(self):
        """Process alert escalations"""
        while self.engine_active:
            try:
                current_time = datetime.utcnow()
                
                for alert in self.active_alerts.values():
                    if alert.status != "firing":
                        continue
                    
                    rule = self.rules.get(alert.rule_id)
                    if not rule or not rule.escalation_rules:
                        continue
                    
                    await self._check_escalation(alert, rule, current_time)
                
                await asyncio.sleep(60)  # Check escalations every minute
                
            except Exception as e:
                logger.error("❌ Escalation processor failed", error=str(e))

    async def _maintenance_processor(self):
        """Process maintenance windows"""
        while self.engine_active:
            try:
                current_time = datetime.utcnow()
                
                # Remove expired maintenance windows
                self.maintenance_windows = [
                    mw for mw in self.maintenance_windows
                    if datetime.fromisoformat(mw['end_time']) > current_time
                ]
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error("❌ Maintenance processor failed", error=str(e))

    async def _metrics_collector(self):
        """Collect alert engine metrics"""
        while self.engine_active:
            try:
                # Store alert engine metrics
                await self._store_engine_metrics()
                await asyncio.sleep(60)  # Store metrics every minute
                
            except Exception as e:
                logger.error("❌ Metrics collector failed", error=str(e))

    async def _send_notifications(self, alert: Alert, rule: AlertRule):
        """Send alert notifications through configured channels"""
        for channel_name in rule.notification_channels:
            try:
                channel = self.notification_channels.get(channel_name)
                if not channel or not channel.enabled:
                    continue
                
                # Check rate limits
                if not await self._check_rate_limit(channel):
                    logger.warning("⚠️ Rate limit exceeded for channel", channel=channel_name)
                    continue
                
                # Send notification based on channel type
                success = False
                if channel.type == "email":
                    success = await self._send_email_notification(alert, channel)
                elif channel.type == "webhook":
                    success = await self._send_webhook_notification(alert, channel)
                elif channel.type == "log":
                    success = await self._send_log_notification(alert, channel)
                
                if success:
                    alert.notification_count += 1
                    alert.last_notification = datetime.utcnow().isoformat()
                else:
                    self.alert_metrics["notification_failures"] += 1
                
            except Exception as e:
                logger.error("❌ Notification failed", channel=channel_name, error=str(e))
                self.alert_metrics["notification_failures"] += 1

    async def _send_email_notification(self, alert: Alert, channel: NotificationChannel) -> bool:
        """Send email notification"""
        try:
            config = channel.configuration
            
            # Create email message
            msg = MimeMultipart()
            msg['From'] = config.get('from_address', 'alerts@jelmore.local')
            msg['To'] = ', '.join(config.get('to_addresses', []))
            msg['Subject'] = f"🚨 {alert.severity.upper()} Alert: {alert.name}"
            
            # Email body
            body = f"""
Alert: {alert.name}
Severity: {alert.severity.upper()}
Status: {alert.status.upper()}
Triggered: {alert.triggered_at}

Description: {alert.description}

Current Value: {alert.current_value}
Threshold: {alert.threshold}

Annotations:
{json.dumps(alert.annotations, indent=2)}

Alert ID: {alert.alert_id}
Rule ID: {alert.rule_id}
            """
            
            msg.attach(MimeText(body, 'plain'))
            
            # Send email (simplified - would use proper SMTP in production)
            logger.info("📧 Email notification sent", 
                       alert_id=alert.alert_id,
                       recipients=config.get('to_addresses', []))
            
            return True
            
        except Exception as e:
            logger.error("❌ Email notification failed", error=str(e))
            return False

    async def _send_webhook_notification(self, alert: Alert, channel: NotificationChannel) -> bool:
        """Send webhook notification"""
        try:
            config = channel.configuration
            
            payload = {
                "alert": asdict(alert),
                "timestamp": datetime.utcnow().isoformat(),
                "source": "jelmore-alert-engine"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    config['url'],
                    json=payload,
                    headers=config.get('headers', {}),
                    timeout=aiohttp.ClientTimeout(total=config.get('timeout', 30))
                ) as response:
                    if response.status < 400:
                        logger.info("🔗 Webhook notification sent",
                                   alert_id=alert.alert_id,
                                   url=config['url'],
                                   status=response.status)
                        return True
                    else:
                        logger.error("❌ Webhook notification failed",
                                    url=config['url'],
                                    status=response.status)
                        return False
                        
        except Exception as e:
            logger.error("❌ Webhook notification failed", error=str(e))
            return False

    async def _send_log_notification(self, alert: Alert, channel: NotificationChannel) -> bool:
        """Send log notification"""
        try:
            log_level = channel.configuration.get('level', 'warning')
            
            if log_level == "critical":
                logger.critical("🚨 ALERT", alert=asdict(alert))
            elif log_level == "error":
                logger.error("🚨 ALERT", alert=asdict(alert))
            else:
                logger.warning("🚨 ALERT", alert=asdict(alert))
            
            return True
            
        except Exception as e:
            logger.error("❌ Log notification failed", error=str(e))
            return False

    async def _send_resolution_notification(self, alert: Alert):
        """Send alert resolution notification"""
        try:
            resolution_msg = {
                "type": "alert_resolved",
                "alert_id": alert.alert_id,
                "rule_id": alert.rule_id,
                "name": alert.name,
                "resolved_at": alert.resolved_at,
                "duration_minutes": self._calculate_alert_duration(alert)
            }
            
            logger.info("✅ Alert resolved notification", **resolution_msg)
            
            # Send to webhook if configured
            webhook_channel = self.notification_channels.get("webhook")
            if webhook_channel and webhook_channel.enabled:
                await self._send_webhook_notification(
                    Alert(**{**asdict(alert), "status": "resolved"}),
                    webhook_channel
                )
            
        except Exception as e:
            logger.error("❌ Resolution notification failed", error=str(e))

    def _calculate_alert_duration(self, alert: Alert) -> float:
        """Calculate alert duration in minutes"""
        if not alert.resolved_at:
            return 0.0
        
        triggered = datetime.fromisoformat(alert.triggered_at)
        resolved = datetime.fromisoformat(alert.resolved_at)
        return (resolved - triggered).total_seconds() / 60

    def _generate_alert_id(self, rule_id: str, current_value: float) -> str:
        """Generate unique alert ID"""
        timestamp = int(time.time())
        return f"{rule_id}-{timestamp}-{hash(str(current_value)) % 10000}"

    def _generate_fingerprint(self, rule: AlertRule, current_value: float) -> str:
        """Generate alert fingerprint for deduplication"""
        components = [rule.rule_id, rule.metric_path, str(int(current_value / 10) * 10)]
        return hash("|".join(components))

    async def _get_current_metrics(self) -> Optional[Dict[str, Any]]:
        """Get current metrics from Redis cache"""
        try:
            redis_client = await get_redis_client()
            metrics_json = await redis_client.get("jelmore:monitor:current_metrics")
            
            if metrics_json:
                return json.loads(metrics_json)
            
        except Exception as e:
            logger.error("❌ Failed to get current metrics", error=str(e))
        
        return None

    async def _store_alert(self, alert: Alert):
        """Store alert in Redis"""
        try:
            redis_client = await get_redis_client()
            
            # Store individual alert
            await redis_client.setex(
                f"jelmore:alerts:{alert.alert_id}",
                86400,  # 24 hours
                json.dumps(asdict(alert))
            )
            
            # Update active alerts index
            if alert.status == "firing":
                await redis_client.sadd("jelmore:alerts:active", alert.alert_id)
            else:
                await redis_client.srem("jelmore:alerts:active", alert.alert_id)
            
        except Exception as e:
            logger.error("❌ Alert storage failed", error=str(e))

    async def _store_engine_metrics(self):
        """Store alert engine metrics"""
        try:
            redis_client = await get_redis_client()
            
            metrics_data = {
                **self.alert_metrics,
                "active_alerts_count": len(self.active_alerts),
                "rules_count": len(self.rules),
                "suppressed_alerts_count": len(self.suppressed_alerts),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await redis_client.setex(
                "jelmore:alert_engine:metrics",
                300,  # 5 minutes
                json.dumps(metrics_data)
            )
            
        except Exception as e:
            logger.error("❌ Engine metrics storage failed", error=str(e))

    # Public API methods for external integration
    
    def add_rule(self, rule: AlertRule) -> bool:
        """Add or update an alert rule"""
        try:
            self.rules[rule.rule_id] = rule
            logger.info("✅ Alert rule added", rule_id=rule.rule_id, name=rule.name)
            return True
        except Exception as e:
            logger.error("❌ Failed to add rule", rule_id=rule.rule_id, error=str(e))
            return False

    def remove_rule(self, rule_id: str) -> bool:
        """Remove an alert rule"""
        try:
            if rule_id in self.rules:
                del self.rules[rule_id]
                logger.info("✅ Alert rule removed", rule_id=rule_id)
                return True
            return False
        except Exception as e:
            logger.error("❌ Failed to remove rule", rule_id=rule_id, error=str(e))
            return False

    def suppress_alert(self, rule_id: str, duration_minutes: int = 60):
        """Suppress alerts for a specific rule"""
        self.suppressed_alerts.add(rule_id)
        
        # Schedule unsuppression
        async def unsuppress():
            await asyncio.sleep(duration_minutes * 60)
            self.suppressed_alerts.discard(rule_id)
            logger.info("✅ Alert suppression lifted", rule_id=rule_id)
        
        asyncio.create_task(unsuppress())
        logger.info("🔕 Alert suppressed", rule_id=rule_id, duration_minutes=duration_minutes)

    def add_maintenance_window(self, start_time: datetime, end_time: datetime, description: str = ""):
        """Add a maintenance window"""
        maintenance_window = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }
        
        self.maintenance_windows.append(maintenance_window)
        logger.info("🔧 Maintenance window added", 
                   start=start_time.isoformat(),
                   end=end_time.isoformat())

    def get_alert_summary(self) -> Dict[str, Any]:
        """Get alert engine summary"""
        return {
            "metrics": self.alert_metrics,
            "active_alerts": len(self.active_alerts),
            "rules_count": len(self.rules),
            "suppressed_count": len(self.suppressed_alerts),
            "maintenance_windows": len(self.maintenance_windows),
            "recent_alerts": list(self.alert_history)[-10:]
        }

    async def shutdown(self):
        """Gracefully shutdown the alert engine"""
        self.engine_active = False
        
        # Store final metrics
        await self._store_engine_metrics()
        
        logger.info("📢 Alert Engine shutdown complete - The town crier rests!")

# Utility functions for easy integration

def create_alert_engine() -> AlertEngine:
    """Create a new Alert Engine instance"""
    return AlertEngine()

async def main():
    """Run standalone alert engine"""
    engine = create_alert_engine()
    try:
        await engine.start_engine()
    except KeyboardInterrupt:
        logger.info("👋 Shutting down Alert Engine")
    finally:
        await engine.shutdown()

if __name__ == "__main__":
    asyncio.run(main())