import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterator
from urllib.parse import urlparse

import boto3
import requests
from bs4 import BeautifulSoup
from requests_html import HTMLSession
import pyppeteer

from custom_connector_framework.ccf_client import CCFClient
from custom_connector_framework.custom_connector_interface import \
    QBusinessCustomConnectorInterface
from custom_connector_framework.models.document import (Document, DocumentFile,
                                                        DocumentMetadata)
from custom_connector_framework.models.qbusiness import (AccessControl,
                                                         AccessType,
                                                         MemberRelation,
                                                         MembershipType,
                                                         Principal,
                                                         PrincipalUser)

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Environment variable names
ENV_CONFIG_FILE = "CRAWLER_CONFIG_PATH"
ENV_APP_ID = "Q_BUSINESS_APP_ID"
ENV_INDEX_ID = "Q_BUSINESS_INDEX_ID"
ENV_DATA_SOURCE_ID = "Q_BUSINESS_DATA_SOURCE_ID"
ENV_S3_BUCKET = "OUTPUT_BUCKET"  # Optional, but needed for files larger than 10MB
ENV_REGION = "AWS_REGION"  # Provided by framework
ENV_CCF_ENDPOINT = "CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT"
ENV_CCF_CONNECTOR_ID = "CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID"
ENV_LOG_LEVEL = "LOG_LEVEL"


