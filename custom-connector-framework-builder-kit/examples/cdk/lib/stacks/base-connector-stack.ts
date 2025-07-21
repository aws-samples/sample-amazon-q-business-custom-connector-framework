/**
 * Base Connector Stack for Amazon Q Business Custom Connector Framework
 *
 * This module provides the core infrastructure components needed to deploy
 * and run custom connectors for Amazon Q Business. It handles:
 * - Docker image building and deployment
 * - IAM role configuration
 * - Custom connector registration
 * - Scheduled job execution
 */

import {
  Stack,
  StackProps,
  Duration,
  CfnOutput,
  CustomResource,
  CfnRule,
  RemovalPolicy,
} from "aws-cdk-lib";
import { Construct } from "constructs";
import * as FileUtils from "../utils/file-utils";
import { Names } from "aws-cdk-lib";
import { DockerImageAsset, Platform } from "aws-cdk-lib/aws-ecr-assets";
import {
  ManagedPolicy,
  PolicyStatement,
  Role,
  ServicePrincipal,
} from "aws-cdk-lib/aws-iam";
import { Provider } from "aws-cdk-lib/custom-resources";
import { Code, Runtime, Function } from "aws-cdk-lib/aws-lambda";
import { LogGroup, RetentionDays } from "aws-cdk-lib/aws-logs";
import { Rule, RuleTargetInput, Schedule } from "aws-cdk-lib/aws-events";
import { LambdaFunction } from "aws-cdk-lib/aws-events-targets";
import * as path from "path";
import * as fs from "fs";

/**
 * Configuration interface for Amazon Q Business integration
 */
export interface QBusinessConfig {
  /**
   * The ID of the Amazon Q Business application to integrate with
   */
  applicationId: string;
}

/**
 * Properties for configuring a BaseConnectorStack
 */
export interface BaseConnectorStackProps extends StackProps {
  /**
   * Name of the custom connector
   */
  connectorName: string;

  /**
   * Description of the custom connector's purpose
   */
  connectorDescription: string;

  /**
   * Endpoint URL for the Custom Connector Framework API
   */
  ccfEndpoint: string;

  /**
   * Path to the connector code on the local filesystem
   */
  connectorPath: string;

  /**
   * Docker entrypoint command for the connector container
   */
  entryPoint: string[];

  /**
   * Memory allocation for the connector job in MB (optional)
   */
  memory?: number;

  /**
   * CPU allocation for the connector job in vCPU units (optional)
   */
  cpu?: number;

  /**
   * Timeout for the connector job in seconds (optional)
   */
  timeout?: number;

  /**
   * Schedule for automatic connector job execution (optional)
   */
  schedule?: Schedule;

  /**
   * Environment variables to pass to the connector job (optional)
   */
  environmentVariables?: Record<string, string>;

  /**
   * Amazon Q Business configuration (optional)
   */
  qBusinessConfig?: QBusinessConfig;

  /**
   * Log retention period for Lambda functions (optional, defaults to 1 day)
   */
  logRetention?: RetentionDays;
}

/**
 * Base stack for deploying custom connectors for Amazon Q Business
 *
 * This stack provides the core infrastructure for running custom connectors,
 * including Docker image building, IAM role configuration, and job scheduling.
 */
export class BaseConnectorStack extends Stack {
  /**
   * IAM role used by the ECS task execution
   */
  protected executionRole: Role;

  /**
   * IAM role used by the connector job itself
   */
  protected jobRole: Role;

  /**
   * API Gateway ID extracted from the CCF endpoint
   */
  protected ccfEndpointId: string;

  /**
   * Full endpoint URL for the CCF API
   */
  protected ccfEndpoint: string;

  /**
   * Lambda function that starts connector jobs
   */
  protected jobFunction: Function;

  /**
   * EventBridge rule for scheduled job execution
   */
  protected rule?: Rule;

  /**
   * Name of the custom connector
   */
  protected connectorName: string;

  /**
   * Custom resource for the connector
   */
  protected connector: CustomResource;

  /**
   * Schedule for automatic job execution
   */
  protected schedule?: Schedule;

  /**
   * Removal policy for resources when stack is deleted
   */
  protected removalPolicy: RemovalPolicy;

