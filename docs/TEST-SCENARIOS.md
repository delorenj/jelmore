# Jelmore n8n Integration Test Scenarios

## Overview

This document outlines comprehensive test scenarios to validate the Jelmore n8n integration for GitHub PR workflows.

## Test Environment

- **Jelmore Server**: http://192.168.1.12:8000
- **n8n Instance**: Local development environment  
- **GitHub Repository**: Test repository with webhook configured
- **API Key**: `0xw6oy-AAQ3ESPw56KV6xr2DkxqXq4-frfY9XEVy16E`

## Pre-Test Setup

1. **Environment Verification**:
   ```bash
   # Check Jelmore accessibility
   curl -I http://192.168.1.12:8000/health
   
   # Verify environment variables
   echo $JELMORE_API_KEY
   echo $JELMORE_BASE_URL
   
   # Load secrets if needed
   source ~/.config/zshyzsh/secrets.zsh
   ```

2. **n8n Configuration**:
   - Import `workflow-jelmore-integrated.json`
   - Activate the workflow
   - Verify environment variables are accessible

## Test Scenarios

### 1. API Authentication Test

**Objective**: Validate API key authentication works correctly

**Test Steps**:
```bash
# Valid API key test
curl -H "X-API-Key: 0xw6oy-AAQ3ESPw56KV6xr2DkxqXq4-frfY9XEVy16E" \
     -H "Content-Type: application/json" \
     -X POST http://192.168.1.12:8000/api/v1/sessions \
     -d '{"query": "test authentication", "config": {"context": "test"}}'

# Invalid API key test
curl -H "X-API-Key: invalid-key-123" \
     -H "Content-Type: application/json" \
     -X POST http://192.168.1.12:8000/api/v1/sessions \
     -d '{"query": "test authentication", "config": {"context": "test"}}'
```

**Expected Results**:
- Valid key: HTTP 200/201 with session data
- Invalid key: HTTP 401 Unauthorized

### 2. New PR Event Test

**Objective**: Test workflow response to new PR creation

**Trigger Method**: Create new PR in connected repository

**Expected Data Flow**:
```json
{
  "query": "Review new PR #123: Implement user authentication",
  "config": {
    "working_directory": "/home/delorenj/code/triumph/trinote2.0/pr-123-implement-user-auth",
    "context": "github_pr_new",
    "pr_number": 123,
    "repository": "trinote2.0",
    "author": "delorenj",
    "pr_url": "https://github.com/YIC-Triumph/trinote2.0/pull/123"
  }
}
```

**Validation Points**:
- [ ] Webhook received and parsed correctly
- [ ] Worktree path generated correctly
- [ ] Jelmore API called with proper headers
- [ ] Session ID returned and captured
- [ ] No error in workflow execution

### 3. PR Comment Event Test

**Objective**: Test workflow response to PR review comments

**Trigger Method**: Add review comment to existing PR

**Expected Data Flow**:
```json
{
  "query": "Address PR comment: This function needs error handling on src/auth.js line 45",
  "config": {
    "working_directory": "/home/delorenj/code/triumph/trinote2.0/pr-123-implement-user-auth",
    "context": "github_pr_comment",
    "pr_number": 123,
    "repository": "trinote2.0",
    "comment_info": {
      "file_path": "src/auth.js",
      "line_number": 45,
      "code_context": "function authenticate(user) {\n  return user.token;\n}",
      "comment_url": "https://github.com/YIC-Triumph/trinote2.0/pull/123#discussion_r123456789"
    },
    "author": "reviewer-username"
  }
}
```

**Validation Points**:
- [ ] Comment text parsed correctly
- [ ] File path and line number captured
- [ ] Code context included in request
- [ ] Comment URL properly formatted
- [ ] Jelmore processes comment context

### 4. PR Update Event Test

**Objective**: Test workflow response to PR updates/new commits

**Trigger Method**: Push new commits to existing PR branch

**Expected Data Flow**:
```json
{
  "query": "Review updates to PR #123: Implement user authentication",
  "config": {
    "working_directory": "/home/delorenj/code/triumph/trinote2.0/pr-123-implement-user-auth",
    "context": "github_pr_update",
    "pr_number": 123,
    "repository": "trinote2.0",
    "commit_id": "a1b2c3d4e5f6789012345678901234567890abcd",
    "author": "delorenj",
    "pr_url": "https://github.com/YIC-Triumph/trinote2.0/pull/123"
  }
}
```

