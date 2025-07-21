import {
  Stack,
  StackProps,
  RemovalPolicy,
  Duration,
  CfnOutput,
  aws_dynamodb as dynamodb,
  aws_lambda as lambda,
  aws_apigateway as apigateway,
  aws_iam as iam,
  aws_ec2 as ec2,
  aws_batch as batch,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Rule } from 'aws-cdk-lib/aws-events';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';

export interface CustomConnectorFrameworkStackProps extends StackProps {
  env: {
    account: string | undefined;
    region: string | undefined;
    vpcId: string | undefined;
  };
}

export class CustomConnectorFrameworkStack extends Stack {
  private readonly tableNames = {
    connectors: 'CustomConnectors',
    jobs: 'CustomConnectorJobs',
    documents: 'CustomConnectorDocuments',
  };

  private readonly lambdaEnvironment = {
    CUSTOM_CONNECTORS_TABLE: this.tableNames.connectors,
    CUSTOM_CONNECTOR_JOBS_TABLE: this.tableNames.jobs,
    CUSTOM_CONNECTOR_DOCUMENTS_TABLE: this.tableNames.documents,
    LOG_LEVEL: 'INFO',
    POWERTOOLS_SERVICE_NAME: 'CustomConnectorsFramework',
    POWERTOOLS_METRICS_NAMESPACE: 'CustomConnectorsFramework',
    POWERTOOLS_TRACER_CAPTURE_RESPONSE: 'true',
    POWERTOOLS_TRACER_CAPTURE_ERROR: 'true',
    POWERTOOLS_LOGGER_LOG_EVENT: 'true',
    POWERTOOLS_LOGGER_SAMPLE_RATE: '1',
  };

  public readonly vpc: ec2.Vpc;
  public readonly apiEndpoint: string;

  constructor(scope: Construct, id: string, props: CustomConnectorFrameworkStackProps) {
    super(scope, id, props);

    // Create VPC and Batch infrastructure
    this.vpc = this.createVpc(props.env.vpcId);
    const { jobQueue, batchPolicy, jobDefPolicy, ecrPolicy, passRolePolicy } =
      this.createBatchInfrastructure();

    const tables = this.createDynamoDBTables();

    const apiLambda = this.createLambdaFunction('ApiHandler', 'api_handler.handler');
    const jobOrchestratorLambda = this.createLambdaFunction(
      'JobOrchestrator',
      'job_orchestrator_handler.handler',
      {
        ...this.lambdaEnvironment,
        AWS_BATCH_JOB_QUEUE: jobQueue.jobQueueName,
      }
    );

    const jobStatusLambda = this.createLambdaFunction(
      'JobStatusLambda',
      'job_status_handler.handler',
      {
        ...this.lambdaEnvironment,
      }
    );

    const batchJobRule = new Rule(this, 'BatchJobStatusRule', {
      eventPattern: {
        source: ['aws.batch'],
        detailType: ['Batch Job State Change'],
        detail: {
          status: ['SUCCEEDED', 'FAILED'],
          jobName: [
            {
              prefix: 'ccj-',
            },
          ],
        },
      },
    });

    batchJobRule.addTarget(new LambdaFunction(jobStatusLambda));

    this.grantTablePermissions(tables, apiLambda, jobOrchestratorLambda, jobStatusLambda);

    jobOrchestratorLambda.role?.addToPrincipalPolicy(batchPolicy);
    jobOrchestratorLambda.role?.addToPrincipalPolicy(jobDefPolicy);
    jobOrchestratorLambda.role?.addToPrincipalPolicy(ecrPolicy);
    jobOrchestratorLambda.role?.addToPrincipalPolicy(passRolePolicy);

    new lambda.EventSourceMapping(this, 'JobsTableStreamMapping', {
      target: jobOrchestratorLambda,
      eventSourceArn: tables.jobs.tableStreamArn,
      startingPosition: lambda.StartingPosition.LATEST,
      batchSize: 1,
      retryAttempts: 3,
      filters: [
        {
          pattern: JSON.stringify({
            eventName: ['INSERT', 'MODIFY'],
            dynamodb: {
              NewImage: {
                status: {
                  S: ['STARTED', 'STOPPING'],
                },
              },
            },
          }),
        },
      ],
    });

    const api = this.createApiGateway(apiLambda);
    this.apiEndpoint = api.url;
    jobOrchestratorLambda.addEnvironment('CUSTOM_CONNECTOR_API_ENDPOINT', this.apiEndpoint);
  }