  /**
   * Creates a new BaseConnectorStack
   *
   * @param scope The parent construct
   * @param id The construct ID
   * @param props Configuration properties for the stack
   */
  constructor(scope: Construct, id: string, props: BaseConnectorStackProps) {
    super(scope, id, props);
    const uniqueId = Names.uniqueId(this);

    this.ccfEndpoint = props.ccfEndpoint;
    this.connectorName = props.connectorName;
    this.schedule = props.schedule;
    this.removalPolicy = RemovalPolicy.DESTROY; // Ensure logs are deleted when stack is deleted

    // Set log retention period (default to 1 day if not specified)
    const logRetention = props.logRetention || RetentionDays.ONE_DAY;

    // Build the Docker image containing the connector code
    const dockerImage = this.buildConnectorImage(
      props.connectorPath,
      props.entryPoint,
    );

    // Create execution role for ECS tasks
    this.executionRole = new Role(this, "ExecutionRole", {
      assumedBy: new ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: `Execution role for ${props.connectorName} connector`,
    });

    this.executionRole.addManagedPolicy(
      ManagedPolicy.fromAwsManagedPolicyName(
        "service-role/AmazonECSTaskExecutionRolePolicy",
      ),
    );

    // Create job role for connector code
    this.jobRole = new Role(this, "JobRole", {
      assumedBy: new ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: `Job role for ${props.connectorName} connector`,
    });

    // Extract API ID from the CCF endpoint for IAM permissions
    this.ccfEndpointId = props.ccfEndpoint.split("//")[1]?.split(".")[0];

    // Add base policies required by all connectors
    this.addBasePolicies(props);

    // Add Q Business policies if config is provided
    if (props.qBusinessConfig) {
      this.addQBusinessPolicies(props.qBusinessConfig);
    }

    // Create custom resource provider for connector registration
    const createConnectorFunction = new Function(
      this,
      `CreateCustomConnectorFn-${uniqueId}`,
      {
        runtime: Runtime.PYTHON_3_12,
        handler: "create_custom_connector_custom_resource.handler",
        code: Code.fromAsset(path.join("lambdas", "src")),
        timeout: Duration.minutes(5),
        environment: {
          AWS_DATA_PATH: "/var/task/",
          CCF_ENDPOINT: props.ccfEndpoint,
        },
      },
    );

    // Create log group with retention policy for CreateCustomConnectorFn
    new LogGroup(this, `CreateCustomConnectorFnLogGroup-${uniqueId}`, {
      logGroupName: `/aws/lambda/${createConnectorFunction.functionName}`,
      retention: logRetention,
      removalPolicy: this.removalPolicy,
    });

    const onEventHandler = new Provider(
      this,
      `CreateCustomConnectorProvider-${uniqueId}`,
      {
        onEventHandler: createConnectorFunction,
      },
    );

    // Grant permissions to call the CCF API
    createConnectorFunction.addToRolePolicy(
      new PolicyStatement({
        actions: ["execute-api:Invoke"],
        resources: [
          `arn:aws:execute-api:${this.region}:${this.account}:${this.ccfEndpointId}/prod/*/api/v1/custom-connectors*`,
        ],
      }),
    );

    // Create the custom connector using the custom resource
    this.connector = new CustomResource(
      this,
      `CreateCustomConnectorCustomResource-${uniqueId}`,
      {
        serviceToken: onEventHandler.serviceToken,
        properties: {
          ConnectorName: props.connectorName,
          Description: props.connectorDescription,
          DockerImageUri: dockerImage.imageUri,
          ExecutionRoleArn: this.executionRole.roleArn,
          JobRoleArn: this.jobRole.roleArn,
          Memory: props.memory,
          Cpu: props.cpu,
          Timeout: props.timeout,
        },
      },
    );

    // Store the connector ID as the physical ID of the custom resource
    const connectorId = this.connector.ref;

    // Output the connector name for reference
    new CfnOutput(this, "ConnectorName", {
      value: props.connectorName,
      description: "The name of the custom connector",
    });

    // Output the connector ID for reference
    const connectorIdOutput = new CfnOutput(this, "ConnectorId", {
      value: connectorId,
      description: "The ID of the custom connector",
    });

    // Create scheduled job if a schedule is provided
    if (props.schedule) {
      this.createScheduledJob(
        props,
        uniqueId,
        connectorId,
        props.environmentVariables || {},
        logRetention,
      );
    }
  }

