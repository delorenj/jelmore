# Security Best Practices for Jelmore

## Overview

This document outlines security best practices, secret management, and security configurations for the Jelmore project. **Security is a critical requirement, not an optional feature.**

## 🚨 Critical Security Requirements

### 1. No Hardcoded Secrets

**ABSOLUTE RULE**: Never commit secrets, passwords, API keys, or tokens to version control.

#### ❌ Prohibited Practices:
```python
# NEVER DO THIS
password = "jelmore_dev"  # Hardcoded password
api_key = "dev-key-123"   # Hardcoded API key
secret = "my-secret"      # Any hardcoded secret
```

#### ✅ Secure Practices:
```python
# ALWAYS DO THIS
password = os.getenv("POSTGRES_PASSWORD")  # From environment
api_key = settings.api_key_admin          # From configuration
```

### 2. Environment-Based Configuration

All sensitive configuration must come from environment variables:

```python
# config.py - Secure configuration pattern
class Settings(BaseSettings):
    postgres_password: str = Field(description="PostgreSQL password (REQUIRED)")
    api_key_admin: str = Field(default="", description="Admin API key")
    
    def model_post_init(self, __context) -> None:
        if not self.postgres_password:
            raise ValueError("POSTGRES_PASSWORD environment variable is required")
```

### 3. Fail-Safe Defaults

Never provide insecure fallback values:

```yaml
# docker-compose.yml - Secure patterns
environment:
  # ✅ SECURE: No fallback to insecure defaults
  - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
  
  # ❌ INSECURE: Fallback to hardcoded password
  # - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-jelmore_dev}
```

## Secret Management

### Development Environment

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Generate secure secrets:**
   ```bash
   # Database password
   openssl rand -base64 32
   
   # API keys (32+ characters recommended)
   openssl rand -hex 32
   ```

3. **Configure .env file:**
   ```env
   POSTGRES_PASSWORD=your-generated-secure-password
   API_KEY_ADMIN=your-generated-admin-key
   API_KEY_CLIENT=your-generated-client-key
   API_KEY_READONLY=your-generated-readonly-key
   ```

### Production Environment

#### Docker Secrets (Recommended)

```yaml
# docker-compose.prod.yml
services:
  jelmore:
    secrets:
      - postgres_password
      - api_key_admin
    environment:
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
      - API_KEY_ADMIN_FILE=/run/secrets/api_key_admin

secrets:
  postgres_password:
    external: true
  api_key_admin:
    external: true
```

#### External Secret Managers

- **AWS Secrets Manager**
- **HashiCorp Vault**
- **Azure Key Vault**
- **Google Secret Manager**

#### Environment Variables (Production)

For containerized deployments:

```bash
# Set secrets through container orchestration
docker run -e POSTGRES_PASSWORD="$(cat /secure/postgres_password)" \
           -e API_KEY_ADMIN="$(cat /secure/api_key_admin)" \
           jelmore:latest
```

## API Security

### Authentication

Jelmore uses API key-based authentication with role-based permissions:

#### API Key Types:

1. **Admin Keys** (`API_KEY_ADMIN`):
   - Full system access
   - User management
   - System configuration
   - Data deletion

2. **Client Keys** (`API_KEY_CLIENT`):
   - Standard application access
   - Read and write data
   - Session management

3. **Read-only Keys** (`API_KEY_READONLY`):
   - View data only
   - Health checks
   - Metrics access

### Key Management

#### Generation:
```bash
# Generate 32-byte hex keys (64 characters)
openssl rand -hex 32

# Generate base64 keys (44 characters)
openssl rand -base64 32
```

#### Rotation:
1. Generate new keys
2. Update environment configuration
3. Restart services
4. Invalidate old keys
5. Update client applications

### Request Security

All API requests require proper authentication:

```bash
# Example authenticated request
curl -H "X-API-Key: your-api-key-here" \
     https://api.jelmore.com/api/v1/sessions
```

## Database Security

### Connection Security

- **TLS/SSL**: Always use encrypted connections in production
- **Network Isolation**: Database should not be directly accessible from internet
- **User Permissions**: Use principle of least privilege

### Configuration:

```env
# Production database configuration
DATABASE_URL=postgresql+asyncpg://jelmore:${POSTGRES_PASSWORD}@postgres:5432/jelmore?sslmode=require
```

### Backup Security

