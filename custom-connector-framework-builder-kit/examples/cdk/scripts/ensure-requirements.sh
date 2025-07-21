#!/bin/bash
# Script to ensure requirements.txt exists before CDK synthesis

echo "requirements.txt not found. Generating..."

# Navigate to the lambdas directory
cd lambdas

# Generate requirements.txt
make install

echo "requirements.txt generated successfully."

# Return to original directory
cd ..