**Validation Points**:
- [ ] Update detected correctly
- [ ] Latest commit SHA captured
- [ ] Existing worktree reused
- [ ] Update context differentiated from new PR

### 5. Error Handling Tests

**Objective**: Validate proper error handling and fallback behavior

#### 5.1 Jelmore API Unavailable

**Test Method**: Stop Jelmore service or block port 8000

**Expected Behavior**:
- [ ] n8n workflow shows connection error
- [ ] Retry logic attempts 3 times
- [ ] Workflow continues to completion with error logged
- [ ] GitHub webhook receives error response

#### 5.2 Invalid API Response

**Test Method**: Mock Jelmore to return invalid JSON or HTTP 500

**Expected Behavior**:
- [ ] Error handling node catches response error
- [ ] Workflow logs descriptive error message
- [ ] Does not crash the entire workflow

#### 5.3 Missing Environment Variables

**Test Method**: Remove JELMORE_API_KEY from environment

**Expected Behavior**:
- [ ] n8n node shows configuration error
- [ ] Clear error message about missing API key
- [ ] Workflow fails gracefully

### 6. Performance and Load Tests

**Objective**: Ensure integration handles typical load scenarios

#### 6.1 Multiple Simultaneous PRs

**Test Method**: Create/update multiple PRs within short time window

**Validation Points**:
- [ ] All requests processed without timeout
- [ ] No queue backup in n8n
- [ ] Session IDs unique for each request
- [ ] Jelmore handles concurrent sessions

#### 6.2 Large PR Data

**Test Method**: Create PR with large diff or many files

**Validation Points**:
- [ ] Request payload within size limits
- [ ] Processing time acceptable (< 30 seconds)
- [ ] No truncation of important data

### 7. End-to-End Integration Test

**Objective**: Validate complete workflow from GitHub to Jelmore

**Test Sequence**:
1. Create new PR → Verify Jelmore session created
2. Add review comment → Verify comment analysis triggered
3. Push update commits → Verify update processing
4. Merge PR → Verify cleanup if applicable

**Success Criteria**:
- [ ] All three event types trigger correctly
- [ ] Session continuity maintained across events
- [ ] No data loss or corruption
- [ ] Performance meets acceptable thresholds

## Test Data Setup

### Sample PR for Testing

```markdown
**Title**: "Add user authentication with JWT tokens"
**Description**: "Implements secure user authentication using JWT tokens with refresh functionality"
**Files**: 
- src/auth/index.js (new)
- src/auth/jwt.js (new)  
- src/middleware/auth.js (modified)
- tests/auth.test.js (new)
```

### Test Comments

```markdown
1. "This function should validate the JWT token format before processing"
2. "Consider adding rate limiting for failed authentication attempts"
3. "The refresh token logic needs proper error handling"
```

## Monitoring and Logging

### n8n Execution Logs

Monitor for:
- Successful HTTP requests to Jelmore
- Proper environment variable resolution
- Correct JSON payload construction
- Error handling activation

### Jelmore Server Logs

Monitor for:
- Incoming API requests with correct headers
- Session creation and management
- Working directory setup
- Context processing

### GitHub Webhook Logs

Monitor for:
- Successful webhook delivery
- Proper response codes from n8n
- No webhook retries due to errors

## Cleanup

After testing, ensure:
- [ ] Test PRs closed/deleted
- [ ] Test repository webhooks disabled if needed
- [ ] Jelmore test sessions cleaned up
- [ ] n8n workflow deactivated if not in production use

## Troubleshooting Guide

### Common Issues

1. **Connection Refused**: Verify Jelmore is running and accessible
2. **Authentication Failed**: Check API key in environment variables
3. **Invalid JSON**: Verify request payload structure
4. **Timeout Errors**: Check network connectivity and Jelmore response time

### Debug Commands

```bash
# Check Jelmore status
curl -v http://192.168.1.12:8000/health

# Test API endpoint manually
curl -v -H "X-API-Key: $JELMORE_API_KEY" \
     -H "Content-Type: application/json" \
     -X POST http://192.168.1.12:8000/api/v1/sessions \
     -d '{"query": "debug test", "config": {"context": "debug"}}'

# Monitor Jelmore logs in real-time
ssh big-chungus "tail -f /path/to/jelmore/logs/app.log"
```

---

**Test Plan Version**: v1.0.0
**Last Updated**: 2025-08-08
**Estimated Test Duration**: 2-3 hours