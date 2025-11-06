#!/bin/bash

# Trello Pipeline Monitor
# This script monitors the hive memory for agent updates and updates Trello cards accordingly

BOARD_ID="685ee626bd3f9d52fd2f4c5e"
PIPELINE_LIST_ID="68986d00558810f4fb9ddcd5"
FAILED_LIST_ID="68986d1ea7ea34440de47a46"

# Function to update card checklist item
update_checklist_item() {
    local card_id=$1
    local item_name=$2
    local state=$3  # complete or incomplete
    
    # Get checklist ID
    local checklist_id=$(curl -s "https://api.trello.com/1/cards/${card_id}/checklists?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" | \
        jq -r '.[0].id')
    
    if [ ! -z "$checklist_id" ]; then
        # Get check item ID
        local item_id=$(curl -s "https://api.trello.com/1/checklists/${checklist_id}/checkItems?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" | \
            jq -r ".[] | select(.name == \"${item_name}\") | .id")
        
        if [ ! -z "$item_id" ]; then
            curl -X PUT "https://api.trello.com/1/cards/${card_id}/checkItem/${item_id}" \
                -d "state=${state}" \
                -d "key=${TRELLO_API_KEY}" \
                -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
            echo "Updated ${item_name} to ${state}"
        fi
    fi
}

# Function to add comment to card
add_comment() {
    local card_id=$1
    local comment=$2
    
    curl -X POST "https://api.trello.com/1/cards/${card_id}/actions/comments" \
        -d "text=${comment}" \
        -d "key=${TRELLO_API_KEY}" \
        -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
}

# Function to update card label
update_label() {
    local card_id=$1
    local label_name=$2
    
    # Get label ID
    local label_id=$(curl -s "https://api.trello.com/1/boards/${BOARD_ID}/labels?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" | \
        jq -r ".[] | select(.name == \"${label_name}\") | .id")
    
    if [ ! -z "$label_id" ]; then
        # Remove all labels first
        curl -s "https://api.trello.com/1/cards/${card_id}?key=${TRELLO_API_KEY}&token=${TRELLO_TOKEN}" | \
            jq -r '.idLabels[]' | while read old_label; do
            curl -X DELETE "https://api.trello.com/1/cards/${card_id}/idLabels/${old_label}" \
                -d "key=${TRELLO_API_KEY}" \
                -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
        done
        
        # Add new label
        curl -X POST "https://api.trello.com/1/cards/${card_id}/idLabels" \
            -d "value=${label_id}" \
            -d "key=${TRELLO_API_KEY}" \
            -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
        echo "Updated label to ${label_name}"
    fi
}

# Function to move card to failed list
move_to_failed() {
    local card_id=$1
    
    curl -X PUT "https://api.trello.com/1/cards/${card_id}" \
        -d "idList=${FAILED_LIST_ID}" \
        -d "key=${TRELLO_API_KEY}" \
        -d "token=${TRELLO_TOKEN}" > /dev/null 2>&1
    echo "Moved card to Failed Quality Checks"
}

# Main monitoring loop
echo "Starting Trello Pipeline Monitor..."
echo "Board ID: ${BOARD_ID}"
echo "Pipeline List: ${PIPELINE_LIST_ID}"
echo "Failed List: ${FAILED_LIST_ID}"

# Check for agent updates in memory
while true; do
    # Get latest status from memory
    STATUS_UPDATE=$(npx claude-flow@alpha memory retrieve --pattern "hive/*/status" 2>/dev/null | head -1)
    
    if [ ! -z "$STATUS_UPDATE" ]; then
        echo "Found status update: $STATUS_UPDATE"
        # Process the update and update Trello accordingly
        # This would be expanded based on actual agent status format
    fi
    
    # Sleep for 30 seconds before next check
    sleep 30
done