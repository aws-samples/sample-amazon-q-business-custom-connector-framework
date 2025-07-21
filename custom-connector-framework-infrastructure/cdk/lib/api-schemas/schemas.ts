/**
 * This file contains the models using JSON schema for the Custom Connector Framework APIs.
 */
import { JsonSchemaType } from 'aws-cdk-lib/aws-apigateway';

/**
 * Common HTTP status codes for error responses in the Custom Connector Framework
 */
export const errorStatusCodes = {
  BAD_REQUEST: '400',
  UNAUTHORIZED: '401',
  FORBIDDEN: '403',
  NOT_FOUND: '404',
  CONFLICT: '409',
  TOO_MANY_REQUESTS: '429',
  INTERNAL_SERVER_ERROR: '500',
  SERVICE_UNAVAILABLE: '503',
};

/**
 * Maps Custom Connector Framework error types to HTTP status codes
 */
export const errorTypeToStatusCode = {
  BadRequestException: errorStatusCodes.BAD_REQUEST,
  ConflictException: errorStatusCodes.CONFLICT,
  InternalServerErrorException: errorStatusCodes.INTERNAL_SERVER_ERROR,
  ResourceNotFoundException: errorStatusCodes.NOT_FOUND,
  ResourceLimitExceededException: errorStatusCodes.BAD_REQUEST,
  ServiceUnavailableException: errorStatusCodes.SERVICE_UNAVAILABLE,
  ThrottlingException: errorStatusCodes.TOO_MANY_REQUESTS,
  UnauthorizedException: errorStatusCodes.UNAUTHORIZED,
};

/**
 * Schema for error responses in the Custom Connector Framework
 */
export const errorResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['message', 'errorType'],
  properties: {
    message: {
      type: JsonSchemaType.STRING,
      minLength: 1,
      maxLength: 1024,
      description: 'Detailed error message describing what went wrong',
    },
    errorType: {
      type: JsonSchemaType.STRING,
      description: 'Specific type of error that occurred in the Custom Connector Framework',
      enum: [
        'BadRequestException',
        'ConflictException',
        'InternalServerErrorException',
        'ResourceNotFoundException',
        'ResourceLimitExceededException',
        'ServiceUnavailableException',
        'ThrottlingException',
        'UnauthorizedException',
      ],
    },
  },
};

/**
 * Schema for CreateCustomConnector request
 */
export const createConnectorRequestSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['name', 'container_properties'],
  properties: {
    name: {
      type: JsonSchemaType.STRING,
      minLength: 3,
      maxLength: 128,
      pattern: '^[a-zA-Z0-9-]+$',
      description:
        'Name of the custom connector. Must contain only alphanumeric characters and hyphens.',
    },
    description: {
      type: JsonSchemaType.STRING,
      minLength: 3,
      maxLength: 1000,
      description: 'Optional description of the custom connectors purpose and functionality',
    },
    container_properties: {
      type: JsonSchemaType.OBJECT,
      required: ['execution_role_arn', 'image_uri', 'job_role_arn'],
      properties: {
        execution_role_arn: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^arn:aws:iam::\\d{12}:role/.+$',
          description: 'ARN of the IAM role that the container will use for execution',
        },
        image_uri: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^\\d{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/.+$',
          description: 'ECR URI of the container image to be executed',
        },
        job_role_arn: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^arn:aws:iam::\\d{12}:role/.+$',
          description: 'ARN of the IAM role that will be assumed by the container during execution',
        },
        resource_requirements: {
          type: JsonSchemaType.OBJECT,
          description:
            'Resource requirements for the container following ECS Fargate configurations',
          properties: {
            cpu: {
              type: JsonSchemaType.NUMBER,
              default: 1,
              minimum: 1,
              maximum: 16,
              description: 'CPU units for the container (1 CPU unit = 1024 CPU shares)',
            },
            memory: {
              type: JsonSchemaType.INTEGER,
              default: 2048,
              minimum: 1024,
              maximum: 122880,
              description: 'Memory allocation in MB for the container',
            },
          },
        },
        timeout: {
          type: JsonSchemaType.INTEGER,
          minimum: 1,
          maximum: 604800,
          default: 3600,
          description: 'Maximum execution time in seconds for the container (7 days max)',
        },
      },
    },
  },
};

/**
 * Schema for CreateCustomConnector successful response
 */
