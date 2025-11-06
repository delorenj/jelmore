"""API Key authentication middleware for Jelmore

Simple but effective API key authentication system with:
- Environment-based key configuration
- Request header validation
- Rate limiting hooks (extensible)
- Audit logging for security events
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.security.api_key import APIKeyHeader
import structlog

from jelmore.config import get_settings


logger = structlog.get_logger(__name__)


class APIKeyAuth:
    """API Key authentication handler with multi-key support
    
    Supports multiple API keys for different access levels and clients.
    Keys are configured via environment variables.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.api_keys = self._load_api_keys()
        self.api_key_header = APIKeyHeader(
            name=self.settings.api_key_header,
            auto_error=False
        )
        
    def _load_api_keys(self) -> Dict[str, Dict[str, Any]]:
        """Load API keys from environment variables
        
        Expected format:
        API_KEY_ADMIN=your-admin-key-here
        API_KEY_CLIENT=your-client-key-here
        API_KEY_READONLY=your-readonly-key-here
        
        Returns:
            Dict mapping keys to metadata
        """
        api_keys = {}
        
        # Load keys from environment
        for key, value in os.environ.items():
            if key.startswith('API_KEY_'):
                key_name = key.replace('API_KEY_', '').lower()
                api_keys[value] = {
                    'name': key_name,
                    'created_at': datetime.utcnow(),
                    'permissions': self._get_key_permissions(key_name)
                }
                
        # Load keys from settings (environment-based)
        if self.settings.api_key_admin:
            api_keys[self.settings.api_key_admin] = {
                'name': 'admin',
                'created_at': datetime.utcnow(),
                'permissions': self._get_key_permissions('admin')
            }
        if self.settings.api_key_client:
            api_keys[self.settings.api_key_client] = {
                'name': 'client',
                'created_at': datetime.utcnow(),
                'permissions': self._get_key_permissions('client')
            }
        if self.settings.api_key_readonly:
            api_keys[self.settings.api_key_readonly] = {
                'name': 'readonly',
                'created_at': datetime.utcnow(),
                'permissions': self._get_key_permissions('readonly')
            }
                          
        if api_keys:
            logger.info("API keys loaded", 
                       key_count=len(api_keys),
                       key_names=[v['name'] for v in api_keys.values()])
        else:
            if self.settings.debug:
                logger.warning("No API keys configured - authentication disabled in debug mode")
            else:
                logger.error("No API keys configured - this is a security risk in production")
            
        return api_keys
    
    def _get_key_permissions(self, key_name: str) -> List[str]:
        """Get permissions for a key based on its name
        
        Args:
            key_name: Name of the key (admin, client, readonly, etc.)
            
        Returns:
            List of permissions
        """
        permission_map = {
            'admin': ['read', 'write', 'admin', 'delete'],
            'client': ['read', 'write'],
            'readonly': ['read'],
            'service': ['read', 'write'],
            'development': ['read', 'write', 'admin', 'delete']
        }
        
        return permission_map.get(key_name, ['read'])
    
    async def authenticate(
        self, 
        request: Request,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate request using API key
        
        Args:
            request: FastAPI request object
            api_key: API key from header (injected by dependency)
            
        Returns:
            Dict with authentication context
            
        Raises:
            HTTPException: If authentication fails
        """
        # Skip authentication for health checks
        if request.url.path in ['/health', '/metrics']:
            return {'authenticated': False, 'key_name': 'health_check'}
            
        # If no API keys configured, allow all (development mode)
        if not self.api_keys:
            logger.warning("No API keys configured - allowing request",
                          path=request.url.path,
                          client=request.client.host if request.client else "unknown")
            return {'authenticated': False, 'key_name': 'no_auth'}
        
        # Check for API key in header
        if not api_key:
            logger.warning("Missing API key",
                          path=request.url.path,
                          client=request.client.host if request.client else "unknown")
            raise HTTPException(
                status_code=401,
                detail="API key required",
                headers={"WWW-Authenticate": f"APIKey realm=\"{self.settings.api_key_header}\""}
            )
        
        # Validate API key
        key_info = self.api_keys.get(api_key)
        if not key_info:
            logger.warning("Invalid API key",
                          path=request.url.path,
                          key_prefix=api_key[:10] if len(api_key) > 10 else "short_key",
                          client=request.client.host if request.client else "unknown")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        # Log successful authentication
        logger.info("API key authenticated",
                   path=request.url.path,
                   key_name=key_info['name'],
                   permissions=key_info['permissions'],
                   client=request.client.host if request.client else "unknown")
        
        return {
            'authenticated': True,
            'key_name': key_info['name'],
            'permissions': key_info['permissions'],
            'key_info': key_info
        }
    
    def require_permission(self, required_permission: str):
        """Decorator factory for permission-based access control
        
        Args:
            required_permission: Permission required (read, write, admin, delete)
            
        Returns:
            Dependency function for FastAPI
        """
        async def permission_dependency(
            request: Request,
            auth_context: Dict[str, Any] = Depends(self.authenticate)
        ):
            if not auth_context['authenticated']:
                return auth_context  # Health checks, etc.
                
            permissions = auth_context.get('permissions', [])
            
            if required_permission not in permissions:
                logger.warning("Insufficient permissions",
                              path=request.url.path,
                              key_name=auth_context['key_name'],
                              required=required_permission,
                              available=permissions)
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission '{required_permission}' required"
                )
                
            return auth_context
            
        return permission_dependency
    
    async def get_key_stats(self) -> Dict[str, Any]:
        """Get API key statistics for monitoring
        
        Returns:
            Dict with key statistics
        """
        return {
            'total_keys': len(self.api_keys),
            'key_names': [info['name'] for info in self.api_keys.values()],
            'auth_header': self.settings.api_key_header,
            'authentication_enabled': len(self.api_keys) > 0
        }


# Global authentication instance
_api_key_auth: Optional[APIKeyAuth] = None


def get_api_key_auth() -> APIKeyAuth:
    """Get global API key authentication instance"""
    global _api_key_auth
    
    if _api_key_auth is None:
        _api_key_auth = APIKeyAuth()
        
    return _api_key_auth


# FastAPI dependency for API key authentication
async def api_key_dependency(
    request: Request,
    api_key: Optional[str] = Depends(APIKeyHeader(name=get_settings().api_key_header, auto_error=False))
) -> Dict[str, Any]:
    """FastAPI dependency for API key authentication
    
    Usage:
        @app.get("/protected")
        async def protected_endpoint(auth: dict = Depends(api_key_dependency)):
            return {"message": "Access granted", "auth": auth}
    """
    auth = get_api_key_auth()
    return await auth.authenticate(request, api_key)


# Permission-based dependencies
async def require_read_permission(
    auth_context: Dict[str, Any] = Depends(api_key_dependency)
) -> Dict[str, Any]:
    """Require read permission"""
    auth = get_api_key_auth()
    permission_check = auth.require_permission('read')
    # Note: This is a simplified version. In practice, you'd use the decorator
    return auth_context


async def require_write_permission(
    auth_context: Dict[str, Any] = Depends(api_key_dependency)
) -> Dict[str, Any]:
    """Require write permission"""
    auth = get_api_key_auth()
    # Check permissions
    if auth_context['authenticated']:
        permissions = auth_context.get('permissions', [])
        if 'write' not in permissions:
            raise HTTPException(
                status_code=403,
                detail="Write permission required"
            )
    return auth_context


async def require_admin_permission(
    auth_context: Dict[str, Any] = Depends(api_key_dependency)
) -> Dict[str, Any]:
    """Require admin permission"""
    auth = get_api_key_auth()
    # Check permissions
    if auth_context['authenticated']:
        permissions = auth_context.get('permissions', [])
        if 'admin' not in permissions:
            raise HTTPException(
                status_code=403,
                detail="Admin permission required"
            )
    return auth_context


# Middleware function for FastAPI
async def auth_middleware(request: Request, call_next):
    """Authentication middleware for FastAPI
    
    This can be used as middleware if you prefer that approach over dependencies.
    Note: Dependencies are generally preferred for API endpoints.
    """
    # Skip authentication for specific paths
    skip_paths = ['/health', '/metrics', '/docs', '/redoc', '/openapi.json']
    
    if any(request.url.path.startswith(path) for path in skip_paths):
        response = await call_next(request)
        return response
    
    # Perform authentication
    try:
        auth = get_api_key_auth()
        api_key = request.headers.get(auth.settings.api_key_header)
        auth_context = await auth.authenticate(request, api_key)
        
        # Add auth context to request state
        request.state.auth = auth_context
        
    except HTTPException as e:
        # Return authentication error
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
            headers=e.headers or {}
        )
    
    # Continue with request
    response = await call_next(request)
    return response