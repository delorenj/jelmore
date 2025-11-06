#!/bin/bash

# Start Pipeline Monitor - Complete monitoring solution for Jelmore
# This script starts all monitoring components in the correct order

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="/home/delorenj/code/projects/33GOD/jelmore"
LOG_DIR="$PROJECT_ROOT/hive/monitor/log"
PID_DIR="$PROJECT_ROOT/hive/monitor/pids"
VENV_DIR="$PROJECT_ROOT/.venv"

# Monitoring endpoints
JELMORE_API="http://192.168.1.12:8000"
N8N_WEBHOOK="http://192.168.1.12:5678/webhook/pr-events"
NATS_SERVER="nats://192.168.1.12:4222"
DASHBOARD_URL="http://localhost:8001"

echo -e "${BLUE}🐝 Starting Jelmore Pipeline Monitor${NC}"
echo -e "${BLUE}===================================${NC}"

# Create necessary directories
echo -e "${YELLOW}📁 Creating directories...${NC}"
mkdir -p "$LOG_DIR"
mkdir -p "$PID_DIR"
mkdir -p "$LOG_DIR/archived"

# Activate virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}🐍 Activating virtual environment...${NC}"
    source "$VENV_DIR/bin/activate"
fi

# Change to project directory
cd "$PROJECT_ROOT"

# Function to check if service is running
check_service() {
    local service_name=$1
    local pid_file="$PID_DIR/${service_name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${GREEN}✅ $service_name is running (PID: $pid)${NC}"
            return 0
        else
            echo -e "${RED}❌ $service_name PID file exists but process is not running${NC}"
            rm -f "$pid_file"
            return 1
        fi
    else
        echo -e "${YELLOW}⏸️  $service_name is not running${NC}"
        return 1
    fi
}

# Function to start service
start_service() {
    local service_name=$1
    local python_script=$2
    local log_file="$LOG_DIR/${service_name}.log"
    local pid_file="$PID_DIR/${service_name}.pid"
    
    echo -e "${BLUE}🚀 Starting $service_name...${NC}"
    
    # Start the service in background
    nohup python3 "$python_script" > "$log_file" 2>&1 &
    local pid=$!
    
    # Save PID
    echo "$pid" > "$pid_file"
    
    # Wait a moment and check if it's still running
    sleep 2
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${GREEN}✅ $service_name started successfully (PID: $pid)${NC}"
        echo -e "${GREEN}   Log file: $log_file${NC}"
    else
        echo -e "${RED}❌ Failed to start $service_name${NC}"
        echo -e "${RED}   Check log file: $log_file${NC}"
        return 1
    fi
}

# Function to check external dependencies
check_dependencies() {
    echo -e "${BLUE}🔍 Checking external dependencies...${NC}"
    
    # Check Jelmore API
    echo -e "${YELLOW}Checking Jelmore API at $JELMORE_API...${NC}"
    if curl -s "$JELMORE_API/api/v1/sessions/stats" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Jelmore API is accessible${NC}"
    else
        echo -e "${RED}❌ Jelmore API is not accessible${NC}"
        echo -e "${YELLOW}   Make sure Jelmore is running at $JELMORE_API${NC}"
    fi
    
    # Check N8N webhook endpoint
    echo -e "${YELLOW}Checking N8N webhook availability...${NC}"
    if curl -s -o /dev/null -w "%{http_code}" "$N8N_WEBHOOK" | grep -q "405\|404\|200"; then
        echo -e "${GREEN}✅ N8N webhook endpoint is accessible${NC}"
    else
        echo -e "${RED}❌ N8N webhook endpoint is not accessible${NC}"
        echo -e "${YELLOW}   Make sure N8N is running at http://192.168.1.12:5678${NC}"
    fi
    
    # Check NATS server
    echo -e "${YELLOW}Checking NATS server...${NC}"
    if command -v nats-sub >/dev/null 2>&1; then
        if timeout 2s nats-sub -s "$NATS_SERVER" "test" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ NATS server is accessible${NC}"
        else
            echo -e "${RED}❌ NATS server is not accessible${NC}"
            echo -e "${YELLOW}   Make sure NATS is running at $NATS_SERVER${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  NATS client not installed, skipping NATS check${NC}"
    fi
}