export const createConnectorResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['connector'],
  properties: {
    connector: {
      type: JsonSchemaType.OBJECT,
      required: ['connector_id', 'arn', 'name', 'created_at', 'updated_at', 'status'],
      properties: {
        connector_id: {
          type: JsonSchemaType.STRING,
          minLength: 15,
          maxLength: 15,
          pattern: '^cc-[0-9a-f]{11}$',
          description:
            'Unique identifier for the connector following pattern cc-<11 character hex>',
        },
        arn: {
          type: JsonSchemaType.STRING,
          minLength: 63,
          maxLength: 100,
          pattern: '^arn:aws:ccf:[a-z0-9-]+:\\d{12}:custom-connector/cc-[0-9a-f]{11}$',
          description:
            'ARN of the connector following pattern arn:aws:ccf:region:account-id:custom-connector/cc-<id>',
        },
        name: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 128,
          pattern: '^[a-zA-Z0-9-]+$',
          description:
            'Name of the connector. Must contain only alphanumeric characters and hyphens.',
        },
        created_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was created',
        },
        updated_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was last updated',
        },
        status: {
          type: JsonSchemaType.STRING,
          enum: ['AVAILABLE', 'IN_USE'],
          description:
            'Current status of the connector. AVAILABLE indicates ready for jobs, IN_USE indicates a job is running',
        },
        description: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 1000,
          description: 'Optional description of the connectors purpose and functionality',
        },
      },
    },
  },
};

/**
 * Schema for UpdateCustomConnector request
 */
export const updateConnectorRequestSchema = {
  type: JsonSchemaType.OBJECT,
  properties: {
    name: {
      type: JsonSchemaType.STRING,
      pattern: '^[a-zA-Z0-9-]+$',
      minLength: 3,
      maxLength: 128,
      description:
        'Updated name for the custom connector. Must contain only alphanumeric characters and hyphens.',
    },
    description: {
      type: JsonSchemaType.STRING,
      minLength: 3,
      maxLength: 1000,
      description: "Updated description of the custom connector's purpose and functionality",
    },
    container_properties: {
      type: JsonSchemaType.OBJECT,
      description: 'Updated container configuration properties',
      properties: {
        execution_role_arn: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^arn:aws:iam::\\d{12}:role/.+$',
          description: 'Updated ARN of the IAM role that the container will use for execution',
        },
        image_uri: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^\\d{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/.+$',
          description: 'Updated ECR URI of the container image to be executed',
        },
        job_role_arn: {
          type: JsonSchemaType.STRING,
          minLength: 20,
          maxLength: 2048,
          pattern: '^arn:aws:iam::\\d{12}:role/.+$',
          description:
            'Updated ARN of the IAM role that will be assumed by the container during execution',
        },
        resource_requirements: {
          type: JsonSchemaType.OBJECT,
          description:
            'Updated resource requirements for the container following ECS Fargate configurations',
          properties: {
            cpu: {
              type: JsonSchemaType.NUMBER,
              description: 'Updated CPU units for the container (1 CPU unit = 1024 CPU shares)',
              minimum: 1,
              maximum: 16,
              default: 1,
            },
            memory: {
              type: JsonSchemaType.INTEGER,
              description: 'Updated memory allocation in MB for the container',
              minimum: 1024,
              maximum: 122880,
              default: 1024,
            },
          },
        },
        timeout: {
          type: JsonSchemaType.INTEGER,
          description: 'Updated maximum execution time in seconds for the container (7 days max)',
          minimum: 1,
          maximum: 604800,
          default: 3600,
        },
      },
    },
  },
};

/**
 * Schema for UpdateCustomConnector response
 */
export const updateConnectorResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['connector'],
  properties: {
    connector: {
      type: JsonSchemaType.OBJECT,
      required: ['connector_id', 'arn', 'name', 'created_at', 'updated_at', 'status'],
      properties: {
        connector_id: {
          type: JsonSchemaType.STRING,
          minLength: 15,
          maxLength: 15,
          pattern: '^cc-[0-9a-f]{11}$',
          description:
            'Unique identifier for the connector following pattern cc-<11 character hex>',
        },
        arn: {
          type: JsonSchemaType.STRING,
          minLength: 63,
          maxLength: 100,
          pattern: '^arn:aws:ccf:[a-z0-9-]+:\\d{12}:custom-connector/cc-[0-9a-f]{11}$',
          description:
            'ARN of the connector following pattern arn:aws:ccf:region:account-id:custom-connector/cc-<id>',
        },
        name: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 128,
          pattern: '^[a-zA-Z0-9-]+$',
          description: 'Name of the connector',
        },
        created_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was created',
        },
        updated_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was last updated',
        },
        description: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 1000,
          description: "Optional description of the connector's purpose and functionality",
        },
        status: {
          type: JsonSchemaType.STRING,
          enum: ['AVAILABLE', 'IN_USE'],
          description:
            'Current status of the connector. AVAILABLE indicates ready for jobs, IN_USE indicates a job is running',
        },
      },
    },
  },
};

