# Jelmore Pipeline Monitoring System 🐝

## Overview

The Jelmore Pipeline Monitoring System is a comprehensive, real-time monitoring solution for tracking PR processing sessions from n8n webhooks, detecting failures, and providing immediate alerts. The system monitors the complete pipeline at http://192.168.1.12:8000 and logs everything to structured log files.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   N8N Webhook   │───▶│ Webhook Tracker  │───▶│ Session Manager │
│ (PR Events)     │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Alert System  │◀───│ Pipeline Monitor │───▶│ Advanced Logger │
│                 │    │      Hub         │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                ▼
                       ┌──────────────────┐
                       │  Web Dashboard   │
                       │ (Real-time UI)   │
                       └──────────────────┘
```

## Components

### 1. Pipeline Monitor Hub (`pipeline_monitor_hub.py`)
- **Purpose**: Central nervous system for monitoring
- **Features**: 
  - Subscribes to NATS events (`jelmore.*`)
  - Tracks session lifecycle
  - Detects anomalies and timeouts
  - Coordinates all monitoring components

### 2. Webhook Tracker (`webhook_tracker.py`)
- **Purpose**: Monitor n8n webhook sessions
- **Features**:
  - Correlates webhook events with sessions
  - Tracks session processing stages
  - Detects stuck/failed sessions
  - Pattern recognition for spam detection

### 3. Advanced Logger (`log/logger.py`)
- **Purpose**: Structured logging with categories
- **Features**:
  - Multiple log categories (pipeline, session, webhook, api, nats, system, performance, security)
  - Automatic log rotation
  - Real-time log buffer
  - Searchable log history

### 4. Alert System (`alert_system.py`)
- **Purpose**: Multi-channel alerting with escalation
- **Features**:
  - Multiple channels (console, log file, webhook, email)
  - Escalation policies
  - Cooldown periods
  - Alert acknowledgment/resolution

### 5. Web Dashboard (`pipeline_dashboard.py`)
- **Purpose**: Real-time monitoring interface
- **Features**:
  - Live metrics and charts
  - Session tracking
  - Alert management
  - WebSocket real-time updates

## Quick Start

### 1. Start the Monitoring System

```bash
# Make startup script executable (if not already)
chmod +x ./scripts/start_pipeline_monitor.sh

# Start monitoring
./scripts/start_pipeline_monitor.sh start
```

### 2. Access the Dashboard

Open your browser and navigate to: **http://localhost:8001**

### 3. View Logs

```bash
# View recent logs
./scripts/start_pipeline_monitor.sh logs

# Check system status
./scripts/start_pipeline_monitor.sh status
```

## Monitoring Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| **Dashboard** | http://localhost:8001 | Real-time monitoring interface |
| **Jelmore API** | http://192.168.1.12:8000 | Main API being monitored |
| **N8N Webhook** | http://192.168.1.12:5678/webhook/pr-events | Webhook endpoint |
| **NATS Server** | nats://192.168.1.12:4222 | Event streaming |

## Log Files

All logs are stored in `/home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/`:

- **`pipeline.log`** - Pipeline events and session lifecycle
- **`sessions.log`** - Session-specific activities  
- **`webhooks.log`** - Webhook events from n8n
- **`api.log`** - API interactions and responses
- **`nats.log`** - NATS messaging events
- **`system.log`** - System health and monitoring
- **`performance.log`** - Performance metrics and benchmarks
- **`security.log`** - Security events and alerts
- **`alerts.log`** - All triggered alerts

## Alert Configuration

### Alert Channels

1. **Console** - Immediate alerts with color coding
2. **Log File** - All alerts logged to `alerts.log`
3. **Webhook** - Slack/Teams integration (configure in `alert_config.json`)
4. **Email** - SMTP email alerts (configure in `alert_config.json`)

### Alert Severities

- **🔴 Critical** - System failures, security breaches
- **🟠 High** - Session failures, high error rates  
- **🟡 Medium** - Performance issues, warnings
- **🔵 Low** - Informational alerts

### Escalation Policies

Alerts can escalate based on time and conditions:

1. **Critical Session Failure** - 5min → 15min → 30min escalation
2. **Performance Issues** - 10min → 30min escalation  
3. **External Service Issues** - 2min → 10min escalation
4. **Data/Security Issues** - Immediate escalation

## Configuration

### Main Config (`alert_config.json`)

```json
{
  "channels": {
    "webhook": {
      "enabled": true,
      "config": {
        "url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
      }
    }
  }
}
```

### Environment Variables

Set these in your environment or `.env` file:

```bash
# Optional: Override default URLs
JELMORE_API_URL="http://192.168.1.12:8000"
N8N_WEBHOOK_URL="http://192.168.1.12:5678/webhook/pr-events"
NATS_URL="nats://192.168.1.12:4222"

