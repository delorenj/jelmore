#!/bin/bash

# Jelmore Environment Validation Script - Simplified Version
# Checks PostgreSQL, Redis, and NATS connections

# Don't use set -e as it may exit on non-critical failures
set -uo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
BOLD='\033[1m'

# Configuration
CONNECTION_TIMEOUT=${TIMEOUT:-2}
CHECKS_PASSED=0
CHECKS_FAILED=0

# Print functions
print_header() {
    echo -e "\n${BOLD}$1${NC}"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((CHECKS_PASSED++))
}

print_error() {
    echo -e "${RED}✗${NC} $1"
    ((CHECKS_FAILED++))
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Load environment
load_env() {
    if [[ ! -f .env ]]; then
        print_error "Environment file not found: .env"
        exit 1
    fi
    
    set -a
    source .env
    set +a
    
    print_success "Loaded environment from .env"
}

# Check environment variables
check_env_vars() {
    print_header "Checking Environment Variables"
    
    # Required vars
    [[ -n "${POSTGRES_HOST:-}" ]] && print_success "POSTGRES_HOST: $POSTGRES_HOST" || print_error "POSTGRES_HOST not set"
    [[ -n "${POSTGRES_PORT:-}" ]] && print_success "POSTGRES_PORT: $POSTGRES_PORT" || print_error "POSTGRES_PORT not set"
    [[ -n "${POSTGRES_USER:-}" ]] && print_success "POSTGRES_USER: $POSTGRES_USER" || print_error "POSTGRES_USER not set"
    [[ -n "${POSTGRES_PASSWORD:-}" ]] && print_success "POSTGRES_PASSWORD: ***" || print_error "POSTGRES_PASSWORD not set"
    [[ -n "${POSTGRES_DB:-}" ]] && print_success "POSTGRES_DB: $POSTGRES_DB" || print_error "POSTGRES_DB not set"
    [[ -n "${REDIS_HOST:-}" ]] && print_success "REDIS_HOST: $REDIS_HOST" || print_error "REDIS_HOST not set"
    [[ -n "${REDIS_PORT:-}" ]] && print_success "REDIS_PORT: $REDIS_PORT" || print_error "REDIS_PORT not set"
    [[ -n "${NATS_URL:-}" ]] && print_success "NATS_URL: $NATS_URL" || print_error "NATS_URL not set"
    
    # Optional vars
    [[ -n "${APP_NAME:-}" ]] && print_info "APP_NAME: $APP_NAME" || print_warning "APP_NAME not set (optional)"
    [[ -n "${APP_VERSION:-}" ]] && print_info "APP_VERSION: $APP_VERSION" || print_warning "APP_VERSION not set (optional)"
    [[ -n "${DEBUG:-}" ]] && print_info "DEBUG: $DEBUG" || print_warning "DEBUG not set (optional)"
    [[ -n "${LOG_LEVEL:-}" ]] && print_info "LOG_LEVEL: $LOG_LEVEL" || print_warning "LOG_LEVEL not set (optional)"
}

# Check PostgreSQL
check_postgres() {
    print_header "Checking PostgreSQL Connection"
    
    if ! command -v psql &> /dev/null; then
        print_warning "psql not installed, trying Python..."
        check_postgres_python
        return
    fi
    
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    
    if timeout "$CONNECTION_TIMEOUT" psql \
        -h "${POSTGRES_HOST}" \
        -p "${POSTGRES_PORT}" \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -c "SELECT 1;" &> /dev/null; then
        print_success "PostgreSQL connection successful"
    else
        print_error "PostgreSQL connection failed"
    fi
    
    unset PGPASSWORD
}

# Check PostgreSQL with Python
check_postgres_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Neither psql nor python3 available"
        return
    fi
    
    python3 <<EOF 2>/dev/null && print_success "PostgreSQL connection successful (Python)" || print_error "PostgreSQL connection failed (Python)"
try:
    import psycopg2
    conn = psycopg2.connect(
        host="${POSTGRES_HOST}",
        port="${POSTGRES_PORT}",
        user="${POSTGRES_USER}",
        password="${POSTGRES_PASSWORD}",
        database="${POSTGRES_DB}",
        connect_timeout=${CONNECTION_TIMEOUT}
    )
    conn.close()
except:
    exit(1)
EOF
}

# Check Redis
check_redis() {
    print_header "Checking Redis Connection"
    
    if ! command -v redis-cli &> /dev/null; then
        print_warning "redis-cli not installed, trying Python..."
        check_redis_python
        return
    fi
    
    if timeout "$CONNECTION_TIMEOUT" redis-cli \
        -h "${REDIS_HOST}" \
        -p "${REDIS_PORT}" \
        ping &> /dev/null; then
        print_success "Redis connection successful"
    else
        print_error "Redis connection failed"
    fi
}