/**
 * Schema for GetCustomConnector successful response
 */
export const getConnectorResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['connector'],
  properties: {
    connector: {
      type: JsonSchemaType.OBJECT,
      required: [
        'connector_id',
        'arn',
        'name',
        'created_at',
        'updated_at',
        'status',
        'container_properties',
      ],
      properties: {
        connector_id: {
          type: JsonSchemaType.STRING,
          minLength: 15,
          maxLength: 15,
          pattern: '^cc-[0-9a-f]{11}$',
          description:
            'Unique identifier for the connector following pattern cc-<11 character hex>',
        },
        arn: {
          type: JsonSchemaType.STRING,
          minLength: 63,
          maxLength: 100,
          pattern: '^arn:aws:ccf:[a-z0-9-]+:\\d{12}:custom-connector/cc-[0-9a-f]{11}$',
          description:
            'ARN of the connector following pattern arn:aws:ccf:region:account-id:custom-connector/cc-<id>',
        },
        name: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 128,
          pattern: '^[a-zA-Z0-9-]+$',
          description:
            'Name of the connector. Must contain only alphanumeric characters and hyphens.',
        },
        created_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was created',
        },
        updated_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the connector was last updated',
        },
        status: {
          type: JsonSchemaType.STRING,
          enum: ['AVAILABLE', 'IN_USE'],
          description:
            'Current status of the connector. AVAILABLE indicates ready for jobs, IN_USE indicates a job is running',
        },
        description: {
          type: JsonSchemaType.STRING,
          minLength: 3,
          maxLength: 1000,
          description: "Optional description of the connector's purpose and functionality",
        },
        container_properties: {
          type: JsonSchemaType.OBJECT,
          required: ['execution_role_arn', 'image_uri', 'job_role_arn'],
          properties: {
            execution_role_arn: {
              type: JsonSchemaType.STRING,
              minLength: 20,
              maxLength: 2048,
              pattern: '^arn:aws:iam::\\d{12}:role/.+$',
              description: 'ARN of the IAM role that the container uses for execution',
            },
            image_uri: {
              type: JsonSchemaType.STRING,
              minLength: 20,
              maxLength: 2048,
              pattern: '^\\d{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/.+$',
              description: 'ECR URI of the container image being executed',
            },
            job_role_arn: {
              type: JsonSchemaType.STRING,
              minLength: 20,
              maxLength: 2048,
              pattern: '^arn:aws:iam::\\d{12}:role/.+$',
              description: 'ARN of the IAM role that the container assumes during execution',
            },
            resource_requirements: {
              type: JsonSchemaType.OBJECT,
              properties: {
                cpu: {
                  type: JsonSchemaType.NUMBER,
                  minimum: 1,
                  maximum: 16,
                  default: 1,
                  description: 'CPU units for the container (1 CPU unit = 1024 CPU shares)',
                },
                memory: {
                  type: JsonSchemaType.INTEGER,
                  minimum: 1024,
                  maximum: 122880,
                  default: 1024,
                  description: 'Memory allocation in MB for the container',
                },
              },
              description:
                'Resource requirements for the container following ECS Fargate configurations',
            },
            timeout: {
              type: JsonSchemaType.INTEGER,
              minimum: 1,
              maximum: 604800,
              default: 3600,
              description: 'Maximum execution time in seconds for the container (7 days max)',
            },
          },
          description: 'Container configuration properties',
        },
      },
      description: 'Details of the requested connector',
    },
  },
};

/**
 * Schema for ListCustomConnectors successful response
 */