  /**
   * Updates environment variables for the scheduled job Lambda function
   *
   * This method allows updating environment variables after the stack is created,
   * which is useful for dynamic configuration changes.
   *
   * @param newEnvVars New environment variables to set
   */
  protected updateEnvironmentVariables(newEnvVars: Record<string, string>) {
    // Update the environment variables for the Lambda function
    if (this.jobFunction) {
      Object.entries(newEnvVars).forEach(([key, value]) => {
        this.jobFunction.addEnvironment(key, value);
      });
    }

    // Update the Rule if it exists by recreating it with the new environment variables
    if (this.rule) {
      // Store the original schedule
      const originalSchedule = this.schedule;

      // Remove the existing rule completely
      const ruleId = this.rule.node.id;
      const parentNode = this.rule.node.scope as Construct;
      parentNode.node.tryRemoveChild(ruleId);

      // Create a new rule with a unique id
      const uniqueId = Names.uniqueId(this);
      this.rule = this.createEventRule(`${uniqueId}-${Date.now()}`, newEnvVars);
    }
  }

  /**
   * Creates an EventBridge rule for scheduled job execution
   *
   * @param uniqueId Unique identifier for the rule
   * @param environmentVariables Environment variables to pass to the job
   * @returns The created EventBridge rule
   */
  private createEventRule(
    uniqueId: string,
    environmentVariables: Record<string, string>,
  ): Rule {
    return new Rule(this, `StartCustomConnectorJobSchedule-${uniqueId}`, {
      schedule: this.schedule,
      description: `Schedule for ${this.connectorName} connector job`,
      targets: [
        new LambdaFunction(this.jobFunction, {
          event: RuleTargetInput.fromObject({
            environment: environmentVariables,
            ccf_endpoint: this.ccfEndpoint,
          }),
        }),
      ],
    });
  }

  /**
   * Creates a Lambda function and EventBridge rule for scheduled job execution
   *
   * @param props Stack properties
   * @param uniqueId Unique identifier for resources
   * @param connectorId ID of the custom connector
   * @param environmentVariables Environment variables to pass to the job
   * @param logRetention Log retention period for Lambda functions
   */
  private createScheduledJob(
    props: BaseConnectorStackProps,
    uniqueId: string,
    connectorId: string,
    environmentVariables: Record<string, string>,
    logRetention: RetentionDays,
  ): void {
    // Create Lambda function to start the connector job
    this.jobFunction = new Function(
      this,
      `StartCustomConnectorJobFn-${uniqueId}`,
      {
        runtime: Runtime.PYTHON_3_12,
        handler: "start_custom_connector_job.handler",
        code: Code.fromAsset(path.join("lambdas", "src")),
        timeout: Duration.seconds(5),
        environment: {
          AWS_DATA_PATH: "/var/task/",
          CCF_ENDPOINT: props.ccfEndpoint,
          CUSTOM_CONNECTOR_ID: connectorId,
          ...environmentVariables,
        },
      },
    );

    // Create log group with retention policy for StartCustomConnectorJobFn
    new LogGroup(this, `StartCustomConnectorJobFnLogGroup-${uniqueId}`, {
      logGroupName: `/aws/lambda/${this.jobFunction.functionName}`,
      retention: RetentionDays.ONE_DAY,
      removalPolicy: this.removalPolicy,
    });

    // Ensure Lambda is created after the connector is available
    this.jobFunction.node.addDependency(this.connector);

    // Grant permissions to start connector jobs
    this.jobFunction.addToRolePolicy(
      new PolicyStatement({
        actions: ["execute-api:Invoke"],
        resources: [
          `arn:aws:execute-api:${this.region}:${this.account}:${this.ccfEndpointId}/prod/*/api/v1/custom-connectors/*/jobs`,
        ],
      }),
    );

    // Create scheduled rule if schedule is provided
    if (props.schedule) {
      this.rule = this.createEventRule(uniqueId, environmentVariables);
    }
  }

