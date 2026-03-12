import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { s3vectors } from "@cdklabs/generative-ai-cdk-constructs";
import { NagSuppressions } from "cdk-nag";

export interface ApiStackProps extends cdk.StackProps {
  /**
   * The allowed CORS origin for the API Gateway.
   * Use '*' to allow all origins (default), or specify a specific origin
   * (e.g., 'https://d1234567890.cloudfront.net').
   * @default '*'
   */
  corsOrigin?: string;
}

export class ApiStack extends cdk.Stack {
  public readonly vectorBucket: s3vectors.VectorBucket;
  public readonly vectorIndex: s3vectors.VectorIndex;
  public readonly apiLambda: lambda.Function;
  public readonly api: apigateway.RestApi;
  public readonly stackPrefix: cdk.CfnParameter;

  constructor(scope: Construct, id: string, props?: ApiStackProps) {
    super(scope, id, props);

    // StackPrefix parameter for cross-stack naming consistency
    this.stackPrefix = new cdk.CfnParameter(this, "StackPrefix", {
      type: "String",
      default: "Workshop",
      description:
        "Cross-stack naming prefix for consistency with existing workshop templates (cognito.yaml, code-editor.yaml, agentcore-policies.yaml)",
    });

    // CORS origin configuration - defaults to '*' (allow all)
    const corsOrigin = props?.corsOrigin ?? "*";

    // Generate unique bucket name with account ID and region (max 63 chars)
    const bucketName = `lss-vec-${this.account}-${this.region}`;
    const indexName = "agent-embeddings";

    // S3 Vectors infrastructure using L2 CDK construct
    // Note: autoDeleteObjects disabled to avoid Docker dependency during synthesis
    this.vectorBucket = new s3vectors.VectorBucket(this, "VectorBucket", {
      vectorBucketName: bucketName,
      encryption: s3vectors.VectorBucketEncryption.S3_MANAGED,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create vector index for agent embeddings (1024-dim cosine)
    this.vectorIndex = new s3vectors.VectorIndex(this, "VectorIndex", {
      vectorBucket: this.vectorBucket,
      vectorIndexName: indexName,
      dimension: 1024,
      distanceMetric: s3vectors.VectorIndexDistanceMetric.COSINE,
      nonFilterableMetadataKeys: ["raw_agent_card"],
    });

    // Create IAM role for API Lambda function
    const apiLambdaRole = new iam.Role(this, "ApiLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for LSS Platform API Lambda function",
      inlinePolicies: {
        CloudWatchLogs: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
              ],
              resources: [
                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/${this.stackName}-api:*`,
              ],
            }),
          ],
        }),
        BedrockAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
              ],
              resources: [
                `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
              ],
            }),
          ],
        }),
        S3VectorsAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ["s3vectors:GetVectorBucket", "s3vectors:ListIndexes"],
              resources: [this.vectorBucket.vectorBucketArn],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "s3vectors:GetIndex",
                "s3vectors:PutVectors",
                "s3vectors:GetVectors",
                "s3vectors:DeleteVectors",
                "s3vectors:QueryVectors",
                "s3vectors:ListVectors",
              ],
              resources: [this.vectorIndex.vectorIndexArn],
            }),
          ],
        }),
        AgentCoreAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "bedrock-agentcore:InvokeAgentRuntime",
              ],
              resources: [
                `arn:aws:bedrock-agentcore:*:${this.account}:runtime/*`,
              ],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ["sts:GetCallerIdentity"],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // Create CloudWatch Log Group for API Lambda
    const lambdaLogGroupName = `/aws/lambda/${this.stackName}-api`;
    const apiLambdaLogGroup = new logs.LogGroup(this, "ApiLambdaLogGroup", {
      logGroupName: lambdaLogGroupName,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create main API Lambda function
    // Uses lambda.Code.fromAsset to bundle the Python source directly (no Docker required)
    this.apiLambda = new lambda.Function(this, "ApiLambda", {
      code: lambda.Code.fromAsset("../lambda/src"),
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.lambda_handler",
      role: apiLambdaRole,
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      description: "LSS Workshop Platform API Lambda function",
      logGroup: apiLambdaLogGroup,
      environment: {
        S3_VECTORS_BUCKET: this.vectorBucket.vectorBucketName,
        S3_VECTORS_INDEX: this.vectorIndex.vectorIndexName,
        BEDROCK_MODEL_ID: "amazon.titan-embed-text-v2:0",
        LOG_LEVEL: "INFO",
        CHAT_SERVICE_VERSION: "v4-sse-parse",
      },
    });

    // Create CloudWatch Log Group for API Gateway access logs
    const apiLogGroup = new logs.LogGroup(this, "ApiGatewayLogGroup", {
      logGroupName: `/aws/apigateway/${this.stackName}-api`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Create API Gateway with IAM authentication
    this.api = new apigateway.RestApi(this, "LssPlatformApi", {
      restApiName: "LSS Workshop Platform API",
      description:
        "API for managing and searching agent cards with semantic capabilities and chat",
      defaultCorsPreflightOptions: {
        allowOrigins:
          corsOrigin === "*"
            ? apigateway.Cors.ALL_ORIGINS
            : [corsOrigin],
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
          "X-Amz-Security-Token",
          "X-Amz-User-Agent",
          "X-Amz-Content-Sha256",
          "X-Amz-Target",
        ],
      },
      deployOptions: {
        stageName: "prod",
        throttlingRateLimit: 100,
        throttlingBurstLimit: 200,
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        metricsEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(apiLogGroup),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields({
          caller: true,
          httpMethod: true,
          ip: true,
          protocol: true,
          requestTime: true,
          resourcePath: true,
          responseLength: true,
          status: true,
          user: true,
        }),
      },
      cloudWatchRole: false,
      endpointConfiguration: {
        types: [apigateway.EndpointType.REGIONAL],
      },
    });

    // Add request validator for API Gateway
    const requestValidator = new apigateway.RequestValidator(
      this,
      "RequestValidator",
      {
        restApi: this.api,
        requestValidatorName: "lss-platform-validator",
        validateRequestBody: true,
        validateRequestParameters: true,
      }
    );

    // Create Lambda integration for API Gateway (proxy integration)
    const lambdaIntegration = new apigateway.LambdaIntegration(this.apiLambda, {
      requestTemplates: { "application/json": '{ "statusCode": "200" }' },
      proxy: true,
      allowTestInvoke: true,
    });

    // Configure proxy integration for all paths and methods
    // Lambda handles all routing internally
    this.api.root.addProxy({
      defaultIntegration: lambdaIntegration,
      defaultMethodOptions: {
        authorizationType: apigateway.AuthorizationType.IAM,
        requestValidator: requestValidator,
        requestParameters: {
          "method.request.path.proxy": true,
        },
      },
      anyMethod: true,
    });

    // Add root resource method for base path (non-proxy) with IAM auth
    this.api.root.addMethod("GET", lambdaIntegration, {
      authorizationType: apigateway.AuthorizationType.IAM,
      requestValidator: requestValidator,
    });

    // Grant API Gateway permission to invoke Lambda
    this.apiLambda.addPermission("ApiGatewayInvoke", {
      principal: new iam.ServicePrincipal("apigateway.amazonaws.com"),
      action: "lambda:InvokeFunction",
      sourceArn: this.api.arnForExecuteApi("*"),
    });

    // Add CORS headers to error responses
    const corsAllowOrigin = corsOrigin === "*" ? "'*'" : `'${corsOrigin}'`;

    this.api.addGatewayResponse("Default4XX", {
      type: apigateway.ResponseType.DEFAULT_4XX,
      responseHeaders: {
        "Access-Control-Allow-Origin": corsAllowOrigin,
        "Access-Control-Allow-Headers":
          "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent,X-Amz-Content-Sha256,X-Amz-Target'",
        "Access-Control-Allow-Methods":
          "'OPTIONS,GET,PUT,POST,DELETE,PATCH,HEAD'",
      },
    });

    this.api.addGatewayResponse("Default5XX", {
      type: apigateway.ResponseType.DEFAULT_5XX,
      responseHeaders: {
        "Access-Control-Allow-Origin": corsAllowOrigin,
        "Access-Control-Allow-Headers":
          "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent,X-Amz-Content-Sha256,X-Amz-Target'",
        "Access-Control-Allow-Methods":
          "'OPTIONS,GET,PUT,POST,DELETE,PATCH,HEAD'",
      },
    });

    // SSM Parameter Store: API URL for auto-discovery by registration scripts
    // Use CfnResource because the parameter name contains a CfnParameter token
    new cdk.CfnResource(this, "ApiUrlParameter", {
      type: "AWS::SSM::Parameter",
      properties: {
        Type: "String",
        Name: cdk.Fn.sub("/${StackPrefix}/platform/${Region}/api-url", {
          StackPrefix: this.stackPrefix.valueAsString,
          Region: this.region,
        }),
        Value: this.api.url,
        Description: "LSS Workshop Platform API Gateway URL for auto-discovery",
      },
    });

    // CloudFormation outputs for cross-stack references
    new cdk.CfnOutput(this, "ApiGatewayUrl", {
      value: this.api.url,
      description: "LSS Workshop Platform API Gateway URL",
      exportName: `${this.stackName}-ApiUrl`,
    });

    new cdk.CfnOutput(this, "ApiGatewayId", {
      value: this.api.restApiId,
      description: "LSS Workshop Platform API Gateway ID",
      exportName: `${this.stackName}-ApiId`,
    });

    // ---------------------------------------------------------------
    // cdk-nag AwsSolutions Suppressions
    // ---------------------------------------------------------------

    // Suppress wildcard permissions for CloudWatch Logs - scoped to specific log group
    NagSuppressions.addResourceSuppressionsByPath(
      this,
      `/${id}/ApiLambdaRole/Resource`,
      [
        {
          id: "AwsSolutions-IAM5",
          reason:
            "Wildcard permission needed for CloudWatch Logs stream creation. The resource is scoped to the specific log group for this Lambda function.",
          appliesTo: [
            {
              regex:
                "/Resource::arn:aws:logs:.*:.*:log-group:/aws/lambda/.*-api:\\*/",
            },
          ],
        },
        {
          id: "AwsSolutions-IAM5",
          reason:
            "AgentCore Runtime invoke requires wildcard on runtime resources since agent IDs are dynamic and created by workshop participants. Uses bedrock-agentcore:InvokeAgentRuntime.",
          appliesTo: [
            {
              regex:
                "/Resource::arn:aws:bedrock-agentcore:\\*:.*:runtime/\\*/",
            },
          ],
        },
        {
          id: "AwsSolutions-IAM5",
          reason:
            "sts:GetCallerIdentity requires Resource::* as it does not support resource-level permissions. Used to determine account ID for ARN construction.",
          appliesTo: ["Resource::*"],
        },
      ],
      true
    );

    // Suppress API Gateway security warnings - using IAM authentication
    NagSuppressions.addResourceSuppressions(
      this.api,
      [
        {
          id: "AwsSolutions-COG4",
          reason:
            "Using IAM authentication instead of Cognito authorizer. IAM auth is enforced via Cognito Identity Pool credentials from the WebUI stack.",
        },
        {
          id: "AwsSolutions-APIG3",
          reason:
            "WAF is not required for this workshop API. Access is restricted via IAM authentication and scoped Cognito Identity Pool roles.",
        },
        {
          id: "AwsSolutions-APIG4",
          reason:
            "API uses IAM authentication which provides proper authorization. All methods are protected with IAM auth.",
        },
      ],
      true
    );

    // Suppress Lambda runtime version warning — Python 3.13 is the latest available
    NagSuppressions.addResourceSuppressions(
      this.apiLambda,
      [
        {
          id: "AwsSolutions-L1",
          reason:
            "Python 3.13 is the latest stable runtime supported by AWS Lambda at time of deployment.",
        },
      ],
      true
    );
  }
}
