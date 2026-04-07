#!/bin/bash
set -e

echo "Starting data reset..."

# Run cleanup
echo "Running cleanup..."
python3 /app/scripts/cleanup_ingestion.py

# Run seeding from local folder
echo "Running local seeding..."
python3 /app/data/seed.py

echo "Data reset complete."