export const listConnectorsResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['connectors'],
  properties: {
    connectors: {
      type: JsonSchemaType.ARRAY,
      minItems: 0,
      maxItems: 50,
      items: {
        type: JsonSchemaType.OBJECT,
        required: ['connector_id', 'arn', 'name', 'created_at', 'updated_at', 'status'],
        properties: {
          connector_id: {
            type: JsonSchemaType.STRING,
            minLength: 15,
            maxLength: 15,
            pattern: '^cc-[0-9a-f]{11}$',
            description:
              'Unique identifier for the connector following pattern cc-<11 character hex>',
          },
          arn: {
            type: JsonSchemaType.STRING,
            minLength: 63,
            maxLength: 100,
            pattern: '^arn:aws:ccf:[a-z0-9-]+:\\d{12}:custom-connector/cc-[0-9a-f]{11}$',
            description:
              'ARN of the connector following pattern arn:aws:ccf:region:account-id:custom-connector/cc-<id>',
          },
          name: {
            type: JsonSchemaType.STRING,
            minLength: 3,
            maxLength: 128,
            pattern: '^[a-zA-Z0-9-]+$',
            description:
              'Name of the connector. Must contain only alphanumeric characters and hyphens.',
          },
          created_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the connector was created',
          },
          updated_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the connector was last updated',
          },
          status: {
            type: JsonSchemaType.STRING,
            enum: ['AVAILABLE', 'IN_USE'],
            description:
              'Current status of the connector. AVAILABLE indicates ready for jobs, IN_USE indicates a job is running',
          },
          description: {
            type: JsonSchemaType.STRING,
            minLength: 3,
            maxLength: 1000,
            description: "Optional description of the connector's purpose and functionality",
          },
        },
      },
      description: 'List of connectors',
    },
    next_token: {
      type: JsonSchemaType.STRING,
      maxLength: 2048,
      description: 'Pagination token for retrieving next set of results',
    },
  },
};

/**
 * Schema for StartCustomConnectorJob request
 */
export const startJobRequestSchema = {
  type: JsonSchemaType.OBJECT,
  properties: {
    environment: {
      type: JsonSchemaType.ARRAY,
      minItems: 0,
      maxItems: 50,
      items: {
        type: JsonSchemaType.OBJECT,
        required: ['name', 'value'],
        properties: {
          name: {
            type: JsonSchemaType.STRING,
            minLength: 1,
            maxLength: 128,
            pattern: '^[a-zA-Z][a-zA-Z0-9_]*$',
            description:
              'Name of the environment variable. Must start with a letter and contain only alphanumeric characters and underscores',
          },
          value: {
            type: JsonSchemaType.STRING,
            maxLength: 4096,
            description: 'Value of the environment variable',
          },
        },
      },
      default: [],
      description: 'List of environment variables to pass to the connector job',
    },
  },
};

/**
 * Schema for StartCustomConnectorJob successful response
 */
export const startJobResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['job'],
  properties: {
    job: {
      type: JsonSchemaType.OBJECT,
      required: ['job_id', 'connector_id', 'status', 'created_at'],
      properties: {
        job_id: {
          type: JsonSchemaType.STRING,
          minLength: 17,
          maxLength: 17,
          pattern: '^ccj-[0-9a-f]{12}$',
          description: 'Unique identifier for the job following pattern ccj-<12 character hex>',
        },
        connector_id: {
          type: JsonSchemaType.STRING,
          minLength: 15,
          maxLength: 15,
          pattern: '^cc-[0-9a-f]{11}$',
          description: 'Identifier of the connector this job belongs to',
        },
        status: {
          type: JsonSchemaType.STRING,
          enum: ['STARTED', 'RUNNING', 'COMPLETED', 'FAILED', 'STOPPED'],
          description: 'Current status of the job',
        },
        created_at: {
          type: JsonSchemaType.STRING,
          format: 'date-time',
          description: 'ISO 8601 timestamp when the job was created',
        },
      },
    },
  },
};

/**
 * Schema for ListCustomConnectorJobs successful response
 */
