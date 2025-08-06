"""
Provider System Usage Examples

Demonstrates how to use the Jelmore provider abstraction layer
with different AI providers and configuration scenarios.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from src.jelmore.providers import (
    ProviderFactory,
    get_provider_factory,
    SessionConfig,
    create_session_with_auto_selection
)
from src.jelmore.providers.config import load_provider_config, get_provider_config_dict


async def example_basic_usage():
    """Example 1: Basic provider usage"""
    print("\n=== Example 1: Basic Provider Usage ===")
    
    factory = get_provider_factory()
    
    # Configure Claude provider
    claude_config = {
        "claude_bin": "claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "max_concurrent_sessions": 5,
        "max_turns": 10,
        "timeout_seconds": 300
    }
    
    # Create Claude provider
    claude_provider = await factory.create_provider("claude", claude_config)
    print(f"Created Claude provider: {claude_provider.name}")
    print(f"Available models: {[m.name for m in claude_provider.available_models]}")
    
    # Create a session
    session_config = SessionConfig(
        model="claude-3-5-sonnet-20241022",
        max_turns=5,
        temperature=0.7
    )
    
    session = await claude_provider.create_session(
        query="Hello! Can you help me write a Python function?",
        config=session_config
    )
    
    print(f"Created session: {session.session_id}")
    
    # Stream responses
    print("Streaming responses:")
    async for response in session.stream_output():
        print(f"[{response.event_type}] {response.content[:100]}...")
        if response.event_type.value in ["error", "assistant"]:
            break
    
    # Clean up
    await claude_provider.terminate_session(session.session_id)
    await factory.shutdown_provider("claude")


async def example_multi_provider():
    """Example 2: Multiple providers with auto-selection"""
    print("\n=== Example 2: Multiple Providers with Auto-Selection ===")
    
    factory = get_provider_factory()
    
    # Configure multiple providers
    claude_config = {
        "claude_bin": "claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "max_concurrent_sessions": 5
    }
    
    opencode_config = {
        "opencode_bin": "opencode",
        "api_endpoint": "http://localhost:8080",
        "default_model": "deepseek-v3",
        "max_concurrent_sessions": 10
    }
    
    # Create providers
    claude_provider = await factory.create_provider("claude", claude_config)
    opencode_provider = await factory.create_provider("opencode", opencode_config)
    
    # Set default
    factory.set_default_provider("claude")
    
    print("Available providers:", factory.list_active_providers())
    
    # Test auto-selection scenarios
    scenarios = [
        {
            "name": "Claude-specific model",
            "requirements": {"model": "claude-3-5-sonnet-20241022"},
            "query": "Explain quantum computing"
        },
        {
            "name": "DeepSeek model", 
            "requirements": {"model": "deepseek-v3"},
            "query": "Write a sorting algorithm"
        },
        {
            "name": "Load balancing",
            "requirements": {"load_balancing": True},
            "query": "Analyze this code structure"
        },
        {
            "name": "Cost optimization",
            "requirements": {"cost_optimization": True},
            "query": "Simple greeting response"
        }
    ]
    
    for scenario in scenarios:
        print(f"\nScenario: {scenario['name']}")
        
        # Auto-select provider
        selected_provider = await factory.select_best_provider(scenario["requirements"])
        print(f"Selected provider: {selected_provider}")
        
        if selected_provider:
            provider = await factory.get_provider(selected_provider)
            session = await provider.create_session(scenario["query"])
            
            print(f"Created session {session.session_id} with {provider.name}")
            
            # Get a few response chunks
            count = 0
            async for response in session.stream_output():
                print(f"  [{response.event_type}] {response.content[:50]}...")
                count += 1
                if count >= 2 or response.event_type.value in ["error"]:
                    break
            
            await provider.terminate_session(session.session_id)
    
    # Health check all providers
    health_results = await factory.health_check_all()
    print("\nHealth check results:")
    for provider_name, health in health_results.items():
        print(f"  {provider_name}: {health['status']}")
    
    # Get metrics
    metrics = await factory.get_provider_metrics()
    print(f"\nSystem metrics:")
    print(f"  Total providers: {metrics['total_providers']}")
    print(f"  Default provider: {metrics['default_provider']}")
    
    await factory.shutdown_all_providers()


async def example_configuration_file():
    """Example 3: Configuration from file"""
    print("\n=== Example 3: Configuration from File ===")
    
    # Create example config file
    config_path = Path("examples/provider_config.json")
    config_path.parent.mkdir(exist_ok=True)
    
    example_config = {
        "default_provider": "claude",
        "auto_selection": True,
        "load_balancing": True,
        "cost_optimization": False,
        "claude": {
            "enabled": True,
            "claude_bin": "claude",
            "default_model": "claude-3-5-sonnet-20241022",
            "max_concurrent_sessions": 8
        },
        "opencode": {
            "enabled": True,
            "opencode_bin": "opencode",
            "api_endpoint": "http://localhost:8080",
            "default_model": "kimi-k2",
            "max_concurrent_sessions": 15
        }
    }
    
    with open(config_path, "w") as f:
        json.dump(example_config, f, indent=2)
    
    print(f"Created config file: {config_path}")
    
    # Load configuration
    config = load_provider_config(config_path)
    print(f"Loaded configuration:")
    print(f"  Default provider: {config.default_provider}")
    print(f"  Claude enabled: {config.claude.enabled}")
    print(f"  OpenCode enabled: {config.opencode.enabled}")
    
    # Initialize providers from config
    from src.jelmore.providers.factory import initialize_providers
    
    config_dict = get_provider_config_dict(config)
    factory = await initialize_providers(config_dict)
    
    print(f"Initialized providers: {factory.list_active_providers()}")
    
    # Test with configuration
    session_config = SessionConfig(model=config.claude.default_model)
    default_provider = await factory.get_default_provider()
    
    if default_provider:
        session = await default_provider.create_session(
            "Test session with file configuration",
            session_config
        )
        
        print(f"Created session with configured provider: {session.session_id}")
        
        # Get session status
        status = await session.get_status()
        print(f"Session status: {status['status']}")
        print(f"Model: {status['model']}")
        
        await default_provider.terminate_session(session.session_id)
    
    await factory.shutdown_all_providers()


async def example_advanced_features():
    """Example 4: Advanced features - suspension, resumption, etc."""
    print("\n=== Example 4: Advanced Features ===")
    
    factory = get_provider_factory()
    
    # Create provider with specific capabilities
    claude_config = {
        "claude_bin": "claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "max_concurrent_sessions": 3
    }
    
    provider = await factory.create_provider("claude", claude_config)
    
    # Create session
    session = await provider.create_session("Let's work on a multi-step coding task")
    print(f"Created session: {session.session_id}")
    
    # Process initial response
    response_count = 0
    async for response in session.stream_output():
        print(f"Initial response [{response.event_type}]: {response.content[:80]}...")
        response_count += 1
        if response_count >= 2:
            break
    
    # Demonstrate session suspension
    print("\nSuspending session...")
    session_state = await session.suspend()
    print(f"Session suspended, state keys: {list(session_state.keys())}")
    
    # Create a new session and resume
    new_session = await provider.create_session("dummy", session_id=session.session_id)
    await new_session.resume(session_state)
    print(f"Session resumed: {new_session.session_id}")
    
    # Send follow-up message
    if new_session.status.value in ["idle", "active"]:
        await new_session.send_message("Please continue with the previous task")
        
        # Get response
        async for response in new_session.stream_output():
            print(f"Resume response [{response.event_type}]: {response.content[:80]}...")
            if response.event_type.value in ["assistant", "error"]:
                break
    
    # Demonstrate provider capabilities
    print(f"\nProvider capabilities:")
    caps = provider.capabilities
    print(f"  Streaming: {caps.supports_streaming}")
    print(f"  Tools: {caps.supports_tools}")
    print(f"  Multimodal: {caps.supports_multimodal}")
    print(f"  Max sessions: {caps.max_concurrent_sessions}")
    
    # Get model information
    model_info = provider.get_model_info("claude-3-5-sonnet-20241022")
    if model_info:
        print(f"\nModel info:")
        print(f"  Name: {model_info.name}")
        print(f"  Context length: {model_info.context_length}")
        print(f"  Capabilities: {model_info.capabilities}")
        print(f"  Max tokens: {model_info.max_tokens}")
    
    await provider.terminate_session(new_session.session_id)
    await factory.shutdown_provider("claude")


async def example_error_handling():
    """Example 5: Error handling and resilience"""
    print("\n=== Example 5: Error Handling and Resilience ===")
    
    factory = get_provider_factory()
    
    try:
        # Try to create provider with invalid config
        invalid_config = {
            "claude_bin": "/nonexistent/path/claude",
            "default_model": "invalid-model"
        }
        
        provider = await factory.create_provider("claude", invalid_config)
        print("This should not print - provider creation should fail")
        
    except Exception as e:
        print(f"Expected error creating provider with invalid config: {e}")
    
    # Create valid provider
    valid_config = {
        "claude_bin": "claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "max_concurrent_sessions": 2
    }
    
    try:
        provider = await factory.create_provider("claude", valid_config)
        print("Created provider with valid config")
        
        # Test session limits
        sessions = []
        for i in range(3):  # Try to exceed max_concurrent_sessions
            try:
                session = await provider.create_session(f"Session {i+1}")
                sessions.append(session)
                print(f"Created session {i+1}: {session.session_id}")
            except Exception as e:
                print(f"Expected error creating session {i+1}: {e}")
        
        # Test invalid model
        try:
            invalid_config = SessionConfig(model="nonexistent-model")
            session = await provider.create_session("test", invalid_config)
        except Exception as e:
            print(f"Expected error with invalid model: {e}")
        
        # Cleanup created sessions
        for session in sessions:
            await provider.terminate_session(session.session_id)
        
        await factory.shutdown_provider("claude")
        
    except Exception as e:
        print(f"Unexpected error: {e}")


async def main():
    """Run all examples"""
    print("Jelmore Provider System Examples")
    print("=" * 40)
    
    examples = [
        example_basic_usage,
        example_multi_provider,
        example_configuration_file,
        example_advanced_features,
        example_error_handling
    ]
    
    for example_func in examples:
        try:
            await example_func()
            print("\n" + "─" * 40)
        except Exception as e:
            print(f"\nExample failed: {e}")
            print("─" * 40)
        
        # Small delay between examples
        await asyncio.sleep(0.5)
    
    print("\nAll examples completed!")


if __name__ == "__main__":
    asyncio.run(main())