  /**
   * Builds a Docker image containing the connector code and dependencies
   *
   * This method:
   * 1. Creates a temporary build directory
   * 2. Copies connector code and framework files
   * 3. Creates a Dockerfile if one doesn't exist
   * 4. Builds and uploads the Docker image
   *
   * @param connectorPath Path to the connector code
   * @param entryPoint Docker entrypoint command
   * @returns The built Docker image asset
   */
  private buildConnectorImage(
    connectorPath: string,
    entryPoint: string[],
  ): DockerImageAsset {
    // Create a temporary build directory
    const buildDir = FileUtils.sanitizePath(connectorPath, "build");
    FileUtils.ensureDirectoryExists(buildDir);

    // Copy connector files to the build directory
    FileUtils.copyDirectory(connectorPath, buildDir, [
      "build",
      "__pycache__",
      "*.pyc",
      ".DS_Store",
    ]);

    // Copy framework files to a separate directory to avoid collisions
    const frameworkBuildDir = FileUtils.sanitizePath(buildDir, "framework");
    FileUtils.ensureDirectoryExists(frameworkBuildDir);

    // Copy framework files
    const frameworkPath = path.join(__dirname, "../../../../src");
    FileUtils.copyDirectory(
      frameworkPath,
      FileUtils.sanitizePath(frameworkBuildDir, "src"),
      ["__pycache__", "*.pyc", ".DS_Store", "*.egg-info", "dist", "*.so"],
    );

    // Copy pyproject.toml for framework installation
    // Use path.resolve to safely navigate up one directory from frameworkPath
    const frameworkPyprojectPath = path.resolve(
      frameworkPath,
      "../pyproject.toml",
    );
    const buildFrameworkPyprojectPath = path.join(
      frameworkBuildDir,
      "pyproject.toml",
    );
    fs.copyFileSync(frameworkPyprojectPath, buildFrameworkPyprojectPath);

    // Copy CCF service model for boto3 client
    const modelPath = path.resolve(
      __dirname,
      "../../../../../custom-connector-framework-infrastructure/cdk/model/ccf-service-model.json",
    );

    if (!fs.existsSync(modelPath)) {
      throw new Error(`Service model file not found at: ${modelPath}. 
            Expected at: ${modelPath}`);
    }

    // Copy model to Docker build context
    const dockerDest = FileUtils.sanitizePath(buildDir, "ccf/2025-06-01");
    FileUtils.ensureDirectoryExists(dockerDest);
    fs.copyFileSync(
      modelPath,
      FileUtils.sanitizePath(dockerDest, "service-2.json"),
    );

    // Copy model to Lambda code
    const lambdaDest = FileUtils.sanitizePath("lambdas", "src/ccf/2025-06-01");
    FileUtils.ensureDirectoryExists(lambdaDest);
    fs.copyFileSync(
      modelPath,
      FileUtils.sanitizePath(lambdaDest, "service-2.json"),
    );

    // Update requirements.txt to remove the local framework reference
    const originalRequirements = fs.readFileSync(
      FileUtils.sanitizePath(connectorPath, "requirements.txt"),
      "utf8",
    );

    // Remove the -e ../.. line completely
    const requirements = originalRequirements.replace(
      /^\s*-e\s+\.\.\/\.\.\s*$/m,
      "# Framework will be installed separately",
    );

    FileUtils.writeFileWithDirs(
      FileUtils.sanitizePath(buildDir, "requirements.txt"),
      requirements,
    );

    // Create Dockerfile if it doesn't exist
    const dockerfilePath = FileUtils.sanitizePath(buildDir, "Dockerfile");
    if (!fs.existsSync(dockerfilePath)) {
      FileUtils.writeFileWithDirs(
        dockerfilePath,
        this.getDefaultDockerfile(entryPoint),
      );
    }

    // Build and upload the Docker image
    const dockerImage = new DockerImageAsset(this, "ConnectorImage", {
      directory: buildDir,
      platform: Platform.LINUX_AMD64,
    });

    // Clean up build directory
    fs.rmdirSync(buildDir, { recursive: true });

    return dockerImage;
  }

  /**
   * Sanitizes a file path to prevent path traversal attacks
   * @param basePath The base directory that should contain the path
   * @param userPath The path to sanitize
   */