  private createVpc(vpcId?: string): ec2.Vpc {
    if (vpcId !== undefined) {
      return <ec2.Vpc>ec2.Vpc.fromLookup(this, 'CustomConnectorVPC', {
        vpcId: vpcId,
      });
    }

    return new ec2.Vpc(this, 'CustomConnectorVPC', {
      maxAzs: 2,
      natGateways: 2,
      gatewayEndpoints: {
        S3: {
          service: ec2.GatewayVpcEndpointAwsService.S3,
        },
      },
    });
  }

  /**
   * Creates the necessary Batch infrastructure and IAM policies for job execution.
   *
   * SECURITY NOTE:
   * This implementation scopes down permissions where possible while maintaining framework usability.
   * For stricter environments, consider implementing IAM Permission Boundaries.
   */
  private createBatchInfrastructure(): {
    jobQueue: batch.JobQueue;
    batchPolicy: iam.PolicyStatement;
    jobDefPolicy: iam.PolicyStatement;
    ecrPolicy: iam.PolicyStatement;
    passRolePolicy: iam.PolicyStatement;
  } {
    const computeEnvironment = new batch.FargateComputeEnvironment(this, 'BatchComputeEnv', {
      vpc: this.vpc,
      maxvCpus: 256,
      updateTimeout: Duration.minutes(30),
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
    });

    const jobQueue = new batch.JobQueue(this, 'BatchJobQueue', {
      computeEnvironments: [
        {
          computeEnvironment,
          order: 1,
        },
      ],
    });

    // Batch job operations - scoped to jobs with prefix 'ccj-'
    const batchPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'batch:SubmitJob',
        'batch:CancelJob',
        'batch:DescribeJobs',
        'batch:ListJobs',
        'batch:TerminateJob',
      ],
      resources: [
        `arn:aws:batch:${this.region}:${this.account}:job-queue/${jobQueue.jobQueueName}`,
        `arn:aws:batch:${this.region}:${this.account}:job/ccj-*`,
      ],
    });

    const jobDefPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['batch:RegisterJobDefinition', 'batch:TagResource'],
      // This needs broader access as job definition names are dynamic
      resources: [`arn:aws:batch:${this.region}:${this.account}:job-definition/*`],
    });

    const ecrPolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecr:GetAuthorizationToken',
        'ecr:BatchCheckLayerAvailability',
        'ecr:GetDownloadUrlForLayer',
        'ecr:BatchGetImage',
      ],
      resources: ['*'],
    });

    // Separate policy for PassRole for roles only within this account and excludes admin roles
    // This policy is necessary to pass your job role to ECS Fargate.
    const passRolePolicy = new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['iam:PassRole'],
      resources: [`arn:aws:iam::${this.account}:role/*`],
      conditions: {
        StringNotLike: {
          'iam:PassedToService': ['iam.amazonaws.com'],
          'iam:RoleName': ['*Admin*', '*admin*'],
        },
      },
    });

    return {
      jobQueue,
      batchPolicy,
      jobDefPolicy,
      ecrPolicy,
      passRolePolicy,
    };
  }

  private createDynamoDBTables() {
    const connectors = new dynamodb.Table(this, 'ConnectorsTable', {
      tableName: this.tableNames.connectors,
      partitionKey: { name: 'custom_connector_arn_prefix', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'connector_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const jobs = new dynamodb.Table(this, 'JobsTable', {
      tableName: this.tableNames.jobs,
      partitionKey: { name: 'custom_connector_arn_prefix', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'job_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
      stream: dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
    });

    const documents = new dynamodb.Table(this, 'DocumentsTable', {
      tableName: this.tableNames.documents,
      partitionKey: { name: 'document_id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'custom_connector_arn_prefix', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    [jobs, documents].forEach((table) => {
      table.addGlobalSecondaryIndex({
        indexName: 'GSI1',
        partitionKey: { name: 'custom_connector_arn_prefix', type: dynamodb.AttributeType.STRING },
        sortKey: { name: 'connector_id', type: dynamodb.AttributeType.STRING },
        projectionType: dynamodb.ProjectionType.ALL,
      });
    });

    return { connectors, jobs, documents };
  }

  private createLambdaFunction(
    id: string,
    handler: string,
    environment: { [key: string]: string } = this.lambdaEnvironment
  ): lambda.Function {
    return new lambda.Function(this, id, {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler,
      code: lambda.Code.fromAsset('../lambdas/src', {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash',
            '-c',
            'pip install --no-cache-dir -r requirements.txt --platform manylinux2014_x86_64 --target /asset-output --only-binary=:all: && cp -au . /asset-output',
          ],
          environment: {
            PIP_NO_CACHE_DIR: 'true',
            PYTHONPATH: '/asset-output',
          },
        },
      }),
      environment,
      tracing: lambda.Tracing.ACTIVE,
      timeout: Duration.seconds(29),
      memorySize: 1024,
    });
  }

  private grantTablePermissions(
    tables: { connectors: dynamodb.Table; jobs: dynamodb.Table; documents: dynamodb.Table },
    apiLambda: lambda.Function,
    jobOrchestratorLambda: lambda.Function,
    jobStatusLambda: lambda.Function
  ) {
    Object.values(tables).forEach((table) => table.grantReadWriteData(apiLambda));

    tables.connectors.grantReadWriteData(jobOrchestratorLambda);
    tables.jobs.grantReadWriteData(jobOrchestratorLambda);
    tables.jobs.grantStreamRead(jobOrchestratorLambda);

    tables.connectors.grantReadWriteData(jobStatusLambda);
    tables.jobs.grantReadWriteData(jobStatusLambda);
  }

  private createApiGateway(apiHandler: lambda.Function): apigateway.RestApi {
    const api = new apigateway.RestApi(this, 'CustomConnectorApi', {
      restApiName: 'CustomConnectorFramework',
      description: 'API for Amazon Q Business Custom Connector Framework',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
      },
    });

    const requestValidator = new apigateway.RequestValidator(this, 'ApiRequestValidator', {
      restApi: api,
      validateRequestBody: true,
      validateRequestParameters: true, // This enables path parameter validation
    });

    // Output the API Gateway ID for use in post-deployment scripts
    new CfnOutput(this, 'ApiGatewayId', {
      value: api.restApiId,
      description: 'The ID of the API Gateway',
      exportName: 'CustomConnectorFrameworkApiId',
    });

    const resourcePolicy = new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          principals: [new iam.AccountPrincipal(this.account)],
          actions: ['execute-api:Invoke'],
          // Use a wildcard for the API ID to avoid circular references
          // Additionally, only the account this is deployed in can invoke this API. Cross account
          // invocation has not been verified.
          resources: [
            `arn:aws:execute-api:${this.region}:${this.account}:*/*/*/api/v1/custom-connectors*`,
          ],
          conditions: {
            StringEquals: {
              'aws:Service': ['execute-api.amazonaws.com'],
            },
          },
        }),
      ],
    });

    const cfnRestApi = api.node.defaultChild as apigateway.CfnRestApi;
    cfnRestApi.policy = resourcePolicy.toJSON();

    const schemas = this.importSchemas();

    const apiV1 = api.root.addResource('api').addResource('v1');
    const customConnectorsResource = apiV1.addResource('custom-connectors');

    // POST /api/v1/custom-connectors - Create connector
    const createConnectorRequestModel = api.addModel('CreateCustomConnectorRequestModel', {
      contentType: 'application/json',
      modelName: 'CreateCustomConnectorRequestModel',
      schema: schemas.createConnectorRequestSchema,
    });

    const createConnectorResponseModel = api.addModel('CreateCustomConnectorResponseModel', {
      contentType: 'application/json',
      modelName: 'CreateCustomConnectorResponseModel',
      schema: schemas.createConnectorResponseSchema,
    });

    const errorResponseModel = api.addModel('ErrorResponseModel', {
      contentType: 'application/json',
      modelName: 'ErrorResponseModel',
      schema: schemas.errorResponseSchema,
    });

    const emptyResponseModel = api.addModel('EmptyResponseModel', {
      contentType: 'application/json',
      modelName: 'EmptyResponseModel',
      schema: { type: apigateway.JsonSchemaType.OBJECT },
    });

    const commonErrorResponses = [
      {
        statusCode: schemas.errorStatusCodes.BAD_REQUEST,
        responseModels: { 'application/json': errorResponseModel },
      },
      {
        statusCode: schemas.errorStatusCodes.NOT_FOUND,
        responseModels: { 'application/json': errorResponseModel },
      },
      {
        statusCode: schemas.errorStatusCodes.CONFLICT,
        responseModels: { 'application/json': errorResponseModel },
      },
      {
        statusCode: schemas.errorStatusCodes.INTERNAL_SERVER_ERROR,
        responseModels: { 'application/json': errorResponseModel },
      },
    ];

    customConnectorsResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestModels: {
        'application/json': createConnectorRequestModel,
      },
      methodResponses: [
        {
          statusCode: '201',
          responseModels: {
            'application/json': createConnectorResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // GET /api/v1/custom-connectors - List connectors
    const listConnectorsResponseModel = api.addModel('ListCustomConnectorsResponseModel', {
      contentType: 'application/json',
      modelName: 'ListCustomConnectorsResponseModel',
      schema: schemas.listConnectorsResponseSchema,
    });

    customConnectorsResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': listConnectorsResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    const connectorResource = customConnectorsResource.addResource('{connector_id}');

    // GET /api/v1/custom-connectors/{connector_id} - Get connector
    const getConnectorResponseModel = api.addModel('GetCustomConnectorResponseModel', {
      contentType: 'application/json',
      modelName: 'GetCustomConnectorResponseModel',
      schema: schemas.getConnectorResponseSchema,
    });

    connectorResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': getConnectorResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // PUT /api/v1/custom-connectors/{connector_id} - Update custom connector
    const updateConnectorRequestModel = api.addModel('UpdateCustomConnectorRequestModel', {
      contentType: 'application/json',
      modelName: 'UpdateCustomConnectorRequestModel',
      schema: schemas.updateConnectorRequestSchema,
    });

    const updateConnectorResponseModel = api.addModel('UpdateCustomConnectorResponseModel', {
      contentType: 'application/json',
      modelName: 'UpdateCustomConnectorResponseModel',
      schema: schemas.updateConnectorResponseSchema,
    });

    connectorResource.addMethod('PUT', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      requestModels: {
        'application/json': updateConnectorRequestModel,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': updateConnectorResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // DELETE /api/v1/custom-connectors/{connector_id} - Delete custom connector
    connectorResource.addMethod('DELETE', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '204',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    const jobsResource = connectorResource.addResource('jobs');

    // POST /api/v1/custom-connectors/{connector_id}/jobs - Start custom connector job
    const startJobRequestModel = api.addModel('StartCustomConnectorJobRequestModel', {
      contentType: 'application/json',
      modelName: 'StartCustomConnectorJobRequestModel',
      schema: schemas.startJobRequestSchema,
    });

    const startJobResponseModel = api.addModel('StartCustomConnectorJobResponseModel', {
      contentType: 'application/json',
      modelName: 'StartCustomConnectorJobResponseModel',
      schema: schemas.startJobResponseSchema,
    });

    jobsResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      requestModels: {
        'application/json': startJobRequestModel,
      },
      methodResponses: [
        {
          statusCode: '201',
          responseModels: {
            'application/json': startJobResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // GET /api/v1/custom-connectors/{connector_id}/jobs - List custom connector jobs
    const listJobsResponseModel = api.addModel('ListCustomConnectorJobsResponseModel', {
      contentType: 'application/json',
      modelName: 'ListCustomConnectorJobsResponseModel',
      schema: schemas.listJobsResponseSchema,
    });

    jobsResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': listJobsResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    const jobResource = jobsResource.addResource('{job_id}');
    const stopJobResource = jobResource.addResource('stop');

    // POST /api/v1/custom-connectors/{connector_id}/jobs/{job_id}/stop - Stop custom connector job
    stopJobResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
        'method.request.path.job_id': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    const documentsResource = connectorResource.addResource('documents');

    // POST /api/v1/custom-connectors/{connector_id}/documents - Batch put custom connector documents
    const batchPutDocumentsRequestModel = api.addModel(
      'BatchPutCustomConnectorDocumentsRequestModel',
      {
        contentType: 'application/json',
        modelName: 'BatchPutCustomConnectorDocumentsRequestModel',
        schema: schemas.batchPutDocumentsRequestSchema,
      }
    );

    documentsResource.addMethod('POST', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      requestModels: {
        'application/json': batchPutDocumentsRequestModel,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // DELETE /api/v1/custom-connectors/{connector_id}/documents - Batch delete custom connector documents
    const batchDeleteDocumentsRequestModel = api.addModel(
      'BatchDeleteCustomConnectorDocumentsRequestModel',
      {
        contentType: 'application/json',
        modelName: 'BatchDeleteCustomConnectorDocumentsRequestModel',
        schema: schemas.batchDeleteDocumentsRequestSchema,
      }
    );

    documentsResource.addMethod('DELETE', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      requestModels: {
        'application/json': batchDeleteDocumentsRequestModel,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });
    // GET /api/v1/custom-connectors/{connector_id}/documents - List custom connector documents
    const listDocumentsResponseModel = api.addModel('ListCustomConnectorDocumentsResponseModel', {
      contentType: 'application/json',
      modelName: 'ListCustomConnectorDocumentsResponseModel',
      schema: schemas.listDocumentsResponseSchema,
    });

    documentsResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': listDocumentsResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    const checkpointResource = connectorResource.addResource('checkpoint');

    // PUT /api/v1/custom-connectors/{connector_id}/checkpoint - Put custom connector checkpoint
    const putCheckpointRequestModel = api.addModel('PutCustomConnectorCheckpointRequestModel', {
      contentType: 'application/json',
      modelName: 'PutCustomConnectorCheckpointRequestModel',
      schema: schemas.putCheckpointRequestSchema,
    });

    checkpointResource.addMethod('PUT', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      requestModels: {
        'application/json': putCheckpointRequestModel,
      },
      methodResponses: [
        {
          statusCode: '202',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // GET /api/v1/custom-connectors/{connector_id}/checkpoint - Get custom connector checkpoint
    const getCheckpointResponseModel = api.addModel('GetCustomConnectorCheckpointResponseModel', {
      contentType: 'application/json',
      modelName: 'GetCustomConnectorCheckpointResponseModel',
      schema: schemas.getCheckpointResponseSchema,
    });

    checkpointResource.addMethod('GET', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '200',
          responseModels: {
            'application/json': getCheckpointResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    // DELETE /api/v1/custom-connectors/{connector_id}/checkpoint - Delete custom connector checkpoint
    checkpointResource.addMethod('DELETE', new apigateway.LambdaIntegration(apiHandler), {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
      requestParameters: {
        'method.request.path.connector_id': true,
      },
      methodResponses: [
        {
          statusCode: '204',
          responseModels: {
            'application/json': emptyResponseModel,
          },
        },
        ...commonErrorResponses,
      ],
    });

    return api;
  }

  // Import schemas at the top level instead of in a method
  private readonly schemas = require('../api-schemas');

  private importSchemas() {
    return this.schemas;
  }
}
