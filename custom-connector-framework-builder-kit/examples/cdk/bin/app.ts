#!/usr/bin/env node
import { App } from "aws-cdk-lib";
import { WebCrawlerConnectorStack } from "../lib/stacks/web-crawler-connector-stack";
import { GitLabConnectorStack } from "../lib/stacks/gitlab-connector-stack";
import * as process from "process";

const app = new App();

const ccfEndpoint =
  process.env.CCF_ENDPOINT ||
  "https://<your-id>.execute-api.<your-region>.amazonaws.com/prod/";

// Web Crawler configuration
const webCrawlerConfig = {
  qBusinessAppId: process.env.WEB_CRAWLER_Q_BUSINESS_APP_ID,
  qBusinessIndexId: process.env.WEB_CRAWLER_Q_BUSINESS_INDEX_ID,
  qBusinessDataSourceId: process.env.WEB_CRAWLER_Q_Q_BUSINESS_DATA_SOURCE_ID,
};

// GitLab configuration
const gitlabConfig = {
  qBusinessAppId: process.env.GITLAB_Q_BUSINESS_APP_ID,
  qBusinessIndexId: process.env.GITLAB_Q_BUSINESS_INDEX_ID,
  qBusinessDataSourceId: process.env.GITLAB_Q_BUSINESS_DATA_SOURCE_ID,
  gitlabToken: process.env.GITLAB_TOKEN,
  gitlabUrl: process.env.GITLAB_URL || "https://gitlab.com",
};

// Helper function to check if all required configs are provided
const hasRequiredConfigs = (
  configs: Record<string, string | undefined>,
): boolean => {
  return Object.values(configs).every(
    (value) => value && value.indexOf("<your-") === -1,
  );
};

// Deploy Web Crawler connector if all required configs are provided
if (hasRequiredConfigs(webCrawlerConfig)) {
  new WebCrawlerConnectorStack(app, "WebCrawlerConnectorStack", {
    env: {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    },
    ccfEndpoint,
    qBusinessAppId: webCrawlerConfig.qBusinessAppId!,
    qBusinessIndexId: webCrawlerConfig.qBusinessIndexId!,
    qBusinessDataSourceId: webCrawlerConfig.qBusinessDataSourceId!,
  });
} else {
  console.log(
    "Skipping WebCrawlerConnectorStack deployment due to missing configurations",
  );
}

// Deploy GitLab connector if all required configs are provided
if (hasRequiredConfigs(gitlabConfig)) {
  new GitLabConnectorStack(app, "GitLabConnectorStack", {
    env: {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    },
    ccfEndpoint,
    qBusinessAppId: gitlabConfig.qBusinessAppId!,
    qBusinessIndexId: gitlabConfig.qBusinessIndexId!,
    qBusinessDataSourceId: gitlabConfig.qBusinessDataSourceId!,
    gitlabToken: gitlabConfig.gitlabToken!,
    gitlabUrl: gitlabConfig.gitlabUrl,
  });
} else {
  console.log(
    "Skipping GitLabConnectorStack deployment due to missing configurations",
  );
}

app.synth();
