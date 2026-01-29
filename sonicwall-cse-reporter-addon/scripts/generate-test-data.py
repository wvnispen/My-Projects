#!/usr/bin/env python3
"""
SonicWall CSE Reporter - Test Data Generator
Generates sample events and sends them directly to Loki to test dashboards.

Usage:
    python3 generate-test-data.py [--count 100] [--loki-url http://localhost:3100]
"""

import argparse
import json
import random
import time
import requests
from datetime import datetime, timedelta

# Sample data
USERS = [
    "john.doe@company.com", "jane.smith@company.com", "bob.wilson@company.com",
    "alice.jones@company.com", "mike.brown@company.com", "sarah.davis@company.com",
    "tom.miller@company.com", "emma.taylor@company.com", "chris.anderson@company.com",
    "lisa.white@company.com"
]

SERVICES = [
    "salesforce-prod", "office365", "slack-workspace", "github-enterprise",
    "jira-cloud", "confluence", "zoom-meetings", "dropbox-business",
    "aws-console", "azure-portal", "internal-wiki", "hr-portal"
]

DEVICES = [
    ("WIN-PC-001", "Windows", "10.0.22621"),
    ("MAC-001", "macOS", "14.2"),
    ("WIN-LAPTOP-002", "Windows", "11.0.22631"),
    ("MAC-002", "macOS", "13.6"),
    ("LINUX-DEV-001", "Linux", "Ubuntu 22.04"),
]

TRUST_LEVELS = ["AlwaysTrust", "High", "Medium", "Low"]

ACCESS_TIERS = ["corp-access-tier", "prod-access-tier", "dev-access-tier"]

POLICIES = ["default-access-policy", "high-security-policy", "contractor-policy"]

EVENT_TYPES = [
    ("Identity", "UserPrincipal", ["Grant", "Deny"]),
    ("Access", "Connection", ["Authorized", "Unauthorized"]),
    ("Registration", "Device", ["Register", "Unregister"]),
    ("TrustScoring", "Device", ["Calculate", "Override"]),
    ("Threat", "URL", ["Block"]),
    ("Compliance", "ITP", ["Block"]),
]

MESSAGES = {
    ("Identity", "Grant"): "CSE issued an identity token to {user}",
    ("Identity", "Deny"): "CSE refused to issue token - {reason}",
    ("Access", "Authorized"): "Authorized TCP connection to {service}",
    ("Access", "Unauthorized"): "Unauthorized access attempt to {service}",
    ("Registration", "Register"): "Device {device} registered successfully",
    ("Registration", "Unregister"): "Device {device} unregistered",
    ("TrustScoring", "Calculate"): "Trust level calculated as {trust_level}",
    ("TrustScoring", "Override"): "Trust level overridden to {trust_level}",
    ("Threat", "Block"): "URL blocked by threat protection",
    ("Compliance", "Block"): "Access blocked by ITP policy",
}


def generate_event():
    """Generate a single random event."""
    event_type, subtype, actions = random.choice(EVENT_TYPES)
    action = random.choice(actions)
    user = random.choice(USERS)
    device_name, device_os, device_os_ver = random.choice(DEVICES)
    service = random.choice(SERVICES)
    trust_level = random.choice(TRUST_LEVELS)
    
    # Determine severity based on action
    if action in ["Grant", "Authorized", "Register", "Calculate"]:
        severity = "INFO"
        status = "success"
    elif action in ["Deny", "Unauthorized"]:
        severity = "ERROR"
        status = "denied"
    else:
        severity = "WARN"
        status = action.lower()
    
    # Map to category
    category_map = {
        "Identity": "authentication",
        "Access": "access",
        "Registration": "registration",
        "TrustScoring": "posture",
        "Threat": "security",
        "Compliance": "policy",
    }
    category = category_map.get(event_type, "other")
    
    # Generate message
    message_template = MESSAGES.get((event_type, action), f"{event_type} {action}")
    message = message_template.format(
        user=user,
        device=device_name,
        service=service,
        trust_level=trust_level,
        reason="policy violation" if action == "Deny" else ""
    )
    
    # Build labels
    labels = {
        "job": "sonicwall-cse",
        "source": "test-generator",
        "product": "sonicwall-cse",
        "event_type": event_type,
        "event_subtype": subtype,
        "action": action,
        "severity": severity,
        "status": status,
        "category": category,
    }
    
    # Add optional labels based on event type
    if event_type in ["Identity", "Access"]:
        labels["user_email"] = user
        labels["device_serial"] = device_name
        labels["device_os"] = device_os
        labels["trust_level"] = trust_level
    
    if event_type == "Access":
        labels["service_name"] = service
        labels["access_tier"] = random.choice(ACCESS_TIERS)
        labels["policy_name"] = random.choice(POLICIES)
    
    # Build log line
    log_parts = [message]
    if "user_email" in labels:
        log_parts.append(f"user={labels['user_email']}")
    if "service_name" in labels:
        log_parts.append(f"service={labels['service_name']}")
    if "device_serial" in labels:
        log_parts.append(f"device={labels['device_serial']}")
    
    log_line = " | ".join(log_parts)
    
    return labels, log_line


def send_to_loki(events, loki_url):
    """Send events to Loki."""
    # Group by labels
    streams = {}
    
    for labels, log_line, timestamp_ns in events:
        label_items = sorted(labels.items())
        label_key = json.dumps(label_items)
        
        if label_key not in streams:
            streams[label_key] = {
                "stream": labels,
                "values": []
            }
        
        streams[label_key]["values"].append([timestamp_ns, log_line])
    
    push_request = {"streams": list(streams.values())}
    
    response = requests.post(
        f"{loki_url}/loki/api/v1/push",
        json=push_request,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    response.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description="Generate test CSE events")
    parser.add_argument("--count", type=int, default=100, help="Number of events to generate")
    parser.add_argument("--loki-url", default="http://localhost:3100", help="Loki URL")
    parser.add_argument("--spread-hours", type=int, default=24, help="Spread events over N hours")
    args = parser.parse_args()
    
    print(f"Generating {args.count} test events...")
    print(f"Loki URL: {args.loki_url}")
    print(f"Spreading over {args.spread_hours} hours")
    print()
    
    events = []
    now = datetime.utcnow()
    
    for i in range(args.count):
        # Generate timestamp spread over the time range
        offset_seconds = random.randint(0, args.spread_hours * 3600)
        event_time = now - timedelta(seconds=offset_seconds)
        timestamp_ns = str(int(event_time.timestamp() * 1_000_000_000))
        
        labels, log_line = generate_event()
        events.append((labels, log_line, timestamp_ns))
        
        if (i + 1) % 50 == 0:
            print(f"  Generated {i + 1} / {args.count} events")
    
    print()
    print("Sending events to Loki...")
    
    try:
        # Send in batches
        batch_size = 100
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            send_to_loki(batch, args.loki_url)
            print(f"  Sent batch {i // batch_size + 1}")
        
        print()
        print("✓ Done! Events sent to Loki successfully.")
        print()
        print("Check Grafana dashboards at http://localhost:3000")
        print("Navigate to: Dashboards → SonicWall CSE")
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error sending to Loki: {e}")
        print()
        print("Make sure Loki is running:")
        print("  sudo systemctl status loki")


if __name__ == "__main__":
    main()
