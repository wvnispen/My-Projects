#!/usr/bin/env python3
"""
SonicWall Flow Reporter - Main Entry Point
Runs either the IPFIX collector or the aggregator based on RUN_MODE
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Determine log directory
LOG_DIR = os.environ.get('LOG_DIR', '/var/log/sonicwall-flow-reporter')
Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

# Configure logging
log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    log_handlers.append(
        logging.FileHandler(f'{LOG_DIR}/collector-{datetime.now().strftime("%Y%m%d")}.log')
    )
except PermissionError:
    pass  # Skip file logging if no permissions

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger('swfr')

def main():
    run_mode = os.environ.get('RUN_MODE', 'collector').lower()
    
    logger.info(f"SonicWall Flow Reporter starting in {run_mode} mode")
    
    if run_mode == 'collector':
        from ipfix_collector import IPFIXCollector
        collector = IPFIXCollector()
        collector.run()
    elif run_mode == 'aggregator':
        from aggregator import FlowAggregator
        aggregator = FlowAggregator()
        aggregator.run()
    else:
        logger.error(f"Unknown RUN_MODE: {run_mode}")
        sys.exit(1)

if __name__ == '__main__':
    main()
