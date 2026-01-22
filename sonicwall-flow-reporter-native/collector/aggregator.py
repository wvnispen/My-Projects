#!/usr/bin/env python3
"""
Flow Aggregator Service

Runs scheduled jobs to aggregate raw flow data into:
- Hourly summaries (retained 90 days)
- Daily summaries (retained 365 days)

This reduces storage requirements while maintaining long-term trend data.
"""

import os
import logging
import schedule
import time
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch

from es_writer import AggregationWriter

logger = logging.getLogger('swfr.aggregator')


class FlowAggregator:
    """Aggregates raw flows into hourly and daily summaries"""
    
    def __init__(self):
        self.es_host = os.environ.get('ELASTICSEARCH_HOST', 'localhost')
        self.es_port = int(os.environ.get('ELASTICSEARCH_PORT', '9200'))
        self.es_password = os.environ.get('ELASTIC_PASSWORD', '')
        
        self.es_client = Elasticsearch(
            hosts=[f"http://{self.es_host}:{self.es_port}"],
            basic_auth=("elastic", self.es_password),
            retry_on_timeout=True
        )
        
        self.writer = AggregationWriter(self.es_client)
        self.running = False
        
        logger.info("Aggregator initialized")
    
    def run(self):
        """Start the aggregator scheduler"""
        self.running = True
        
        # Schedule hourly aggregation (run 5 minutes past the hour)
        schedule.every().hour.at(":05").do(self._run_hourly_aggregation)
        
        # Schedule daily aggregation (run at 00:15)
        schedule.every().day.at("00:15").do(self._run_daily_aggregation)
        
        # Run initial aggregation for any missed periods
        self._catchup_aggregation()
        
        logger.info("Aggregator scheduler started")
        
        while self.running:
            schedule.run_pending()
            time.sleep(60)
    
    def _catchup_aggregation(self):
        """Run aggregation for any missed periods on startup"""
        logger.info("Running catchup aggregation...")
        
        # Check last hourly aggregate
        last_hourly = self._get_last_aggregate_time('flows-hourly-*', 'hour')
        if last_hourly:
            # Aggregate missing hours
            current_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            hour = last_hourly + timedelta(hours=1)
            
            while hour < current_hour:
                self._aggregate_hour(hour)
                hour += timedelta(hours=1)
        
        # Check last daily aggregate
        last_daily = self._get_last_aggregate_time('flows-daily-*', 'day')
        if last_daily:
            # Aggregate missing days
            current_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            day = last_daily + timedelta(days=1)
            
            while day < current_day:
                self._aggregate_day(day)
                day += timedelta(days=1)
        
        logger.info("Catchup aggregation complete")
    
    def _get_last_aggregate_time(self, index_pattern: str, time_field: str) -> datetime:
        """Get the timestamp of the last aggregate"""
        try:
            result = self.es_client.search(
                index=index_pattern,
                body={
                    "size": 1,
                    "sort": [{time_field: "desc"}],
                    "_source": [time_field]
                }
            )
            
            if result['hits']['hits']:
                time_str = result['hits']['hits'][0]['_source'][time_field]
                return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            
        except Exception as e:
            logger.debug(f"Error getting last aggregate time: {e}")
        
        return None
    
    def _run_hourly_aggregation(self):
        """Run hourly aggregation for the previous hour"""
        previous_hour = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) - timedelta(hours=1)
        
        self._aggregate_hour(previous_hour)
    
    def _run_daily_aggregation(self):
        """Run daily aggregation for the previous day"""
        previous_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        
        self._aggregate_day(previous_day)
    
    def _aggregate_hour(self, hour: datetime):
        """Aggregate flows for a specific hour"""
        logger.info(f"Aggregating hour: {hour.isoformat()}")
        
        try:
            aggregates = self.writer.aggregate_hourly(hour)
            
            for aggregate in aggregates:
                self.writer.write_hourly_aggregate(aggregate)
            
            logger.info(f"Created {len(aggregates)} hourly aggregates for {hour.isoformat()}")
            
        except Exception as e:
            logger.error(f"Error aggregating hour {hour}: {e}")
    
    def _aggregate_day(self, day: datetime):
        """Aggregate flows for a specific day"""
        logger.info(f"Aggregating day: {day.isoformat()}")
        
        try:
            aggregates = self.writer.aggregate_daily(day)
            
            for aggregate in aggregates:
                self.writer.write_daily_aggregate(aggregate)
            
            logger.info(f"Created {len(aggregates)} daily aggregates for {day.isoformat()}")
            
        except Exception as e:
            logger.error(f"Error aggregating day {day}: {e}")
    
    def stop(self):
        """Stop the aggregator"""
        self.running = False