# Check Redis with Python
check_redis_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Neither redis-cli nor python3 available"
        return
    fi
    
    python3 <<EOF 2>/dev/null && print_success "Redis connection successful (Python)" || print_error "Redis connection failed (Python)"
try:
    import redis
    r = redis.Redis(host="${REDIS_HOST}", port=${REDIS_PORT}, socket_connect_timeout=${CONNECTION_TIMEOUT})
    r.ping()
except:
    exit(1)
EOF
}

# Check NATS
check_nats() {
    print_header "Checking NATS Connection"
    
    local nats_host=$(echo "${NATS_URL}" | sed -E 's|nats://([^:]+):.*|\1|')
    local nats_port=$(echo "${NATS_URL}" | sed -E 's|.*:([0-9]+).*|\1|')
    
    if command -v nc &> /dev/null; then
        if timeout "$CONNECTION_TIMEOUT" nc -zv "$nats_host" "$nats_port" &> /dev/null; then
            print_success "NATS port reachable ($nats_host:$nats_port)"
        else
            print_error "NATS port not reachable ($nats_host:$nats_port)"
        fi
    else
        print_warning "nc not available, trying Python..."
        check_nats_python "$nats_host" "$nats_port"
    fi
}

# Check NATS with Python
check_nats_python() {
    local host=$1
    local port=$2
    
    if ! command -v python3 &> /dev/null; then
        print_error "Neither nc nor python3 available"
        return
    fi
    
    python3 <<EOF 2>/dev/null && print_success "NATS port reachable (Python)" || print_error "NATS port not reachable (Python)"
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(${CONNECTION_TIMEOUT})
result = sock.connect_ex(("${host}", ${port}))
sock.close()
exit(0 if result == 0 else 1)
EOF
}

# Check Claude Code
check_claude() {
    print_header "Checking Claude Code Configuration"
    
    local claude_bin="${CLAUDE_CODE_BIN:-claude}"
    
    if command -v "$claude_bin" &> /dev/null; then
        print_success "Claude Code binary found: $claude_bin"
    else
        print_warning "Claude Code binary not found: $claude_bin"
    fi
    
    [[ -n "${CLAUDE_CODE_MAX_TURNS:-}" ]] && print_info "Max turns: ${CLAUDE_CODE_MAX_TURNS}"
    [[ -n "${CLAUDE_CODE_TIMEOUT:-}" ]] && print_info "Timeout: ${CLAUDE_CODE_TIMEOUT}s"
}

# Summary
print_summary() {
    print_header "Summary"
    
    local total=$((CHECKS_PASSED + CHECKS_FAILED))
    echo -e "${BOLD}Total Checks:${NC} $total"
    echo -e "${GREEN}Passed:${NC} $CHECKS_PASSED"
    echo -e "${RED}Failed:${NC} $CHECKS_FAILED"
    
    if [[ $CHECKS_FAILED -eq 0 ]]; then
        echo -e "\n${GREEN}${BOLD}✓ All checks passed!${NC}"
    else
        echo -e "\n${RED}${BOLD}✗ Some checks failed!${NC}"
        exit 1
    fi
}

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Options:
    -h, --help          Show help
    -t, --timeout SEC   Connection timeout (default: 2)
    --skip-postgres     Skip PostgreSQL check
    --skip-redis        Skip Redis check
    --skip-nats         Skip NATS check
    --skip-claude       Skip Claude check

Examples:
    $0                  # Run all checks
    $0 -t 5             # 5 second timeout
    $0 --skip-redis     # Skip Redis check
EOF
}

# Main
main() {
    local skip_postgres=false
    local skip_redis=false
    local skip_nats=false
    local skip_claude=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -t|--timeout)
                CONNECTION_TIMEOUT="$2"
                shift 2
                ;;
            --skip-postgres)
                skip_postgres=true
                shift
                ;;
            --skip-redis)
                skip_redis=true
                shift
                ;;
            --skip-nats)
                skip_nats=true
                shift
                ;;
            --skip-claude)
                skip_claude=true
                shift
                ;;
            *)
                echo "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done
    
    # Header
    echo -e "${BOLD}${BLUE}Jelmore Environment Validation${NC}"
    echo -e "${BLUE}================================${NC}"
    
    # Run checks
    load_env
    check_env_vars
    
    [[ "$skip_postgres" != true ]] && check_postgres
    [[ "$skip_redis" != true ]] && check_redis
    [[ "$skip_nats" != true ]] && check_nats
    [[ "$skip_claude" != true ]] && check_claude
    
    print_summary
}

# Run
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi