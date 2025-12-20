#!/bin/bash
#
# Elasticsearch Index and ILM Setup Script
# Runs once on container startup to configure indices
#

set -e

ES_HOST="http://elasticsearch:9200"
ES_USER="elastic"
ES_PASS="${ELASTIC_PASSWORD}"

echo "Waiting for Elasticsearch to be ready..."
until curl -s -u "$ES_USER:$ES_PASS" "$ES_HOST/_cluster/health" | grep -q '"status":"green"\|"status":"yellow"'; do
    sleep 5
done

echo "Elasticsearch is ready. Setting up indices..."

# ============================================================================
# Create ILM Policies
# ============================================================================

echo "Creating ILM policy for raw flows (30 days retention)..."
curl -s -X PUT "$ES_HOST/_ilm/policy/flows-raw-policy" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {
                        "max_age": "1d",
                        "max_primary_shard_size": "10gb"
                    },
                    "set_priority": {"priority": 100}
                }
            },
            "warm": {
                "min_age": "7d",
                "actions": {
                    "set_priority": {"priority": 50},
                    "shrink": {"number_of_shards": 1},
                    "forcemerge": {"max_num_segments": 1}
                }
            },
            "delete": {
                "min_age": "30d",
                "actions": {"delete": {}}
            }
        }
    }
}'

echo ""
echo "Creating ILM policy for hourly aggregates (90 days retention)..."
curl -s -X PUT "$ES_HOST/_ilm/policy/flows-hourly-policy" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {
                        "max_age": "7d",
                        "max_primary_shard_size": "20gb"
                    }
                }
            },
            "delete": {
                "min_age": "90d",
                "actions": {"delete": {}}
            }
        }
    }
}'

echo ""
echo "Creating ILM policy for daily aggregates (365 days retention)..."
curl -s -X PUT "$ES_HOST/_ilm/policy/flows-daily-policy" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "policy": {
        "phases": {
            "hot": {
                "min_age": "0ms",
                "actions": {
                    "rollover": {
                        "max_age": "30d",
                        "max_primary_shard_size": "30gb"
                    }
                }
            },
            "delete": {
                "min_age": "365d",
                "actions": {"delete": {}}
            }
        }
    }
}'

# ============================================================================
# Create Index Templates
# ============================================================================

echo ""
echo "Creating index template for raw flows..."
curl -s -X PUT "$ES_HOST/_index_template/flows-raw-template" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "index_patterns": ["flows-raw-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.lifecycle.name": "flows-raw-policy",
            "index.lifecycle.rollover_alias": "flows-raw"
        },
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "firewall_ip": {"type": "ip"},
                "firewall_name": {"type": "keyword"},
                "src_ip": {"type": "ip"},
                "dst_ip": {"type": "ip"},
                "src_port": {"type": "integer"},
                "dst_port": {"type": "integer"},
                "protocol": {"type": "keyword"},
                "protocol_name": {"type": "keyword"},
                "bytes_in": {"type": "long"},
                "bytes_out": {"type": "long"},
                "bytes_total": {"type": "long"},
                "packets_in": {"type": "long"},
                "packets_out": {"type": "long"},
                "packets_total": {"type": "long"},
                "flow_start": {"type": "date"},
                "flow_end": {"type": "date"},
                "flow_duration_ms": {"type": "long"},
                "application_id": {"type": "keyword"},
                "application_name": {"type": "keyword"},
                "interface_in": {"type": "keyword"},
                "interface_out": {"type": "keyword"},
                "tcp_flags": {"type": "keyword"},
                "direction": {"type": "keyword"},
                "nat_src_ip": {"type": "ip"},
                "nat_dst_ip": {"type": "ip"},
                "nat_src_port": {"type": "integer"},
                "nat_dst_port": {"type": "integer"},
                "user_id": {"type": "keyword"},
                "user_name": {"type": "keyword"},
                "user_department": {"type": "keyword"},
                "user_location": {"type": "keyword"},
                "src_geo": {
                    "properties": {
                        "country": {"type": "keyword"},
                        "city": {"type": "keyword"},
                        "location": {"type": "geo_point"}
                    }
                },
                "dst_geo": {
                    "properties": {
                        "country": {"type": "keyword"},
                        "city": {"type": "keyword"},
                        "location": {"type": "geo_point"}
                    }
                }
            }
        }
    }
}'

