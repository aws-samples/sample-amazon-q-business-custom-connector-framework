#!/usr/bin/env node
import 'source-map-support/register';
import { CustomConnectorFrameworkStack } from '../lib/stacks/custom-connector-framework-stack';
import { App } from 'aws-cdk-lib';

/**
 * Main CDK application entry point for the Custom Connector Framework
 */
const app = new App();

new CustomConnectorFrameworkStack(app, 'CustomConnectorFrameworkStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
    vpcId: process.env.VPC_ID,
  },
});

app.synth();
