#!/usr/bin/env python3
"""
SonicWall Flow Reporter - Main Entry Point
Runs either the IPFIX collector or the aggregator based on RUN_MODE
"""

import os
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'/app/logs/collector-{datetime.now().strftime("%Y%m%d")}.log')
    ]
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
