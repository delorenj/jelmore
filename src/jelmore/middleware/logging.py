"""Standardized logging middleware for Jelmore

This module provides:
- Structured logging with structlog
- Request correlation IDs
- Performance tracking
- Security event logging
- Centralized log configuration
"""

import time
import uuid
from typing import Dict, Any, Optional
from contextvars import ContextVar

from fastapi import Request, Response
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from jelmore.config import get_settings


# Context variable for correlation ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


def setup_logging():
    """Configure structured logging with correlation IDs and performance tracking
    
    This should be called once at application startup.
    """
    settings = get_settings()
    
    # Configure structlog
    structlog.configure(
        processors=[
            # Add correlation ID to all log entries
            structlog.contextvars.merge_contextvars,
            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),
            # Add log level
            structlog.processors.add_log_level,
            # Add logger name
            structlog.processors.add_logger_name,
            # Stack info processor (for exceptions)
            structlog.processors.StackInfoRenderer(),
            # Format exceptions
            structlog.dev.set_exc_info,
            # JSON formatter for production, console for development
            structlog.processors.JSONRenderer() if settings.log_format == "json" 
            else structlog.dev.ConsoleRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog._config, settings.log_level.upper(), structlog.INFO)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Get root logger and configure it
    logger = structlog.get_logger("jelmore")
    logger.info("Structured logging configured",
               log_level=settings.log_level,
               log_format=settings.log_format)


async def request_logging_middleware(request: Request, call_next):
    """Request logging middleware with correlation ID and performance tracking
    
    Features:
    - Generates correlation ID for each request
    - Logs request start/end with performance metrics
    - Handles exceptions and errors
    - Security event logging
    """
    # Generate correlation ID
    correlation_id = request.headers.get('X-Correlation-ID', str(uuid.uuid4()))
    correlation_id_var.set(correlation_id)
    
    # Bind correlation ID to structlog context
    bind_contextvars(
        correlation_id=correlation_id,
        request_id=correlation_id,  # Alternative name
    )
    
    logger = structlog.get_logger("jelmore.requests")
    
    # Extract client information
    client_ip = None
    if request.client:
        client_ip = request.client.host
    
    # Check for forwarded headers (reverse proxy)
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        client_ip = forwarded_for.split(',')[0].strip()
        
    # Log request start
    start_time = time.time()
    
    logger.info("Request started",
               method=request.method,
               path=request.url.path,
               query_params=str(request.query_params) if request.query_params else None,
               client_ip=client_ip,
               user_agent=request.headers.get('User-Agent'),
               content_type=request.headers.get('Content-Type'))
    
    # Track authentication events
    auth_header = request.headers.get('X-API-Key') or request.headers.get('Authorization')
    if auth_header:
        logger.debug("Authentication header present",
                    auth_type="api_key" if request.headers.get('X-API-Key') else "bearer")
    
    try:
        # Process request
        response = await call_next(request)
        
        # Calculate request duration
        duration = time.time() - start_time
        
        # Log request completion
        logger.info("Request completed",
                   method=request.method,
                   path=request.url.path,
                   status_code=response.status_code,
                   duration_ms=round(duration * 1000, 2),
                   client_ip=client_ip)
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        # Log slow requests as warnings
        if duration > 5.0:  # 5 seconds
            logger.warning("Slow request detected",
                          duration_ms=round(duration * 1000, 2),
                          path=request.url.path)
        
        return response
        
    except Exception as e:
        # Calculate request duration
        duration = time.time() - start_time
        
        # Log request error
        logger.error("Request failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round(duration * 1000, 2),
                    error=str(e),
                    error_type=type(e).__name__,
                    client_ip=client_ip)
        
        # Re-raise exception to let FastAPI handle it
        raise
        
    finally:
        # Clear context variables
        clear_contextvars()


def log_security_event(event_type: str, details: Dict[str, Any], severity: str = "warning"):
    """Log security events with standardized format
    
    Args:
        event_type: Type of security event (auth_failure, suspicious_activity, etc.)
        details: Event details dictionary
        severity: Log severity (info, warning, error, critical)
    """
    logger = structlog.get_logger("jelmore.security")
    
    log_data = {
        "event_type": event_type,
        "severity": severity,
        **details
    }
    
    # Log at appropriate level
    if severity == "critical":
        logger.critical("Security event", **log_data)
    elif severity == "error":
        logger.error("Security event", **log_data)
    elif severity == "warning":
        logger.warning("Security event", **log_data)
    else:
        logger.info("Security event", **log_data)


def log_performance_metric(metric_name: str, value: float, unit: str = "ms", **tags):
    """Log performance metrics for monitoring
    
    Args:
        metric_name: Name of the metric
        value: Metric value
        unit: Unit of measurement
        **tags: Additional tags for the metric
    """
    logger = structlog.get_logger("jelmore.metrics")
    
    logger.info("Performance metric",
               metric_name=metric_name,
               value=value,
               unit=unit,
               **tags)


def log_business_event(event_name: str, details: Dict[str, Any]):
    """Log business events for analytics
    
    Args:
        event_name: Name of the business event
        details: Event details
    """
    logger = structlog.get_logger("jelmore.events")
    
    logger.info("Business event",
               event_name=event_name,
               **details)


def get_correlation_id() -> Optional[str]:
    """Get current request correlation ID"""
    return correlation_id_var.get()


def get_request_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """Get a logger bound with current request context
    
    Args:
        name: Optional logger name suffix
        
    Returns:
        Bound logger with request context
    """
    logger_name = "jelmore"
    if name:
        logger_name = f"jelmore.{name}"
        
    return structlog.get_logger(logger_name)


# Health check logging (minimal)
async def health_check_middleware(request: Request, call_next):
    """Lightweight middleware for health check endpoints
    
    This provides minimal logging for health checks to avoid log spam.
    """
    if request.url.path in ['/health', '/metrics']:
        # Process without logging
        response = await call_next(request)
        return response
    else:
        # Use full logging middleware
        return await request_logging_middleware(request, call_next)


# Development logging helpers
def log_debug_info(message: str, **kwargs):
    """Log debug information (only in development)"""
    settings = get_settings()
    if settings.log_level == "DEBUG":
        logger = get_request_logger("debug")
        logger.debug(message, **kwargs)


def log_redis_operation(operation: str, key: str, success: bool, **kwargs):
    """Log Redis operations for debugging"""
    logger = get_request_logger("redis")
    
    if success:
        logger.debug("Redis operation succeeded",
                    operation=operation,
                    key=key,
                    **kwargs)
    else:
        logger.warning("Redis operation failed",
                      operation=operation,
                      key=key,
                      **kwargs)