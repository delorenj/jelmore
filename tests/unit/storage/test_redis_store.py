"""
Unit tests for Redis session storage implementation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import redis.asyncio as redis


class RedisSessionStore:
    """Redis-based session storage implementation"""
    
    def __init__(self, redis_client: redis.Redis, key_prefix: str = "session:", ttl: int = 3600):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.ttl = ttl
    
    def _make_key(self, session_id: str) -> str:
        """Generate Redis key for session"""
        return f"{self.key_prefix}{session_id}"
    
    async def store_session(self, session_id: str, session_data: Dict[str, Any]) -> bool:
        """Store session data in Redis"""
        try:
            key = self._make_key(session_id)
            
            # Add metadata
            session_data = session_data.copy()
            session_data["stored_at"] = datetime.utcnow().isoformat()
            session_data["session_id"] = session_id
            
            # Serialize and store
            data = json.dumps(session_data, default=str)
            await self.redis.setex(key, self.ttl, data)
            return True
        except Exception:
            return False
    
    async def retrieve_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session data from Redis"""
        try:
            key = self._make_key(session_id)
            data = await self.redis.get(key)
            
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None
    
    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session data in Redis"""
        try:
            # Get existing session
            existing = await self.retrieve_session(session_id)
            if not existing:
                return False
            
            # Merge updates
            existing.update(updates)
            existing["updated_at"] = datetime.utcnow().isoformat()
            
            # Store updated data
            return await self.store_session(session_id, existing)
        except Exception:
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session from Redis"""
        try:
            key = self._make_key(session_id)
            result = await self.redis.delete(key)
            return result > 0
        except Exception:
            return False
    
    async def session_exists(self, session_id: str) -> bool:
        """Check if session exists in Redis"""
        try:
            key = self._make_key(session_id)
            result = await self.redis.exists(key)
            return result > 0
        except Exception:
            return False
    
    async def extend_session(self, session_id: str, additional_ttl: int = None) -> bool:
        """Extend session TTL"""
        try:
            key = self._make_key(session_id)
            ttl = additional_ttl or self.ttl
            result = await self.redis.expire(key, ttl)
            return result
        except Exception:
            return False
    
    async def list_sessions(self, pattern: str = "*") -> list[str]:
        """List all session IDs matching pattern"""
        try:
            search_pattern = f"{self.key_prefix}{pattern}"
            keys = await self.redis.keys(search_pattern)
            
            # Extract session IDs from keys
            session_ids = []
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                if key.startswith(self.key_prefix):
                    session_id = key[len(self.key_prefix):]
                    session_ids.append(session_id)
            
            return session_ids
        except Exception:
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (manual cleanup)"""
        try:
            all_sessions = await self.list_sessions()
            cleaned_count = 0
            
            for session_id in all_sessions:
                key = self._make_key(session_id)
                ttl = await self.redis.ttl(key)
                
                # If TTL is -1 (no expiry) or -2 (expired), handle it
                if ttl == -2:  # Already expired
                    await self.delete_session(session_id)
                    cleaned_count += 1
            
            return cleaned_count
        except Exception:
            return 0
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        try:
            all_sessions = await self.list_sessions()
            total_sessions = len(all_sessions)
            
            # Calculate memory usage (approximate)
            memory_usage = 0
            for session_id in all_sessions:
                key = self._make_key(session_id)
                try:
                    size = await self.redis.memory_usage(key)
                    if size:
                        memory_usage += size
                except Exception:
                    pass
            
            return {
                "total_sessions": total_sessions,
                "memory_usage_bytes": memory_usage,
                "key_prefix": self.key_prefix,
                "default_ttl": self.ttl
            }
        except Exception:
            return {
                "total_sessions": 0,
                "memory_usage_bytes": 0,
                "key_prefix": self.key_prefix,
                "default_ttl": self.ttl
            }


class TestRedisSessionStore:
    """Test suite for Redis session storage"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for testing"""
        mock_redis = AsyncMock(spec=redis.Redis)
        return mock_redis
    
    @pytest.fixture
    def session_store(self, mock_redis):
        """Create session store with mock Redis"""
        return RedisSessionStore(mock_redis, "test_session:", 1800)
    
    @pytest.fixture
    def sample_session_data(self):
        """Sample session data for testing"""
        return {
            "id": "test-session-123",
            "status": "active",
            "query": "Test query",
            "current_directory": "/home/test",
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "metadata": {"test": True}
        }
    
    def test_make_key(self, session_store):
        """Test Redis key generation"""
        session_id = "test-123"
        key = session_store._make_key(session_id)
        assert key == "test_session:test-123"
    
    @pytest.mark.asyncio
    async def test_store_session_success(self, session_store, mock_redis, sample_session_data):
        """Test successful session storage"""
        mock_redis.setex.return_value = True
        
        result = await session_store.store_session("test-123", sample_session_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # Verify call arguments
        call_args = mock_redis.setex.call_args
        key, ttl, data = call_args[0]
        
        assert key == "test_session:test-123"
        assert ttl == 1800
        
        # Verify data contains metadata
        stored_data = json.loads(data)
        assert stored_data["session_id"] == "test-123"
        assert "stored_at" in stored_data
        assert stored_data["id"] == "test-session-123"
    
    @pytest.mark.asyncio
    async def test_store_session_redis_error(self, session_store, mock_redis, sample_session_data):
        """Test session storage with Redis error"""
        mock_redis.setex.side_effect = redis.ConnectionError("Redis connection failed")
        
        result = await session_store.store_session("test-123", sample_session_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_retrieve_session_success(self, session_store, mock_redis):
        """Test successful session retrieval"""
        stored_data = {
            "session_id": "test-123",
            "status": "active",
            "stored_at": datetime.utcnow().isoformat()
        }
        mock_redis.get.return_value = json.dumps(stored_data)
        
        result = await session_store.retrieve_session("test-123")
        
        assert result == stored_data
        mock_redis.get.assert_called_once_with("test_session:test-123")
    
    @pytest.mark.asyncio
    async def test_retrieve_session_not_found(self, session_store, mock_redis):
        """Test session retrieval when session doesn't exist"""
        mock_redis.get.return_value = None
        
        result = await session_store.retrieve_session("nonexistent")
        
        assert result is None
        mock_redis.get.assert_called_once_with("test_session:nonexistent")
    
    @pytest.mark.asyncio
    async def test_retrieve_session_invalid_json(self, session_store, mock_redis):
        """Test session retrieval with invalid JSON data"""
        mock_redis.get.return_value = "invalid json data"
        
        result = await session_store.retrieve_session("test-123")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_session_success(self, session_store, mock_redis):
        """Test successful session update"""
        # Mock existing session
        existing_data = {
            "session_id": "test-123",
            "status": "active",
            "query": "Original query"
        }
        mock_redis.get.return_value = json.dumps(existing_data)
        mock_redis.setex.return_value = True
        
        updates = {"status": "waiting_input", "new_field": "test_value"}
        result = await session_store.update_session("test-123", updates)
        
        assert result is True
        
        # Verify setex was called with updated data
        call_args = mock_redis.setex.call_args
        key, ttl, data = call_args[0]
        updated_data = json.loads(data)
        
        assert updated_data["status"] == "waiting_input"
        assert updated_data["new_field"] == "test_value"
        assert updated_data["query"] == "Original query"  # Preserved
        assert "updated_at" in updated_data
    
    @pytest.mark.asyncio
    async def test_update_session_not_found(self, session_store, mock_redis):
        """Test updating non-existent session"""
        mock_redis.get.return_value = None
        
        result = await session_store.update_session("nonexistent", {"status": "updated"})
        
        assert result is False
        mock_redis.setex.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_delete_session_success(self, session_store, mock_redis):
        """Test successful session deletion"""
        mock_redis.delete.return_value = 1
        
        result = await session_store.delete_session("test-123")
        
        assert result is True
        mock_redis.delete.assert_called_once_with("test_session:test-123")
    
    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, session_store, mock_redis):
        """Test deletion of non-existent session"""
        mock_redis.delete.return_value = 0
        
        result = await session_store.delete_session("nonexistent")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_session_exists_true(self, session_store, mock_redis):
        """Test session existence check - exists"""
        mock_redis.exists.return_value = 1
        
        result = await session_store.session_exists("test-123")
        
        assert result is True
        mock_redis.exists.assert_called_once_with("test_session:test-123")
    
    @pytest.mark.asyncio
    async def test_session_exists_false(self, session_store, mock_redis):
        """Test session existence check - doesn't exist"""
        mock_redis.exists.return_value = 0
        
        result = await session_store.session_exists("nonexistent")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_extend_session_success(self, session_store, mock_redis):
        """Test successful session TTL extension"""
        mock_redis.expire.return_value = True
        
        result = await session_store.extend_session("test-123", 3600)
        
        assert result is True
        mock_redis.expire.assert_called_once_with("test_session:test-123", 3600)
    
    @pytest.mark.asyncio
    async def test_extend_session_default_ttl(self, session_store, mock_redis):
        """Test session extension with default TTL"""
        mock_redis.expire.return_value = True
        
        result = await session_store.extend_session("test-123")
        
        assert result is True
        mock_redis.expire.assert_called_once_with("test_session:test-123", 1800)
    
    @pytest.mark.asyncio
    async def test_list_sessions_success(self, session_store, mock_redis):
        """Test listing all sessions"""
        mock_keys = [
            b"test_session:session-1",
            b"test_session:session-2",
            b"test_session:session-3",
            "other_key:not-session"  # Mixed bytes/str to test handling
        ]
        mock_redis.keys.return_value = mock_keys
        
        result = await session_store.list_sessions()
        
        assert len(result) == 3
        assert "session-1" in result
        assert "session-2" in result
        assert "session-3" in result
        mock_redis.keys.assert_called_once_with("test_session:*")
    
    @pytest.mark.asyncio
    async def test_list_sessions_with_pattern(self, session_store, mock_redis):
        """Test listing sessions with specific pattern"""
        mock_redis.keys.return_value = [b"test_session:active-session-1"]
        
        result = await session_store.list_sessions("active-*")
        
        assert result == ["active-session-1"]
        mock_redis.keys.assert_called_once_with("test_session:active-*")
    
    @pytest.mark.asyncio
    async def test_list_sessions_redis_error(self, session_store, mock_redis):
        """Test listing sessions with Redis error"""
        mock_redis.keys.side_effect = redis.ConnectionError("Connection failed")
        
        result = await session_store.list_sessions()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, session_store, mock_redis):
        """Test cleanup of expired sessions"""
        # Mock sessions list
        mock_redis.keys.return_value = [b"test_session:session-1", b"test_session:session-2"]
        
        # Mock TTL checks
        mock_redis.ttl.side_effect = [-2, 300]  # First expired, second still valid
        mock_redis.delete.return_value = 1
        
        result = await session_store.cleanup_expired_sessions()
        
        assert result == 1  # One session cleaned
        mock_redis.delete.assert_called_once_with("test_session:session-1")
    
    @pytest.mark.asyncio
    async def test_get_session_stats(self, session_store, mock_redis):
        """Test getting session storage statistics"""
        # Mock sessions
        mock_redis.keys.return_value = [b"test_session:session-1", b"test_session:session-2"]
        mock_redis.memory_usage.side_effect = [1024, 2048]  # Mock memory usage
        
        result = await session_store.get_session_stats()
        
        assert result["total_sessions"] == 2
        assert result["memory_usage_bytes"] == 3072
        assert result["key_prefix"] == "test_session:"
        assert result["default_ttl"] == 1800
    
    @pytest.mark.asyncio
    async def test_get_session_stats_memory_error(self, session_store, mock_redis):
        """Test session stats when memory_usage fails"""
        mock_redis.keys.return_value = [b"test_session:session-1"]
        mock_redis.memory_usage.side_effect = Exception("Memory usage not supported")
        
        result = await session_store.get_session_stats()
        
        assert result["total_sessions"] == 1
        assert result["memory_usage_bytes"] == 0  # Should handle error gracefully
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, session_store, mock_redis, sample_session_data):
        """Test concurrent session operations"""
        import asyncio
        
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = json.dumps(sample_session_data)
        mock_redis.delete.return_value = 1
        
        # Perform concurrent operations
        tasks = []
        
        # Store sessions
        for i in range(5):
            task = asyncio.create_task(
                session_store.store_session(f"session-{i}", sample_session_data)
            )
            tasks.append(task)
        
        # Retrieve sessions
        for i in range(5):
            task = asyncio.create_task(
                session_store.retrieve_session(f"session-{i}")
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All operations should succeed
        store_results = results[:5]
        retrieve_results = results[5:]
        
        assert all(store_results)
        assert all(r is not None for r in retrieve_results)
    
    @pytest.mark.asyncio
    async def test_large_session_data(self, session_store, mock_redis):
        """Test storing large session data"""
        # Create large session data
        large_data = {
            "id": "large-session",
            "status": "active", 
            "large_field": "x" * 10000,  # 10KB of data
            "array_field": list(range(1000))  # Large array
        }
        
        mock_redis.setex.return_value = True
        
        result = await session_store.store_session("large-session", large_data)
        
        assert result is True
        mock_redis.setex.assert_called_once()
        
        # Verify data was serialized properly
        call_args = mock_redis.setex.call_args
        key, ttl, data = call_args[0]
        stored_data = json.loads(data)
        
        assert len(stored_data["large_field"]) == 10000
        assert len(stored_data["array_field"]) == 1000
    
    @pytest.mark.asyncio
    async def test_session_serialization_edge_cases(self, session_store, mock_redis):
        """Test serialization of edge case data types"""
        edge_case_data = {
            "datetime_field": datetime.utcnow(),
            "none_field": None,
            "empty_dict": {},
            "empty_list": [],
            "boolean_true": True,
            "boolean_false": False,
            "zero_int": 0,
            "zero_float": 0.0,
            "unicode_string": "Hello 世界 🌍",
        }
        
        mock_redis.setex.return_value = True
        
        result = await session_store.store_session("edge-case", edge_case_data)
        
        assert result is True
        
        # Verify serialization worked
        call_args = mock_redis.setex.call_args
        data = json.loads(call_args[0][2])
        
        assert data["none_field"] is None
        assert data["empty_dict"] == {}
        assert data["empty_list"] == []
        assert data["unicode_string"] == "Hello 世界 🌍"
        assert isinstance(data["datetime_field"], str)  # Should be string after serialization