  /**
   * Sanitizes a file path to prevent path traversal attacks
   * @param basePath The base directory that should contain the path
   * @param userPath The path to sanitize


  /**
   * Generates a default Dockerfile for the connector
   *
   * @param entryPoint Docker entrypoint command
   * @returns Dockerfile content as a string
   */
  private getDefaultDockerfile(entryPoint: string[]): string {
    const ep = JSON.stringify(entryPoint);
    return `
      FROM public.ecr.aws/lambda/python:3.12
      
      # First install the framework to avoid file collisions
      COPY framework /tmp/framework/
      WORKDIR /tmp/framework
      RUN pip install -e .
      
      # Now copy the connector code
      COPY . /var/task/
      
      # Debug - List files to verify they're copied correctly
      RUN echo "Contents of /var/task:" && ls -la /var/task/
      
      # Install requirements
      WORKDIR /var/task
      RUN pip install --no-cache-dir -r requirements.txt
      
      # Set the AWS_DATA_PATH for the CCF model
      ENV AWS_DATA_PATH=/var/task/
      
      # Add framework source directory to Python path
      ENV PYTHONPATH=/tmp/framework/src:$PYTHONPATH
      
      # Verify the framework can be imported
      RUN python -c "import custom_connector_framework; print('Successfully imported custom_connector_framework')"
      
      # Set the entry point
      ENTRYPOINT ${ep}
    `.trim();
  }

  /**
   * Adds base IAM policies required by all connectors
   *
   * These policies grant:
   * 1. CloudWatch Logs permissions for job logging
   * 2. CCF API permissions for checkpoint and document management
   *
   * @param props Stack properties
   */
  private addBasePolicies(props: BaseConnectorStackProps): void {
    // Add CloudWatch Logs permissions
    this.jobRole.addToPolicy(
      new PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [
          `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/batch/job*`,
        ],
      }),
    );

    // Add CCF API permissions for checkpoint and document management
    const ccfBaseArnPrefix = `arn:aws:execute-api:${this.region}:${this.account}:${this.ccfEndpointId}/prod`;
    this.jobRole.addToPolicy(
      new PolicyStatement({
        actions: ["execute-api:Invoke"],
        resources: [
          `${ccfBaseArnPrefix}/GET/api/v1/custom-connectors/*/checkpoint`,
          `${ccfBaseArnPrefix}/PUT/api/v1/custom-connectors/*/checkpoint`,
          `${ccfBaseArnPrefix}/GET/api/v1/custom-connectors/*/documents`,
          `${ccfBaseArnPrefix}/POST/api/v1/custom-connectors/*/documents`,
        ],
      }),
    );
  }

  /**
   * Adds Amazon Q Business specific IAM policies
   *
   * These policies grant:
   * 1. Document management permissions (add/delete documents, manage sync jobs)
   * 2. User and group management permissions
   *
   * @param qBusinessConfig Amazon Q Business configuration
   */
  private addQBusinessPolicies(qBusinessConfig: QBusinessConfig): void {
    // Add document management permissions
    this.jobRole.addToPolicy(
      new PolicyStatement({
        actions: [
          "qbusiness:BatchPutDocument",
          "qbusiness:BatchDeleteDocument",
          "qbusiness:StartDataSourceSyncJob",
          "qbusiness:StopDataSourceSyncJob",
        ],
        resources: [
          `arn:aws:qbusiness:${this.region}:${this.account}:application/${qBusinessConfig.applicationId}`,
          `arn:aws:qbusiness:${this.region}:${this.account}:application/${qBusinessConfig.applicationId}/index/*`,
        ],
      }),
    );

    // Add user and group management permissions
    this.jobRole.addToPolicy(
      new PolicyStatement({
        actions: [
          "qbusiness:PutGroup",
          "qbusiness:CreateUser",
          "qbusiness:DeleteGroup",
          "qbusiness:UpdateUser",
          "qbusiness:ListGroups",
        ],
        resources: [
          `arn:aws:qbusiness:${this.region}:${this.account}:application/${qBusinessConfig.applicationId}`,
          `arn:aws:qbusiness:${this.region}:${this.account}:application/${qBusinessConfig.applicationId}/index/*`,
          `arn:aws:qbusiness:${this.region}:${this.account}:application/${qBusinessConfig.applicationId}/index/*/data-source/*`,
        ],
      }),
    );
  }
}
