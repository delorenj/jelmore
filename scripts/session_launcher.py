#!/usr/bin/env python3
"""
Interactive Claude Code Session Launcher
Quick tool to create and interact with Tonzies sessions
"""
import asyncio
import httpx
import websockets
import json
import sys
from typing import Optional


class TonziesClient:
    """Client for interacting with Tonzies API"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api/v1"
        self.session_id: Optional[str] = None
    
    async def create_session(self, query: str) -> dict:
        """Create a new session"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_url}/session",
                json={"query": query}
            )
            if resp.status_code == 200:
                session = resp.json()
                self.session_id = session["id"]
                return session
            else:
                raise Exception(f"Failed to create session: {resp.text}")
    
    async def stream_output(self):
        """Stream session output via WebSocket"""
        if not self.session_id:
            raise Exception("No active session")
        
        ws_url = f"ws://localhost:8000/api/v1/session/{self.session_id}/stream"
        
        async with websockets.connect(ws_url) as websocket:
            print(f"📡 Connected to session {self.session_id}")
            print("-" * 50)
            
            async for message in websocket:
                data = json.loads(message)
                
                # Display different message types
                if data.get("type") == "user":
                    print(f"\n👤 USER: {data.get('content', '')}")
                elif data.get("type") == "assistant":
                    print(f"\n🤖 CLAUDE: {data.get('content', '')}")
                elif data.get("type") == "tool_use":
                    tool = data.get("name", "unknown")
                    if tool == "bash":
                        cmd = data.get("input", {}).get("command", "")
                        print(f"\n⚡ COMMAND: {cmd}")
                elif data.get("type") == "tool_result":
                    output = data.get("content", "")
                    if output:
                        print(f"📋 OUTPUT:\n{output[:500]}")  # Truncate long outputs
                elif data.get("type") == "system":
                    content = data.get("content", "")
                    if "waiting" in content.lower():
                        print(f"\n⏳ SYSTEM: Waiting for input...")
                    else:
                        print(f"\n💭 SYSTEM: {content}")

    async def send_input(self, input_text: str):
        """Send input to waiting session"""
        if not self.session_id:
            raise Exception("No active session")
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.api_url}/session/{self.session_id}/input",
                json={"input": input_text}
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to send input: {resp.text}")
    
    async def terminate_session(self):
        """Terminate the current session"""
        if not self.session_id:
            return
        
        async with httpx.AsyncClient() as client:
            await client.delete(f"{self.api_url}/session/{self.session_id}")
            print(f"\n🛑 Session {self.session_id} terminated")
            self.session_id = None


async def main():
    """Main interactive loop"""
    print("🚀 Tonzies Session Launcher")
    print("=" * 50)
    
    # Get initial query
    query = input("\n💬 Enter your initial query for Claude Code:\n> ")
    
    if not query:
        print("❌ No query provided")
        return
    
    client = TonziesClient()
    
    try:
        # Create session
        print(f"\n🔄 Creating session...")
        session = await client.create_session(query)
        print(f"✅ Session created: {session['id']}")
        print(f"📁 Working directory: {session['current_directory']}")
        
        # Stream output
        print("\n📡 Streaming output (Ctrl+C to stop)...")
        await client.stream_output()
        
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        await client.terminate_session()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        await client.terminate_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
