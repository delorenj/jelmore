#!/usr/bin/env python3
"""
N8N Webhook Session Tracker - Monitor PR Processing Sessions
Advanced tracking of webhook events, session correlation, and failure detection
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
from pathlib import Path
import aiohttp
import structlog
from .log.logger import (
    AdvancedLogger, LogLevel, LogCategory, 
    log_info, log_warning, log_error, log_pipeline_event
)

# Initialize logger
logger = structlog.get_logger("webhook.tracker")

@dataclass
class WebhookEvent:
    """Webhook event structure"""
    event_id: str
    webhook_type: str  # pr_opened, pr_comment, pr_closed, etc.
    session_id: Optional[str]
    repository: str
    pr_number: int
    timestamp: str
    payload: Dict[str, Any]
    source_ip: str
    user_agent: str
    processed: bool = False
    processing_time: Optional[float] = None
    error: Optional[str] = None

@dataclass
class SessionTracker:
    """Track PR processing session"""
    session_id: str
    pr_number: int
    repository: str
    status: str  # pending, processing, completed, failed, timeout
    created_at: str
    last_activity: str
    webhook_events: List[str]  # Event IDs
    processing_steps: List[Dict[str, Any]]
    total_processing_time: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    timeout_warnings: int = 0

class WebhookTracker:
    """Advanced webhook tracking and session correlation system"""
    
    def __init__(self, log_directory: str = "/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log"):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        # Event storage
        self.webhook_events: Dict[str, WebhookEvent] = {}
        self.session_trackers: Dict[str, SessionTracker] = {}
        self.event_queue = deque(maxlen=5000)  # Last 5000 events
        
        # Tracking metrics
        self.metrics = {
            "total_webhooks": 0,
            "active_sessions": 0,
            "completed_sessions": 0,
            "failed_sessions": 0,
            "timeout_sessions": 0,
            "average_processing_time": 0.0,
            "success_rate": 0.0,
            "webhook_types": defaultdict(int),
            "hourly_stats": defaultdict(int)
        }
        
        # Alert thresholds
        self.alert_config = {
            "session_timeout_minutes": 15,
            "processing_timeout_minutes": 10,
            "failure_rate_threshold": 20.0,  # %
            "max_concurrent_sessions": 50,
            "stuck_session_threshold": 30  # minutes
        }
        
        # Pattern detection
        self.failure_patterns: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.performance_anomalies: List[Dict[str, Any]] = []
        
        # Background tasks
        self.cleanup_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self.alert_task: Optional[asyncio.Task] = None
        
        logger.info("🔗 Webhook Tracker initialized",
                   log_directory=str(self.log_directory))

    async def initialize(self, advanced_logger: AdvancedLogger):
        """Initialize webhook tracker with logger"""
        self.logger = advanced_logger
        
        # Start background monitoring tasks
        self.cleanup_task = asyncio.create_task(self._cleanup_old_data())
        self.monitoring_task = asyncio.create_task(self._monitor_sessions())
        self.alert_task = asyncio.create_task(self._alert_monitor())
        
        await log_info("✅ Webhook Tracker fully initialized", LogCategory.WEBHOOK)

    async def track_webhook_event(self, event_data: Dict[str, Any], 
                                 source_ip: str = "unknown",
                                 user_agent: str = "unknown") -> str:
        """Track incoming webhook event"""
        try:
            # Generate event ID
            event_id = f"wh_{int(time.time()*1000)}_{len(self.webhook_events)}"
            
            # Extract webhook information
            webhook_type = event_data.get("action", "unknown")
            repository = event_data.get("repository", {}).get("full_name", "unknown")
            pr_number = event_data.get("number", 0)
            
            # Try to correlate with existing session or create new one
            session_id = await self._correlate_session(event_data, webhook_type, repository, pr_number)
            
            # Create webhook event
            webhook_event = WebhookEvent(
                event_id=event_id,
                webhook_type=webhook_type,
                session_id=session_id,
                repository=repository,
                pr_number=pr_number,
                timestamp=datetime.utcnow().isoformat(),
                payload=event_data,
                source_ip=source_ip,
                user_agent=user_agent
            )
            
            # Store event
            self.webhook_events[event_id] = webhook_event
            self.event_queue.append(webhook_event)
            
            # Update metrics
            self.metrics["total_webhooks"] += 1
            self.metrics["webhook_types"][webhook_type] += 1
            hour_key = datetime.utcnow().strftime("%Y-%m-%d-%H")
            self.metrics["hourly_stats"][hour_key] += 1
            
            # Update session tracker
            if session_id:
                await self._update_session_tracker(session_id, event_id, webhook_type)
            
            # Log the event
            await self.logger.log(
                LogLevel.INFO,
                LogCategory.WEBHOOK,
                f"Webhook received: {webhook_type}",
                session_id=session_id,
                component="webhook_tracker",
                data={
                    "event_id": event_id,
                    "repository": repository,
                    "pr_number": pr_number,
                    "webhook_type": webhook_type
                }
            )
            
            # Detect patterns
            await self._detect_webhook_patterns(webhook_event)
            
            return event_id
            
        except Exception as e:
            await log_error("Failed to track webhook event", 
                           LogCategory.WEBHOOK, error=e,
                           data={"event_data": event_data})
            raise

    async def _correlate_session(self, event_data: Dict[str, Any], 
                               webhook_type: str, repository: str, 
                               pr_number: int) -> Optional[str]:
        """Correlate webhook with existing session or create new one"""
        try:
            # Look for existing session for this PR
            existing_session = None
            for session_id, tracker in self.session_trackers.items():
                if (tracker.repository == repository and 
                    tracker.pr_number == pr_number and 
                    tracker.status in ["pending", "processing"]):
                    existing_session = session_id
                    break
            
            # Create new session for PR events that start processing
            if not existing_session and webhook_type in ["opened", "synchronize", "reopened"]:
                session_id = f"pr_{repository.replace('/', '_')}_{pr_number}_{int(time.time())}"
                
                session_tracker = SessionTracker(
                    session_id=session_id,
                    pr_number=pr_number,
                    repository=repository,
                    status="pending",
                    created_at=datetime.utcnow().isoformat(),
                    last_activity=datetime.utcnow().isoformat(),
                    webhook_events=[],
                    processing_steps=[]
                )
                
                self.session_trackers[session_id] = session_tracker
                self.metrics["active_sessions"] += 1
                
                await log_pipeline_event(
                    "session_created",
                    session_id,
                    {
                        "repository": repository,
                        "pr_number": pr_number,
                        "trigger": webhook_type
                    }
                )
                
                return session_id
            
            return existing_session
            
        except Exception as e:
            await log_error("Session correlation failed", 
                           LogCategory.WEBHOOK, error=e)
            return None

    async def _update_session_tracker(self, session_id: str, event_id: str, webhook_type: str):
        """Update session tracker with new event"""
        try:
            if session_id not in self.session_trackers:
                return
            
            tracker = self.session_trackers[session_id]
            tracker.webhook_events.append(event_id)
            tracker.last_activity = datetime.utcnow().isoformat()
            
            # Update status based on webhook type
            if webhook_type in ["opened", "synchronize", "reopened"]:
                tracker.status = "processing"
            elif webhook_type in ["closed", "merged"]:
                tracker.status = "completed"
                await self._complete_session(session_id)
            
            # Add processing step
            processing_step = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": webhook_type,
                "event_id": event_id
            }
            tracker.processing_steps.append(processing_step)
            
        except Exception as e:
            await log_error("Failed to update session tracker", 
                           LogCategory.SESSION, error=e,
                           session_id=session_id)

    async def _complete_session(self, session_id: str):
        """Mark session as completed"""
        try:
            if session_id not in self.session_trackers:
                return
            
            tracker = self.session_trackers[session_id]
            
            # Calculate total processing time
            created_time = datetime.fromisoformat(tracker.created_at)
            completed_time = datetime.utcnow()
            processing_time = (completed_time - created_time).total_seconds()
            
            tracker.total_processing_time = processing_time
            tracker.status = "completed"
            
            # Update metrics
            self.metrics["active_sessions"] -= 1
            self.metrics["completed_sessions"] += 1
            
            # Update average processing time
            total_completed = self.metrics["completed_sessions"]
            current_avg = self.metrics["average_processing_time"]
            self.metrics["average_processing_time"] = (
                (current_avg * (total_completed - 1) + processing_time) / total_completed
            )
            
            # Calculate success rate
            total_sessions = (self.metrics["completed_sessions"] + 
                            self.metrics["failed_sessions"] + 
                            self.metrics["timeout_sessions"])
            if total_sessions > 0:
                success_rate = (self.metrics["completed_sessions"] / total_sessions) * 100
                self.metrics["success_rate"] = success_rate
            
            await log_pipeline_event(
                "session_completed",
                session_id,
                {
                    "processing_time": processing_time,
                    "steps": len(tracker.processing_steps),
                    "events": len(tracker.webhook_events)
                }
            )
            
        except Exception as e:
            await log_error("Failed to complete session", 
                           LogCategory.SESSION, error=e,
                           session_id=session_id)

    async def mark_session_failed(self, session_id: str, error_message: str):
        """Mark session as failed"""
        try:
            if session_id not in self.session_trackers:
                return
            
            tracker = self.session_trackers[session_id]
            tracker.status = "failed"
            tracker.failure_count += 1
            
            # Update metrics
            if tracker.status != "failed":  # Only update if not already failed
                self.metrics["active_sessions"] -= 1
                self.metrics["failed_sessions"] += 1
            
            # Record failure pattern
            failure_pattern = {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id,
                "error": error_message,
                "repository": tracker.repository,
                "pr_number": tracker.pr_number,
                "processing_steps": len(tracker.processing_steps)
            }
            self.failure_patterns[error_message].append(failure_pattern)
            
            await log_pipeline_event(
                "session_failed",
                session_id,
                {
                    "error": error_message,
                    "steps_completed": len(tracker.processing_steps),
                    "events_processed": len(tracker.webhook_events)
                }
            )
            
        except Exception as e:
            await log_error("Failed to mark session as failed", 
                           LogCategory.SESSION, error=e,
                           session_id=session_id)

    async def _detect_webhook_patterns(self, webhook_event: WebhookEvent):
        """Detect patterns in webhook events for anomaly detection"""
        try:
            current_time = datetime.utcnow()
            
            # Check for rapid-fire webhooks (potential spam or loops)
            recent_events = [
                e for e in list(self.event_queue)[-20:]  # Last 20 events
                if e.repository == webhook_event.repository and
                   e.pr_number == webhook_event.pr_number
            ]
            
            if len(recent_events) > 10:  # More than 10 events for same PR recently
                await log_warning(
                    "Rapid webhook activity detected",
                    LogCategory.WEBHOOK,
                    session_id=webhook_event.session_id,
                    data={
                        "repository": webhook_event.repository,
                        "pr_number": webhook_event.pr_number,
                        "event_count": len(recent_events)
                    }
                )
            
            # Check for unusual webhook types
            unusual_types = ["deleted", "locked", "unlocked", "converted_to_draft"]
            if webhook_event.webhook_type in unusual_types:
                await log_info(
                    f"Unusual webhook type: {webhook_event.webhook_type}",
                    LogCategory.WEBHOOK,
                    session_id=webhook_event.session_id,
                    data={
                        "repository": webhook_event.repository,
                        "pr_number": webhook_event.pr_number
                    }
                )
                
        except Exception as e:
            await log_error("Pattern detection failed", 
                           LogCategory.WEBHOOK, error=e)

    async def _monitor_sessions(self):
        """Background task to monitor session health"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                current_time = datetime.utcnow()
                
                stuck_sessions = []
                timeout_sessions = []
                
                for session_id, tracker in self.session_trackers.items():
                    if tracker.status in ["pending", "processing"]:
                        last_activity = datetime.fromisoformat(tracker.last_activity)
                        time_since_activity = current_time - last_activity
                        
                        # Check for stuck sessions
                        if time_since_activity > timedelta(minutes=self.alert_config["stuck_session_threshold"]):
                            stuck_sessions.append((session_id, tracker))
                        
                        # Check for timeouts
                        elif time_since_activity > timedelta(minutes=self.alert_config["session_timeout_minutes"]):
                            timeout_sessions.append((session_id, tracker))
                
                # Handle stuck sessions
                for session_id, tracker in stuck_sessions:
                    await self._handle_stuck_session(session_id, tracker)
                
                # Handle timeout sessions
                for session_id, tracker in timeout_sessions:
                    await self._handle_timeout_session(session_id, tracker)
                
            except Exception as e:
                await log_error("Session monitoring error", 
                               LogCategory.SYSTEM, error=e)

    async def _handle_stuck_session(self, session_id: str, tracker: SessionTracker):
        """Handle sessions that appear to be stuck"""
        try:
            tracker.status = "timeout"
            tracker.timeout_warnings += 1
            
            # Update metrics
            self.metrics["active_sessions"] -= 1
            self.metrics["timeout_sessions"] += 1
            
            await log_warning(
                "Session appears stuck - marking as timeout",
                LogCategory.SESSION,
                session_id=session_id,
                data={
                    "repository": tracker.repository,
                    "pr_number": tracker.pr_number,
                    "stuck_minutes": self.alert_config["stuck_session_threshold"]
                }
            )
            
        except Exception as e:
            await log_error("Failed to handle stuck session", 
                           LogCategory.SESSION, error=e,
                           session_id=session_id)

    async def _handle_timeout_session(self, session_id: str, tracker: SessionTracker):
        """Handle sessions that have timed out"""
        try:
            tracker.timeout_warnings += 1
            
            await log_warning(
                "Session timeout warning",
                LogCategory.SESSION,
                session_id=session_id,
                data={
                    "repository": tracker.repository,
                    "pr_number": tracker.pr_number,
                    "timeout_minutes": self.alert_config["session_timeout_minutes"],
                    "warning_count": tracker.timeout_warnings
                }
            )
            
        except Exception as e:
            await log_error("Failed to handle timeout session", 
                           LogCategory.SESSION, error=e,
                           session_id=session_id)

    async def _alert_monitor(self):
        """Monitor for alert conditions"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                # Check failure rate
                total_sessions = (self.metrics["completed_sessions"] + 
                                self.metrics["failed_sessions"] + 
                                self.metrics["timeout_sessions"])
                
                if total_sessions > 10:  # Only alert if we have enough data
                    failure_rate = ((self.metrics["failed_sessions"] + 
                                   self.metrics["timeout_sessions"]) / total_sessions) * 100
                    
                    if failure_rate > self.alert_config["failure_rate_threshold"]:
                        await log_error(
                            f"High failure rate detected: {failure_rate:.1f}%",
                            LogCategory.SYSTEM,
                            data={
                                "failure_rate": failure_rate,
                                "threshold": self.alert_config["failure_rate_threshold"],
                                "failed_sessions": self.metrics["failed_sessions"],
                                "timeout_sessions": self.metrics["timeout_sessions"],
                                "total_sessions": total_sessions
                            }
                        )
                
                # Check for too many concurrent sessions
                if self.metrics["active_sessions"] > self.alert_config["max_concurrent_sessions"]:
                    await log_warning(
                        "High concurrent session count",
                        LogCategory.SYSTEM,
                        data={
                            "active_sessions": self.metrics["active_sessions"],
                            "threshold": self.alert_config["max_concurrent_sessions"]
                        }
                    )
                
            except Exception as e:
                await log_error("Alert monitoring error", 
                               LogCategory.SYSTEM, error=e)

    async def _cleanup_old_data(self):
        """Background task to clean up old data"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                cleanup_time = datetime.utcnow() - timedelta(hours=24)
                
                # Clean up old webhook events
                events_to_remove = []
                for event_id, event in self.webhook_events.items():
                    event_time = datetime.fromisoformat(event.timestamp)
                    if event_time < cleanup_time:
                        events_to_remove.append(event_id)
                
                for event_id in events_to_remove:
                    del self.webhook_events[event_id]
                
                # Clean up completed sessions older than 24 hours
                sessions_to_remove = []
                for session_id, tracker in self.session_trackers.items():
                    if tracker.status in ["completed", "failed", "timeout"]:
                        created_time = datetime.fromisoformat(tracker.created_at)
                        if created_time < cleanup_time:
                            sessions_to_remove.append(session_id)
                
                for session_id in sessions_to_remove:
                    del self.session_trackers[session_id]
                
                # Clean up old failure patterns
                for error_type, patterns in self.failure_patterns.items():
                    self.failure_patterns[error_type] = [
                        p for p in patterns 
                        if datetime.fromisoformat(p["timestamp"]) >= cleanup_time
                    ]
                
                if events_to_remove or sessions_to_remove:
                    await log_info(
                        "Cleaned up old tracking data",
                        LogCategory.SYSTEM,
                        data={
                            "events_removed": len(events_to_remove),
                            "sessions_removed": len(sessions_to_remove)
                        }
                    )
                
            except Exception as e:
                await log_error("Cleanup task error", 
                               LogCategory.SYSTEM, error=e)

    def get_tracking_stats(self) -> Dict[str, Any]:
        """Get comprehensive tracking statistics"""
        return {
            "metrics": self.metrics,
            "active_session_count": len([
                s for s in self.session_trackers.values() 
                if s.status in ["pending", "processing"]
            ]),
            "recent_events": [
                asdict(e) for e in list(self.event_queue)[-10:]
            ],
            "failure_patterns": {
                error_type: len(patterns)
                for error_type, patterns in self.failure_patterns.items()
            },
            "alert_config": self.alert_config,
            "last_updated": datetime.utcnow().isoformat()
        }

    def get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific session"""
        if session_id not in self.session_trackers:
            return None
        
        tracker = self.session_trackers[session_id]
        
        # Get associated webhook events
        associated_events = [
            asdict(self.webhook_events[event_id])
            for event_id in tracker.webhook_events
            if event_id in self.webhook_events
        ]
        
        return {
            "session": asdict(tracker),
            "webhook_events": associated_events,
            "event_count": len(associated_events),
            "status_history": tracker.processing_steps
        }

    async def shutdown(self):
        """Gracefully shutdown the tracker"""
        await log_info("Shutting down Webhook Tracker", LogCategory.WEBHOOK)
        
        # Cancel background tasks
        if self.cleanup_task:
            self.cleanup_task.cancel()
        if self.monitoring_task:
            self.monitoring_task.cancel()
        if self.alert_task:
            self.alert_task.cancel()
        
        # Save final statistics
        final_stats = self.get_tracking_stats()
        stats_file = self.log_directory / "final_webhook_stats.json"
        
        try:
            with open(stats_file, 'w') as f:
                json.dump(final_stats, f, indent=2, default=str)
        except Exception as e:
            await log_error("Failed to save final stats", 
                           LogCategory.SYSTEM, error=e)
        
        await log_info("Webhook Tracker shutdown complete", LogCategory.WEBHOOK)