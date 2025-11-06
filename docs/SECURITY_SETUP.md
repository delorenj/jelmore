# Jelmore Secure Setup Guide

## Overview

This guide walks you through setting up Jelmore with proper security practices. **All secrets must come from environment variables - no hardcoded credentials are allowed.**

## Quick Secure Setup

### 1. Environment Configuration

```bash
# Copy the environment template
cp .env.example .env

# Generate secure credentials
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)" >> .env
echo "API_KEY_ADMIN=$(openssl rand -hex 32)" >> .env  
echo "API_KEY_CLIENT=$(openssl rand -hex 32)" >> .env
echo "API_KEY_READONLY=$(openssl rand -hex 32)" >> .env
```

### 2. Configure Environment Variables

Edit `.env` with your generated values:

```env
# Database (REQUIRED)
POSTGRES_PASSWORD=your-generated-password-here

# API Keys (REQUIRED for production)
API_KEY_ADMIN=your-generated-admin-key-here
API_KEY_CLIENT=your-generated-client-key-here
API_KEY_READONLY=your-generated-readonly-key-here

# Optional: Customize other settings
DEBUG=false
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-domain.com
```

### 3. Validate Security Configuration

```bash
# Test configuration loads without errors
python -c "from src.jelmore.config import get_settings; print('✅ Config valid!')"

# Run comprehensive security validation
python scripts/validate_security.py
```

Expected output:
```
🔍 Running security validation...

📊 Security Validation Results:
   Errors: 0
   Warnings: 0

✅ All security validations passed!

🛡️  Security validation complete!
```

### 4. Start Services

```bash
# Development
docker-compose up -d

# Check services are healthy
docker-compose ps

# Test API with authentication
curl -H "X-API-Key: your-admin-key" http://localhost:8687/health
```

## Production Deployment

### Environment-Specific Configuration

#### Staging Environment

```bash
# staging.env
POSTGRES_PASSWORD=${STAGING_DB_PASSWORD}
API_KEY_ADMIN=${STAGING_ADMIN_KEY}
API_KEY_CLIENT=${STAGING_CLIENT_KEY}
DEBUG=false
LOG_LEVEL=INFO
CORS_ORIGINS=https://staging.your-domain.com
```

#### Production Environment

```bash
# production.env  
POSTGRES_PASSWORD=${PRODUCTION_DB_PASSWORD}
API_KEY_ADMIN=${PRODUCTION_ADMIN_KEY}
API_KEY_CLIENT=${PRODUCTION_CLIENT_KEY}
DEBUG=false
LOG_LEVEL=WARNING
CORS_ORIGINS=https://your-domain.com,https://api.your-domain.com
```

### Docker Secrets (Recommended for Production)

```yaml
# docker-compose.prod.yml
services:
  jelmore:
    secrets:
      - postgres_password
      - api_key_admin
      - api_key_client
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
      - API_KEY_ADMIN_FILE=/run/secrets/api_key_admin
      - API_KEY_CLIENT_FILE=/run/secrets/api_key_client

secrets:
  postgres_password:
    external: true
    name: jelmore_postgres_password
  api_key_admin:
    external: true
    name: jelmore_api_key_admin
  api_key_client:
    external: true
    name: jelmore_api_key_client
```

Create secrets:
```bash
# Create Docker secrets
echo "your-secure-password" | docker secret create jelmore_postgres_password -
echo "your-admin-key" | docker secret create jelmore_api_key_admin -
echo "your-client-key" | docker secret create jelmore_api_key_client -
```

## Security Validation

### Pre-commit Hooks (Recommended)

```bash
# Install pre-commit hooks for security scanning
pip install pre-commit
pre-commit install

# Test hooks manually
pre-commit run --all-files
```

### Manual Security Audit

```bash
# Run the security validation script
python scripts/validate_security.py

# Check for hardcoded secrets in code
grep -r "password.*=" src/ --include="*.py"
grep -r "secret.*=" src/ --include="*.py" 
grep -r "key.*=" src/ --include="*.py"

# Verify .gitignore includes security patterns
grep -E "\.(env|key|pem)" .gitignore
```

## API Authentication

### Key Types and Permissions

1. **Admin Key** (`API_KEY_ADMIN`):
   - Full system access
   - User management
   - System configuration
   - **Use cases**: Administrative tools, system management

