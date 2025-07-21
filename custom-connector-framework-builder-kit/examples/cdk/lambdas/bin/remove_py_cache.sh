#!/bin/bash

# Remove Python cache files recursively from the specified directory
# Usage: ./remove_py_cache.sh <directory>

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <directory>"
  exit 1
fi

DIR="$1"

echo "Removing Python cache files from $DIR"

# Find and remove __pycache__ directories
find "$DIR" -type d -name "__pycache__" -exec rm -rf {} +

# Find and remove .pyc files
find "$DIR" -type f -name "*.pyc" -delete

echo "Done!"
