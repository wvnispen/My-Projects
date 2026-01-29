#!/bin/bash
#
# SonicWall CSE Reporter - Test Data Generator
# Generates sample syslog messages to test the pipeline
#

SYSLOG_HOST="${1:-localhost}"
SYSLOG_PORT="${2:-6514}"
COUNT="${3:-100}"

echo "Sending $COUNT test messages to $SYSLOG_HOST:$SYSLOG_PORT"
echo ""

# Sample users
USERS=("john.doe" "jane.smith" "bob.wilson" "alice.jones" "mike.brown" "sarah.davis" "tom.miller" "emma.taylor")

# Sample applications
APPS=("salesforce" "office365" "slack" "github" "jira" "confluence" "zoom" "dropbox" "aws-console" "azure-portal")

# Sample actions
AUTH_ACTIONS=("success" "success" "success" "success" "failed" "denied")
ACCESS_ACTIONS=("allow" "allow" "allow" "allow" "deny" "block")

# Sample posture statuses
POSTURE=("compliant" "compliant" "compliant" "non-compliant")

# Sample event types
EVENT_TYPES=("authentication" "access" "policy" "posture" "session")

# Sample source IPs
SRC_IPS=("192.168.1.50" "192.168.1.51" "10.0.0.100" "10.0.0.101" "172.16.0.25" "192.168.2.30")

generate_timestamp() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

get_random() {
    local arr=("$@")
    echo "${arr[$RANDOM % ${#arr[@]}]}"
}

send_auth_event() {
    local user=$(get_random "${USERS[@]}")
    local action=$(get_random "${AUTH_ACTIONS[@]}")
    local src_ip=$(get_random "${SRC_IPS[@]}")
    local ts=$(generate_timestamp)
    
    local msg="<14>1 $ts cse-gateway sonicwall-cse - - - event_type=authentication user=$user action=$action src_ip=$src_ip method=sso"
    echo "$msg" | nc -w 1 $SYSLOG_HOST $SYSLOG_PORT
}

send_access_event() {
    local user=$(get_random "${USERS[@]}")
    local app=$(get_random "${APPS[@]}")
    local action=$(get_random "${ACCESS_ACTIONS[@]}")
    local src_ip=$(get_random "${SRC_IPS[@]}")
    local ts=$(generate_timestamp)
    
    local msg="<14>1 $ts cse-gateway sonicwall-cse - - - event_type=access user=$user application=$app action=$action src_ip=$src_ip"
    echo "$msg" | nc -w 1 $SYSLOG_HOST $SYSLOG_PORT
}

send_policy_event() {
    local user=$(get_random "${USERS[@]}")
    local app=$(get_random "${APPS[@]}")
    local action=$(get_random "${ACCESS_ACTIONS[@]}")
    local ts=$(generate_timestamp)
    
    local msg="<14>1 $ts cse-gateway sonicwall-cse - - - event_type=policy user=$user application=$app action=$action policy=default-access-policy"
    echo "$msg" | nc -w 1 $SYSLOG_HOST $SYSLOG_PORT
}

send_posture_event() {
    local user=$(get_random "${USERS[@]}")
    local status=$(get_random "${POSTURE[@]}")
    local src_ip=$(get_random "${SRC_IPS[@]}")
    local ts=$(generate_timestamp)
    
    local msg="<14>1 $ts cse-gateway sonicwall-cse - - - event_type=posture user=$user posture_status=$status src_ip=$src_ip device_type=windows"
    echo "$msg" | nc -w 1 $SYSLOG_HOST $SYSLOG_PORT
}

send_session_event() {
    local user=$(get_random "${USERS[@]}")
    local action="start"
    local src_ip=$(get_random "${SRC_IPS[@]}")
    local ts=$(generate_timestamp)
    
    local msg="<14>1 $ts cse-gateway sonicwall-cse - - - event_type=session user=$user action=$action src_ip=$src_ip session_id=$(uuidgen 2>/dev/null || echo "sess-$RANDOM")"
    echo "$msg" | nc -w 1 $SYSLOG_HOST $SYSLOG_PORT
}

# Main loop
echo "Generating test events..."
for ((i=1; i<=COUNT; i++)); do
    event_type=$(get_random "${EVENT_TYPES[@]}")
    
    case $event_type in
        "authentication")
            send_auth_event
            ;;
        "access")
            send_access_event
            ;;
        "policy")
            send_policy_event
            ;;
        "posture")
            send_posture_event
            ;;
        "session")
            send_session_event
            ;;
    esac
    
    # Progress indicator
    if (( i % 10 == 0 )); then
        echo "  Sent $i / $COUNT events"
    fi
    
    # Small delay to avoid overwhelming
    sleep 0.05
done

echo ""
echo "Done! Sent $COUNT test events."
echo ""
echo "Check Grafana dashboards at http://localhost:3000"
echo "Navigate to: Dashboards → SonicWall CSE"
