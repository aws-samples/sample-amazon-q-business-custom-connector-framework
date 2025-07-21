/**
 * GitLab Connector Stack for Amazon Q Business
 *
 * This module provides a CDK stack for deploying the GitLab connector,
 * which can index GitLab repositories in Amazon Q Business.
 */

import * as path from "path";
import { Duration, SecretValue } from "aws-cdk-lib";
import { Schedule } from "aws-cdk-lib/aws-events";
import { Secret } from "aws-cdk-lib/aws-secretsmanager";
import { Construct } from "constructs";
import {
  BaseConnectorStack,
  BaseConnectorStackProps,
} from "./base-connector-stack";

/**
 * Properties for configuring a GitLabConnectorStack
 *
 * This interface extends BaseConnectorStackProps but omits some properties
 * that are hardcoded for the GitLab connector.
 */
interface GitLabConnectorStackProps
  extends Omit<
    BaseConnectorStackProps,
    | "connectorName"
    | "connectorDescription"
    | "connectorPath"
    | "qBusinessConfig"
    | "entryPoint"
    | "environmentVariables"
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

  /**
   * GitLab API token for authentication
   *
   * This token will be stored securely in AWS Secrets Manager
   */
  gitlabToken: string;

  /**
   * GitLab instance URL (optional, defaults to https://gitlab.com)
   */
  gitlabUrl?: string;
}

/**
 * CDK Stack for deploying the GitLab connector
 *
 * This stack configures and deploys a GitLab connector that can
 * index GitLab repositories in Amazon Q Business. It securely stores
 * the GitLab API token in AWS Secrets Manager.
 */
export class GitLabConnectorStack extends BaseConnectorStack {
  /**
   * Creates a new GitLabConnectorStack
   *
   * @param scope The parent construct
   * @param id The construct ID
   * @param props Configuration properties for the stack
   */
  constructor(scope: Construct, id: string, props: GitLabConnectorStackProps) {
    // Resolve the path to the GitLab connector code
    const connectorPath = path.join(__dirname, "../../../../examples/gitlab");

    // Initialize the base connector stack with GitLab specific configuration
    // Note: We initially set environmentVariables to an empty object because
    // we need to create the secret first, then update the environment variables
    super(scope, id, {
      ...props,
      connectorName: "gitlab-connector",
      connectorDescription: "GitLab Connector for Amazon Q Business",
      connectorPath: connectorPath,
      entryPoint: ["python", "custom_connector_cli.py"],
      memory: 2048, // 2GB memory
      cpu: 1, // 1 vCPU
      timeout: 900, // 15 minutes (maximum execution time)
      schedule: Schedule.rate(Duration.days(1)), // Run daily
      qBusinessConfig: {
        applicationId: props.qBusinessAppId,
      },
      environmentVariables: {}, // Will be updated after secret creation
    });

    // Create a secret to store the GitLab API token securely
    // This is more secure than passing the token as an environment variable
    const gitlabTokenSecret = new Secret(this, "GitLabTokenSecret", {
      description: "GitLab API token for the GitLab connector",
      secretStringValue: SecretValue.unsafePlainText(props.gitlabToken),
    });

    // Grant the connector job role permission to read the secret
    gitlabTokenSecret.grantRead(this.jobRole);

    // Update the environment variables with all required configuration
    // Including the ARN of the secret containing the GitLab token
    this.updateEnvironmentVariables({
      GITLAB_CONFIG_PATH: "/var/task/gitlab_config.json",
      Q_BUSINESS_APP_ID: props.qBusinessAppId,
      Q_BUSINESS_INDEX_ID: props.qBusinessIndexId,
      Q_BUSINESS_DATA_SOURCE_ID: props.qBusinessDataSourceId,
      GITLAB_URL: props.gitlabUrl || "https://gitlab.com",
      AWS_DATA_PATH: "/var/task/",
      GITLAB_TOKEN_SECRET_ARN: gitlabTokenSecret.secretArn,
    });
  }
}