export const listJobsResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['jobs'],
  properties: {
    jobs: {
      type: JsonSchemaType.ARRAY,
      minItems: 0,
      maxItems: 50,
      items: {
        type: JsonSchemaType.OBJECT,
        required: ['job_id', 'connector_id', 'status', 'created_at'],
        properties: {
          job_id: {
            type: JsonSchemaType.STRING,
            minLength: 17,
            maxLength: 17,
            pattern: '^ccj-[0-9a-f]{12}$',
            description: 'Unique identifier for the job following pattern ccj-<12 character hex>',
          },
          connector_id: {
            type: JsonSchemaType.STRING,
            minLength: 15,
            maxLength: 15,
            pattern: '^cc-[0-9a-f]{11}$',
            description: 'Identifier of the connector this job belongs to',
          },
          status: {
            type: JsonSchemaType.STRING,
            enum: ['STARTED', 'RUNNING', 'COMPLETED', 'FAILED', 'STOPPED'],
            description: 'Current status of the job',
          },
          created_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the job was created',
          },
          completed_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the job completed, if applicable',
          },
          failure_reason: {
            type: JsonSchemaType.STRING,
            maxLength: 1024,
            description: 'Detailed reason for failure if job status is FAILED',
          },
        },
      },
      description: 'List of jobs for the connector',
    },
    next_token: {
      type: JsonSchemaType.STRING,
      maxLength: 2048,
      description: 'Pagination token for retrieving next set of results',
    },
  },
};

/**
 * Schema for PutCustomConnectorCheckpoint request
 */
export const putCheckpointRequestSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['checkpoint_data'],
  properties: {
    checkpoint_data: {
      type: JsonSchemaType.STRING,
      minLength: 1,
      maxLength: 1048576, // 1MB
      description: 'JSON serialized checkpoint data to be stored for the connector',
    },
  },
};

/**
 * Schema for GetCustomConnectorCheckpoint successful response
 */
export const getCheckpointResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['checkpoint'],
  properties: {
    checkpoint: {
      type: JsonSchemaType.OBJECT,
      required: ['connector_id', 'checkpoint_data'],
      properties: {
        connector_id: {
          type: JsonSchemaType.STRING,
          minLength: 15,
          maxLength: 15,
          pattern: '^cc-[0-9a-f]{11}$',
          description: 'Identifier of the connector this checkpoint belongs to',
        },
        checkpoint_data: {
          type: JsonSchemaType.STRING,
          minLength: 1,
          maxLength: 1048576, // 1MB
          description: 'JSON serialized checkpoint data stored for the connector',
        },
      },
      description: 'Checkpoint information for the connector',
    },
  },
};

/**
 * Schema for BatchPutCustomConnectorDocuments request
 */
export const batchPutDocumentsRequestSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['documents'],
  properties: {
    documents: {
      type: JsonSchemaType.ARRAY,
      minItems: 1,
      maxItems: 100,
      items: {
        type: JsonSchemaType.OBJECT,
        required: ['document_id', 'checksum'],
        properties: {
          document_id: {
            type: JsonSchemaType.STRING,
            minLength: 1,
            maxLength: 512,
            description: 'Unique identifier for the document within the connector',
          },
          checksum: {
            type: JsonSchemaType.STRING,
            minLength: 32,
            maxLength: 512,
            description: 'Checksum of the document content for change detection',
          },
        },
      },
      description: 'List of documents to be added or updated',
    },
  },
};

/**
 * Schema for BatchDeleteCustomConnectorDocuments request
 */
export const batchDeleteDocumentsRequestSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['document_ids'],
  properties: {
    document_ids: {
      type: JsonSchemaType.ARRAY,
      minItems: 1,
      maxItems: 50,
      items: {
        type: JsonSchemaType.STRING,
        minLength: 1,
        maxLength: 512,
        description: 'Document identifier to be deleted',
      },
      description: 'List of document IDs to be deleted',
    },
  },
};

/**
 * Schema for ListCustomConnectorDocuments successful response
 */
export const listDocumentsResponseSchema = {
  type: JsonSchemaType.OBJECT,
  required: ['documents'],
  properties: {
    documents: {
      type: JsonSchemaType.ARRAY,
      minItems: 0,
      maxItems: 50,
      items: {
        type: JsonSchemaType.OBJECT,
        required: ['document_id', 'checksum', 'created_at', 'updated_at'],
        properties: {
          document_id: {
            type: JsonSchemaType.STRING,
            minLength: 1,
            maxLength: 512,
            description: 'Unique identifier for the document within the connector',
          },
          checksum: {
            type: JsonSchemaType.STRING,
            minLength: 32,
            maxLength: 512,
            description: 'Checksum of the document content for change detection',
          },
          created_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the document was created',
          },
          updated_at: {
            type: JsonSchemaType.STRING,
            format: 'date-time',
            description: 'ISO 8601 timestamp when the document was last updated',
          },
        },
      },
      description: 'List of documents for the connector',
    },
    next_token: {
      type: JsonSchemaType.STRING,
      maxLength: 2048,
      description: 'Pagination token for retrieving next set of results',
    },
  },
};
