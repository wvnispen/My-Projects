#!/usr/bin/env python3
"""
SonicWall CSE Events API Collector
Version 2.2.3

Polls the SonicWall Cloud Secure Edge Events API and forwards events to Loki.
This version properly extracts all fields from the CSE API response structure.

Fixes in 2.2.3:
- Improved label sanitization (names and values)
- Better HTTP error response capture
- Removed control characters from label values

Usage:
    CSE_API_KEY=your_api_key python3 cse-collector.py

Or configure via /etc/cse-collector/config.yaml
"""

import os
import sys
import json
import time
import logging
import argparse
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
import yaml

# Configuration defaults
DEFAULT_CONFIG = {
    "cse_api_url": "https://net.banyanops.com/api/v1/events",
    "loki_url": "http://localhost:3100/loki/api/v1/push",
    "poll_interval_seconds": 60,
    "batch_size": 1000,
    "lookback_minutes": 5,  # How far back to look on first run
    "cursor_file": "/var/lib/cse-collector/cursor.json",
    "log_level": "INFO",
    "log_file": "/var/log/cse-collector/collector.log",
    "labels": {
        "job": "sonicwall-cse",
        "source": "api",
        "product": "sonicwall-cse"
    }
}

class CSECollector:
    """Collects events from SonicWall CSE API and forwards to Loki."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("cse_api_key") or os.environ.get("CSE_API_KEY")
        if not self.api_key:
            raise ValueError("CSE API key not configured. Set CSE_API_KEY environment variable or cse_api_key in config.")

        self.api_url = config.get("cse_api_url", DEFAULT_CONFIG["cse_api_url"])
        self.loki_url = config.get("loki_url", DEFAULT_CONFIG["loki_url"])
        self.poll_interval = config.get("poll_interval_seconds", DEFAULT_CONFIG["poll_interval_seconds"])
        self.batch_size = config.get("batch_size", DEFAULT_CONFIG["batch_size"])
        self.cursor_file = Path(config.get("cursor_file", DEFAULT_CONFIG["cursor_file"]))
        self.labels = config.get("labels", DEFAULT_CONFIG["labels"])

        self.running = True
        self.last_created_at: Optional[int] = None

        # Setup logging
        self._setup_logging(config)

        # Load cursor
        self._load_cursor()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _setup_logging(self, config: Dict[str, Any]):
        """Configure logging."""
        log_level = getattr(logging, config.get("log_level", "INFO").upper())
        log_file = config.get("log_file")

        handlers = [logging.StreamHandler(sys.stdout)]
        if log_file:
            log_dir = Path(log_file).parent
            log_dir.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_file))

        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=handlers
        )
        self.logger = logging.getLogger("cse-collector")

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _load_cursor(self):
        """Load the last processed timestamp from cursor file."""
        try:
            if self.cursor_file.exists():
                with open(self.cursor_file) as f:
                    data = json.load(f)
                    self.last_created_at = data.get("last_created_at")
                    self.logger.info(f"Loaded cursor: last_created_at={self.last_created_at}")
        except Exception as e:
            self.logger.warning(f"Could not load cursor file: {e}")

        if self.last_created_at is None:
            # Default to lookback_minutes ago
            lookback = self.config.get("lookback_minutes", DEFAULT_CONFIG["lookback_minutes"])
            self.last_created_at = int((datetime.now(timezone.utc) - timedelta(minutes=lookback)).timestamp() * 1000)
            self.logger.info(f"No cursor found, starting from {lookback} minutes ago")

    def _save_cursor(self):
        """Save the current cursor to file."""
        try:
            self.cursor_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cursor_file, 'w') as f:
                json.dump({"last_created_at": self.last_created_at}, f)
        except Exception as e:
            self.logger.error(f"Could not save cursor: {e}")

    def fetch_events(self) -> List[Dict[str, Any]]:
        """Fetch events from CSE API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        params = {
            "after": self.last_created_at,
            "order": "ASC",
            "severity": "INFO",  # Gets INFO, WARN, ERROR
            "limit": self.batch_size
        }

        try:
            self.logger.debug(f"Fetching events from {self.api_url} after={self.last_created_at}")
            response = requests.get(self.api_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            events = data.get("data", [])

            self.logger.info(f"Fetched {len(events)} events from CSE API")
            return events

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching events from CSE API: {e}")
            return []

    def _safe_get(self, d: Dict, *keys, default=""):
        """Safely get nested dictionary value."""
        for key in keys:
            if isinstance(d, dict):
                d = d.get(key, {})
            else:
                return default
        return d if d and d != {} else default

    def _sanitize_label_value(self, value: str) -> str:
        """Sanitize a label value for Loki compatibility."""
        if not value:
            return ""
        # Convert to string and strip whitespace
        value = str(value).strip()
        # Replace problematic characters that break Loki
        # Loki label values cannot contain: ", \, newlines
        value = value.replace('\\', '_')  # Backslash
        value = value.replace('"', "'")   # Double quotes
        value = value.replace('\n', ' ')  # Newlines
        value = value.replace('\r', '')   # Carriage returns
        value = value.replace('\t', ' ')  # Tabs
        # Remove any other control characters
        value = ''.join(c if ord(c) >= 32 else ' ' for c in value)
        # Collapse multiple spaces
        while '  ' in value:
            value = value.replace('  ', ' ')
        value = value.strip()
        # Limit length (Loki has limits on label values)
        if len(value) > 128:
            value = value[:125] + "..."
        return value

    def _sanitize_label_name(self, name: str) -> str:
        """Sanitize a label name for Loki compatibility."""
        # Label names must match [a-zA-Z_][a-zA-Z0-9_]*
        if not name:
            return ""
        # Replace invalid characters with underscore
        result = ""
        for i, c in enumerate(name):
            if c.isalnum() or c == '_':
                result += c
            else:
                result += '_'
        # Ensure it starts with letter or underscore
        if result and result[0].isdigit():
            result = '_' + result
        return result

    def _add_label(self, labels: Dict, key: str, value: Any) -> None:
        """Add a label only if the value is non-empty."""
        if value is not None and value != "" and value != {}:
            sanitized = self._sanitize_label_value(str(value))
            if sanitized:  # Only add if still non-empty after sanitization
                labels[key] = sanitized

    def transform_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Transform CSE event to Loki format with proper field extraction."""
        # Extract timestamp (CSE uses Unix milliseconds)
        timestamp_ms = event.get("created_at", int(time.time() * 1000))
        timestamp_ns = str(timestamp_ms * 1_000_000)  # Convert to nanoseconds

        # Build labels - start with base labels
        labels = dict(self.labels)

        # === Core Event Fields ===
        event_type = event.get("type", "unknown")
        labels["event_type"] = event_type if event_type else "unknown"
        self._add_label(labels, "event_subtype", event.get("sub_type"))
        self._add_label(labels, "severity", event.get("severity", "INFO"))
        self._add_label(labels, "action", event.get("action"))

        # Map event types to categories
        type_to_category = {
            "Registration": "registration",
            "Identity": "authentication",
            "Access": "access",
            "TrustScoring": "posture",
            "Threat": "security",
            "Compliance": "policy",
            "AdminLogin": "admin",
            "Audit": "audit",
            "NetagentRestart": "system",
            "ITPStatus": "itp"
        }
        labels["category"] = type_to_category.get(event.get("type", ""), "other")

        # Map action to status
        action = event.get("action", "")
        if action in ["Grant", "Authorized", "Register", "Calculate"]:
            labels["status"] = "success"
        elif action in ["Deny", "Unauthorized", "Failed", "Unregister"]:
            labels["status"] = "denied"
        else:
            labels["status"] = action.lower() if action else "unknown"

        # === User Principal Fields (user_principal.user.*) ===
        user_principal = event.get("user_principal", {})
        user = user_principal.get("user", {})
        
        user_email = user.get("email", "")
        user_name = user.get("name", "")
        if user_email:
            labels["user_email"] = user_email
        if user_name:
            labels["user_name"] = user_name
        
        # User groups (take first one as primary for label, or join for log)
        user_groups = user.get("groups", [])
        if user_groups:
            labels["user_group"] = user_groups[0] if len(user_groups) == 1 else "multiple"
        
        # User roles
        user_roles = user.get("roles", [])
        if user_roles:
            labels["user_role"] = user_roles[0] if len(user_roles) == 1 else "multiple"

        # === Device Fields (user_principal.device.*) ===
        device = user_principal.get("device", {})
        
        device_platform = device.get("platform", "")
        device_model = device.get("model", "")
        device_os = device.get("os", "")
        device_friendly_name = device.get("friendly_name", "")
        device_ownership = device.get("ownership", "")
        device_serial = device.get("serial_number", "")
        
        if device_platform:
            labels["device_platform"] = device_platform
        if device_model:
            labels["device_model"] = device_model
        if device_os:
            labels["device_os"] = device_os
        if device_ownership:
            labels["device_ownership"] = device_ownership

        # === Client/Network Fields (user_principal.client.*) ===
        client = user_principal.get("client", {})
        
        client_ip = client.get("ip_address", "")
        if client_ip:
            # Clean up IP format (remove port if present, handle multiple IPs)
            if "," in client_ip:
                # Multiple IPs - take the public one (usually second)
                ips = [ip.split(":")[0] for ip in client_ip.split(",")]
                # Prefer non-RFC1918 addresses
                public_ip = next((ip for ip in ips if not ip.startswith(("10.", "172.", "192.168.", "100.64."))), ips[-1])
                labels["client_ip"] = public_ip
            else:
                labels["client_ip"] = client_ip.split(":")[0]
        
        # Geolocation
        geo = client.get("geo_location", {})
        geo_city = geo.get("city", "")
        geo_country = geo.get("country", "")
        geo_region = geo.get("region", "")
        
        if geo_city:
            labels["geo_city"] = geo_city
        if geo_country:
            labels["geo_country"] = geo_country
        if geo_region:
            labels["geo_region"] = geo_region

        # === Trust Score Fields (trustscore.*) ===
        trustscore = event.get("trustscore", {})
        
        trust_level = trustscore.get("trust_level", "")
        trust_score = trustscore.get("score")
        trust_profile = trustscore.get("trust_profile_name", "")
        
        if trust_level:
            labels["trust_level"] = trust_level
        if trust_score is not None:
            labels["trust_score"] = str(trust_score)
        
        # Passed factors
        passed_factors = trustscore.get("passed_factors", [])

        # === Service Fields (service.*) ===
        service = event.get("service", {})
        
        service_name = service.get("name", "")
        service_type = service.get("type", "")
        
        if service_name:
            labels["service_name"] = service_name
        if service_type:
            labels["service_type"] = service_type

        # === Policy Fields (policy.*) ===
        policy = event.get("policy", {})
        
        policy_name = policy.get("name", "")
        if policy_name:
            labels["policy_name"] = policy_name

        # === Role Fields (role[]) ===
        roles = event.get("role", [])
        if roles:
            role_names = [r.get("name", "") for r in roles if r.get("name")]
            if role_names:
                labels["role_name"] = role_names[0] if len(role_names) == 1 else ",".join(role_names[:3])

        # === Workload Fields (for Access events) ===
        workload = event.get("workload_principal", {})
        workload_set = workload.get("workload_set", {})
        app_name = workload_set.get("app_name", "")
        if app_name and not service_name:
            labels["service_name"] = app_name

        # === Link Fields (source/destination for Access events) ===
        link = event.get("link", {})
        dest = link.get("destination", {})
        dest_service = dest.get("service_name", "")
        if dest_service and "service_name" not in labels:
            labels["service_name"] = dest_service

        # === Clean up labels ===
        # Remove empty labels and ensure all values are strings
        labels = {k: str(v) for k, v in labels.items() if v and str(v).strip()}

        # === Build detailed log line ===
        log_parts = []
        
        # Message first
        message = event.get("message", "")
        if message:
            log_parts.append(message)
        
        # User info
        if user_email:
            log_parts.append(f"user={user_email}")
        elif user_name:
            log_parts.append(f"user={user_name}")
        
        # Device info
        if device_friendly_name:
            log_parts.append(f"device={device_friendly_name}")
        elif device_model:
            log_parts.append(f"device={device_model}")
        
        if device_platform:
            log_parts.append(f"platform={device_platform}")
        
        # Trust info
        if trust_level:
            log_parts.append(f"trust={trust_level}")
        if trust_score is not None:
            log_parts.append(f"score={trust_score}")
        
        # Service/policy
        if service_name:
            log_parts.append(f"service={service_name}")
        if policy_name:
            log_parts.append(f"policy={policy_name}")
        
        # Location
        if geo_city and geo_country:
            log_parts.append(f"location={geo_city},{geo_country}")
        
        # Client IP
        if "client_ip" in labels:
            log_parts.append(f"ip={labels['client_ip']}")
        
        # Passed trust factors (for TrustScoring events)
        if passed_factors:
            log_parts.append(f"factors={';'.join(passed_factors[:5])}")

        log_line = " | ".join(filter(None, log_parts))

        return {
            "labels": labels,
            "timestamp_ns": timestamp_ns,
            "line": log_line,
            "raw_event": event
        }

    def send_to_loki(self, events: List[Dict[str, Any]]) -> bool:
        """Send transformed events to Loki."""
        if not events:
            return True

        # Group events by label set
        streams: Dict[str, Dict] = {}

        for event in events:
            # Use only LOW-CARDINALITY labels for stream identification
            # High-cardinality fields go in the log line only
            low_cardinality_keys = {
                'job', 'source', 'product',  # Base labels
                'event_type', 'category', 'severity', 'status',  # Event classification
                'device_platform', 'device_ownership',  # Device (low cardinality)
            }
            
            clean_labels = {}
            for k, v in event["labels"].items():
                # Skip empty values
                if not v or not str(v).strip():
                    continue
                # Only include low-cardinality labels
                if k not in low_cardinality_keys:
                    continue
                # Sanitize label name and value
                clean_name = self._sanitize_label_name(k)
                clean_value = self._sanitize_label_value(str(v))
                if clean_name and clean_value:
                    clean_labels[clean_name] = clean_value
            
            # Ensure we have at least the base labels
            if 'job' not in clean_labels:
                clean_labels['job'] = 'sonicwall-cse'
            
            # Create label string for grouping
            label_items = sorted(clean_labels.items())
            label_str = str(hash(tuple(label_items)))

            if label_str not in streams:
                streams[label_str] = {
                    "stream": clean_labels,
                    "values": []
                }

            streams[label_str]["values"].append([
                event["timestamp_ns"],
                event["line"]
            ])
        
        # Sort values within each stream by timestamp (ascending - oldest first)
        for stream_key in streams:
            streams[stream_key]["values"].sort(key=lambda x: int(x[0]))

        # Build Loki push request
        push_request = {
            "streams": list(streams.values())
        }

        try:
            self.logger.debug(f"Sending {len(events)} events to Loki")
            response = requests.post(
                self.loki_url,
                json=push_request,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            # Check for errors before raise_for_status so we can capture the response body
            if response.status_code >= 400:
                error_body = response.text[:500] if response.text else "Empty response"
                self.logger.error(f"Loki HTTP error {response.status_code}: {error_body}")
                # Log first stream for debugging
                if push_request.get("streams") and len(push_request["streams"]) > 0:
                    first_stream = push_request["streams"][0]
                    self.logger.debug(f"First stream labels: {first_stream.get('stream', {})}")
                return False
            
            self.logger.info(f"Successfully sent {len(events)} events to Loki")
            return True

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending events to Loki: {e}")
            return False

    def process_events(self, events: List[Dict[str, Any]]) -> bool:
        """Process and forward events."""
        if not events:
            return True

        # Transform events
        transformed = [self.transform_event(e) for e in events]

        # Send to Loki
        success = self.send_to_loki(transformed)

        if success:
            # Update cursor to the last event's created_at + 1ms
            last_event = events[-1]
            self.last_created_at = last_event.get("created_at", self.last_created_at) + 1
            self._save_cursor()

        return success

    def run(self):
        """Main collection loop."""
        self.logger.info("Starting CSE Events Collector v2.3.0")
        self.logger.info(f"API URL: {self.api_url}")
        self.logger.info(f"Loki URL: {self.loki_url}")
        self.logger.info(f"Poll interval: {self.poll_interval}s")

        while self.running:
            try:
                # Fetch events
                events = self.fetch_events()

                # Process and forward
                if events:
                    self.process_events(events)

                    # If we got a full batch, poll again immediately
                    if len(events) >= self.batch_size:
                        self.logger.info("Got full batch, polling again immediately")
                        continue

                # Wait for next poll
                self.logger.debug(f"Waiting {self.poll_interval}s until next poll")
                for _ in range(self.poll_interval):
                    if not self.running:
                        break
                    time.sleep(1)

            except Exception as e:
                self.logger.error(f"Unexpected error in collection loop: {e}", exc_info=True)
                time.sleep(10)  # Back off on error

        self.logger.info("CSE Events Collector stopped")


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from file or defaults."""
    config = dict(DEFAULT_CONFIG)

    # Check for config file
    if config_path:
        config_file = Path(config_path)
    else:
        config_file = Path("/etc/cse-collector/config.yaml")

    if config_file.exists():
        try:
            with open(config_file) as f:
                file_config = yaml.safe_load(f)
                if file_config:
                    config.update(file_config)
        except Exception as e:
            logging.warning(f"Could not load config file {config_file}: {e}")

    return config


def main():
    parser = argparse.ArgumentParser(description="SonicWall CSE Events Collector")
    parser.add_argument("-c", "--config", help="Path to config file")
    parser.add_argument("--api-key", help="CSE API key (or use CSE_API_KEY env var)")
    parser.add_argument("--loki-url", help="Loki push URL")
    parser.add_argument("--poll-interval", type=int, help="Poll interval in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Override with command line args
    if args.api_key:
        config["cse_api_key"] = args.api_key
    if args.loki_url:
        config["loki_url"] = args.loki_url
    if args.poll_interval:
        config["poll_interval_seconds"] = args.poll_interval
    if args.debug:
        config["log_level"] = "DEBUG"

    # Create and run collector
    try:
        collector = CSECollector(config)
        collector.run()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


if __name__ == "__main__":
    main()