class WebCrawlerConnector(QBusinessCustomConnectorInterface):
    def __init__(self, config: Dict[str, Any], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.urls_config = config.get("urls", [])
        self.global_acl = config.get("global_acl")
        
        # Initialize browser settings for better performance
        self._initialize_browser_settings()
    
    def _initialize_browser_settings(self):
        """Configure pyppeteer for optimal performance in containerized environments"""
        try:
            # Set environment variables for pyppeteer
            os.environ["PYPPETEER_CHROMIUM_REVISION"] = "1181205"  # Use a specific Chromium version
            
            # Set pyppeteer launch options via environment variables
            os.environ["PYPPETEER_ARGS"] = "--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage --disable-gpu"
            
            logger.info("Browser settings initialized for optimal performance")
        except Exception as e:
            logger.warning(f"Failed to initialize browser settings: {e}")
            # Continue even if initialization fails

    def _create_access_control(self, acl_config: Dict[str, Any]) -> AccessControl:
        """Create AccessControl object from ACL configuration"""
        principals = []
        for principal in acl_config.get("principals", []):
            principals.append(
                Principal(
                    user=PrincipalUser(
                        id=principal["user_id"],
                        access=AccessType(principal["access"]),
                        membershipType=MembershipType(principal["membership_type"]),
                    )
                )
            )

        return AccessControl(memberRelation=MemberRelation.OR, principals=principals)

    def _crawl_url(self, url: str):
        """Crawl a URL and extract content, handling both HTML and PDF"""
        logger.info(f"Processing {url}")

        try:
            # First check if it's a PDF
            response = requests.head(url, timeout=30)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()

            if "application/pdf" in content_type:
                # Handle PDF content
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                content = response.content
                title = urlparse(url).path.split("/")[-1]
                is_binary = True
                file_suffix = ".pdf"
                file_mode = "wb"
            else:
                # Handle HTML content with JavaScript rendering
                try:
                    session = HTMLSession()
                    response = session.get(url, timeout=30)

                    try:
                        # Try to render JavaScript content with enhanced options
                        # Using only parameters that are supported by the render method
                        response.html.render(
                            timeout=60,  # Increased timeout
                            sleep=2,     # Wait after rendering
                            scrolldown=3,  # Scroll down to render more content
                            keep_page=True  # Keep page in memory for better performance
                        )
                        content = response.html.html
                    except Exception as e:
                        logger.warning(f"JavaScript rendering failed, falling back to static content: {e}")
                        content = response.text
                except Exception as e:
                    logger.warning(f"HTMLSession failed, falling back to regular requests: {e}")
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    content = response.text

                soup = BeautifulSoup(content, "html.parser")
                title = soup.title.string.strip() if soup.title else url
                is_binary = False
                file_suffix = ".html"
                file_mode = "w"

            # Calculate checksum for content
            checksum = hashlib.sha256(content.encode("utf-8") if isinstance(content, str) else content).hexdigest()

            return {
                "content": content,
                "title": title,
                "is_binary": is_binary,
                "file_suffix": file_suffix,
                "file_mode": file_mode,
                "checksum": checksum,
            }

        except Exception as e:
            logger.error(f"Failed to process {url}: {e}")
            return None

    def get_documents_to_add(self) -> Iterator[Document]:
        for url_entry in self.urls_config:
            url = url_entry["url"]

            # Crawl the URL with enhanced capabilities
            crawled_data = self._crawl_url(url)
            if not crawled_data:
                continue

            # Create a temporary file to store the content
            with NamedTemporaryFile(
                mode=crawled_data["file_mode"], suffix=crawled_data["file_suffix"], delete=False
            ) as temp_file:
                temp_file.write(crawled_data["content"])
                temp_file.flush()
                temp_file_path = Path(temp_file.name)

            # Use URL-specific ACL if provided, otherwise use global ACL
            acl_config = url_entry.get("acl", self.global_acl)
            access_control_list = []
            if acl_config:
                access_control_list.append(self._create_access_control(acl_config))

            # Create document with enhanced metadata
            doc = Document(
                id=url,
                file=DocumentFile(temp_file_path),
                metadata=DocumentMetadata(
                    title=crawled_data["title"],
                    source_uri=url,
                    attributes={
                        "url": url,
                        "content_type": "PDF" if crawled_data["is_binary"] else "HTML",
                        "checksum": crawled_data["checksum"],
                        "domain": urlparse(url).netloc,
                    },
                    access_control_list=access_control_list,
                ),
            )
            yield doc

    def get_documents_to_delete(self) -> Iterator[str]:
        return iter([])


def load_config_file(file_path: str) -> Dict[str, Any]:
    """Load and validate the configuration file"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Basic validation
        if "urls" not in config:
            raise ValueError("Configuration file must contain 'urls' key")

        if not isinstance(config["urls"], list):
            raise ValueError("'urls' must be a list")

        for url_entry in config["urls"]:
            if not isinstance(url_entry, dict) or "url" not in url_entry:
                raise ValueError("Each URL entry must be a dictionary with at least a 'url' key")

        return config
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading configuration file: {e}")


def get_config():
    """Get configuration from environment variables and command line arguments."""
    parser = argparse.ArgumentParser(description="Web Crawler Connector for Amazon Q Business")

    parser.add_argument(
        "--config-file",
        type=str,
        default=os.getenv(ENV_CONFIG_FILE, "/var/task/crawler_urls.json"),
        help="Path to the crawler configuration JSON file",
    )
    parser.add_argument(
        "--app-id",
        type=str,
        default=os.getenv(ENV_APP_ID),
        help="Amazon Q Business Application ID",
    )
    parser.add_argument(
        "--index-id",
        type=str,
        default=os.getenv(ENV_INDEX_ID),
        help="Amazon Q Business Index ID",
    )
    parser.add_argument(
        "--data-source-id",
        type=str,
        default=os.getenv(ENV_DATA_SOURCE_ID),
        help="Amazon Q Business Data Source ID",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=os.getenv(ENV_S3_BUCKET),
        help="S3 bucket name for large document storage (optional)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=os.getenv(ENV_REGION, "us-east-1"),
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=os.getenv(ENV_LOG_LEVEL, "INFO"),
        help="Set the logging level",
    )
    parser.add_argument(
        "--ccf-endpoint",
        type=str,
        default=os.getenv(ENV_CCF_ENDPOINT),
        help="The endpoint for the custom connector framework",
    )
    parser.add_argument(
        "--ccf-connector-id",
        type=str,
        default=os.getenv(ENV_CCF_CONNECTOR_ID),
        help="The custom connector ID for the custom connector framework",
    )

    args = parser.parse_args()

    # Validate required parameters
    required_params = {
        "config_file": args.config_file,
        "app_id": args.app_id,
        "index_id": args.index_id,
        "data_source_id": args.data_source_id,
    }

    missing_params = [k for k, v in required_params.items() if not v]
    if missing_params:
        parser.error(f"Missing required parameters: {', '.join(missing_params)}")

    return args


def main():
    """
    Main function that can be run either through CLI or with environment variables.

    Environment variables:
    CRAWLER_CONFIG_PATH="/var/task/crawler_urls.json"
    Q_BUSINESS_APP_ID="your-app-id"
    Q_BUSINESS_INDEX_ID="your-index-id"
    Q_BUSINESS_DATA_SOURCE_ID="your-data-source-id"
    OUTPUT_BUCKET="your-bucket"
    AWS_REGION="your-region"
    CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT="your-ccf-endpoint"
    CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID="your-ccf-connector-id"
    LOG_LEVEL="INFO"

    The CCF client initialization requires two parameters:
    1. A boto3 client for the CCF service, created with the endpoint URL and region
    2. The connector ID for the custom connector

    When deployed by the Custom Connector Framework, these values are provided as environment variables:
    - CUSTOM_CONNECTOR_FRAMEWORK_API_ENDPOINT: The endpoint URL for the CCF API
    - CUSTOM_CONNECTOR_FRAMEWORK_CUSTOM_CONNECTOR_ID: The ID of the custom connector
    """
    config = get_config()
    logging.getLogger().setLevel(getattr(logging, config.log_level))

    try:
        # Load and validate the configuration file
        crawler_config = load_config_file(config.config_file)

        # Initialize clients
        q_client = boto3.client("qbusiness", region_name=config.region)
        s3_client = boto3.client("s3", region_name=config.region) if config.s3_bucket else None
        ccf_client = None

        if config.ccf_endpoint and config.ccf_connector_id:
            try:
                # Create a boto3 client for the CCF service
                boto3_ccf_client = boto3.client(
                    "ccf",
                    endpoint_url=config.ccf_endpoint,
                    region_name=config.region,
                )
                # Initialize the CCFClient with the boto3 client and connector ID
                ccf_client = CCFClient(
                    ccf_client=boto3_ccf_client,
                    connector_id=config.ccf_connector_id,
                )
            except Exception as e:
                logger.error(f"Failed to initialize CCF client: {e}")
                logger.warning("Continuing without CCF client")

        logger.info("Initializing Web Crawler Connector...")
        connector = WebCrawlerConnector(
            config=crawler_config,
            ccf_client=ccf_client,
            qbusiness_client=q_client,
            qbusiness_app_id=config.app_id,
            qbusiness_index_id=config.index_id,
            qbusiness_data_source_id=config.data_source_id,
            s3_client=s3_client,
            s3_bucket=config.s3_bucket,
        )

        logger.info("Starting sync process...")
        connector.sync()
        logger.info("Sync process completed successfully!")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
