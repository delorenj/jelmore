#!/usr/bin/env python3
"""
Comprehensive Logging System for Jelmore Pipeline
Advanced logging with structured output, filtering, and real-time monitoring
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, TextIO
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
import aiofiles
from contextlib import asynccontextmanager
import gzip
import traceback

class LogLevel(Enum):
    """Log severity levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class LogCategory(Enum):
    """Log categories for filtering"""
    PIPELINE = "pipeline"
    SESSION = "session"
    WEBHOOK = "webhook"
    API = "api"
    NATS = "nats"
    SYSTEM = "system"
    PERFORMANCE = "performance"
    SECURITY = "security"

@dataclass
class LogEntry:
    """Structured log entry"""
    timestamp: str
    level: str
    category: str
    message: str
    session_id: Optional[str] = None
    component: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stack_trace: Optional[str] = None
    request_id: Optional[str] = None
    user_id: Optional[str] = None

class AdvancedLogger:
    """Advanced logging system with structured output and real-time monitoring"""
    
    def __init__(self, log_directory: Path):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
        
        # Log files for different categories
        self.log_files = {
            LogCategory.PIPELINE: self.log_directory / "pipeline.log",
            LogCategory.SESSION: self.log_directory / "sessions.log", 
            LogCategory.WEBHOOK: self.log_directory / "webhooks.log",
            LogCategory.API: self.log_directory / "api.log",
            LogCategory.NATS: self.log_directory / "nats.log",
            LogCategory.SYSTEM: self.log_directory / "system.log",
            LogCategory.PERFORMANCE: self.log_directory / "performance.log",
            LogCategory.SECURITY: self.log_directory / "security.log"
        }
        
        # Real-time log buffer
        self.log_buffer: List[LogEntry] = []
        self.max_buffer_size = 1000
        
        # File handles for async writing
        self.file_handles: Dict[LogCategory, TextIO] = {}
        
        # Statistics
        self.log_stats = {
            "total_logs": 0,
            "error_count": 0,
            "warning_count": 0,
            "session_logs": 0,
            "webhook_logs": 0
        }
        
        # Background tasks
        self.log_writer_task: Optional[asyncio.Task] = None
        self.log_rotator_task: Optional[asyncio.Task] = None
        
        # Initialize structured logger
        self.logger = structlog.get_logger("jelmore.monitor")
        
        self.logger.info("🗒️ Advanced Logger initialized", 
                        log_directory=str(self.log_directory))

    async def initialize(self):
        """Initialize async components"""
        try:
            # Create all log files if they don't exist
            for category, file_path in self.log_files.items():
                file_path.touch(exist_ok=True)
            
            # Start background tasks
            self.log_writer_task = asyncio.create_task(self._background_log_writer())
            self.log_rotator_task = asyncio.create_task(self._log_rotator())
            
            self.logger.info("✅ Advanced Logger fully initialized")
            
        except Exception as e:
            self.logger.error("❌ Failed to initialize Advanced Logger", error=str(e))
            raise

    async def log(self, level: LogLevel, category: LogCategory, message: str, 
                 session_id: str = None, component: str = None, 
                 data: Dict[str, Any] = None, error: Exception = None,
                 request_id: str = None, user_id: str = None):
        """Log a structured entry"""
        try:
            entry = LogEntry(
                timestamp=datetime.utcnow().isoformat(),
                level=level.value,
                category=category.value,
                message=message,
                session_id=session_id,
                component=component,
                data=data or {},
                error=str(error) if error else None,
                stack_trace=traceback.format_exc() if error else None,
                request_id=request_id,
                user_id=user_id
            )
            
            # Add to buffer for real-time monitoring
            self.log_buffer.append(entry)
            if len(self.log_buffer) > self.max_buffer_size:
                self.log_buffer.pop(0)
            
            # Update statistics
            self.log_stats["total_logs"] += 1
            if level == LogLevel.ERROR or level == LogLevel.CRITICAL:
                self.log_stats["error_count"] += 1
            elif level == LogLevel.WARNING:
                self.log_stats["warning_count"] += 1
                
            if category == LogCategory.SESSION:
                self.log_stats["session_logs"] += 1
            elif category == LogCategory.WEBHOOK:
                self.log_stats["webhook_logs"] += 1
                
            # Write to appropriate log file asynchronously
            await self._write_log_entry(entry, category)
            
            # Also log to structlog for console output
            log_func = getattr(self.logger, level.value.lower())
            log_func(message, 
                    category=category.value,
                    session_id=session_id,
                    component=component,
                    data=data)
            
        except Exception as e:
            # Fallback logging - don't let logging failures break the system
            print(f"LOGGING ERROR: {str(e)}")

    async def _write_log_entry(self, entry: LogEntry, category: LogCategory):
        """Write log entry to appropriate file"""
        try:
            log_file = self.log_files[category]
            
            # Create JSON log line
            log_line = json.dumps(asdict(entry), default=str, separators=(',', ':'))
            
            # Append to file asynchronously
            async with aiofiles.open(log_file, 'a') as f:
                await f.write(log_line + '\n')
                
        except Exception as e:
            print(f"FILE WRITE ERROR: {str(e)}")

    async def _background_log_writer(self):
        """Background task for efficient log writing"""
        while True:
            try:
                # Flush any pending writes and sync files
                for category in LogCategory:
                    log_file = self.log_files[category]
                    if log_file.exists() and log_file.stat().st_size > 0:
                        # Force sync to disk
                        async with aiofiles.open(log_file, 'r+') as f:
                            await f.fsync()
                
                await asyncio.sleep(5)  # Sync every 5 seconds
                
            except Exception as e:
                print(f"BACKGROUND WRITER ERROR: {str(e)}")
                await asyncio.sleep(10)

    async def _log_rotator(self):
        """Background task for log rotation"""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                
                # Rotate logs if they're too large (>10MB)
                for category, log_file in self.log_files.items():
                    if log_file.exists():
                        file_size = log_file.stat().st_size
                        if file_size > 10 * 1024 * 1024:  # 10MB
                            await self._rotate_log_file(log_file, category)
                            
            except Exception as e:
                print(f"LOG ROTATOR ERROR: {str(e)}")

    async def _rotate_log_file(self, log_file: Path, category: LogCategory):
        """Rotate a log file when it gets too large"""
        try:
            # Create archived filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archived_name = f"{log_file.stem}_{timestamp}.log.gz"
            archived_path = log_file.parent / "archived" / archived_name
            
            # Create archived directory if it doesn't exist
            archived_path.parent.mkdir(exist_ok=True)
            
            # Compress and move the file
            async with aiofiles.open(log_file, 'rb') as f_in:
                content = await f_in.read()
                
            with gzip.open(archived_path, 'wb') as f_out:
                f_out.write(content)
            
            # Clear the original file
            async with aiofiles.open(log_file, 'w') as f:
                await f.write('')
            
            self.logger.info("📦 Log file rotated", 
                           category=category.value,
                           archived_path=str(archived_path))
                           
        except Exception as e:
            self.logger.error("❌ Log rotation failed", 
                            category=category.value, 
                            error=str(e))

    def get_recent_logs(self, category: LogCategory = None, 
                       level: LogLevel = None, 
                       session_id: str = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent logs with filtering"""
        filtered_logs = []
        
        for entry in reversed(self.log_buffer):
            # Apply filters
            if category and entry.category != category.value:
                continue
            if level and entry.level != level.value:
                continue
            if session_id and entry.session_id != session_id:
                continue
                
            filtered_logs.append(asdict(entry))
            
            if len(filtered_logs) >= limit:
                break
        
        return filtered_logs

    async def search_logs(self, query: str, category: LogCategory = None, 
                         start_time: datetime = None, end_time: datetime = None,
                         limit: int = 500) -> List[Dict[str, Any]]:
        """Search through log files"""
        results = []
        
        try:
            # Determine which files to search
            files_to_search = []
            if category:
                files_to_search = [self.log_files[category]]
            else:
                files_to_search = list(self.log_files.values())
            
            for log_file in files_to_search:
                if not log_file.exists():
                    continue
                    
                async with aiofiles.open(log_file, 'r') as f:
                    async for line in f:
                        try:
                            entry = json.loads(line.strip())
                            
                            # Time filtering
                            if start_time or end_time:
                                entry_time = datetime.fromisoformat(entry['timestamp'])
                                if start_time and entry_time < start_time:
                                    continue
                                if end_time and entry_time > end_time:
                                    continue
                            
                            # Text search
                            if query.lower() in json.dumps(entry).lower():
                                results.append(entry)
                                
                            if len(results) >= limit:
                                break
                                
                        except json.JSONDecodeError:
                            continue
                
                if len(results) >= limit:
                    break
            
            return results
            
        except Exception as e:
            self.logger.error("❌ Log search failed", query=query, error=str(e))
            return []

    def get_log_stats(self) -> Dict[str, Any]:
        """Get logging statistics"""
        return {
            **self.log_stats,
            "buffer_size": len(self.log_buffer),
            "log_files": {
                category.value: {
                    "path": str(log_file),
                    "size": log_file.stat().st_size if log_file.exists() else 0,
                    "exists": log_file.exists()
                }
                for category, log_file in self.log_files.items()
            },
            "last_updated": datetime.utcnow().isoformat()
        }

    async def export_logs(self, category: LogCategory = None, 
                         start_time: datetime = None, 
                         end_time: datetime = None,
                         format: str = "json") -> str:
        """Export logs to different formats"""
        try:
            logs = await self.search_logs(
                query="", 
                category=category,
                start_time=start_time,
                end_time=end_time,
                limit=10000
            )
            
            if format == "json":
                return json.dumps(logs, indent=2, default=str)
            elif format == "csv":
                if not logs:
                    return "No logs found"
                    
                import csv
                import io
                
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
                return output.getvalue()
            else:
                return "Unsupported format"
                
        except Exception as e:
            self.logger.error("❌ Log export failed", error=str(e))
            return f"Export failed: {str(e)}"

    async def shutdown(self):
        """Gracefully shutdown the logger"""
        self.logger.info("🔄 Shutting down Advanced Logger...")
        
        # Cancel background tasks
        if self.log_writer_task:
            self.log_writer_task.cancel()
        if self.log_rotator_task:
            self.log_rotator_task.cancel()
        
        # Final flush of all files
        for category in LogCategory:
            log_file = self.log_files[category]
            if log_file.exists():
                async with aiofiles.open(log_file, 'a') as f:
                    await f.fsync()
        
        self.logger.info("✅ Advanced Logger shutdown complete")

# Global logger instance
global_logger: Optional[AdvancedLogger] = None

def get_logger() -> AdvancedLogger:
    """Get the global logger instance"""
    return global_logger

async def initialize_logger(log_directory: str = "/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log"):
    """Initialize the global logger"""
    global global_logger
    global_logger = AdvancedLogger(Path(log_directory))
    await global_logger.initialize()
    return global_logger

# Convenience functions
async def log_info(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log info message"""
    if global_logger:
        await global_logger.log(LogLevel.INFO, category, message, **kwargs)

async def log_warning(message: str, category: LogCategory = LogCategory.SYSTEM, **kwargs):
    """Log warning message"""
    if global_logger:
        await global_logger.log(LogLevel.WARNING, category, message, **kwargs)

async def log_error(message: str, category: LogCategory = LogCategory.SYSTEM, 
                   error: Exception = None, **kwargs):
    """Log error message"""
    if global_logger:
        await global_logger.log(LogLevel.ERROR, category, message, error=error, **kwargs)

async def log_pipeline_event(event_type: str, session_id: str, data: Dict[str, Any] = None):
    """Log pipeline-specific events"""
    if global_logger:
        await global_logger.log(
            LogLevel.INFO, 
            LogCategory.PIPELINE,
            f"Pipeline event: {event_type}",
            session_id=session_id,
            data=data
        )