#!/usr/bin/env python3
"""
SonicWall CSE Events API Collector
Version 2.0.0

Polls the SonicWall Cloud Secure Edge Events API and forwards events to Loki.
This replaces syslog-based collection with direct API integration.

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
from datetime import datetime, timedelta
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
            self.last_created_at = int((datetime.utcnow() - timedelta(minutes=lookback)).timestamp() * 1000)
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
    
    def transform_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Transform CSE event to Loki format."""
        # Extract timestamp (CSE uses Unix milliseconds)
        timestamp_ms = event.get("created_at", int(time.time() * 1000))
        timestamp_ns = str(timestamp_ms * 1_000_000)  # Convert to nanoseconds
        
        # Build labels
        labels = dict(self.labels)
        
        # Add event-specific labels
        labels["event_type"] = event.get("type", "unknown")
        labels["event_subtype"] = event.get("subtype", "")
        labels["severity"] = event.get("level", "INFO")
        labels["action"] = event.get("action", "")
        
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
        
        # Extract subject info (user/device)
        subject = event.get("subject", {})
        if subject:
            if subject.get("email"):
                labels["user_email"] = subject["email"]
            if subject.get("device_serial"):
                labels["device_serial"] = subject["device_serial"]
            if subject.get("os"):
                labels["device_os"] = subject["os"]
            
            # Trust data
            trust_data = subject.get("trust_data", {})
            if trust_data.get("level"):
                labels["trust_level"] = trust_data["level"]
        
        # Extract object info (service/resource)
        obj = event.get("object", {})
        if obj:
            if obj.get("service_name"):
                labels["service_name"] = obj["service_name"]
            if obj.get("service_type"):
                labels["service_type"] = obj["service_type"]
            if obj.get("access_tier_name"):
                labels["access_tier"] = obj["access_tier_name"]
            
            # Policy info
            policy = obj.get("policy", {})
            if policy.get("name"):
                labels["policy_name"] = policy["name"]
        
        # Clean up empty labels
        labels = {k: v for k, v in labels.items() if v}
        
        # Build log line
        log_parts = [event.get("message", "")]
        
        if subject.get("email"):
            log_parts.append(f"user={subject['email']}")
        if subject.get("device_friendly_name"):
            log_parts.append(f"device={subject['device_friendly_name']}")
        if subject.get("device_ip"):
            log_parts.append(f"src_ip={subject['device_ip']}")
        if obj.get("service_name"):
            log_parts.append(f"service={obj['service_name']}")
        if obj.get("host"):
            log_parts.append(f"host={obj['host']}")
        
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
        streams: Dict[str, List] = {}
        
        for event in events:
            # Create label string (sorted for consistency)
            label_items = sorted(event["labels"].items())
            label_str = "{" + ", ".join(f'{k}="{v}"' for k, v in label_items) + "}"
            
            if label_str not in streams:
                streams[label_str] = {
                    "stream": event["labels"],
                    "values": []
                }
            
            streams[label_str]["values"].append([
                event["timestamp_ns"],
                event["line"]
            ])
        
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
            response.raise_for_status()
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
        self.logger.info("Starting CSE Events Collector")
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
