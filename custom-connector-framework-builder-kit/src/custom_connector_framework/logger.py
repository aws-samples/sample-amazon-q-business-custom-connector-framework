"""
Logging configuration for the Custom Connector Framework.

This module sets up a standardized logger for use throughout the framework,
ensuring consistent log formatting and behavior.
"""

import logging

# Set up logging with timestamp, log level, and message format
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Create a named logger for the framework
logger = logging.getLogger(__name__)
