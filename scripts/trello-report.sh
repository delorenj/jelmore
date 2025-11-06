#!/bin/bash

# Trello Pipeline Status Report Generator

BOARD_ID="685ee626bd3f9d52fd2f4c5e"
PIPELINE_LIST_ID="68986d00558810f4fb9ddcd5"

generate_status_report() {
    echo "Generating Pipeline Status Report..."
    
    # Get all cards in Pipeline Execution list
    CARDS=$(curl -s "https://api.trello.com/1/lists/${PIPELINE_LIST_ID}/cards?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}")
    
    TOTAL_CARDS=$(echo "$CARDS" | jq '. | length')
    
    # Count cards by label
    SUCCESS_COUNT=0
    PROCESSING_COUNT=0
    FAILED_COUNT=0
    
    echo "$CARDS" | jq -c '.[]' | while read card; do
        CARD_ID=$(echo "$card" | jq -r '.id')
        CARD_NAME=$(echo "$card" | jq -r '.name')
        
        # Get labels for this card
        LABELS=$(curl -s "https://api.trello.com/1/cards/${CARD_ID}?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" | jq -r '.labels[].name')
        
        if echo "$LABELS" | grep -q "Success"; then
            ((SUCCESS_COUNT++))
        elif echo "$LABELS" | grep -q "Processing"; then
            ((PROCESSING_COUNT++))
        elif echo "$LABELS" | grep -q "Failed"; then
            ((FAILED_COUNT++))
        fi
    done
    
    # Create status report card
    TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S UTC")
    REPORT_TEXT="# Pipeline Status Report - ${TIMESTAMP}

## Summary
- Total Sessions: ${TOTAL_CARDS}
- ✅ Successful: ${SUCCESS_COUNT}
- 🔄 Processing: ${PROCESSING_COUNT}  
- ❌ Failed: ${FAILED_COUNT}

## Success Rate
$((SUCCESS_COUNT * 100 / (TOTAL_CARDS > 0 ? TOTAL_CARDS : 1)))%

## Current Active Sessions
"
    
    # Add active sessions details
    echo "$CARDS" | jq -c '.[] | select(.labels[].name == "Processing")' | while read card; do
        CARD_NAME=$(echo "$card" | jq -r '.name')
        REPORT_TEXT="${REPORT_TEXT}- ${CARD_NAME}\n"
    done
    
    # Create report card
    curl -X POST "https://api.trello.com/1/cards" \
        -d "name=📊 Status Report - ${TIMESTAMP}" \
        -d "desc=${REPORT_TEXT}" \
        -d "idList=${PIPELINE_LIST_ID}" \
        -d "pos=top" \
        -d "key=${TRELLO_API_KEY}" \
        -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
    
    echo "Status report generated and posted to Trello"
    
    # Store in memory
    npx claude-flow@alpha hooks notify --message "Generated status report: ${SUCCESS_COUNT} success, ${PROCESSING_COUNT} processing, ${FAILED_COUNT} failed"
}

# Run the report generator
generate_status_report