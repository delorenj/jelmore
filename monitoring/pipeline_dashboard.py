#!/usr/bin/env python3
"""
Jelmore Pipeline Dashboard - Real-time Monitoring Interface
Web dashboard for monitoring pipeline status, metrics, and alerts
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from pathlib import Path
import aiofiles
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import structlog
from .pipeline_monitor_hub import PipelineMonitorHub

# Initialize logger
logger = structlog.get_logger()

class PipelineDashboard:
    """Real-time dashboard for pipeline monitoring"""
    
    def __init__(self, monitor_hub: PipelineMonitorHub):
        self.monitor_hub = monitor_hub
        self.app = FastAPI(title="Jelmore Pipeline Dashboard")
        self.active_connections: List[WebSocket] = []
        self.log_directory = Path("/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log")
        
        # Setup routes
        self._setup_routes()
        
        # Start background tasks
        asyncio.create_task(self._broadcast_updates())
        
        logger.info("📊 Pipeline Dashboard initialized")

    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard_home(request: Request):
            """Main dashboard page"""
            return await self._render_dashboard()

        @self.app.get("/api/dashboard")
        async def get_dashboard_data():
            """Get current dashboard data"""
            return self.monitor_hub.get_dashboard_data()

        @self.app.get("/api/logs/{log_type}")
        async def get_logs(log_type: str, lines: int = 100):
            """Get log files"""
            try:
                log_file = self.log_directory / f"{log_type}.log"
                if not log_file.exists():
                    return {"error": f"Log file {log_type}.log not found"}
                
                async with aiofiles.open(log_file, 'r') as f:
                    content = await f.read()
                    log_lines = content.split('\n')[-lines:]
                    return {"logs": log_lines, "count": len(log_lines)}
            except Exception as e:
                logger.error("Failed to read logs", log_type=log_type, error=str(e))
                return {"error": str(e)}

        @self.app.get("/api/sessions")
        async def get_sessions():
            """Get all session data"""
            return {
                "sessions": self.monitor_hub.session_registry,
                "count": len(self.monitor_hub.session_registry)
            }

        @self.app.get("/api/metrics/history")
        async def get_metrics_history():
            """Get metrics history"""
            return {
                "history": list(self.monitor_hub.performance_history),
                "count": len(self.monitor_hub.performance_history)
            }

        @self.app.get("/api/alerts")
        async def get_alerts():
            """Get current alerts"""
            return {
                "alerts": self.monitor_hub.anomaly_detections,
                "count": len(self.monitor_hub.anomaly_detections)
            }

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates"""
            await websocket.accept()
            self.active_connections.append(websocket)
            
            try:
                while True:
                    # Send periodic updates
                    data = self.monitor_hub.get_dashboard_data()
                    await websocket.send_json({
                        "type": "dashboard_update",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    await asyncio.sleep(5)  # Update every 5 seconds
                    
            except WebSocketDisconnect:
                self.active_connections.remove(websocket)
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)

    async def _render_dashboard(self) -> str:
        """Render dashboard HTML"""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jelmore Pipeline Monitor</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
        }
        .container { 
            max-width: 1400px; 
            margin: 0 auto; 
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .status-badge {
            display: inline-block;
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: bold;
            margin: 5px;
        }
        .status-healthy { background: #4CAF50; }
        .status-unhealthy { background: #f44336; }
        .status-degraded { background: #ff9800; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 15px;
            padding: 20px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .card h2 {
            margin-bottom: 15px;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
            padding: 10px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
        }
        .metric-value {
            font-weight: bold;
            font-size: 1.2em;
        }
        .logs-container {
            max-height: 400px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 15px;
            font-family: monospace;
            font-size: 0.9em;
        }
        .log-line {
            margin: 2px 0;
            padding: 2px 5px;
            border-radius: 3px;
        }
        .log-error { background: rgba(244, 67, 54, 0.3); }
        .log-warning { background: rgba(255, 152, 0, 0.3); }
        .log-info { background: rgba(76, 175, 80, 0.3); }
        .alert {
            background: rgba(244, 67, 54, 0.2);
            border: 1px solid #f44336;
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
        }
        .chart-container {
            position: relative;
            height: 300px;
            margin: 20px 0;
        }
        .connection-status {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: bold;
        }
        .connected { background: #4CAF50; }
        .disconnected { background: #f44336; }
        .session-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
            max-height: 400px;
            overflow-y: auto;
        }
        .session-card {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 15px;
            border-left: 4px solid;
        }
        .session-active { border-left-color: #4CAF50; }
        .session-completed { border-left-color: #2196F3; }
        .session-failed { border-left-color: #f44336; }
    </style>
</head>
<body>
    <div class="connection-status" id="connectionStatus">🔌 Connecting...</div>
    
    <div class="container">
        <div class="header">
            <h1>🐝 Jelmore Pipeline Monitor</h1>
            <p>Real-time monitoring of PR processing sessions and pipeline health</p>
            <div id="overallStatus">
                <span class="status-badge status-healthy" id="statusBadge">🟢 Initializing...</span>
            </div>
        </div>

        <div class="grid">
            <!-- System Metrics -->
            <div class="card">
                <h2>📊 System Metrics</h2>
                <div class="metric">
                    <span>Active Sessions</span>
                    <span class="metric-value" id="activeSessions">0</span>
                </div>
                <div class="metric">
                    <span>Total Sessions</span>
                    <span class="metric-value" id="totalSessions">0</span>
                </div>
                <div class="metric">
                    <span>Success Rate</span>
                    <span class="metric-value" id="successRate">0%</span>
                </div>
                <div class="metric">
                    <span>Error Rate</span>
                    <span class="metric-value" id="errorRate">0%</span>
                </div>
                <div class="metric">
                    <span>Agent Health</span>
                    <span class="metric-value" id="agentHealth">100%</span>
                </div>
            </div>

            <!-- Performance Chart -->
            <div class="card">
                <h2>📈 Performance Trends</h2>
                <div class="chart-container">
                    <canvas id="performanceChart"></canvas>
                </div>
            </div>

            <!-- Recent Events -->
            <div class="card">
                <h2>🔄 Recent Events</h2>
                <div id="recentEvents" class="logs-container">
                    <div class="log-line">Waiting for events...</div>
                </div>
            </div>

            <!-- Alerts -->
            <div class="card">
                <h2>🚨 Active Alerts</h2>
                <div id="alertsContainer">
                    <p>No active alerts</p>
                </div>
            </div>

            <!-- Active Sessions -->
            <div class="card">
                <h2>💼 Active Sessions</h2>
                <div id="sessionsContainer" class="session-grid">
                    <div class="session-card session-active">
                        <div>No active sessions</div>
                    </div>
                </div>
            </div>

            <!-- System Health -->
            <div class="card">
                <h2>🏥 Component Health</h2>
                <div id="componentHealth">
                    <div class="metric">
                        <span>Jelmore API</span>
                        <span class="status-badge status-healthy">🟢 Healthy</span>
                    </div>
                    <div class="metric">
                        <span>NATS</span>
                        <span class="status-badge status-healthy">🟢 Healthy</span>
                    </div>
                    <div class="metric">
                        <span>N8N Webhook</span>
                        <span class="status-badge status-healthy">🟢 Healthy</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Real-time Logs -->
        <div class="card">
            <h2>📋 Real-time Logs</h2>
            <div id="realTimeLogs" class="logs-container">
                <div class="log-line log-info">[INFO] Dashboard initialized</div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let performanceChart = null;
        let isConnected = false;

        // Initialize WebSocket connection
        function initWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = function() {
                isConnected = true;
                updateConnectionStatus();
                console.log('WebSocket connected');
            };
            
            ws.onmessage = function(event) {
                const message = JSON.parse(event.data);
                if (message.type === 'dashboard_update') {
                    updateDashboard(message.data);
                }
            };
            
            ws.onclose = function() {
                isConnected = false;
                updateConnectionStatus();
                console.log('WebSocket disconnected. Attempting to reconnect...');
                setTimeout(initWebSocket, 5000);
            };
            
            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
                isConnected = false;
                updateConnectionStatus();
            };
        }

        function updateConnectionStatus() {
            const statusEl = document.getElementById('connectionStatus');
            if (isConnected) {
                statusEl.textContent = '🟢 Connected';
                statusEl.className = 'connection-status connected';
            } else {
                statusEl.textContent = '🔴 Disconnected';
                statusEl.className = 'connection-status disconnected';
            }
        }

        function updateDashboard(data) {
            // Update metrics
            document.getElementById('activeSessions').textContent = data.active_sessions || 0;
            document.getElementById('totalSessions').textContent = data.session_count || 0;
            document.getElementById('successRate').textContent = `${(data.metrics?.success_rate || 0).toFixed(1)}%`;
            document.getElementById('errorRate').textContent = `${(data.metrics?.error_rate || 0).toFixed(1)}%`;
            document.getElementById('agentHealth').textContent = `${(data.metrics?.agent_health_score || 100).toFixed(1)}%`;

            // Update recent events
            const eventsContainer = document.getElementById('recentEvents');
            if (data.recent_events && data.recent_events.length > 0) {
                eventsContainer.innerHTML = data.recent_events
                    .slice(-10)
                    .map(event => `<div class="log-line log-info">[${new Date(event.timestamp).toLocaleTimeString()}] ${event.event_type}: ${event.session_id}</div>`)
                    .join('');
            }

            // Update alerts
            const alertsContainer = document.getElementById('alertsContainer');
            if (data.alerts && data.alerts.length > 0) {
                alertsContainer.innerHTML = data.alerts
                    .slice(-5)
                    .map(alert => `<div class="alert"><strong>${alert.alert_type}</strong><br>${JSON.stringify(alert.details)}</div>`)
                    .join('');
            } else {
                alertsContainer.innerHTML = '<p>No active alerts</p>';
            }

            // Update status badge
            const statusBadge = document.getElementById('statusBadge');
            if (data.monitoring_status === 'active') {
                statusBadge.textContent = '🟢 Active';
                statusBadge.className = 'status-badge status-healthy';
            } else {
                statusBadge.textContent = '🔴 Inactive';
                statusBadge.className = 'status-badge status-unhealthy';
            }

            // Update performance chart
            updatePerformanceChart(data);
        }

        function initPerformanceChart() {
            const ctx = document.getElementById('performanceChart').getContext('2d');
            performanceChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Success Rate %',
                            data: [],
                            borderColor: '#4CAF50',
                            backgroundColor: 'rgba(76, 175, 80, 0.1)',
                            tension: 0.4
                        },
                        {
                            label: 'Error Rate %',
                            data: [],
                            borderColor: '#f44336',
                            backgroundColor: 'rgba(244, 67, 54, 0.1)',
                            tension: 0.4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            labels: { color: 'white' }
                        }
                    },
                    scales: {
                        x: { 
                            ticks: { color: 'white' },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        },
                        y: { 
                            ticks: { color: 'white' },
                            grid: { color: 'rgba(255, 255, 255, 0.1)' }
                        }
                    }
                }
            });
        }

        function updatePerformanceChart(data) {
            if (!performanceChart || !data.metrics) return;

            const now = new Date().toLocaleTimeString();
            const chart = performanceChart;
            
            // Keep last 20 data points
            if (chart.data.labels.length >= 20) {
                chart.data.labels.shift();
                chart.data.datasets[0].data.shift();
                chart.data.datasets[1].data.shift();
            }
            
            chart.data.labels.push(now);
            chart.data.datasets[0].data.push(data.metrics.success_rate || 0);
            chart.data.datasets[1].data.push(data.metrics.error_rate || 0);
            
            chart.update('none');
        }

        // Initialize everything
        document.addEventListener('DOMContentLoaded', function() {
            initWebSocket();
            initPerformanceChart();
        });
    </script>
</body>
</html>
        """

    async def _broadcast_updates(self):
        """Broadcast updates to all connected WebSocket clients"""
        while True:
            if self.active_connections:
                try:
                    data = self.monitor_hub.get_dashboard_data()
                    message = {
                        "type": "dashboard_update",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    
                    # Send to all connected clients
                    disconnected = []
                    for connection in self.active_connections:
                        try:
                            await connection.send_json(message)
                        except:
                            disconnected.append(connection)
                    
                    # Remove disconnected clients
                    for connection in disconnected:
                        self.active_connections.remove(connection)
                        
                except Exception as e:
                    logger.error("Broadcast error", error=str(e))
            
            await asyncio.sleep(5)  # Broadcast every 5 seconds

    async def start_server(self, host: str = "0.0.0.0", port: int = 8001):
        """Start the dashboard server"""
        logger.info(f"🚀 Starting Pipeline Dashboard server on http://{host}:{port}")
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()

# Main execution for dashboard
async def run_dashboard():
    """Run the dashboard independently"""
    monitor_hub = PipelineMonitorHub()
    await monitor_hub.initialize()
    
    dashboard = PipelineDashboard(monitor_hub)
    await dashboard.start_server()

if __name__ == "__main__":
    asyncio.run(run_dashboard())