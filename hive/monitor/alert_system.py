#!/usr/bin/env python3
"""
Alert System for Jelmore Pipeline Monitoring
Advanced alerting with multiple channels and escalation policies
"""

import asyncio
import json
import smtplib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from pathlib import Path
import aiohttp
import structlog
from .log.logger import AdvancedLogger, LogLevel, LogCategory

logger = structlog.get_logger("alert.system")

@dataclass
class Alert:
    """Alert structure"""
    alert_id: str
    alert_type: str
    severity: str  # critical, high, medium, low
    title: str
    message: str
    source_component: str
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str = ""
    acknowledged: bool = False
    resolved: bool = False
    escalated: bool = False
    escalation_count: int = 0

@dataclass
class AlertChannel:
    """Alert delivery channel configuration"""
    channel_type: str  # email, slack, webhook, console
    enabled: bool
    config: Dict[str, Any]
    severity_threshold: str  # minimum severity to alert
    cooldown_minutes: int = 5  # minimum time between same alerts

@dataclass
class EscalationPolicy:
    """Alert escalation policy"""
    name: str
    triggers: List[str]  # alert types that trigger this policy
    escalation_steps: List[Dict[str, Any]]
    max_escalations: int = 3

class AlertManager:
    """Advanced alert management system"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.channels: Dict[str, AlertChannel] = {}
        self.escalation_policies: Dict[str, EscalationPolicy] = {}
        
        # Alert tracking
        self.last_alert_times: Dict[str, datetime] = {}
        self.alert_stats = {
            "total_alerts": 0,
            "critical_alerts": 0,
            "resolved_alerts": 0,
            "escalated_alerts": 0
        }
        
        # Configuration
        self.config_file = config_file or "/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/alert_config.json"
        self.logger: Optional[AdvancedLogger] = None
        
        # Background tasks
        self.escalation_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
        
        # Default configuration
        self._setup_default_config()
        
        logger.info("🚨 Alert Manager initialized")

    def _setup_default_config(self):
        """Setup default alert configuration"""
        
        # Default channels
        self.channels = {
            "console": AlertChannel(
                channel_type="console",
                enabled=True,
                config={},
                severity_threshold="medium",
                cooldown_minutes=1
            ),
            "log_file": AlertChannel(
                channel_type="log_file",
                enabled=True,
                config={
                    "log_file": "/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/alerts.log"
                },
                severity_threshold="low",
                cooldown_minutes=0
            ),
            "webhook": AlertChannel(
                channel_type="webhook",
                enabled=False,  # Disabled by default, enable via config
                config={
                    "url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
                    "timeout": 10
                },
                severity_threshold="high",
                cooldown_minutes=10
            )
        }
        
        # Default escalation policies
        self.escalation_policies = {
            "critical_session_failure": EscalationPolicy(
                name="Critical Session Failure",
                triggers=["session_timeout", "high_error_rate", "system_failure"],
                escalation_steps=[
                    {"delay_minutes": 5, "channels": ["console", "log_file"]},
                    {"delay_minutes": 15, "channels": ["console", "log_file", "webhook"]},
                    {"delay_minutes": 30, "channels": ["console", "log_file", "webhook"]}
                ],
                max_escalations=3
            ),
            "performance_degradation": EscalationPolicy(
                name="Performance Issues",
                triggers=["slow_processing", "high_memory", "high_cpu"],
                escalation_steps=[
                    {"delay_minutes": 10, "channels": ["console", "log_file"]},
                    {"delay_minutes": 30, "channels": ["console", "log_file", "webhook"]}
                ],
                max_escalations=2
            )
        }

    async def initialize(self, advanced_logger: AdvancedLogger):
        """Initialize alert manager with logger"""
        self.logger = advanced_logger
        
        # Load configuration if file exists
        await self._load_config()
        
        # Start background tasks
        self.escalation_task = asyncio.create_task(self._escalation_monitor())
        self.cleanup_task = asyncio.create_task(self._cleanup_old_alerts())
        
        await self.logger.log(
            LogLevel.INFO,
            LogCategory.SYSTEM,
            "Alert Manager initialized",
            data={
                "channels_configured": len(self.channels),
                "escalation_policies": len(self.escalation_policies)
            }
        )

    async def _load_config(self):
        """Load alert configuration from file"""
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                # Update channels
                if "channels" in config:
                    for channel_name, channel_config in config["channels"].items():
                        if channel_name in self.channels:
                            # Update existing channel
                            for key, value in channel_config.items():
                                if hasattr(self.channels[channel_name], key):
                                    setattr(self.channels[channel_name], key, value)
                
                # Update escalation policies
                if "escalation_policies" in config:
                    for policy_name, policy_config in config["escalation_policies"].items():
                        self.escalation_policies[policy_name] = EscalationPolicy(**policy_config)
                
                logger.info("Alert configuration loaded", config_file=self.config_file)
                
        except Exception as e:
            logger.warning("Failed to load alert config, using defaults", error=str(e))

    async def trigger_alert(self, alert_type: str, severity: str, title: str, 
                           message: str, source_component: str,
                           session_id: str = None, data: Dict[str, Any] = None) -> str:
        """Trigger a new alert"""
        try:
            # Generate unique alert ID
            alert_id = f"alert_{int(datetime.utcnow().timestamp()*1000)}"
            
            # Check cooldown period
            cooldown_key = f"{alert_type}_{source_component}_{session_id or 'global'}"
            if await self._is_in_cooldown(cooldown_key, severity):
                logger.debug("Alert skipped due to cooldown", 
                           alert_type=alert_type, cooldown_key=cooldown_key)
                return None
            
            # Create alert
            alert = Alert(
                alert_id=alert_id,
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                source_component=source_component,
                session_id=session_id,
                data=data or {},
                timestamp=datetime.utcnow().isoformat()
            )
            
            # Store alert
            self.alerts[alert_id] = alert
            self.alert_history.append(alert)
            
            # Update statistics
            self.alert_stats["total_alerts"] += 1
            if severity == "critical":
                self.alert_stats["critical_alerts"] += 1
            
            # Log the alert
            if self.logger:
                await self.logger.log(
                    LogLevel.ERROR if severity in ["critical", "high"] else LogLevel.WARNING,
                    LogCategory.SYSTEM,
                    f"🚨 Alert triggered: {title}",
                    session_id=session_id,
                    component=source_component,
                    data={
                        "alert_id": alert_id,
                        "alert_type": alert_type,
                        "severity": severity,
                        "message": message,
                        "alert_data": data
                    }
                )
            
            # Send through appropriate channels
            await self._send_alert(alert)
            
            # Update cooldown
            self.last_alert_times[cooldown_key] = datetime.utcnow()
            
            logger.info("Alert triggered", 
                       alert_id=alert_id, 
                       alert_type=alert_type,
                       severity=severity)
            
            return alert_id
            
        except Exception as e:
            logger.error("Failed to trigger alert", error=str(e))
            raise

    async def _is_in_cooldown(self, cooldown_key: str, severity: str) -> bool:
        """Check if alert is in cooldown period"""
        if cooldown_key not in self.last_alert_times:
            return False
        
        # Get minimum cooldown for this severity across all channels
        min_cooldown = min(
            channel.cooldown_minutes
            for channel in self.channels.values()
            if channel.enabled and self._severity_meets_threshold(severity, channel.severity_threshold)
        )
        
        if min_cooldown == 0:
            return False
        
        last_alert_time = self.last_alert_times[cooldown_key]
        return datetime.utcnow() - last_alert_time < timedelta(minutes=min_cooldown)

    def _severity_meets_threshold(self, alert_severity: str, threshold: str) -> bool:
        """Check if alert severity meets channel threshold"""
        severity_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        return severity_levels.get(alert_severity, 0) >= severity_levels.get(threshold, 0)

    async def _send_alert(self, alert: Alert):
        """Send alert through all appropriate channels"""
        try:
            for channel_name, channel in self.channels.items():
                if not channel.enabled:
                    continue
                
                if not self._severity_meets_threshold(alert.severity, channel.severity_threshold):
                    continue
                
                try:
                    await self._send_to_channel(alert, channel)
                except Exception as e:
                    logger.error("Failed to send alert to channel", 
                               channel=channel_name, alert_id=alert.alert_id, error=str(e))
        
        except Exception as e:
            logger.error("Failed to send alert", alert_id=alert.alert_id, error=str(e))

    async def _send_to_channel(self, alert: Alert, channel: AlertChannel):
        """Send alert to specific channel"""
        try:
            if channel.channel_type == "console":
                await self._send_console_alert(alert)
            elif channel.channel_type == "log_file":
                await self._send_log_file_alert(alert, channel)
            elif channel.channel_type == "webhook":
                await self._send_webhook_alert(alert, channel)
            elif channel.channel_type == "email":
                await self._send_email_alert(alert, channel)
            else:
                logger.warning("Unknown channel type", channel_type=channel.channel_type)
                
        except Exception as e:
            logger.error("Channel send failed", channel_type=channel.channel_type, error=str(e))
            raise

    async def _send_console_alert(self, alert: Alert):
        """Send alert to console"""
        severity_colors = {
            "critical": "\033[41m",  # Red background
            "high": "\033[91m",      # Bright red
            "medium": "\033[93m",    # Yellow
            "low": "\033[94m"        # Blue
        }
        reset_color = "\033[0m"
        
        color = severity_colors.get(alert.severity, "")
        
        print(f"\n{color}🚨 ALERT [{alert.severity.upper()}]{reset_color}")
        print(f"🕐 {alert.timestamp}")
        print(f"🏷️  {alert.title}")
        print(f"📝 {alert.message}")
        print(f"🔧 Component: {alert.source_component}")
        if alert.session_id:
            print(f"🆔 Session: {alert.session_id}")
        print(f"🔗 Alert ID: {alert.alert_id}")
        print(f"{'-'*50}\n")

    async def _send_log_file_alert(self, alert: Alert, channel: AlertChannel):
        """Send alert to log file"""
        log_file = Path(channel.config.get("log_file", "/tmp/alerts.log"))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        alert_line = json.dumps(asdict(alert), default=str, separators=(',', ':'))
        
        try:
            with open(log_file, 'a') as f:
                f.write(alert_line + '\n')
        except Exception as e:
            logger.error("Failed to write alert to log file", log_file=str(log_file), error=str(e))

    async def _send_webhook_alert(self, alert: Alert, channel: AlertChannel):
        """Send alert via webhook"""
        webhook_url = channel.config.get("url")
        timeout = channel.config.get("timeout", 10)
        
        if not webhook_url:
            logger.warning("Webhook URL not configured")
            return
        
        # Prepare webhook payload
        payload = {
            "text": f"🚨 Alert: {alert.title}",
            "attachments": [
                {
                    "color": "danger" if alert.severity in ["critical", "high"] else "warning",
                    "fields": [
                        {"title": "Severity", "value": alert.severity.upper(), "short": True},
                        {"title": "Component", "value": alert.source_component, "short": True},
                        {"title": "Message", "value": alert.message, "short": False},
                        {"title": "Session ID", "value": alert.session_id or "N/A", "short": True},
                        {"title": "Alert ID", "value": alert.alert_id, "short": True}
                    ],
                    "ts": int(datetime.fromisoformat(alert.timestamp).timestamp())
                }
            ]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url, 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        logger.debug("Webhook alert sent successfully", alert_id=alert.alert_id)
                    else:
                        logger.warning("Webhook alert failed", 
                                     status=response.status, alert_id=alert.alert_id)
        except Exception as e:
            logger.error("Webhook alert error", alert_id=alert.alert_id, error=str(e))
            raise

    async def _send_email_alert(self, alert: Alert, channel: AlertChannel):
        """Send alert via email"""
        # This is a placeholder for email functionality
        # In a real implementation, you would configure SMTP settings
        logger.info("Email alert triggered (not implemented)", alert_id=alert.alert_id)

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """Acknowledge an alert"""
        try:
            if alert_id not in self.alerts:
                return False
            
            alert = self.alerts[alert_id]
            alert.acknowledged = True
            
            if self.logger:
                await self.logger.log(
                    LogLevel.INFO,
                    LogCategory.SYSTEM,
                    f"Alert acknowledged: {alert.title}",
                    data={
                        "alert_id": alert_id,
                        "acknowledged_by": acknowledged_by
                    }
                )
            
            logger.info("Alert acknowledged", alert_id=alert_id, acknowledged_by=acknowledged_by)
            return True
            
        except Exception as e:
            logger.error("Failed to acknowledge alert", alert_id=alert_id, error=str(e))
            return False

    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """Resolve an alert"""
        try:
            if alert_id not in self.alerts:
                return False
            
            alert = self.alerts[alert_id]
            alert.resolved = True
            
            # Update statistics
            self.alert_stats["resolved_alerts"] += 1
            
            if self.logger:
                await self.logger.log(
                    LogLevel.INFO,
                    LogCategory.SYSTEM,
                    f"Alert resolved: {alert.title}",
                    data={
                        "alert_id": alert_id,
                        "resolved_by": resolved_by
                    }
                )
            
            logger.info("Alert resolved", alert_id=alert_id, resolved_by=resolved_by)
            return True
            
        except Exception as e:
            logger.error("Failed to resolve alert", alert_id=alert_id, error=str(e))
            return False

    async def _escalation_monitor(self):
        """Monitor alerts for escalation"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.utcnow()
                
                for alert_id, alert in self.alerts.items():
                    if alert.resolved or alert.acknowledged:
                        continue
                    
                    # Check if alert should be escalated
                    for policy_name, policy in self.escalation_policies.items():
                        if alert.alert_type in policy.triggers:
                            await self._check_escalation(alert, policy, current_time)
                
            except Exception as e:
                logger.error("Escalation monitor error", error=str(e))
                await asyncio.sleep(60)

    async def _check_escalation(self, alert: Alert, policy: EscalationPolicy, current_time: datetime):
        """Check if alert should be escalated"""
        try:
            alert_time = datetime.fromisoformat(alert.timestamp)
            
            for step_index, step in enumerate(policy.escalation_steps):
                # Check if it's time for this escalation step
                step_delay = timedelta(minutes=step["delay_minutes"])
                
                if (current_time - alert_time >= step_delay and 
                    alert.escalation_count <= step_index and
                    alert.escalation_count < policy.max_escalations):
                    
                    # Escalate alert
                    await self._escalate_alert(alert, step, step_index, policy.name)
                    break
                    
        except Exception as e:
            logger.error("Escalation check failed", alert_id=alert.alert_id, error=str(e))

    async def _escalate_alert(self, alert: Alert, step: Dict[str, Any], step_index: int, policy_name: str):
        """Escalate an alert"""
        try:
            alert.escalated = True
            alert.escalation_count = step_index + 1
            
            # Update statistics
            self.alert_stats["escalated_alerts"] += 1
            
            # Create escalated alert message
            escalated_alert = Alert(
                alert_id=f"{alert.alert_id}_escalated_{step_index}",
                alert_type=f"{alert.alert_type}_escalated",
                severity="critical",  # Escalated alerts are always critical
                title=f"ESCALATED: {alert.title}",
                message=f"Alert has been escalated (Step {step_index + 1} of policy '{policy_name}'). Original: {alert.message}",
                source_component=alert.source_component,
                session_id=alert.session_id,
                data={
                    "original_alert_id": alert.alert_id,
                    "escalation_step": step_index + 1,
                    "escalation_policy": policy_name,
                    "original_alert_data": alert.data
                },
                timestamp=datetime.utcnow().isoformat()
            )
            
            # Send escalated alert to specified channels
            for channel_name in step.get("channels", []):
                if channel_name in self.channels and self.channels[channel_name].enabled:
                    await self._send_to_channel(escalated_alert, self.channels[channel_name])
            
            if self.logger:
                await self.logger.log(
                    LogLevel.CRITICAL,
                    LogCategory.SYSTEM,
                    f"Alert escalated: {alert.title}",
                    session_id=alert.session_id,
                    data={
                        "original_alert_id": alert.alert_id,
                        "escalation_step": step_index + 1,
                        "policy": policy_name
                    }
                )
            
            logger.warning("Alert escalated", 
                         alert_id=alert.alert_id, 
                         step=step_index + 1, 
                         policy=policy_name)
            
        except Exception as e:
            logger.error("Failed to escalate alert", alert_id=alert.alert_id, error=str(e))

    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                cutoff_time = datetime.utcnow() - timedelta(days=7)  # Keep alerts for 7 days
                
                # Clean up resolved alerts older than cutoff
                alerts_to_remove = []
                for alert_id, alert in self.alerts.items():
                    if alert.resolved:
                        alert_time = datetime.fromisoformat(alert.timestamp)
                        if alert_time < cutoff_time:
                            alerts_to_remove.append(alert_id)
                
                for alert_id in alerts_to_remove:
                    del self.alerts[alert_id]
                
                # Clean up alert history
                self.alert_history = [
                    alert for alert in self.alert_history
                    if datetime.fromisoformat(alert.timestamp) >= cutoff_time
                ]
                
                if alerts_to_remove:
                    logger.info("Cleaned up old alerts", count=len(alerts_to_remove))
                
            except Exception as e:
                logger.error("Alert cleanup error", error=str(e))
                await asyncio.sleep(3600)

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics"""
        return {
            **self.alert_stats,
            "active_alerts": len([a for a in self.alerts.values() if not a.resolved]),
            "acknowledged_alerts": len([a for a in self.alerts.values() if a.acknowledged]),
            "total_alerts_tracked": len(self.alerts),
            "alert_history_size": len(self.alert_history),
            "last_updated": datetime.utcnow().isoformat()
        }

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get list of active (unresolved) alerts"""
        return [
            asdict(alert) for alert in self.alerts.values() 
            if not alert.resolved
        ]

    async def shutdown(self):
        """Shutdown alert manager"""
        logger.info("Shutting down Alert Manager...")
        
        # Cancel background tasks
        if self.escalation_task:
            self.escalation_task.cancel()
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # Final statistics
        if self.logger:
            await self.logger.log(
                LogLevel.INFO,
                LogCategory.SYSTEM,
                "Alert Manager shutdown",
                data=self.get_alert_stats()
            )
        
        logger.info("Alert Manager shutdown complete")

# Global alert manager instance
global_alert_manager: Optional[AlertManager] = None

async def initialize_alert_manager(config_file: str = None) -> AlertManager:
    """Initialize the global alert manager"""
    global global_alert_manager
    global_alert_manager = AlertManager(config_file)
    return global_alert_manager

def get_alert_manager() -> Optional[AlertManager]:
    """Get the global alert manager"""
    return global_alert_manager

# Convenience functions
async def trigger_alert(alert_type: str, severity: str, title: str, message: str, 
                       source_component: str, session_id: str = None, 
                       data: Dict[str, Any] = None) -> str:
    """Trigger alert through global alert manager"""
    if global_alert_manager:
        return await global_alert_manager.trigger_alert(
            alert_type, severity, title, message, source_component, session_id, data
        )
    return None