- Encrypt database backups
- Secure backup storage
- Test backup restoration
- Regular backup validation

## Container Security

### Docker Configuration

#### Secure practices:
- Use non-root users
- Minimal base images
- Security scanning
- Resource limits

```dockerfile
# Example secure Dockerfile patterns
FROM python:3.11-alpine
RUN addgroup -g 1001 -S jelmore && \
    adduser -S jelmore -u 1001 -G jelmore
USER jelmore
```

#### Security Labels:
```yaml
services:
  jelmore:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
```

## Network Security

### HTTPS/TLS

Always use HTTPS in production:

```yaml
# Traefik HTTPS configuration
labels:
  - "traefik.http.routers.jelmore.tls=true"
  - "traefik.http.routers.jelmore.tls.certresolver=letsencrypt"
```

### CORS Configuration

Restrict CORS origins to known domains:

```env
# Development
CORS_ORIGINS=http://localhost:3000,http://localhost:3360

# Production
CORS_ORIGINS=https://your-domain.com,https://api.your-domain.com
```

### Firewall Rules

- Only expose necessary ports
- Use internal networking for service communication
- Implement rate limiting

## Monitoring & Auditing

### Security Logging

Enable comprehensive security logging:

```python
# Log authentication attempts
logger.info("API key authenticated", 
           key_name=key_info['name'],
           client_ip=request.client.host)

# Log failed authentications
logger.warning("Invalid API key attempt",
              client_ip=request.client.host,
              key_prefix=api_key[:10])
```

### Metrics Monitoring

Track security metrics:
- Failed authentication attempts
- Rate limit violations
- Unusual access patterns
- API key usage patterns

### Alerting

Set up alerts for:
- Multiple failed authentication attempts
- Access from unusual locations
- High rate limit violations
- Database connection failures

## Pre-commit Security Hooks

Install pre-commit hooks to prevent secret commits:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
  
  - repo: https://github.com/gitguardian/ggshield
    rev: v1.18.0
    hooks:
      - id: ggshield
        language: python
        stages: [commit]
```

Setup:
```bash
pip install pre-commit detect-secrets
pre-commit install
detect-secrets scan --baseline .secrets.baseline
```

## Security Testing

### Automated Security Scanning

```bash
# Container scanning
docker scan jelmore:latest

# Dependency scanning
safety check

# Secret scanning
detect-secrets scan --all-files

# SAST scanning
bandit -r src/
```

### Manual Testing

1. **Authentication Testing**:
   - Test with invalid API keys
   - Test without API keys
   - Test with expired keys

2. **Authorization Testing**:
   - Test access with different permission levels
   - Test cross-user data access

3. **Input Validation**:
   - Test SQL injection attempts
   - Test XSS attempts
   - Test parameter tampering

## Incident Response

### Security Incident Checklist

1. **Immediate Response**:
   - Isolate affected systems
   - Revoke compromised credentials
   - Document the incident

2. **Investigation**:
   - Analyze logs for breach scope
   - Identify attack vectors
   - Assess data exposure

3. **Recovery**:
   - Patch vulnerabilities
   - Restore systems from clean backups
   - Update security controls

4. **Post-Incident**:
   - Update security procedures
   - Conduct lessons learned
   - Improve monitoring

## Compliance Considerations

### Data Protection

- Implement data encryption at rest and in transit
- Regular security assessments
- User access controls and audit trails
- Data retention and deletion policies

### Regulatory Requirements

Consider compliance requirements for:
- GDPR (General Data Protection Regulation)
- CCPA (California Consumer Privacy Act)
- HIPAA (if handling health data)
- SOC 2 (Service Organization Control 2)

## Security Contacts

### Reporting Security Issues

- **Email**: security@jelmore.com
- **Response Time**: 24 hours for critical issues
- **PGP Key**: Available on request

### Security Team Contacts

- Security Lead: [contact]
- DevOps Security: [contact]
- Incident Response: [contact]

## Regular Security Tasks

### Daily
- Monitor security logs
- Check for failed authentication attempts
- Review system health

### Weekly
- Rotate development credentials
- Review access logs
- Update security documentation

### Monthly
- Security dependency updates
- API key rotation
- Security metrics review
- Backup restoration testing

### Quarterly
- Full security assessment
- Penetration testing
- Security training updates
- Disaster recovery testing

---

**Remember**: Security is everyone's responsibility. When in doubt, choose the more secure option and consult the security team.