2. **Client Key** (`API_KEY_CLIENT`):
   - Standard application access
   - Session creation and management
   - **Use cases**: Frontend applications, mobile apps

3. **Read-only Key** (`API_KEY_READONLY`):
   - View-only access
   - Health checks and metrics
   - **Use cases**: Monitoring systems, dashboards

### Using API Keys

```bash
# Health check (any key or no key in debug mode)
curl -H "X-API-Key: your-client-key" \
     http://localhost:8687/health

# Create session (client or admin key required)
curl -H "X-API-Key: your-client-key" \
     -H "Content-Type: application/json" \
     -X POST http://localhost:8687/api/v1/sessions \
     -d '{"query": "Hello, Jelmore!"}'

# Admin operations (admin key required)
curl -H "X-API-Key: your-admin-key" \
     -H "Content-Type: application/json" \
     -X GET http://localhost:8687/api/v1/admin/stats
```

## Troubleshooting

### Common Security Issues

#### "POSTGRES_PASSWORD environment variable is required"

**Cause**: Missing or empty `POSTGRES_PASSWORD` in environment.

**Solution**:
```bash
# Check if .env exists and has POSTGRES_PASSWORD
cat .env | grep POSTGRES_PASSWORD

# If missing, add it:
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)" >> .env

# Restart services
docker-compose restart
```

#### "No API keys configured"

**Cause**: All API key environment variables are empty.

**Solution**:
```bash
# Add at least one API key to .env
echo "API_KEY_ADMIN=$(openssl rand -hex 32)" >> .env

# Or for all keys:
echo "API_KEY_CLIENT=$(openssl rand -hex 32)" >> .env
echo "API_KEY_READONLY=$(openssl rand -hex 32)" >> .env

# Restart services
docker-compose restart
```

#### "Invalid API key" (401 Unauthorized)

**Cause**: Using wrong API key or key not configured.

**Solution**:
```bash
# Check configured keys (without revealing values)
python -c "
from src.jelmore.config import get_settings
s = get_settings()
print('Admin key configured:', bool(s.api_key_admin))
print('Client key configured:', bool(s.api_key_client))  
print('Readonly key configured:', bool(s.api_key_readonly))
"

# Test with correct key
curl -H "X-API-Key: $(grep API_KEY_ADMIN .env | cut -d= -f2)" \
     http://localhost:8687/health
```

#### Docker Compose Variables Not Loading

**Cause**: Docker Compose not reading `.env` file.

**Solution**:
```bash
# Ensure .env is in same directory as docker-compose.yml
ls -la .env docker-compose.yml

# Test variable substitution
docker-compose config | grep POSTGRES_PASSWORD

# Force recreate containers with new environment
docker-compose down
docker-compose up -d --force-recreate
```

### Security Validation Failures

If `python scripts/validate_security.py` reports issues:

1. **Fix hardcoded secrets**:
   ```bash
   # Remove any hardcoded passwords/keys from code
   # Use environment variables instead
   ```

2. **Update .gitignore**:
   ```bash
   # Ensure sensitive patterns are ignored
   echo "*.env" >> .gitignore
   echo "secrets/" >> .gitignore
   ```

3. **Check Docker configuration**:
   ```bash
   # Remove fallback values from docker-compose.yml
   # Change: ${VAR:-default} to: ${VAR}
   ```

## Best Practices Summary

### ✅ DO:
- Use environment variables for ALL secrets
- Generate random, unique keys (32+ characters)
- Use different keys for different environments
- Run security validation regularly
- Implement pre-commit hooks
- Use Docker secrets in production
- Rotate keys regularly

### ❌ DON'T:
- Hardcode passwords, keys, or secrets in code
- Commit `.env` files to version control
- Use default or example values in production
- Share API keys between environments
- Skip security validation
- Use weak or predictable secrets

## Security Checklist

Before deploying to production:

- [ ] All secrets come from environment variables
- [ ] No hardcoded credentials in codebase
- [ ] Security validation passes
- [ ] Pre-commit hooks configured
- [ ] API keys are unique and secure (32+ chars)
- [ ] HTTPS enabled with valid certificates
- [ ] CORS origins restricted to known domains
- [ ] Database uses encrypted connections
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery procedures tested

---

**Remember**: Security is everyone's responsibility. When in doubt, choose the more secure option and consult the security documentation.