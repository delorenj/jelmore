"""Parallel Infrastructure Initialization Utilities

This module implements the "Infrastructure Parallelization Protocol" - a revolutionary approach
to startup optimization that would make even the most hardened DevOps consultant weep tears
of pure efficiency.

Features:
- Parallel service initialization with asyncio.gather()
- Exponential backoff retry logic
- Circuit breaker patterns for resilient startup
- Performance timing and metrics
- Connection pooling optimizations
- Health check coordination

WARNING: This module contains advanced infrastructure patterns that may cause
spontaneous optimization of your entire tech stack. Side effects may include:
- Dramatically reduced startup times
- Increased developer happiness  
- Uncontrollable urge to parallelize everything
- Sudden understanding of asyncio gather patterns
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Callable, Tuple
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum

import structlog


logger = structlog.get_logger("jelmore.parallel_init")


class ServiceStatus(Enum):
    """Service initialization status"""
    PENDING = "pending"
    CONNECTING = "connecting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class ServiceResult:
    """Result of service initialization"""
    name: str
    status: ServiceStatus
    startup_time: float
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class StartupMetrics:
    """Startup performance metrics"""
    total_startup_time: float
    parallel_init_time: float
    service_results: List[ServiceResult]
    services_healthy: int
    services_failed: int
    
    @property
    def success_rate(self) -> float:
        """Calculate service initialization success rate"""
        total = len(self.service_results)
        return (self.services_healthy / total * 100) if total > 0 else 0.0


class ConnectionPool:
    """Optimized connection pool manager"""
    
    def __init__(self, pool_size: int = 20, max_overflow: int = 40):
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.connections = {}
        
    async def get_connection_config(self, service: str) -> Dict[str, Any]:
        """Get optimized connection configuration for service"""
        configs = {
            "postgresql": {
                "pool_size": self.pool_size,
                "max_overflow": self.max_overflow,
                "pool_pre_ping": True,
                "pool_recycle": 3600,  # 1 hour
                "connect_args": {
                    "connect_timeout": 10,
                    "server_settings": {
                        "application_name": "jelmore-api"
                    }
                }
            },
            "redis": {
                "max_connections": 50,
                "retry_on_timeout": True,
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
                "health_check_interval": 30
            },
            "nats": {
                "connect_timeout": 10,
                "max_reconnect_attempts": 5,
                "reconnect_time_wait": 2,
                "ping_interval": 120,
                "max_outstanding_pings": 2
            }
        }
        return configs.get(service, {})


class RetryManager:
    """Exponential backoff retry manager"""
    
    def __init__(self, 
                 max_retries: int = 5,
                 base_delay: float = 1.0,
                 max_delay: float = 30.0,
                 backoff_factor: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
    
    async def retry_with_backoff(self, 
                                func: Callable,
                                service_name: str,
                                *args, 
                                **kwargs) -> Tuple[bool, Any, Optional[str]]:
        """Retry function with exponential backoff"""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = await func(*args, **kwargs)
                if attempt > 0:
                    logger.info("Service connection successful after retries",
                               service=service_name,
                               attempt=attempt + 1,
                               total_attempts=self.max_retries + 1)
                return True, result, None
                
            except Exception as e:
                last_error = str(e)
                logger.warning("Service connection attempt failed",
                              service=service_name,
                              attempt=attempt + 1,
                              total_attempts=self.max_retries + 1,
                              error=last_error)
                
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (self.backoff_factor ** attempt),
                        self.max_delay
                    )
                    logger.info("Retrying service connection",
                               service=service_name,
                               delay_seconds=delay,
                               next_attempt=attempt + 2)
                    await asyncio.sleep(delay)
        
        return False, None, last_error


class CircuitBreaker:
    """Circuit breaker for service initialization"""
    
    def __init__(self, 
                 failure_threshold: int = 3,
                 timeout: float = 60.0,
                 expected_exception: type = Exception):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func: Callable, *args, **kwargs):
        """Call function through circuit breaker"""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception(f"Circuit breaker OPEN - service unavailable")
        
        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failure_count = 0
                logger.info("Circuit breaker reset to CLOSED")
            return result
            
        except self.expected_exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error("Circuit breaker opened due to failures",
                            failure_count=self.failure_count,
                            threshold=self.failure_threshold)
            raise e


class ParallelInitializer:
    """The crown jewel of infrastructure parallelization!
    
    This class orchestrates the parallel initialization of all services
    with the precision of a Swiss watch and the speed of a caffeinated
    DevOps engineer deploying on a Friday afternoon.
    """
    
    def __init__(self):
        self.retry_manager = RetryManager()
        self.connection_pool = ConnectionPool()
        self.circuit_breakers = {}
        self.startup_start_time = None
        
    def get_circuit_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for service"""
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        return self.circuit_breakers[service_name]
    
    async def initialize_service(self, 
                                service_name: str,
                                init_func: Callable,
                                *args,
                                **kwargs) -> ServiceResult:
        """Initialize a single service with full error handling"""
        start_time = time.time()
        logger.info("Initializing service", service=service_name)
        
        try:
            # Get circuit breaker for this service
            circuit_breaker = self.get_circuit_breaker(service_name)
            
            # Wrap initialization with retry logic
            async def init_with_retry():
                return await circuit_breaker.call(init_func, *args, **kwargs)
            
            # Execute with exponential backoff
            success, result, error = await self.retry_manager.retry_with_backoff(
                init_with_retry,
                service_name
            )
            
            startup_time = time.time() - start_time
            
            if success:
                logger.info("Service initialized successfully",
                           service=service_name,
                           startup_time_seconds=round(startup_time, 3))
                
                return ServiceResult(
                    name=service_name,
                    status=ServiceStatus.HEALTHY,
                    startup_time=startup_time,
                    metadata={"result": str(result) if result else "success"}
                )
            else:
                logger.error("Service initialization failed after all retries",
                            service=service_name,
                            startup_time_seconds=round(startup_time, 3),
                            error=error)
                
                return ServiceResult(
                    name=service_name,
                    status=ServiceStatus.FAILED,
                    startup_time=startup_time,
                    error=error
                )
                
        except Exception as e:
            startup_time = time.time() - start_time
            error_msg = str(e)
            
            logger.error("Service initialization exception",
                        service=service_name,
                        startup_time_seconds=round(startup_time, 3),
                        error=error_msg,
                        error_type=type(e).__name__)
            
            return ServiceResult(
                name=service_name,
                status=ServiceStatus.FAILED,
                startup_time=startup_time,
                error=error_msg
            )
    
    async def parallel_initialize(self, 
                                 service_configs: List[Tuple[str, Callable, tuple, dict]]) -> StartupMetrics:
        """Initialize multiple services in parallel
        
        Args:
            service_configs: List of (name, init_func, args, kwargs) tuples
        
        Returns:
            StartupMetrics with detailed timing and results
        """
        self.startup_start_time = time.time()
        
        logger.info("🚀 Starting parallel service initialization",
                   total_services=len(service_configs))
        
        # Create initialization tasks
        tasks = []
        for service_name, init_func, args, kwargs in service_configs:
            task = asyncio.create_task(
                self.initialize_service(service_name, init_func, *args, **kwargs),
                name=f"init-{service_name}"
            )
            tasks.append(task)
        
        # Run all initializations in parallel using asyncio.gather
        parallel_start = time.time()
        try:
            # Wait for all services to initialize
            service_results = await asyncio.gather(*tasks, return_exceptions=False)
            
        except Exception as e:
            logger.error("Critical error during parallel initialization", error=str(e))
            # If gather fails, collect partial results
            service_results = []
            for task in tasks:
                if task.done():
                    try:
                        service_results.append(task.result())
                    except Exception as task_error:
                        service_results.append(ServiceResult(
                            name="unknown",
                            status=ServiceStatus.FAILED,
                            startup_time=0.0,
                            error=str(task_error)
                        ))
        
        parallel_time = time.time() - parallel_start
        total_time = time.time() - self.startup_start_time
        
        # Calculate metrics
        healthy_count = sum(1 for r in service_results if r.status == ServiceStatus.HEALTHY)
        failed_count = sum(1 for r in service_results if r.status == ServiceStatus.FAILED)
        
        metrics = StartupMetrics(
            total_startup_time=total_time,
            parallel_init_time=parallel_time,
            service_results=service_results,
            services_healthy=healthy_count,
            services_failed=failed_count
        )
        
        # Log comprehensive results
        logger.info("🎉 Parallel initialization complete",
                   total_time_seconds=round(total_time, 3),
                   parallel_time_seconds=round(parallel_time, 3),
                   services_healthy=healthy_count,
                   services_failed=failed_count,
                   success_rate_percent=round(metrics.success_rate, 1))
        
        # Log individual service results
        for result in service_results:
            level = "info" if result.status == ServiceStatus.HEALTHY else "error"
            getattr(logger, level)(
                f"Service {result.name}: {result.status.value}",
                service=result.name,
                status=result.status.value,
                startup_time_seconds=round(result.startup_time, 3),
                error=result.error
            )
        
        return metrics
    
    async def create_health_check_endpoint(self) -> Dict[str, Any]:
        """Create comprehensive health check data"""
        health_status = {
            "infrastructure": {
                "circuit_breakers": {}
            },
            "startup_metrics": {
                "last_startup_time": getattr(self, 'last_startup_metrics', None)
            }
        }
        
        # Add circuit breaker states
        for service_name, breaker in self.circuit_breakers.items():
            health_status["infrastructure"]["circuit_breakers"][service_name] = {
                "state": breaker.state,
                "failure_count": breaker.failure_count,
                "last_failure_time": breaker.last_failure_time
            }
        
        return health_status


# Global initializer instance
_parallel_initializer = None


def get_parallel_initializer() -> ParallelInitializer:
    """Get global parallel initializer instance"""
    global _parallel_initializer
    if _parallel_initializer is None:
        _parallel_initializer = ParallelInitializer()
    return _parallel_initializer


async def create_optimized_startup_sequence(
    init_db_func: Callable,
    init_redis_func: Callable, 
    init_nats_func: Callable,
    init_session_service_func: Callable,
    init_websocket_manager_func: Callable,
    init_rate_limiter_func: Callable,
    init_auth_func: Callable
) -> StartupMetrics:
    """Create optimized parallel startup sequence
    
    This is the main entry point for parallel infrastructure initialization.
    It orchestrates all service startups with the precision of a Swiss watch
    and the speed that would make a DevOps consultant weep with joy.
    
    Returns:
        StartupMetrics containing detailed timing and success information
    """
    
    initializer = get_parallel_initializer()
    
    # Define service initialization sequence
    # Order matters for dependencies, but execution is parallel within groups
    service_configs = [
        # Core infrastructure (can start in parallel)
        ("database", init_db_func, (), {}),
        ("redis", init_redis_func, (), {}),
        ("nats", init_nats_func, (), {}),
        
        # Application services (depend on infrastructure)
        ("session_service", init_session_service_func, (), {}),
        ("websocket_manager", init_websocket_manager_func, (), {}),
        ("rate_limiter", init_rate_limiter_func, (), {}),
        ("auth", init_auth_func, (), {}),
    ]
    
    return await initializer.parallel_initialize(service_configs)


@asynccontextmanager
async def startup_performance_monitor():
    """Context manager for monitoring startup performance"""
    start_time = time.time()
    
    logger.info("📊 Starting startup performance monitoring")
    
    try:
        yield
    finally:
        total_time = time.time() - start_time
        logger.info("📊 Startup performance monitoring complete",
                   total_duration_seconds=round(total_time, 3))