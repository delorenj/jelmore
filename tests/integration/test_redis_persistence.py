"""
Integration tests for Redis session persistence
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
import uuid
import redis.asyncio as redis


class TestRedisIntegration:
    """Integration tests for Redis session persistence"""
    
    @pytest.mark.asyncio
    async def test_redis_session_storage_integration(self, integration_config):
        """Test full Redis storage integration"""
        # Skip if Redis not available in test environment
        pytest.importorskip("redis")
        
        try:
            # Connect to test Redis instance
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            
            # Create session store with real Redis
            session_store = RedisSessionStore(redis_client, "integration_test:", 60)
            
            # Test session lifecycle with real Redis
            session_id = str(uuid.uuid4())
            session_data = {
                "id": session_id,
                "status": "active",
                "query": "Integration test query",
                "current_directory": "/tmp/test",
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow(),
                "metadata": {"test_type": "integration"}
            }
            
            # Store session
            stored = await session_store.store_session(session_id, session_data)
            assert stored is True
            
            # Verify session exists
            exists = await session_store.session_exists(session_id)
            assert exists is True
            
            # Retrieve session
            retrieved = await session_store.retrieve_session(session_id)
            assert retrieved is not None
            assert retrieved["id"] == session_id
            assert retrieved["status"] == "active"
            assert retrieved["query"] == "Integration test query"
            assert "stored_at" in retrieved
            
            # Update session
            updates = {"status": "waiting_input", "current_directory": "/tmp/updated"}
            updated = await session_store.update_session(session_id, updates)
            assert updated is True
            
            # Verify updates
            updated_session = await session_store.retrieve_session(session_id)
            assert updated_session["status"] == "waiting_input"
            assert updated_session["current_directory"] == "/tmp/updated"
            assert "updated_at" in updated_session
            
            # Test session listing
            session_list = await session_store.list_sessions()
            assert session_id in session_list
            
            # Test TTL extension
            extended = await session_store.extend_session(session_id, 120)
            assert extended is True
            
            # Get statistics
            stats = await session_store.get_session_stats()
            assert stats["total_sessions"] >= 1
            assert stats["key_prefix"] == "integration_test:"
            
            # Delete session
            deleted = await session_store.delete_session(session_id)
            assert deleted is True
            
            # Verify deletion
            exists_after_delete = await session_store.session_exists(session_id)
            assert exists_after_delete is False
            
        finally:
            # Cleanup
            await redis_client.flushdb()  # Clear test database
            await redis_client.close()
    
    @pytest.mark.asyncio
    async def test_redis_connection_recovery(self, integration_config):
        """Test Redis connection recovery scenarios"""
        pytest.importorskip("redis")
        
        # Create a Redis connection that we can control
        redis_client = AsyncMock(spec=redis.Redis)
        
        from tests.unit.storage.test_redis_store import RedisSessionStore
        session_store = RedisSessionStore(redis_client, "recovery_test:", 60)
        
        session_id = str(uuid.uuid4())
        session_data = {"id": session_id, "status": "active"}
        
        # Simulate connection failure, then recovery
        redis_client.setex.side_effect = [
            redis.ConnectionError("Connection lost"),  # First call fails
            True  # Second call succeeds (after reconnection)
        ]
        
        # First attempt should fail
        result1 = await session_store.store_session(session_id, session_data)
        assert result1 is False
        
        # Second attempt should succeed (simulating reconnection)
        result2 = await session_store.store_session(session_id, session_data)
        assert result2 is True
    
    @pytest.mark.asyncio
    async def test_redis_data_consistency(self, integration_config):
        """Test Redis data consistency across operations"""
        pytest.importorskip("redis")
        
        try:
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            session_store = RedisSessionStore(redis_client, "consistency_test:", 60)
            
            # Create multiple sessions with overlapping operations
            session_ids = [str(uuid.uuid4()) for _ in range(3)]
            base_data = {
                "status": "active",
                "query": "Consistency test",
                "created_at": datetime.utcnow()
            }
            
            # Store all sessions
            tasks = []
            for i, session_id in enumerate(session_ids):
                data = base_data.copy()
                data["id"] = session_id
                data["sequence"] = i
                task = asyncio.create_task(
                    session_store.store_session(session_id, data)
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            assert all(results)
            
            # Verify all sessions were stored correctly
            for i, session_id in enumerate(session_ids):
                retrieved = await session_store.retrieve_session(session_id)
                assert retrieved is not None
                assert retrieved["id"] == session_id
                assert retrieved["sequence"] == i
            
            # Perform concurrent updates
            update_tasks = []
            for i, session_id in enumerate(session_ids):
                updates = {"status": "updated", "update_sequence": i * 10}
                task = asyncio.create_task(
                    session_store.update_session(session_id, updates)
                )
                update_tasks.append(task)
            
            update_results = await asyncio.gather(*update_tasks)
            assert all(update_results)
            
            # Verify updates were applied correctly
            for i, session_id in enumerate(session_ids):
                updated = await session_store.retrieve_session(session_id)
                assert updated["status"] == "updated"
                assert updated["update_sequence"] == i * 10
                assert updated["sequence"] == i  # Original data preserved
            
        finally:
            await redis_client.flushdb()
            await redis_client.close()
    
    @pytest.mark.asyncio
    async def test_redis_memory_usage_tracking(self, integration_config):
        """Test Redis memory usage tracking"""
        pytest.importorskip("redis")
        
        try:
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            session_store = RedisSessionStore(redis_client, "memory_test:", 300)
            
            # Store sessions of varying sizes
            small_session = {
                "id": "small",
                "status": "active",
                "data": "small"
            }
            
            large_session = {
                "id": "large",
                "status": "active",
                "data": "x" * 5000,  # 5KB of data
                "array_data": list(range(500))
            }
            
            await session_store.store_session("small", small_session)
            await session_store.store_session("large", large_session)
            
            # Get memory stats
            stats = await session_store.get_session_stats()
            
            assert stats["total_sessions"] == 2
            # Memory usage should be greater than 0 if supported
            # (Some Redis versions might not support MEMORY USAGE)
            assert stats["memory_usage_bytes"] >= 0
            
        finally:
            await redis_client.flushdb()
            await redis_client.close()
    
    @pytest.mark.asyncio
    async def test_redis_ttl_expiration(self, integration_config):
        """Test Redis TTL expiration behavior"""
        pytest.importorskip("redis")
        
        try:
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            
            # Use very short TTL for testing
            session_store = RedisSessionStore(redis_client, "ttl_test:", 2)  # 2 seconds
            
            session_id = str(uuid.uuid4())
            session_data = {"id": session_id, "status": "active"}
            
            # Store session
            stored = await session_store.store_session(session_id, session_data)
            assert stored is True
            
            # Verify session exists immediately
            exists = await session_store.session_exists(session_id)
            assert exists is True
            
            # Check TTL
            key = session_store._make_key(session_id)
            ttl = await redis_client.ttl(key)
            assert ttl > 0 and ttl <= 2
            
            # Wait for expiration
            await asyncio.sleep(3)
            
            # Verify session has expired
            exists_after_ttl = await session_store.session_exists(session_id)
            assert exists_after_ttl is False
            
            retrieved_after_ttl = await session_store.retrieve_session(session_id)
            assert retrieved_after_ttl is None
            
        finally:
            await redis_client.flushdb()
            await redis_client.close()
    
    @pytest.mark.asyncio
    async def test_redis_high_concurrency(self, integration_config):
        """Test Redis under high concurrency load"""
        pytest.importorskip("redis")
        
        try:
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            session_store = RedisSessionStore(redis_client, "concurrency_test:", 60)
            
            # Create many concurrent operations
            num_sessions = 50
            
            # Concurrent session creation
            create_tasks = []
            session_ids = []
            
            for i in range(num_sessions):
                session_id = f"session-{i}"
                session_ids.append(session_id)
                data = {
                    "id": session_id,
                    "status": "active",
                    "index": i,
                    "created_at": datetime.utcnow()
                }
                task = asyncio.create_task(
                    session_store.store_session(session_id, data)
                )
                create_tasks.append(task)
            
            # Wait for all creations to complete
            create_results = await asyncio.gather(*create_tasks, return_exceptions=True)
            
            # Count successful operations
            successful_creates = sum(1 for r in create_results if r is True)
            assert successful_creates > num_sessions * 0.9  # At least 90% success rate
            
            # Concurrent retrieval
            retrieve_tasks = []
            for session_id in session_ids[:successful_creates]:
                task = asyncio.create_task(
                    session_store.retrieve_session(session_id)
                )
                retrieve_tasks.append(task)
            
            retrieve_results = await asyncio.gather(*retrieve_tasks, return_exceptions=True)
            
            # Verify retrievals
            successful_retrievals = sum(1 for r in retrieve_results if r is not None and not isinstance(r, Exception))
            assert successful_retrievals > successful_creates * 0.9
            
            # Concurrent updates
            update_tasks = []
            for session_id in session_ids[:successful_retrievals]:
                updates = {"status": "updated", "updated_at": datetime.utcnow().isoformat()}
                task = asyncio.create_task(
                    session_store.update_session(session_id, updates)
                )
                update_tasks.append(task)
            
            update_results = await asyncio.gather(*update_tasks, return_exceptions=True)
            successful_updates = sum(1 for r in update_results if r is True)
            assert successful_updates > successful_retrievals * 0.9
            
            # Final statistics
            stats = await session_store.get_session_stats()
            assert stats["total_sessions"] >= successful_creates * 0.9
            
        finally:
            await redis_client.flushdb()
            await redis_client.close()
    
    @pytest.mark.asyncio
    async def test_redis_failover_simulation(self, integration_config):
        """Test Redis failover scenarios"""
        # This test simulates Redis connection issues and recovery
        redis_client = AsyncMock(spec=redis.Redis)
        
        from tests.unit.storage.test_redis_store import RedisSessionStore
        session_store = RedisSessionStore(redis_client, "failover_test:", 60)
        
        session_id = str(uuid.uuid4())
        session_data = {"id": session_id, "status": "active"}
        
        # Simulate various failure scenarios
        failure_scenarios = [
            redis.ConnectionError("Connection refused"),
            redis.TimeoutError("Operation timed out"),
            redis.ResponseError("Server error"),
            Exception("Unknown error")
        ]
        
        for failure in failure_scenarios:
            # Configure mock to fail then succeed
            redis_client.setex.side_effect = [failure, True]
            
            # First call should fail gracefully
            result1 = await session_store.store_session(session_id, session_data)
            assert result1 is False
            
            # Second call should succeed (simulating recovery)
            result2 = await session_store.store_session(session_id, session_data)
            assert result2 is True
    
    @pytest.mark.asyncio
    async def test_redis_data_serialization_edge_cases(self, integration_config):
        """Test Redis serialization of complex data types"""
        pytest.importorskip("redis")
        
        try:
            redis_client = redis.from_url(
                integration_config["redis_test_url"],
                decode_responses=True
            )
            await redis_client.ping()
        except Exception:
            pytest.skip("Redis not available for integration testing")
        
        try:
            from tests.unit.storage.test_redis_store import RedisSessionStore
            session_store = RedisSessionStore(redis_client, "serialization_test:", 60)
            
            # Complex session data with various data types
            complex_data = {
                "id": "complex-session",
                "status": "active",
                "datetime_field": datetime.utcnow(),
                "timedelta_field": timedelta(hours=1, minutes=30),
                "nested_dict": {
                    "level1": {
                        "level2": {
                            "level3": "deep_value"
                        }
                    }
                },
                "mixed_array": [1, "string", True, None, {"nested": "object"}],
                "unicode_text": "Hello 世界! 🌍 Emojis and unicode work",
                "large_number": 123456789012345678901234567890,
                "float_precision": 3.14159265359,
                "boolean_values": [True, False],
                "null_values": [None, None, None],
                "empty_containers": {"empty_dict": {}, "empty_list": []},
            }
            
            # Store complex data
            stored = await session_store.store_session("complex", complex_data)
            assert stored is True
            
            # Retrieve and verify
            retrieved = await session_store.retrieve_session("complex")
            assert retrieved is not None
            
            # Verify data integrity
            assert retrieved["id"] == "complex-session"
            assert retrieved["status"] == "active"
            assert retrieved["nested_dict"]["level1"]["level2"]["level3"] == "deep_value"
            assert retrieved["unicode_text"] == "Hello 世界! 🌍 Emojis and unicode work"
            assert len(retrieved["mixed_array"]) == 5
            assert retrieved["large_number"] == 123456789012345678901234567890
            assert abs(retrieved["float_precision"] - 3.14159265359) < 0.000001
            assert retrieved["boolean_values"] == [True, False]
            assert retrieved["null_values"] == [None, None, None]
            assert retrieved["empty_containers"]["empty_dict"] == {}
            assert retrieved["empty_containers"]["empty_list"] == []
            
            # Note: datetime objects are serialized as strings
            assert isinstance(retrieved["datetime_field"], str)
            
        finally:
            await redis_client.flushdb()
            await redis_client.close()