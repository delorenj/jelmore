"""
Integration tests for provider switching and model selection
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime


class TestProviderSwitching:
    """Integration tests for provider switching functionality"""
    
    @pytest.fixture
    def mock_provider_factory(self):
        """Mock provider factory for testing"""
        factory = MagicMock()
        
        # Mock Claude Code provider
        claude_provider = AsyncMock()
        claude_provider.provider_type = "claude_code"
        claude_provider.is_available = True
        claude_provider.create_session.return_value = {
            "session_id": str(uuid.uuid4()),
            "provider": "claude_code",
            "status": "active"
        }
        
        # Mock OpenCode provider
        opencode_provider = AsyncMock()
        opencode_provider.provider_type = "opencode"
        opencode_provider.is_available = True
        opencode_provider.create_session.return_value = {
            "session_id": str(uuid.uuid4()),
            "provider": "opencode",
            "status": "active"
        }
        
        factory.get_provider.side_effect = lambda ptype: {
            "claude_code": claude_provider,
            "opencode": opencode_provider
        }.get(ptype)
        
        factory.get_available_providers.return_value = {
            "claude_code": claude_provider,
            "opencode": opencode_provider
        }
        
        return factory, claude_provider, opencode_provider
    
    @pytest.fixture
    def mock_model_selector(self, mock_provider_factory):
        """Mock model selector for testing"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        selector = MagicMock()
        selector.factory = factory
        
        # Mock selection logic
        async def select_provider(task_type="general", **kwargs):
            preferences = {
                "code_generation": claude_provider,
                "text_analysis": opencode_provider,
                "debugging": claude_provider,
                "documentation": opencode_provider
            }
            return preferences.get(task_type, claude_provider)
        
        selector.select_provider = select_provider
        return selector
    
    @pytest.mark.asyncio
    async def test_automatic_provider_selection(self, mock_model_selector):
        """Test automatic provider selection based on task type"""
        # Test code generation task
        provider = await mock_model_selector.select_provider("code_generation")
        assert provider.provider_type == "claude_code"
        
        # Test text analysis task
        provider = await mock_model_selector.select_provider("text_analysis")
        assert provider.provider_type == "opencode"
        
        # Test debugging task
        provider = await mock_model_selector.select_provider("debugging")
        assert provider.provider_type == "claude_code"
        
        # Test documentation task
        provider = await mock_model_selector.select_provider("documentation")
        assert provider.provider_type == "opencode"
        
        # Test unknown task (should default to claude_code)
        provider = await mock_model_selector.select_provider("unknown_task")
        assert provider.provider_type == "claude_code"
    
    @pytest.mark.asyncio
    async def test_provider_failover(self, mock_provider_factory):
        """Test provider failover when primary provider is unavailable"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Simulate Claude provider being unavailable
        claude_provider.is_available = False
        factory.get_available_providers.return_value = {
            "opencode": opencode_provider
        }
        
        # Mock selector with failover logic
        async def select_with_failover(task_type="general", **kwargs):
            available_providers = factory.get_available_providers()
            
            # Preferred order for code generation
            if task_type == "code_generation":
                for provider_type in ["claude_code", "opencode"]:
                    if provider_type in available_providers:
                        return available_providers[provider_type]
            
            # Return first available provider
            return list(available_providers.values())[0]
        
        # Test failover for code generation
        provider = await select_with_failover("code_generation")
        assert provider.provider_type == "opencode"  # Fell back to OpenCode
    
    @pytest.mark.asyncio
    async def test_concurrent_provider_usage(self, mock_provider_factory):
        """Test concurrent usage of multiple providers"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Create sessions using different providers concurrently
        tasks = []
        
        # Claude Code sessions
        for i in range(3):
            task = asyncio.create_task(
                claude_provider.create_session(f"Code task {i}")
            )
            tasks.append(task)
        
        # OpenCode sessions
        for i in range(3):
            task = asyncio.create_task(
                opencode_provider.create_session(f"Text task {i}")
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Verify all sessions were created
        assert len(results) == 6
        
        # Verify provider distribution
        claude_sessions = [r for r in results if r["provider"] == "claude_code"]
        opencode_sessions = [r for r in results if r["provider"] == "opencode"]
        
        assert len(claude_sessions) == 3
        assert len(opencode_sessions) == 3
    
    @pytest.mark.asyncio
    async def test_provider_health_monitoring(self, mock_provider_factory):
        """Test provider health monitoring and switching"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Initial state - both providers healthy
        claude_health = await claude_provider.health_check()
        opencode_health = await opencode_provider.health_check()
        
        assert claude_health["is_available"] is True
        assert opencode_health["is_available"] is True
        
        # Simulate Claude provider becoming unhealthy
        claude_provider.is_available = False
        claude_provider.health_check.return_value = {
            "provider_type": "claude_code",
            "is_available": False,
            "status": "unhealthy",
            "error": "Binary not found"
        }
        
        # Update factory's available providers
        factory.get_available_providers.return_value = {
            "opencode": opencode_provider
        }
        
        # Health check should reflect the change
        claude_health_after = await claude_provider.health_check()
        assert claude_health_after["is_available"] is False
        assert claude_health_after["status"] == "unhealthy"
        
        # Available providers should only include healthy ones
        available = factory.get_available_providers()
        assert "claude_code" not in available
        assert "opencode" in available
    
    @pytest.mark.asyncio
    async def test_session_migration_between_providers(self, mock_provider_factory):
        """Test migrating sessions between providers (conceptual)"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Create session on Claude provider
        claude_session = await claude_provider.create_session("Initial task")
        claude_session_id = claude_session["session_id"]
        
        # Simulate need to migrate (e.g., Claude provider becomes unavailable)
        claude_provider.is_available = False
        
        # Mock session state retrieval
        session_state = {
            "original_query": "Initial task",
            "conversation_history": [
                {"role": "user", "content": "Initial task"},
                {"role": "assistant", "content": "I'll help you with that task."}
            ],
            "current_context": "Working on initial task implementation"
        }
        
        # Create new session on OpenCode provider with migrated state
        migration_query = f"Continue from previous session: {session_state['original_query']}"
        opencode_session = await opencode_provider.create_session(migration_query)
        
        # Verify new session was created
        assert opencode_session["provider"] == "opencode"
        assert opencode_session["status"] == "active"
        
        # In a real implementation, you would:
        # 1. Extract state from old session
        # 2. Create new session with context
        # 3. Update client references
        # 4. Clean up old session
    
    @pytest.mark.asyncio
    async def test_load_balancing_across_providers(self, mock_provider_factory):
        """Test load balancing across multiple providers"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Mock load balancing logic
        session_counts = {"claude_code": 0, "opencode": 0}
        
        async def load_balanced_selection():
            available = factory.get_available_providers()
            
            # Simple round-robin load balancing
            if session_counts["claude_code"] <= session_counts["opencode"]:
                selected_type = "claude_code"
            else:
                selected_type = "opencode"
            
            session_counts[selected_type] += 1
            return available[selected_type]
        
        # Create multiple sessions with load balancing
        sessions = []
        for i in range(10):
            provider = await load_balanced_selection()
            session = await provider.create_session(f"Task {i}")
            sessions.append(session)
        
        # Verify load distribution
        claude_count = len([s for s in sessions if s["provider"] == "claude_code"])
        opencode_count = len([s for s in sessions if s["provider"] == "opencode"])
        
        # Should be roughly balanced (5-5 or 6-4)
        assert abs(claude_count - opencode_count) <= 1
    
    @pytest.mark.asyncio
    async def test_provider_performance_tracking(self, mock_provider_factory):
        """Test tracking provider performance for selection decisions"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Mock performance metrics
        performance_metrics = {
            "claude_code": {
                "average_response_time": 2.5,
                "success_rate": 0.98,
                "total_requests": 150,
                "failed_requests": 3
            },
            "opencode": {
                "average_response_time": 1.8,
                "success_rate": 0.95,
                "total_requests": 200,
                "failed_requests": 10
            }
        }
        
        # Mock performance-based selection
        async def performance_based_selection(task_type="general"):
            available = factory.get_available_providers()
            
            if task_type == "speed_critical":
                # Choose fastest provider
                best_provider = min(
                    available.items(),
                    key=lambda x: performance_metrics[x[0]]["average_response_time"]
                )
                return best_provider[1]
            elif task_type == "reliability_critical":
                # Choose most reliable provider
                best_provider = max(
                    available.items(),
                    key=lambda x: performance_metrics[x[0]]["success_rate"]
                )
                return best_provider[1]
            else:
                # Default selection
                return list(available.values())[0]
        
        # Test speed-critical selection
        speed_provider = await performance_based_selection("speed_critical")
        assert speed_provider.provider_type == "opencode"  # Faster response time
        
        # Test reliability-critical selection
        reliability_provider = await performance_based_selection("reliability_critical")
        assert reliability_provider.provider_type == "claude_code"  # Higher success rate
    
    @pytest.mark.asyncio
    async def test_provider_capacity_management(self, mock_provider_factory):
        """Test provider capacity management and throttling"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Mock capacity limits
        capacity_limits = {
            "claude_code": {"max_sessions": 5, "current_sessions": 0},
            "opencode": {"max_sessions": 10, "current_sessions": 0}
        }
        
        async def capacity_aware_selection():
            available = factory.get_available_providers()
            
            # Find provider with available capacity
            for provider_type, provider in available.items():
                capacity = capacity_limits[provider_type]
                if capacity["current_sessions"] < capacity["max_sessions"]:
                    capacity["current_sessions"] += 1
                    return provider
            
            # No capacity available
            raise RuntimeError("No provider capacity available")
        
        # Test normal capacity usage
        sessions = []
        for i in range(8):  # Within total capacity (5 + 10 = 15)
            provider = await capacity_aware_selection()
            session = await provider.create_session(f"Task {i}")
            sessions.append((provider.provider_type, session))
        
        # Verify capacity distribution
        claude_sessions = [s for ptype, s in sessions if ptype == "claude_code"]
        opencode_sessions = [s for ptype, s in sessions if ptype == "opencode"]
        
        # Claude should be at max capacity (5), remaining should go to OpenCode
        assert len(claude_sessions) == 5
        assert len(opencode_sessions) == 3
    
    @pytest.mark.asyncio
    async def test_provider_configuration_switching(self, mock_provider_factory):
        """Test switching provider configurations dynamically"""
        factory, claude_provider, opencode_provider = mock_provider_factory
        
        # Mock configuration updates
        initial_config = {
            "claude_code": {"max_turns": 10, "timeout": 60},
            "opencode": {"model": "gpt-4", "max_tokens": 4000}
        }
        
        updated_config = {
            "claude_code": {"max_turns": 20, "timeout": 120},  # Increased limits
            "opencode": {"model": "gpt-3.5-turbo", "max_tokens": 2000}  # Faster model
        }
        
        # Apply initial configuration
        claude_provider.config = initial_config["claude_code"]
        opencode_provider.config = initial_config["opencode"]
        
        # Create session with initial config
        initial_session = await claude_provider.create_session("Test with initial config")
        assert initial_session["provider"] == "claude_code"
        
        # Update configuration
        claude_provider.config = updated_config["claude_code"]
        opencode_provider.config = updated_config["opencode"]
        
        # Verify configuration was updated
        assert claude_provider.config["max_turns"] == 20
        assert claude_provider.config["timeout"] == 120
        assert opencode_provider.config["model"] == "gpt-3.5-turbo"
        
        # Create session with updated config
        updated_session = await claude_provider.create_session("Test with updated config")
        assert updated_session["provider"] == "claude_code"
        
        # Both sessions should exist but with different configurations
        assert initial_session["session_id"] != updated_session["session_id"]