echo ""
echo "Creating index template for hourly aggregates..."
curl -s -X PUT "$ES_HOST/_index_template/flows-hourly-template" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "index_patterns": ["flows-hourly-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.lifecycle.name": "flows-hourly-policy",
            "index.lifecycle.rollover_alias": "flows-hourly"
        },
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "hour": {"type": "date"},
                "firewall_ip": {"type": "ip"},
                "user_name": {"type": "keyword"},
                "user_department": {"type": "keyword"},
                "application_name": {"type": "keyword"},
                "src_ip": {"type": "ip"},
                "dst_ip": {"type": "ip"},
                "protocol": {"type": "keyword"},
                "bytes_in": {"type": "long"},
                "bytes_out": {"type": "long"},
                "bytes_total": {"type": "long"},
                "packets_total": {"type": "long"},
                "flow_count": {"type": "long"},
                "unique_destinations": {"type": "integer"}
            }
        }
    }
}'

echo ""
echo "Creating index template for daily aggregates..."
curl -s -X PUT "$ES_HOST/_index_template/flows-daily-template" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "index_patterns": ["flows-daily-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.lifecycle.name": "flows-daily-policy",
            "index.lifecycle.rollover_alias": "flows-daily"
        },
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "day": {"type": "date"},
                "firewall_ip": {"type": "ip"},
                "user_name": {"type": "keyword"},
                "user_department": {"type": "keyword"},
                "application_name": {"type": "keyword"},
                "bytes_in": {"type": "long"},
                "bytes_out": {"type": "long"},
                "bytes_total": {"type": "long"},
                "packets_total": {"type": "long"},
                "flow_count": {"type": "long"},
                "peak_bandwidth_bps": {"type": "long"},
                "unique_destinations": {"type": "integer"},
                "unique_applications": {"type": "integer"}
            }
        }
    }
}'

echo ""
echo "Creating index template for identity mappings..."
curl -s -X PUT "$ES_HOST/_index_template/identity-template" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "index_patterns": ["identity-*"],
    "template": {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        },
        "mappings": {
            "properties": {
                "ip_address": {"type": "ip"},
                "subnet": {"type": "ip_range"},
                "user_id": {"type": "keyword"},
                "user_name": {"type": "keyword"},
                "department": {"type": "keyword"},
                "location": {"type": "keyword"},
                "description": {"type": "text"},
                "source": {"type": "keyword"},
                "last_seen": {"type": "date"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "active": {"type": "boolean"}
            }
        }
    }
}'

# ============================================================================
# Create Initial Indices with Aliases
# ============================================================================

echo ""
echo "Creating initial indices with aliases..."

# Raw flows
curl -s -X PUT "$ES_HOST/flows-raw-000001" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "aliases": {
        "flows-raw": {
            "is_write_index": true
        }
    }
}'

# Hourly aggregates
curl -s -X PUT "$ES_HOST/flows-hourly-000001" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "aliases": {
        "flows-hourly": {
            "is_write_index": true
        }
    }
}'

# Daily aggregates
curl -s -X PUT "$ES_HOST/flows-daily-000001" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json" \
    -d '{
    "aliases": {
        "flows-daily": {
            "is_write_index": true
        }
    }
}'

# Identity mappings
curl -s -X PUT "$ES_HOST/identity-mappings" \
    -u "$ES_USER:$ES_PASS" \
    -H "Content-Type: application/json"

echo ""
echo "============================================"
echo "Elasticsearch setup complete!"
echo "============================================"
echo ""
echo "Indices created:"
echo "  - flows-raw (30 day retention)"
echo "  - flows-hourly (90 day retention)"
echo "  - flows-daily (365 day retention)"
echo "  - identity-mappings"
echo ""
