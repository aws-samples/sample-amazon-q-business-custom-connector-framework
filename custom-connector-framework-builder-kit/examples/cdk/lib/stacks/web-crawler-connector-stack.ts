/**
 * Web Crawler Connector Stack for Amazon Q Business
 *
 * This module provides a CDK stack for deploying the Web Crawler connector,
 * which can crawl websites and index their content in Amazon Q Business.
 */

import * as path from "path";
import { Duration, Stack } from "aws-cdk-lib";
import { Schedule } from "aws-cdk-lib/aws-events";
import { Construct } from "constructs";
import {
  BaseConnectorStack,
  BaseConnectorStackProps,
} from "./base-connector-stack";

/**
 * Properties for configuring a WebCrawlerConnectorStack
 *
 * This interface extends BaseConnectorStackProps but omits some properties
 * that are hardcoded for the Web Crawler connector.
 */
interface WebCrawlerConnectorStackProps
  extends Omit<
    BaseConnectorStackProps,
    | "connectorName"
    | "connectorDescription"
    | "connectorPath"
    | "qBusinessConfig"
    | "entryPoint"
  > {
  /**
   * The ID of the Amazon Q Business application to index content in
   */
  qBusinessAppId: string;

  /**
   * The ID of the Amazon Q Business index to use
   */
  qBusinessIndexId: string;

  /**
   * The ID of the Amazon Q Business data source to use
   */
  qBusinessDataSourceId: string;
}

/**
 * CDK Stack for deploying the Web Crawler connector
 *
 * This stack configures and deploys a Web Crawler connector that can
 * crawl websites and index their content in Amazon Q Business.
 */
export class WebCrawlerConnectorStack extends BaseConnectorStack {
  /**
   * Creates a new WebCrawlerConnectorStack
   *
   * @param scope The parent construct
   * @param id The construct ID
   * @param props Configuration properties for the stack
   */
  constructor(
    scope: Construct,
    id: string,
    props: WebCrawlerConnectorStackProps,
  ) {
    // Resolve the path to the web crawler connector code
    const connectorPath = path.join(
      __dirname,
      "../../../../examples/web_crawler",
    );

    // Initialize the base connector stack with web crawler specific configuration
    super(scope, id, {
      ...props,
      connectorName: "web-crawler-connector",
      connectorDescription: "Web Crawler Connector for Amazon Q Business",
      connectorPath: connectorPath,
      entryPoint: ["python", "custom_connector_cli.py"],
      memory: 4096, // 4GB memory (increased from 2GB)
      cpu: 2, // 2 vCPU (increased from 1)
      timeout: 900, // 15 minutes (maximum crawl time)
      schedule: Schedule.rate(Duration.days(1)), // Run daily
      // Configure Amazon Q Business integration
      qBusinessConfig: {
        applicationId: props.qBusinessAppId,
      },
      // Environment variables passed to the connector container
      environmentVariables: {
        CRAWLER_CONFIG_PATH: "/var/task/crawler_urls.json",
        Q_BUSINESS_APP_ID: props.qBusinessAppId,
        Q_BUSINESS_INDEX_ID: props.qBusinessIndexId,
        Q_BUSINESS_DATA_SOURCE_ID: props.qBusinessDataSourceId,
      },
    });
  }
}
