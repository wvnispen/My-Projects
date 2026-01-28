#!/bin/bash
# Download GeoLite2 databases from MaxMind
# Requires a free MaxMind license key
#
# Get a free license key at: https://www.maxmind.com/en/geolite2/signup
#
# Usage: ./download-geoip.sh YOUR_LICENSE_KEY

set -e

LICENSE_KEY="${1:-}"
DB_DIR="/opt/sonicwall-flow-reporter/geoip"

if [ -z "$LICENSE_KEY" ]; then
    echo "Usage: $0 <MaxMind_License_Key>"
    echo ""
    echo "Get a free license key at: https://www.maxmind.com/en/geolite2/signup"
    echo ""
    echo "After signing up:"
    echo "1. Go to Account > Manage License Keys"
    echo "2. Generate a new license key"
    echo "3. Run this script with your key"
    exit 1
fi

echo "Creating GeoIP database directory..."
mkdir -p "$DB_DIR"

download_db() {
    local edition_id=$1
    local filename=$2
    
    echo "Downloading $edition_id..."
    
    # Download the tar.gz file
    curl -s -L -o "/tmp/${edition_id}.tar.gz" \
        "https://download.maxmind.com/app/geoip_download?edition_id=${edition_id}&license_key=${LICENSE_KEY}&suffix=tar.gz"
    
    # Check if download was successful
    if [ ! -f "/tmp/${edition_id}.tar.gz" ] || [ ! -s "/tmp/${edition_id}.tar.gz" ]; then
        echo "Error: Failed to download $edition_id"
        return 1
    fi
    
    # Extract the .mmdb file
    echo "Extracting $filename..."
    cd /tmp
    tar -xzf "${edition_id}.tar.gz"
    
    # Find and move the .mmdb file
    find . -name "*.mmdb" -path "*${edition_id}*" -exec mv {} "$DB_DIR/$filename" \;
    
    # Cleanup
    rm -rf "${edition_id}.tar.gz" ${edition_id}_*
    
    echo "Successfully installed $filename"
}

# Download City database (for country, city, coordinates)
download_db "GeoLite2-City" "GeoLite2-City.mmdb"

# Download ASN database (for organization/ISP info)
download_db "GeoLite2-ASN" "GeoLite2-ASN.mmdb"

echo ""
echo "GeoIP databases installed successfully!"
echo "Location: $DB_DIR"
ls -la "$DB_DIR"

echo ""
echo "Restart the collector to enable GeoIP enrichment:"
echo "  sudo systemctl restart swfr-collector"