# Optional: Alert configuration
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK"
ALERT_EMAIL_TO="admin@yourorg.com"
```

## API Endpoints

The monitoring system exposes several API endpoints:

### Dashboard Data
```bash
curl http://localhost:8001/api/dashboard
```

### Session Information  
```bash
curl http://localhost:8001/api/sessions
```

### Recent Logs
```bash
curl http://localhost:8001/api/logs/pipeline?lines=50
```

### Metrics History
```bash
curl http://localhost:8001/api/metrics/history
```

### Active Alerts
```bash
curl http://localhost:8001/api/alerts
```

## Troubleshooting

### Common Issues

#### 1. Dashboard Not Loading
```bash
# Check if service is running
./scripts/start_pipeline_monitor.sh status

# Check logs for errors
./scripts/start_pipeline_monitor.sh logs

# Restart if needed
./scripts/start_pipeline_monitor.sh restart
```

#### 2. No Webhook Events
```bash
# Test webhook endpoint accessibility
curl -X POST http://192.168.1.12:5678/webhook/pr-events \
  -H "Content-Type: application/json" \
  -d '{"test": "event"}'

# Check if n8n is running
curl http://192.168.1.12:5678/healthz
```

#### 3. Missing Session Data
```bash
# Check Jelmore API
curl http://192.168.1.12:8000/api/v1/sessions/stats

# Check NATS connectivity
./scripts/start_pipeline_monitor.sh check
```

#### 4. Logs Not Writing
```bash
# Check permissions
ls -la /home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/

# Check disk space
df -h /home/delorenj/code/projects/33GOD/jelmore/
```

### Log Analysis

#### Search for Specific Session
```bash
grep "session-id-here" /home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/*.log
```

#### Find Recent Errors
```bash
grep -i error /home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/*.log | tail -20
```

#### Monitor Webhook Activity
```bash
tail -f /home/delorenj/code/projects/33GOD/jelmore/hive/monitor/log/webhooks.log
```

## Performance Monitoring

The system tracks several performance metrics:

- **Session Success Rate** - Percentage of successful session completions
- **Average Processing Time** - Time from webhook to completion
- **Webhook Throughput** - Events processed per hour
- **System Resource Usage** - CPU, memory, disk usage
- **Alert Frequency** - Rate of alerts being triggered

## Maintenance

### Daily Tasks
- Review dashboard for any persistent alerts
- Check log file sizes and rotation
- Verify all external dependencies are healthy

### Weekly Tasks  
- Review performance trends
- Update alert thresholds if needed
- Clean up old archived logs

### Monthly Tasks
- Review and update escalation policies
- Performance optimization review
- Update monitoring documentation

## Integration with Jelmore

The monitoring system integrates with Jelmore through:

1. **API Monitoring** - Health checks and metrics from `/api/v1/sessions/stats`
2. **NATS Events** - Subscribes to `jelmore.*` events
3. **Session Tracking** - Correlates webhook events with session lifecycle
4. **Performance Metrics** - Tracks processing times and success rates

## Security Considerations

- Logs may contain sensitive information - ensure proper access controls
- Webhook URLs should use HTTPS in production
- Alert channels should be secured (use app passwords for email)
- Monitor for suspicious webhook patterns

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review log files for error details
3. Check the monitoring dashboard for system health
4. Review alert notifications for system issues

## Development

To extend the monitoring system:

1. **Add new log categories** in `log/logger.py`
2. **Create new alert types** in `alert_system.py` 
3. **Add dashboard widgets** in `pipeline_dashboard.py`
4. **Extend webhook tracking** in `webhook_tracker.py`

The system is designed to be modular and extensible for future enhancements.

---

## System Status

✅ **Pipeline Monitor Hub** - Central coordination  
✅ **Webhook Tracker** - n8n event monitoring  
✅ **Advanced Logger** - Structured logging  
✅ **Alert System** - Multi-channel alerting  
✅ **Web Dashboard** - Real-time interface  
✅ **Health Checks** - Component monitoring  
✅ **Metrics Collection** - Performance tracking  
✅ **Startup Scripts** - Easy management  

**🎯 Ready for Production Use!**