# Jelmore n8n Integration Setup Guide

## Overview

This guide explains how to set up and use the Jelmore-integrated n8n workflow for GitHub PR reviews. The integration replaces OpenCode PR Review nodes with direct HTTP requests to the Jelmore API.

## Prerequisites

- **Jelmore Server**: Running on `192.168.1.12:8000` (hostname: big-chungus)
- **n8n Instance**: With access to environment variables
- **GitHub Webhook**: Configured to send PR events to n8n
- **Shell Access**: To configure API keys and environment variables

## Setup Instructions

### 1. API Key Configuration

The API key has been automatically generated and configured in your secrets file:

```bash
# Location: ~/.config/zshyzsh/secrets.zsh
export JELMORE_API_KEY="0xw6oy-AAQ3ESPw56KV6xr2DkxqXq4-frfY9XEVy16E"
export JELMORE_BASE_URL="http://192.168.1.12:8000"
export N8N_JELMORE_API_KEY="${JELMORE_API_KEY}"
export N8N_JELMORE_BASE_URL="${JELMORE_BASE_URL}"
```

**Important**: Ensure these environment variables are loaded in your shell session:
```bash
source ~/.config/zshyzsh/secrets.zsh
```

### 2. n8n Environment Variables

Make sure n8n has access to the following environment variables:
- `JELMORE_API_KEY`: Your Jelmore API authentication key
- `JELMORE_BASE_URL`: Base URL for Jelmore API (http://192.168.1.12:8000)

### 3. Import the Workflow

1. Open your n8n instance
2. Go to "Workflows" section
3. Click "Import from JSON"
4. Upload the file: `workflow-jelmore-integrated.json`
5. Activate the workflow

### 4. Jelmore API Key Validation (Optional)

If Jelmore doesn't already have API key validation, you may need to add it. The workflow expects:

**Endpoint**: `POST /api/v1/sessions`
**Headers**:
- `X-API-Key`: Your API key
- `Content-Type`: application/json

**Request Body**:
```json
{
  "query": "Review new PR #123: Feature implementation",
  "config": {
    "working_directory": "/path/to/worktree",
    "context": "github_pr_new|github_pr_comment|github_pr_update",
    "pr_number": 123,
    "repository": "repo-name",
    "author": "username"
  }
}
```

## How It Works

### Workflow Changes

The integration replaces three OpenCode PR Review nodes with HTTP Request nodes:

1. **Jelmore PR Review3** (New PR):
   - Query: "Review new PR #{number}: {title}"
   - Context: "github_pr_new"

2. **Jelmore PR Review4** (Address Comment):
   - Query: "Address PR comment: {comment} on {file} line {line}"
   - Context: "github_pr_comment"

3. **Jelmore PR Review5** (PR Update):
   - Query: "Review updates to PR #{number}: {title}"
   - Context: "github_pr_update"

### Added Features

1. **Error Handling**: Added IF nodes to check API response success
2. **Contextual Queries**: Dynamic query generation based on event type
3. **Retry Logic**: 3 retry attempts with 30-second timeout
4. **Session Tracking**: Captures `session_id` from Jelmore responses

### Event Flow

```
GitHub Webhook → Parse Data → Route by Type → Create Worktree → Set Path → Jelmore API → Check Success → Response
```

## Testing

### Test Scenarios

1. **New PR Event**:
   ```bash
   # Trigger by opening a new PR
   # Expected: Jelmore receives "Review new PR #X: Title"
   ```

2. **PR Comment Event**:
   ```bash
   # Trigger by adding a review comment
   # Expected: Jelmore receives "Address PR comment: [comment] on [file] line [line]"
   ```

3. **PR Update Event**:
   ```bash
   # Trigger by pushing commits to PR
   # Expected: Jelmore receives "Review updates to PR #X: Title"
   ```

### Validation Steps

1. **API Key Authentication**:
   ```bash
   curl -H "X-API-Key: 0xw6oy-AAQ3ESPw56KV6xr2DkxqXq4-frfY9XEVy16E" \
        -H "Content-Type: application/json" \
        -X POST http://192.168.1.12:8000/api/v1/sessions \
        -d '{"query": "test", "config": {}}'
   ```

2. **Workflow Execution**:
   - Check n8n execution logs for successful API calls
   - Verify session IDs are returned in responses
   - Confirm error handling works with invalid requests

3. **Jelmore Processing**:
   - Monitor Jelmore logs for incoming requests
   - Verify working directory is correctly set
   - Check that context information is properly parsed

## Troubleshooting

### Common Issues

1. **API Key Authentication Failed**:
   - Verify `JELMORE_API_KEY` is correctly set in environment
   - Check that Jelmore has API key validation implemented
   - Ensure n8n can access environment variables

2. **Connection Timeout**:
   - Verify Jelmore is running on `192.168.1.12:8000`
   - Check network connectivity between n8n and Jelmore hosts
   - Review firewall settings if applicable

3. **Missing Session Data**:
   - Check Jelmore API response format
   - Verify that `session_id` field is returned
   - Review n8n logs for response parsing errors

4. **Workflow Execution Errors**:
   - Check n8n execution logs for detailed error messages
   - Verify all environment variables are accessible
   - Test individual nodes in isolation

### Debug Commands

```bash
# Test API connectivity
curl -v http://192.168.1.12:8000/health

# Check environment variables in n8n context
# (Use n8n's Code node for debugging)
console.log(process.env.JELMORE_API_KEY);

# Monitor Jelmore logs
tail -f /path/to/jelmore/logs/application.log
```

## Configuration Files

- **Workflow**: `workflow-jelmore-integrated.json`
- **Environment**: `~/.config/zshyzsh/secrets.zsh`
- **Original Workflow**: `workflow-integration-mvp.json` (backup)

## Security Notes

1. **API Key Protection**: The API key is stored in secrets file - never commit to version control
2. **Network Security**: Ensure proper firewall rules between n8n and Jelmore
3. **Access Control**: Consider implementing IP-based restrictions on Jelmore API
4. **Logging**: Monitor API access logs for unauthorized attempts

## Support

For issues specific to:
- **Jelmore API**: Check Jelmore server logs and documentation
- **n8n Workflow**: Review n8n execution logs and node configurations  
- **GitHub Integration**: Verify webhook configuration and payload format

---

**Last Updated**: 2025-08-08
**Integration Version**: v1.0.0