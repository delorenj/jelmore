#!/usr/bin/env python3
"""
Quick test script for Tonzies API
"""
import asyncio
import httpx
import json


async def test_tonzies():
    """Test basic Tonzies functionality"""
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # Test health endpoint
        print("🏥 Testing health endpoint...")
        resp = await client.get(f"{base_url}/health")
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {resp.json()}")
        
        # Create a session
        print("\n🚀 Creating a new session...")
        resp = await client.post(
            f"{base_url}/api/v1/session",
            json={"query": "What directory am I in? List the files here."}
        )
        
        if resp.status_code == 200:
            session = resp.json()
            print(f"   Session ID: {session['id']}")
            print(f"   Status: {session['status']}")
            print(f"   Directory: {session['current_directory']}")
            
            # List sessions
            print("\n📋 Listing all sessions...")
            resp = await client.get(f"{base_url}/api/v1/sessions")
            sessions = resp.json()
            print(f"   Active sessions: {len(sessions)}")
            
            # Get session details
            print(f"\n🔍 Getting session details...")
            resp = await client.get(f"{base_url}/api/v1/session/{session['id']}")
            details = resp.json()
            print(f"   Status: {details['status']}")
            print(f"   Last activity: {details['last_activity']}")
            
            # Wait a bit then terminate
            print("\n⏰ Waiting 5 seconds...")
            await asyncio.sleep(5)
            
            print(f"\n🛑 Terminating session...")
            resp = await client.delete(f"{base_url}/api/v1/session/{session['id']}")
            print(f"   Response: {resp.json()}")
        else:
            print(f"   Error: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    asyncio.run(test_tonzies())
