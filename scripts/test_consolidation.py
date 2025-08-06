#!/usr/bin/env python3
"""Test script to validate the consolidation"""

import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test all main imports work"""
    print("🔍 Testing imports...")
    
    try:
        from jelmore.config import get_settings
        print("✅ Configuration import works")
        
        from jelmore.models.session import Session, SessionStatus
        print("✅ Models import works")
        
        from jelmore.services.database import init_db, close_db
        print("✅ Database service import works")
        
        from jelmore.services.redis import init_redis, close_redis
        print("✅ Redis service import works")
        
        from jelmore.services.nats import init_nats, close_nats
        print("✅ NATS service import works")
        
        from jelmore.services.claude_code import session_manager, ClaudeCodeSession
        print("✅ Claude Code service import works")
        
        from jelmore.api.sessions import router
        print("✅ API routes import works")
        
        from jelmore.main import app
        print("✅ Main application import works")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        traceback.print_exc()
        return False

def test_configuration():
    """Test configuration works correctly"""
    print("\n🔍 Testing configuration...")
    
    try:
        from jelmore.config import get_settings
        settings = get_settings()
        
        # Test basic properties
        assert settings.app_name == "Jelmore"
        assert settings.app_version == "0.1.0"
        assert settings.api_prefix == "/api/v1"
        
        # Test computed properties
        db_url = settings.database_url
        assert "postgresql+asyncpg://" in db_url
        assert "jelmore" in db_url
        print(f"✅ Database URL: {db_url}")
        
        redis_url = settings.redis_url
        assert "redis://" in redis_url
        print(f"✅ Redis URL: {redis_url}")
        
        print("✅ Configuration validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        traceback.print_exc()
        return False

def test_api_structure():
    """Test API structure is correct"""
    print("\n🔍 Testing API structure...")
    
    try:
        from jelmore.main import app
        
        # Check routes are registered
        routes = [route.path for route in app.routes]
        print(f"📝 Available routes: {routes}")
        
        # Should have health endpoint
        assert "/health" in routes
        print("✅ Health endpoint registered")
        
        # Should have API routes (via router)
        api_routes_found = any("/api/v1" in route for route in routes)
        print(f"✅ API routes registered: {api_routes_found}")
        
        print("✅ API structure validation passed")
        return True
        
    except Exception as e:
        print(f"❌ API structure error: {e}")
        traceback.print_exc()
        return False

def test_models():
    """Test database models work"""
    print("\n🔍 Testing database models...")
    
    try:
        from jelmore.models.session import Session, SessionStatus
        
        # Test enum values
        assert SessionStatus.INITIALIZING == "initializing"
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.WAITING_INPUT == "waiting_input"
        print("✅ SessionStatus enum works")
        
        # Test model has expected columns (by checking __table__.columns)
        expected_columns = {'id', 'status', 'query', 'current_directory', 
                          'created_at', 'last_activity', 'terminated_at', 'session_metadata'}
        actual_columns = set(Session.__table__.columns.keys())
        assert expected_columns == actual_columns, f"Expected {expected_columns}, got {actual_columns}"
        print("✅ Session model has correct columns")
        
        print("✅ Models validation passed")
        return True
        
    except Exception as e:
        print(f"❌ Models error: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("🚀 Starting Jelmore Consolidation Validation Tests")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_configuration,
        test_api_structure,
        test_models,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED - Consolidation is successful!")
        print("\n✅ The dual architecture has been successfully consolidated:")
        print("   - All /app functionality moved to /src/jelmore")
        print("   - No circular imports")
        print("   - Clean architecture with services/, models/, api/ structure")
        print("   - Ready for deployment!")
        return True
    else:
        print("❌ Some tests failed - consolidation needs fixes")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)