# Function to show status
show_status() {
    echo -e "\n${PURPLE}📊 Pipeline Monitor Status${NC}"
    echo -e "${PURPLE}=========================${NC}"
    
    check_service "integrated_monitor"
    
    if [ -f "$PID_DIR/integrated_monitor.pid" ]; then
        echo -e "\n${BLUE}🔗 Service Endpoints:${NC}"
        echo -e "${GREEN}   📊 Dashboard: $DASHBOARD_URL${NC}"
        echo -e "${GREEN}   🔍 Monitoring: $JELMORE_API${NC}"
        echo -e "${GREEN}   🔗 Webhooks: $N8N_WEBHOOK${NC}"
        echo -e "${GREEN}   📋 Logs: $LOG_DIR${NC}"
    fi
}

# Function to stop services
stop_services() {
    echo -e "${YELLOW}🛑 Stopping Pipeline Monitor services...${NC}"
    
    local pid_file="$PID_DIR/integrated_monitor.pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}Stopping integrated monitor (PID: $pid)...${NC}"
            kill -TERM "$pid"
            
            # Wait for graceful shutdown
            sleep 5
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${RED}Force killing integrated monitor...${NC}"
                kill -KILL "$pid"
            fi
        fi
        rm -f "$pid_file"
    fi
    
    echo -e "${GREEN}✅ Pipeline Monitor stopped${NC}"
}

# Main execution based on command line argument
case "${1:-start}" in
    "start")
        echo -e "${BLUE}🚀 Starting Pipeline Monitor...${NC}"
        
        # Check if already running
        if check_service "integrated_monitor" >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  Pipeline Monitor is already running${NC}"
            show_status
            exit 0
        fi
        
        # Check dependencies
        check_dependencies
        echo ""
        
        # Start integrated monitoring service
        start_service "integrated_monitor" "hive/monitor/integrated_monitor.py"
        
        # Wait a moment for full startup
        echo -e "${YELLOW}⏳ Waiting for services to fully initialize...${NC}"
        sleep 5
        
        # Show final status
        show_status
        
        echo -e "\n${GREEN}🎉 Pipeline Monitor started successfully!${NC}"
        echo -e "${GREEN}   Dashboard available at: $DASHBOARD_URL${NC}"
        echo -e "${GREEN}   Logs are being written to: $LOG_DIR${NC}"
        echo -e "${GREEN}   Use './scripts/start_pipeline_monitor.sh status' to check status${NC}"
        echo -e "${GREEN}   Use './scripts/start_pipeline_monitor.sh stop' to stop services${NC}"
        ;;
        
    "stop")
        stop_services
        ;;
        
    "restart")
        stop_services
        sleep 2
        exec "$0" start
        ;;
        
    "status")
        show_status
        ;;
        
    "logs")
        echo -e "${BLUE}📋 Recent Pipeline Monitor Logs${NC}"
        echo -e "${BLUE}==============================${NC}"
        if [ -f "$LOG_DIR/integrated_monitor.log" ]; then
            tail -n 50 "$LOG_DIR/integrated_monitor.log"
        else
            echo -e "${YELLOW}No logs found at $LOG_DIR/integrated_monitor.log${NC}"
        fi
        ;;
        
    "check")
        check_dependencies
        ;;
        
    *)
        echo -e "${RED}Usage: $0 {start|stop|restart|status|logs|check}${NC}"
        echo -e "${YELLOW}Commands:${NC}"
        echo -e "${YELLOW}  start   - Start the pipeline monitor${NC}"
        echo -e "${YELLOW}  stop    - Stop the pipeline monitor${NC}" 
        echo -e "${YELLOW}  restart - Restart the pipeline monitor${NC}"
        echo -e "${YELLOW}  status  - Show service status${NC}"
        echo -e "${YELLOW}  logs    - Show recent logs${NC}"
        echo -e "${YELLOW}  check   - Check external dependencies${NC}"
        exit 1
        ;;
esac