"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ApiStack = void 0;
const cdk = require("aws-cdk-lib");
const lambda = require("aws-cdk-lib/aws-lambda");
const apigateway = require("aws-cdk-lib/aws-apigateway");
const iam = require("aws-cdk-lib/aws-iam");
const logs = require("aws-cdk-lib/aws-logs");
const generative_ai_cdk_constructs_1 = require("@cdklabs/generative-ai-cdk-constructs");
const cdk_nag_1 = require("cdk-nag");
class ApiStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        // StackPrefix parameter for cross-stack naming consistency
        this.stackPrefix = new cdk.CfnParameter(this, "StackPrefix", {
            type: "String",
            default: "Workshop",
            description: "Cross-stack naming prefix for consistency with existing workshop templates (cognito.yaml, code-editor.yaml, agentcore-policies.yaml)",
        });
        // CORS origin configuration - defaults to '*' (allow all)
        const corsOrigin = props?.corsOrigin ?? "*";
        // Generate unique bucket name with account ID and region (max 63 chars)
        const bucketName = `lss-vec-${this.account}-${this.region}`;
        const indexName = "agent-embeddings";
        // S3 Vectors infrastructure using L2 CDK construct
        // Note: autoDeleteObjects disabled to avoid Docker dependency during synthesis
        this.vectorBucket = new generative_ai_cdk_constructs_1.s3vectors.VectorBucket(this, "VectorBucket", {
            vectorBucketName: bucketName,
            encryption: generative_ai_cdk_constructs_1.s3vectors.VectorBucketEncryption.S3_MANAGED,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });
        // Create vector index for agent embeddings (1024-dim cosine)
        this.vectorIndex = new generative_ai_cdk_constructs_1.s3vectors.VectorIndex(this, "VectorIndex", {
            vectorBucket: this.vectorBucket,
            vectorIndexName: indexName,
            dimension: 1024,
            distanceMetric: generative_ai_cdk_constructs_1.s3vectors.VectorIndexDistanceMetric.COSINE,
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
                                `arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/lss-platform-api:*`,
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
                            actions: ["bedrock:InvokeAgent"],
                            resources: [
                                `arn:aws:bedrock:${this.region}:${this.account}:agent-runtime/*`,
                            ],
                        }),
                    ],
                }),
            },
        });
        // Create CloudWatch Log Group for API Lambda
        const apiLambdaLogGroup = new logs.LogGroup(this, "ApiLambdaLogGroup", {
            logGroupName: `/aws/lambda/lss-platform-api`,
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
            timeout: cdk.Duration.seconds(30),
            memorySize: 512,
            description: "LSS Workshop Platform API Lambda function",
            logGroup: apiLambdaLogGroup,
            environment: {
                S3_VECTORS_BUCKET: this.vectorBucket.vectorBucketName,
                S3_VECTORS_INDEX: this.vectorIndex.vectorIndexName,
                BEDROCK_MODEL_ID: "amazon.titan-embed-text-v2:0",
                LOG_LEVEL: "INFO",
            },
        });
        // Create CloudWatch Log Group for API Gateway access logs
        const apiLogGroup = new logs.LogGroup(this, "ApiGatewayLogGroup", {
            logGroupName: `/aws/apigateway/lss-platform-api`,
            retention: logs.RetentionDays.ONE_WEEK,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });
        // Create API Gateway with IAM authentication
        this.api = new apigateway.RestApi(this, "LssPlatformApi", {
            restApiName: "LSS Workshop Platform API",
            description: "API for managing and searching agent cards with semantic capabilities and chat",
            defaultCorsPreflightOptions: {
                allowOrigins: corsOrigin === "*"
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
        const requestValidator = new apigateway.RequestValidator(this, "RequestValidator", {
            restApi: this.api,
            requestValidatorName: "lss-platform-validator",
            validateRequestBody: true,
            validateRequestParameters: true,
        });
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
                "Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent,X-Amz-Content-Sha256,X-Amz-Target'",
                "Access-Control-Allow-Methods": "'OPTIONS,GET,PUT,POST,DELETE,PATCH,HEAD'",
            },
        });
        this.api.addGatewayResponse("Default5XX", {
            type: apigateway.ResponseType.DEFAULT_5XX,
            responseHeaders: {
                "Access-Control-Allow-Origin": corsAllowOrigin,
                "Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amz-User-Agent,X-Amz-Content-Sha256,X-Amz-Target'",
                "Access-Control-Allow-Methods": "'OPTIONS,GET,PUT,POST,DELETE,PATCH,HEAD'",
            },
        });
        // SSM Parameter Store: API URL for auto-discovery by registration scripts
        // Use CfnResource because the parameter name contains a CfnParameter token
        new cdk.CfnResource(this, "ApiUrlParameter", {
            type: "AWS::SSM::Parameter",
            properties: {
                Type: "String",
                Name: cdk.Fn.sub("/${StackPrefix}/platform/api-url", {
                    StackPrefix: this.stackPrefix.valueAsString,
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
        cdk_nag_1.NagSuppressions.addResourceSuppressionsByPath(this, `/${id}/ApiLambdaRole/Resource`, [
            {
                id: "AwsSolutions-IAM5",
                reason: "Wildcard permission needed for CloudWatch Logs stream creation. The resource is scoped to the specific log group for this Lambda function.",
                appliesTo: [
                    {
                        regex: "/Resource::arn:aws:logs:.*:.*:log-group:/aws/lambda/lss-platform-api:\\*/",
                    },
                ],
            },
            {
                id: "AwsSolutions-IAM5",
                reason: "AgentCore Runtime invoke requires wildcard on agent-runtime resources since agent IDs are dynamic and created by workshop participants.",
                appliesTo: [
                    {
                        regex: "/Resource::arn:aws:bedrock:.*:.*:agent-runtime/\\*/",
                    },
                ],
            },
        ], true);
        // Suppress API Gateway security warnings - using IAM authentication
        cdk_nag_1.NagSuppressions.addResourceSuppressions(this.api, [
            {
                id: "AwsSolutions-COG4",
                reason: "Using IAM authentication instead of Cognito authorizer. IAM auth is enforced via Cognito Identity Pool credentials from the WebUI stack.",
            },
            {
                id: "AwsSolutions-APIG3",
                reason: "WAF is not required for this workshop API. Access is restricted via IAM authentication and scoped Cognito Identity Pool roles.",
            },
            {
                id: "AwsSolutions-APIG4",
                reason: "API uses IAM authentication which provides proper authorization. All methods are protected with IAM auth.",
            },
        ], true);
        // Suppress Lambda runtime version warning — Python 3.13 is the latest available
        cdk_nag_1.NagSuppressions.addResourceSuppressions(this.apiLambda, [
            {
                id: "AwsSolutions-L1",
                reason: "Python 3.13 is the latest stable runtime supported by AWS Lambda at time of deployment.",
            },
        ], true);
    }
}
exports.ApiStack = ApiStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiYXBpLXN0YWNrLmpzIiwic291cmNlUm9vdCI6IiIsInNvdXJjZXMiOlsiYXBpLXN0YWNrLnRzIl0sIm5hbWVzIjpbXSwibWFwcGluZ3MiOiI7OztBQUFBLG1DQUFtQztBQUVuQyxpREFBaUQ7QUFDakQseURBQXlEO0FBQ3pELDJDQUEyQztBQUMzQyw2Q0FBNkM7QUFFN0Msd0ZBQWtFO0FBQ2xFLHFDQUEwQztBQVkxQyxNQUFhLFFBQVMsU0FBUSxHQUFHLENBQUMsS0FBSztJQU9yQyxZQUFZLEtBQWdCLEVBQUUsRUFBVSxFQUFFLEtBQXFCO1FBQzdELEtBQUssQ0FBQyxLQUFLLEVBQUUsRUFBRSxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBRXhCLDJEQUEyRDtRQUMzRCxJQUFJLENBQUMsV0FBVyxHQUFHLElBQUksR0FBRyxDQUFDLFlBQVksQ0FBQyxJQUFJLEVBQUUsYUFBYSxFQUFFO1lBQzNELElBQUksRUFBRSxRQUFRO1lBQ2QsT0FBTyxFQUFFLFVBQVU7WUFDbkIsV0FBVyxFQUNULHNJQUFzSTtTQUN6SSxDQUFDLENBQUM7UUFFSCwwREFBMEQ7UUFDMUQsTUFBTSxVQUFVLEdBQUcsS0FBSyxFQUFFLFVBQVUsSUFBSSxHQUFHLENBQUM7UUFFNUMsd0VBQXdFO1FBQ3hFLE1BQU0sVUFBVSxHQUFHLFdBQVcsSUFBSSxDQUFDLE9BQU8sSUFBSSxJQUFJLENBQUMsTUFBTSxFQUFFLENBQUM7UUFDNUQsTUFBTSxTQUFTLEdBQUcsa0JBQWtCLENBQUM7UUFFckMsbURBQW1EO1FBQ25ELCtFQUErRTtRQUMvRSxJQUFJLENBQUMsWUFBWSxHQUFHLElBQUksd0NBQVMsQ0FBQyxZQUFZLENBQUMsSUFBSSxFQUFFLGNBQWMsRUFBRTtZQUNuRSxnQkFBZ0IsRUFBRSxVQUFVO1lBQzVCLFVBQVUsRUFBRSx3Q0FBUyxDQUFDLHNCQUFzQixDQUFDLFVBQVU7WUFDdkQsYUFBYSxFQUFFLEdBQUcsQ0FBQyxhQUFhLENBQUMsT0FBTztTQUN6QyxDQUFDLENBQUM7UUFFSCw2REFBNkQ7UUFD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O3FCQUN4RDtpQkFDRjthQUNGO1NBQ0YsRUFDRCxJQUFJLENBQ0wsQ0FBQztRQUVGLG9FQUFvRTtRQUNwRSx5QkFBZSxDQUFDLHVCQUF1QixDQUNyQyxJQUFJLENBQUMsR0FBRyxFQUNSO1lBQ0U7Z0JBQ0UsRUFBRSxFQUFFLG1CQUFtQjtnQkFDdkIsTUFBTSxFQUNKLDBJQUEwSTthQUM3STtZQUNEO2dCQUNFLEVBQUUsRUFBRSxvQkFBb0I7Z0JBQ3hCLE1BQU0sRUFDSixnSUFBZ0k7YUFDbkk7WUFDRDtnQkFDRSxFQUFFLEVBQUUsb0JBQW9CO2dCQUN4QixNQUFNLEVBQ0osMkdBQTJHO2FBQzlHO1NBQ0YsRUFDRCxJQUFJLENBQ0wsQ0FBQztRQUVGLGdGQUFnRjtRQUNoRix5QkFBZSxDQUFDLHVCQUF1QixDQUNyQyxJQUFJLENBQUMsU0FBUyxFQUNkO1lBQ0U7Z0JBQ0UsRUFBRSxFQUFFLGlCQUFpQjtnQkFDckIsTUFBTSxFQUNKLHlGQUF5RjthQUM1RjtTQUNGLEVBQ0QsSUFBSSxDQUNMLENBQUM7SUFDSixDQUFDO0NBQ0Y7QUF6V0QsNEJBeVdDIiwic291cmNlc0NvbnRlbnQiOlsiaW1wb3J0ICogYXMgY2RrIGZyb20gXCJhd3MtY2RrLWxpYlwiO1xuaW1wb3J0IHsgQ29uc3RydWN0IH0gZnJvbSBcImNvbnN0cnVjdHNcIjtcbmltcG9ydCAqIGFzIGxhbWJkYSBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWxhbWJkYVwiO1xuaW1wb3J0ICogYXMgYXBpZ2F0ZXdheSBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWFwaWdhdGV3YXlcIjtcbmltcG9ydCAqIGFzIGlhbSBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWlhbVwiO1xuaW1wb3J0ICogYXMgbG9ncyBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWxvZ3NcIjtcbmltcG9ydCAqIGFzIHNzbSBmcm9tIFwiYXdzLWNkay1saWIvYXdzLXNzbVwiO1xuaW1wb3J0IHsgczN2ZWN0b3JzIH0gZnJvbSBcIkBjZGtsYWJzL2dlbmVyYXRpdmUtYWktY2RrLWNvbnN0cnVjdHNcIjtcbmltcG9ydCB7IE5hZ1N1cHByZXNzaW9ucyB9IGZyb20gXCJjZGstbmFnXCI7XG5cbmV4cG9ydCBpbnRlcmZhY2UgQXBpU3RhY2tQcm9wcyBleHRlbmRzIGNkay5TdGFja1Byb3BzIHtcbiAgLyoqXG4gICAqIFRoZSBhbGxvd2VkIENPUlMgb3JpZ2luIGZvciB0aGUgQVBJIEdhdGV3YXkuXG4gICAqIFVzZSAnKicgdG8gYWxsb3cgYWxsIG9yaWdpbnMgKGRlZmF1bHQpLCBvciBzcGVjaWZ5IGEgc3BlY2lmaWMgb3JpZ2luXG4gICAqIChlLmcuLCAnaHR0cHM6Ly9kMTIzNDU2Nzg5MC5jbG91ZGZyb250Lm5ldCcpLlxuICAgKiBAZGVmYXVsdCAnKidcbiAgICovXG4gIGNvcnNPcmlnaW4/OiBzdHJpbmc7XG59XG5cbmV4cG9ydCBjbGFzcyBBcGlTdGFjayBleHRlbmRzIGNkay5TdGFjayB7XG4gIHB1YmxpYyByZWFkb25seSB2ZWN0b3JCdWNrZXQ6IHMzdmVjdG9ycy5WZWN0b3JCdWNrZXQ7XG4gIHB1YmxpYyByZWFkb25seSB2ZWN0b3JJbmRleDogczN2ZWN0b3JzLlZlY3RvckluZGV4O1xuICBwdWJsaWMgcmVhZG9ubHkgYXBpTGFtYmRhOiBsYW1iZGEuRnVuY3Rpb247XG4gIHB1YmxpYyByZWFkb25seSBhcGk6IGFwaWdhdGV3YXkuUmVzdEFwaTtcbiAgcHVibGljIHJlYWRvbmx5IHN0YWNrUHJlZml4OiBjZGsuQ2ZuUGFyYW1ldGVyO1xuXG4gIGNvbnN0cnVjdG9yKHNjb3BlOiBDb25zdHJ1Y3QsIGlkOiBzdHJpbmcsIHByb3BzPzogQXBpU3RhY2tQcm9wcykge1xuICAgIHN1cGVyKHNjb3BlLCBpZCwgcHJvcHMpO1xuXG4gICAgLy8gU3RhY2tQcmVmaXggcGFyYW1ldGVyIGZvciBjcm9zcy1zdGFjayBuYW1pbmcgY29uc2lzdGVuY3lcbiAgICB0aGlzLnN0YWNrUHJlZml4ID0gbmV3IGNkay5DZm5QYXJhbWV0ZXIodGhpcywgXCJTdGFja1ByZWZpeFwiLCB7XG4gICAgICB0eXBlOiBcIlN0cmluZ1wiLFxuICAgICAgZGVmYXVsdDogXCJXb3Jrc2hvcFwiLFxuICAgICAgZGVzY3JpcHRpb246XG4gICAgICAgIFwiQ3Jvc3Mtc3RhY2sgbmFtaW5nIHByZWZpeCBmb3IgY29uc2lzdGVuY3kgd2l0aCBleGlzdGluZyB3b3Jrc2hvcCB0ZW1wbGF0ZXMgKGNvZ25pdG8ueWFtbCwgY29kZS1lZGl0b3IueWFtbCwgYWdlbnRjb3JlLXBvbGljaWVzLnlhbWwpXCIsXG4gICAgfSk7XG5cbiAgICAvLyBDT1JTIG9yaWdpbiBjb25maWd1cmF0aW9uIC0gZGVmYXVsdHMgdG8gJyonIChhbGxvdyBhbGwpXG4gICAgY29uc3QgY29yc09yaWdpbiA9IHByb3BzPy5jb3JzT3JpZ2luID8/IFwiKlwiO1xuXG4gICAgLy8gR2VuZXJhdGUgdW5pcXVlIGJ1Y2tldCBuYW1lIHdpdGggYWNjb3VudCBJRCBhbmQgcmVnaW9uIChtYXggNjMgY2hhcnMpXG4gICAgY29uc3QgYnVja2V0TmFtZSA9IGBsc3MtdmVjLSR7dGhpcy5hY2NvdW50fS0ke3RoaXMucmVnaW9ufWA7XG4gICAgY29uc3QgaW5kZXhOYW1lID0gXCJhZ2VudC1lbWJlZGRpbmdzXCI7XG5cbiAgICAvLyBTMyBWZWN0b3JzIGluZnJhc3RydWN0dXJlIHVzaW5nIEwyIENESyBjb25zdHJ1Y3RcbiAgICAvLyBOb3RlOiBhdXRvRGVsZXRlT2JqZWN0cyBkaXNhYmxlZCB0byBhdm9pZCBEb2NrZXIgZGVwZW5kZW5jeSBkdXJpbmcgc3ludGhlc2lzXG4gICAgdGhpcy52ZWN0b3JCdWNrZXQgPSBuZXcgczN2ZWN0b3JzLlZlY3RvckJ1Y2tldCh0aGlzLCBcIlZlY3RvckJ1Y2tldFwiLCB7XG4gICAgICB2ZWN0b3JCdWNrZXROYW1lOiBidWNrZXROYW1lLFxuICAgICAgZW5jcnlwdGlvbjogczN2ZWN0b3JzLlZlY3RvckJ1Y2tldEVuY3J5cHRpb24uUzNfTUFOQUdFRCxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgdmVjdG9yIGluZGV4IGZvciBhZ2VudCBlbWJlZGRpbmdzICgxMDI0LWRpbSBjb3NpbmUpXG4gICAgdGhpcy52ZWN0b3JJbmRleCA9IG5ldyBzM3ZlY3RvcnMuVmVjdG9ySW5kZXgodGhpcywgXCJWZWN0b3JJbmRleFwiLCB7XG4gICAgICB2ZWN0b3JCdWNrZXQ6IHRoaXMudmVjdG9yQnVja2V0LFxuICAgICAgdmVjdG9ySW5kZXhOYW1lOiBpbmRleE5hbWUsXG4gICAgICBkaW1lbnNpb246IDEwMjQsXG4gICAgICBkaXN0YW5jZU1ldHJpYzogczN2ZWN0b3JzLlZlY3RvckluZGV4RGlzdGFuY2VNZXRyaWMuQ09TSU5FLFxuICAgICAgbm9uRmlsdGVyYWJsZU1ldGFkYXRhS2V5czogW1wicmF3X2FnZW50X2NhcmRcIl0sXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgSUFNIHJvbGUgZm9yIEFQSSBMYW1iZGEgZnVuY3Rpb25cbiAgICBjb25zdCBhcGlMYW1iZGFSb2xlID0gbmV3IGlhbS5Sb2xlKHRoaXMsIFwiQXBpTGFtYmRhUm9sZVwiLCB7XG4gICAgICBhc3N1bWVkQnk6IG5ldyBpYW0uU2VydmljZVByaW5jaXBhbChcImxhbWJkYS5hbWF6b25hd3MuY29tXCIpLFxuICAgICAgZGVzY3JpcHRpb246IFwiSUFNIHJvbGUgZm9yIExTUyBQbGF0Zm9ybSBBUEkgTGFtYmRhIGZ1bmN0aW9uXCIsXG4gICAgICBpbmxpbmVQb2xpY2llczoge1xuICAgICAgICBDbG91ZFdhdGNoTG9nczogbmV3IGlhbS5Qb2xpY3lEb2N1bWVudCh7XG4gICAgICAgICAgc3RhdGVtZW50czogW1xuICAgICAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgICAgIGFjdGlvbnM6IFtcbiAgICAgICAgICAgICAgICBcImxvZ3M6Q3JlYXRlTG9nR3JvdXBcIixcbiAgICAgICAgICAgICAgICBcImxvZ3M6Q3JlYXRlTG9nU3RyZWFtXCIsXG4gICAgICAgICAgICAgICAgXCJsb2dzOlB1dExvZ0V2ZW50c1wiLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgICAgICAgICBgYXJuOmF3czpsb2dzOiR7dGhpcy5yZWdpb259OiR7dGhpcy5hY2NvdW50fTpsb2ctZ3JvdXA6L2F3cy9sYW1iZGEvbHNzLXBsYXRmb3JtLWFwaToqYCxcbiAgICAgICAgICAgICAgXSxcbiAgICAgICAgICAgIH0pLFxuICAgICAgICAgIF0sXG4gICAgICAgIH0pLFxuICAgICAgICBCZWRyb2NrQWNjZXNzOiBuZXcgaWFtLlBvbGljeURvY3VtZW50KHtcbiAgICAgICAgICBzdGF0ZW1lbnRzOiBbXG4gICAgICAgICAgICBuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICAgICAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgICAgICAgICAgYWN0aW9uczogW1xuICAgICAgICAgICAgICAgIFwiYmVkcm9jazpJbnZva2VNb2RlbFwiLFxuICAgICAgICAgICAgICAgIFwiYmVkcm9jazpJbnZva2VNb2RlbFdpdGhSZXNwb25zZVN0cmVhbVwiLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgICAgICAgICBgYXJuOmF3czpiZWRyb2NrOiR7dGhpcy5yZWdpb259Ojpmb3VuZGF0aW9uLW1vZGVsL2FtYXpvbi50aXRhbi1lbWJlZC10ZXh0LXYyOjBgLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgXSxcbiAgICAgICAgfSksXG4gICAgICAgIFMzVmVjdG9yc0FjY2VzczogbmV3IGlhbS5Qb2xpY3lEb2N1bWVudCh7XG4gICAgICAgICAgc3RhdGVtZW50czogW1xuICAgICAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgICAgIGFjdGlvbnM6IFtcInMzdmVjdG9yczpHZXRWZWN0b3JCdWNrZXRcIiwgXCJzM3ZlY3RvcnM6TGlzdEluZGV4ZXNcIl0sXG4gICAgICAgICAgICAgIHJlc291cmNlczogW3RoaXMudmVjdG9yQnVja2V0LnZlY3RvckJ1Y2tldEFybl0sXG4gICAgICAgICAgICB9KSxcbiAgICAgICAgICAgIG5ldyBpYW0uUG9saWN5U3RhdGVtZW50KHtcbiAgICAgICAgICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgICAgICAgICBhY3Rpb25zOiBbXG4gICAgICAgICAgICAgICAgXCJzM3ZlY3RvcnM6R2V0SW5kZXhcIixcbiAgICAgICAgICAgICAgICBcInMzdmVjdG9yczpQdXRWZWN0b3JzXCIsXG4gICAgICAgICAgICAgICAgXCJzM3ZlY3RvcnM6R2V0VmVjdG9yc1wiLFxuICAgICAgICAgICAgICAgIFwiczN2ZWN0b3JzOkRlbGV0ZVZlY3RvcnNcIixcbiAgICAgICAgICAgICAgICBcInMzdmVjdG9yczpRdWVyeVZlY3RvcnNcIixcbiAgICAgICAgICAgICAgICBcInMzdmVjdG9yczpMaXN0VmVjdG9yc1wiLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgICByZXNvdXJjZXM6IFt0aGlzLnZlY3RvckluZGV4LnZlY3RvckluZGV4QXJuXSxcbiAgICAgICAgICAgIH0pLFxuICAgICAgICAgIF0sXG4gICAgICAgIH0pLFxuICAgICAgICBBZ2VudENvcmVBY2Nlc3M6IG5ldyBpYW0uUG9saWN5RG9jdW1lbnQoe1xuICAgICAgICAgIHN0YXRlbWVudHM6IFtcbiAgICAgICAgICAgIG5ldyBpYW0uUG9saWN5U3RhdGVtZW50KHtcbiAgICAgICAgICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgICAgICAgICBhY3Rpb25zOiBbXCJiZWRyb2NrOkludm9rZUFnZW50XCJdLFxuICAgICAgICAgICAgICByZXNvdXJjZXM6IFtcbiAgICAgICAgICAgICAgICBgYXJuOmF3czpiZWRyb2NrOiR7dGhpcy5yZWdpb259OiR7dGhpcy5hY2NvdW50fTphZ2VudC1ydW50aW1lLypgLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgXSxcbiAgICAgICAgfSksXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gQ3JlYXRlIENsb3VkV2F0Y2ggTG9nIEdyb3VwIGZvciBBUEkgTGFtYmRhXG4gICAgY29uc3QgYXBpTGFtYmRhTG9nR3JvdXAgPSBuZXcgbG9ncy5Mb2dHcm91cCh0aGlzLCBcIkFwaUxhbWJkYUxvZ0dyb3VwXCIsIHtcbiAgICAgIGxvZ0dyb3VwTmFtZTogYC9hd3MvbGFtYmRhL2xzcy1wbGF0Zm9ybS1hcGlgLFxuICAgICAgcmV0ZW50aW9uOiBsb2dzLlJldGVudGlvbkRheXMuT05FX1dFRUssXG4gICAgICByZW1vdmFsUG9saWN5OiBjZGsuUmVtb3ZhbFBvbGljeS5ERVNUUk9ZLFxuICAgIH0pO1xuXG4gICAgLy8gQ3JlYXRlIG1haW4gQVBJIExhbWJkYSBmdW5jdGlvblxuICAgIC8vIFVzZXMgbGFtYmRhLkNvZGUuZnJvbUFzc2V0IHRvIGJ1bmRsZSB0aGUgUHl0aG9uIHNvdXJjZSBkaXJlY3RseSAobm8gRG9ja2VyIHJlcXVpcmVkKVxuICAgIHRoaXMuYXBpTGFtYmRhID0gbmV3IGxhbWJkYS5GdW5jdGlvbih0aGlzLCBcIkFwaUxhbWJkYVwiLCB7XG4gICAgICBjb2RlOiBsYW1iZGEuQ29kZS5mcm9tQXNzZXQoXCIuLi9sYW1iZGEvc3JjXCIpLFxuICAgICAgcnVudGltZTogbGFtYmRhLlJ1bnRpbWUuUFlUSE9OXzNfMTIsXG4gICAgICBoYW5kbGVyOiBcImhhbmRsZXIubGFtYmRhX2hhbmRsZXJcIixcbiAgICAgIHJvbGU6IGFwaUxhbWJkYVJvbGUsXG4gICAgICB0aW1lb3V0OiBjZGsuRHVyYXRpb24uc2Vjb25kcygzMCksXG4gICAgICBtZW1vcnlTaXplOiA1MTIsXG4gICAgICBkZXNjcmlwdGlvbjogXCJMU1MgV29ya3Nob3AgUGxhdGZvcm0gQVBJIExhbWJkYSBmdW5jdGlvblwiLFxuICAgICAgbG9nR3JvdXA6IGFwaUxhbWJkYUxvZ0dyb3VwLFxuICAgICAgZW52aXJvbm1lbnQ6IHtcbiAgICAgICAgUzNfVkVDVE9SU19CVUNLRVQ6IHRoaXMudmVjdG9yQnVja2V0LnZlY3RvckJ1Y2tldE5hbWUsXG4gICAgICAgIFMzX1ZFQ1RPUlNfSU5ERVg6IHRoaXMudmVjdG9ySW5kZXgudmVjdG9ySW5kZXhOYW1lLFxuICAgICAgICBCRURST0NLX01PREVMX0lEOiBcImFtYXpvbi50aXRhbi1lbWJlZC10ZXh0LXYyOjBcIixcbiAgICAgICAgTE9HX0xFVkVMOiBcIklORk9cIixcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgQ2xvdWRXYXRjaCBMb2cgR3JvdXAgZm9yIEFQSSBHYXRld2F5IGFjY2VzcyBsb2dzXG4gICAgY29uc3QgYXBpTG9nR3JvdXAgPSBuZXcgbG9ncy5Mb2dHcm91cCh0aGlzLCBcIkFwaUdhdGV3YXlMb2dHcm91cFwiLCB7XG4gICAgICBsb2dHcm91cE5hbWU6IGAvYXdzL2FwaWdhdGV3YXkvbHNzLXBsYXRmb3JtLWFwaWAsXG4gICAgICByZXRlbnRpb246IGxvZ3MuUmV0ZW50aW9uRGF5cy5PTkVfV0VFSyxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgfSk7XG5cbiAgICAvLyBDcmVhdGUgQVBJIEdhdGV3YXkgd2l0aCBJQU0gYXV0aGVudGljYXRpb25cbiAgICB0aGlzLmFwaSA9IG5ldyBhcGlnYXRld2F5LlJlc3RBcGkodGhpcywgXCJMc3NQbGF0Zm9ybUFwaVwiLCB7XG4gICAgICByZXN0QXBpTmFtZTogXCJMU1MgV29ya3Nob3AgUGxhdGZvcm0gQVBJXCIsXG4gICAgICBkZXNjcmlwdGlvbjpcbiAgICAgICAgXCJBUEkgZm9yIG1hbmFnaW5nIGFuZCBzZWFyY2hpbmcgYWdlbnQgY2FyZHMgd2l0aCBzZW1hbnRpYyBjYXBhYmlsaXRpZXMgYW5kIGNoYXRcIixcbiAgICAgIGRlZmF1bHRDb3JzUHJlZmxpZ2h0T3B0aW9uczoge1xuICAgICAgICBhbGxvd09yaWdpbnM6XG4gICAgICAgICAgY29yc09yaWdpbiA9PT0gXCIqXCJcbiAgICAgICAgICAgID8gYXBpZ2F0ZXdheS5Db3JzLkFMTF9PUklHSU5TXG4gICAgICAgICAgICA6IFtjb3JzT3JpZ2luXSxcbiAgICAgICAgYWxsb3dNZXRob2RzOiBhcGlnYXRld2F5LkNvcnMuQUxMX01FVEhPRFMsXG4gICAgICAgIGFsbG93SGVhZGVyczogW1xuICAgICAgICAgIFwiQ29udGVudC1UeXBlXCIsXG4gICAgICAgICAgXCJYLUFtei1EYXRlXCIsXG4gICAgICAgICAgXCJBdXRob3JpemF0aW9uXCIsXG4gICAgICAgICAgXCJYLUFwaS1LZXlcIixcbiAgICAgICAgICBcIlgtQW16LVNlY3VyaXR5LVRva2VuXCIsXG4gICAgICAgICAgXCJYLUFtei1Vc2VyLUFnZW50XCIsXG4gICAgICAgICAgXCJYLUFtei1Db250ZW50LVNoYTI1NlwiLFxuICAgICAgICAgIFwiWC1BbXotVGFyZ2V0XCIsXG4gICAgICAgIF0sXG4gICAgICB9LFxuICAgICAgZGVwbG95T3B0aW9uczoge1xuICAgICAgICBzdGFnZU5hbWU6IFwicHJvZFwiLFxuICAgICAgICB0aHJvdHRsaW5nUmF0ZUxpbWl0OiAxMDAsXG4gICAgICAgIHRocm90dGxpbmdCdXJzdExpbWl0OiAyMDAsXG4gICAgICAgIGxvZ2dpbmdMZXZlbDogYXBpZ2F0ZXdheS5NZXRob2RMb2dnaW5nTGV2ZWwuSU5GTyxcbiAgICAgICAgZGF0YVRyYWNlRW5hYmxlZDogdHJ1ZSxcbiAgICAgICAgbWV0cmljc0VuYWJsZWQ6IHRydWUsXG4gICAgICAgIGFjY2Vzc0xvZ0Rlc3RpbmF0aW9uOiBuZXcgYXBpZ2F0ZXdheS5Mb2dHcm91cExvZ0Rlc3RpbmF0aW9uKGFwaUxvZ0dyb3VwKSxcbiAgICAgICAgYWNjZXNzTG9nRm9ybWF0OiBhcGlnYXRld2F5LkFjY2Vzc0xvZ0Zvcm1hdC5qc29uV2l0aFN0YW5kYXJkRmllbGRzKHtcbiAgICAgICAgICBjYWxsZXI6IHRydWUsXG4gICAgICAgICAgaHR0cE1ldGhvZDogdHJ1ZSxcbiAgICAgICAgICBpcDogdHJ1ZSxcbiAgICAgICAgICBwcm90b2NvbDogdHJ1ZSxcbiAgICAgICAgICByZXF1ZXN0VGltZTogdHJ1ZSxcbiAgICAgICAgICByZXNvdXJjZVBhdGg6IHRydWUsXG4gICAgICAgICAgcmVzcG9uc2VMZW5ndGg6IHRydWUsXG4gICAgICAgICAgc3RhdHVzOiB0cnVlLFxuICAgICAgICAgIHVzZXI6IHRydWUsXG4gICAgICAgIH0pLFxuICAgICAgfSxcbiAgICAgIGNsb3VkV2F0Y2hSb2xlOiBmYWxzZSxcbiAgICAgIGVuZHBvaW50Q29uZmlndXJhdGlvbjoge1xuICAgICAgICB0eXBlczogW2FwaWdhdGV3YXkuRW5kcG9pbnRUeXBlLlJFR0lPTkFMXSxcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyBBZGQgcmVxdWVzdCB2YWxpZGF0b3IgZm9yIEFQSSBHYXRld2F5XG4gICAgY29uc3QgcmVxdWVzdFZhbGlkYXRvciA9IG5ldyBhcGlnYXRld2F5LlJlcXVlc3RWYWxpZGF0b3IoXG4gICAgICB0aGlzLFxuICAgICAgXCJSZXF1ZXN0VmFsaWRhdG9yXCIsXG4gICAgICB7XG4gICAgICAgIHJlc3RBcGk6IHRoaXMuYXBpLFxuICAgICAgICByZXF1ZXN0VmFsaWRhdG9yTmFtZTogXCJsc3MtcGxhdGZvcm0tdmFsaWRhdG9yXCIsXG4gICAgICAgIHZhbGlkYXRlUmVxdWVzdEJvZHk6IHRydWUsXG4gICAgICAgIHZhbGlkYXRlUmVxdWVzdFBhcmFtZXRlcnM6IHRydWUsXG4gICAgICB9XG4gICAgKTtcblxuICAgIC8vIENyZWF0ZSBMYW1iZGEgaW50ZWdyYXRpb24gZm9yIEFQSSBHYXRld2F5IChwcm94eSBpbnRlZ3JhdGlvbilcbiAgICBjb25zdCBsYW1iZGFJbnRlZ3JhdGlvbiA9IG5ldyBhcGlnYXRld2F5LkxhbWJkYUludGVncmF0aW9uKHRoaXMuYXBpTGFtYmRhLCB7XG4gICAgICByZXF1ZXN0VGVtcGxhdGVzOiB7IFwiYXBwbGljYXRpb24vanNvblwiOiAneyBcInN0YXR1c0NvZGVcIjogXCIyMDBcIiB9JyB9LFxuICAgICAgcHJveHk6IHRydWUsXG4gICAgICBhbGxvd1Rlc3RJbnZva2U6IHRydWUsXG4gICAgfSk7XG5cbiAgICAvLyBDb25maWd1cmUgcHJveHkgaW50ZWdyYXRpb24gZm9yIGFsbCBwYXRocyBhbmQgbWV0aG9kc1xuICAgIC8vIExhbWJkYSBoYW5kbGVzIGFsbCByb3V0aW5nIGludGVybmFsbHlcbiAgICB0aGlzLmFwaS5yb290LmFkZFByb3h5KHtcbiAgICAgIGRlZmF1bHRJbnRlZ3JhdGlvbjogbGFtYmRhSW50ZWdyYXRpb24sXG4gICAgICBkZWZhdWx0TWV0aG9kT3B0aW9uczoge1xuICAgICAgICBhdXRob3JpemF0aW9uVHlwZTogYXBpZ2F0ZXdheS5BdXRob3JpemF0aW9uVHlwZS5JQU0sXG4gICAgICAgIHJlcXVlc3RWYWxpZGF0b3I6IHJlcXVlc3RWYWxpZGF0b3IsXG4gICAgICAgIHJlcXVlc3RQYXJhbWV0ZXJzOiB7XG4gICAgICAgICAgXCJtZXRob2QucmVxdWVzdC5wYXRoLnByb3h5XCI6IHRydWUsXG4gICAgICAgIH0sXG4gICAgICB9LFxuICAgICAgYW55TWV0aG9kOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gQWRkIHJvb3QgcmVzb3VyY2UgbWV0aG9kIGZvciBiYXNlIHBhdGggKG5vbi1wcm94eSkgd2l0aCBJQU0gYXV0aFxuICAgIHRoaXMuYXBpLnJvb3QuYWRkTWV0aG9kKFwiR0VUXCIsIGxhbWJkYUludGVncmF0aW9uLCB7XG4gICAgICBhdXRob3JpemF0aW9uVHlwZTogYXBpZ2F0ZXdheS5BdXRob3JpemF0aW9uVHlwZS5JQU0sXG4gICAgICByZXF1ZXN0VmFsaWRhdG9yOiByZXF1ZXN0VmFsaWRhdG9yLFxuICAgIH0pO1xuXG4gICAgLy8gR3JhbnQgQVBJIEdhdGV3YXkgcGVybWlzc2lvbiB0byBpbnZva2UgTGFtYmRhXG4gICAgdGhpcy5hcGlMYW1iZGEuYWRkUGVybWlzc2lvbihcIkFwaUdhdGV3YXlJbnZva2VcIiwge1xuICAgICAgcHJpbmNpcGFsOiBuZXcgaWFtLlNlcnZpY2VQcmluY2lwYWwoXCJhcGlnYXRld2F5LmFtYXpvbmF3cy5jb21cIiksXG4gICAgICBhY3Rpb246IFwibGFtYmRhOkludm9rZUZ1bmN0aW9uXCIsXG4gICAgICBzb3VyY2VBcm46IHRoaXMuYXBpLmFybkZvckV4ZWN1dGVBcGkoXCIqXCIpLFxuICAgIH0pO1xuXG4gICAgLy8gQWRkIENPUlMgaGVhZGVycyB0byBlcnJvciByZXNwb25zZXNcbiAgICBjb25zdCBjb3JzQWxsb3dPcmlnaW4gPSBjb3JzT3JpZ2luID09PSBcIipcIiA/IFwiJyonXCIgOiBgJyR7Y29yc09yaWdpbn0nYDtcblxuICAgIHRoaXMuYXBpLmFkZEdhdGV3YXlSZXNwb25zZShcIkRlZmF1bHQ0WFhcIiwge1xuICAgICAgdHlwZTogYXBpZ2F0ZXdheS5SZXNwb25zZVR5cGUuREVGQVVMVF80WFgsXG4gICAgICByZXNwb25zZUhlYWRlcnM6IHtcbiAgICAgICAgXCJBY2Nlc3MtQ29udHJvbC1BbGxvdy1PcmlnaW5cIjogY29yc0FsbG93T3JpZ2luLFxuICAgICAgICBcIkFjY2Vzcy1Db250cm9sLUFsbG93LUhlYWRlcnNcIjpcbiAgICAgICAgICBcIidDb250ZW50LVR5cGUsWC1BbXotRGF0ZSxBdXRob3JpemF0aW9uLFgtQXBpLUtleSxYLUFtei1TZWN1cml0eS1Ub2tlbixYLUFtei1Vc2VyLUFnZW50LFgtQW16LUNvbnRlbnQtU2hhMjU2LFgtQW16LVRhcmdldCdcIixcbiAgICAgICAgXCJBY2Nlc3MtQ29udHJvbC1BbGxvdy1NZXRob2RzXCI6XG4gICAgICAgICAgXCInT1BUSU9OUyxHRVQsUFVULFBPU1QsREVMRVRFLFBBVENILEhFQUQnXCIsXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgdGhpcy5hcGkuYWRkR2F0ZXdheVJlc3BvbnNlKFwiRGVmYXVsdDVYWFwiLCB7XG4gICAgICB0eXBlOiBhcGlnYXRld2F5LlJlc3BvbnNlVHlwZS5ERUZBVUxUXzVYWCxcbiAgICAgIHJlc3BvbnNlSGVhZGVyczoge1xuICAgICAgICBcIkFjY2Vzcy1Db250cm9sLUFsbG93LU9yaWdpblwiOiBjb3JzQWxsb3dPcmlnaW4sXG4gICAgICAgIFwiQWNjZXNzLUNvbnRyb2wtQWxsb3ctSGVhZGVyc1wiOlxuICAgICAgICAgIFwiJ0NvbnRlbnQtVHlwZSxYLUFtei1EYXRlLEF1dGhvcml6YXRpb24sWC1BcGktS2V5LFgtQW16LVNlY3VyaXR5LVRva2VuLFgtQW16LVVzZXItQWdlbnQsWC1BbXotQ29udGVudC1TaGEyNTYsWC1BbXotVGFyZ2V0J1wiLFxuICAgICAgICBcIkFjY2Vzcy1Db250cm9sLUFsbG93LU1ldGhvZHNcIjpcbiAgICAgICAgICBcIidPUFRJT05TLEdFVCxQVVQsUE9TVCxERUxFVEUsUEFUQ0gsSEVBRCdcIixcbiAgICAgIH0sXG4gICAgfSk7XG5cbiAgICAvLyBTU00gUGFyYW1ldGVyIFN0b3JlOiBBUEkgVVJMIGZvciBhdXRvLWRpc2NvdmVyeSBieSByZWdpc3RyYXRpb24gc2NyaXB0c1xuICAgIC8vIFVzZSBDZm5SZXNvdXJjZSBiZWNhdXNlIHRoZSBwYXJhbWV0ZXIgbmFtZSBjb250YWlucyBhIENmblBhcmFtZXRlciB0b2tlblxuICAgIG5ldyBjZGsuQ2ZuUmVzb3VyY2UodGhpcywgXCJBcGlVcmxQYXJhbWV0ZXJcIiwge1xuICAgICAgdHlwZTogXCJBV1M6OlNTTTo6UGFyYW1ldGVyXCIsXG4gICAgICBwcm9wZXJ0aWVzOiB7XG4gICAgICAgIFR5cGU6IFwiU3RyaW5nXCIsXG4gICAgICAgIE5hbWU6IGNkay5Gbi5zdWIoXCIvJHtTdGFja1ByZWZpeH0vcGxhdGZvcm0vYXBpLXVybFwiLCB7XG4gICAgICAgICAgU3RhY2tQcmVmaXg6IHRoaXMuc3RhY2tQcmVmaXgudmFsdWVBc1N0cmluZyxcbiAgICAgICAgfSksXG4gICAgICAgIFZhbHVlOiB0aGlzLmFwaS51cmwsXG4gICAgICAgIERlc2NyaXB0aW9uOiBcIkxTUyBXb3Jrc2hvcCBQbGF0Zm9ybSBBUEkgR2F0ZXdheSBVUkwgZm9yIGF1dG8tZGlzY292ZXJ5XCIsXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gQ2xvdWRGb3JtYXRpb24gb3V0cHV0cyBmb3IgY3Jvc3Mtc3RhY2sgcmVmZXJlbmNlc1xuICAgIG5ldyBjZGsuQ2ZuT3V0cHV0KHRoaXMsIFwiQXBpR2F0ZXdheVVybFwiLCB7XG4gICAgICB2YWx1ZTogdGhpcy5hcGkudXJsLFxuICAgICAgZGVzY3JpcHRpb246IFwiTFNTIFdvcmtzaG9wIFBsYXRmb3JtIEFQSSBHYXRld2F5IFVSTFwiLFxuICAgICAgZXhwb3J0TmFtZTogYCR7dGhpcy5zdGFja05hbWV9LUFwaVVybGAsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCBcIkFwaUdhdGV3YXlJZFwiLCB7XG4gICAgICB2YWx1ZTogdGhpcy5hcGkucmVzdEFwaUlkLFxuICAgICAgZGVzY3JpcHRpb246IFwiTFNTIFdvcmtzaG9wIFBsYXRmb3JtIEFQSSBHYXRld2F5IElEXCIsXG4gICAgICBleHBvcnROYW1lOiBgJHt0aGlzLnN0YWNrTmFtZX0tQXBpSWRgLFxuICAgIH0pO1xuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgLy8gY2RrLW5hZyBBd3NTb2x1dGlvbnMgU3VwcHJlc3Npb25zXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG5cbiAgICAvLyBTdXBwcmVzcyB3aWxkY2FyZCBwZXJtaXNzaW9ucyBmb3IgQ2xvdWRXYXRjaCBMb2dzIC0gc2NvcGVkIHRvIHNwZWNpZmljIGxvZyBncm91cFxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9uc0J5UGF0aChcbiAgICAgIHRoaXMsXG4gICAgICBgLyR7aWR9L0FwaUxhbWJkYVJvbGUvUmVzb3VyY2VgLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUlBTTVcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIldpbGRjYXJkIHBlcm1pc3Npb24gbmVlZGVkIGZvciBDbG91ZFdhdGNoIExvZ3Mgc3RyZWFtIGNyZWF0aW9uLiBUaGUgcmVzb3VyY2UgaXMgc2NvcGVkIHRvIHRoZSBzcGVjaWZpYyBsb2cgZ3JvdXAgZm9yIHRoaXMgTGFtYmRhIGZ1bmN0aW9uLlwiLFxuICAgICAgICAgIGFwcGxpZXNUbzogW1xuICAgICAgICAgICAge1xuICAgICAgICAgICAgICByZWdleDpcbiAgICAgICAgICAgICAgICBcIi9SZXNvdXJjZTo6YXJuOmF3czpsb2dzOi4qOi4qOmxvZy1ncm91cDovYXdzL2xhbWJkYS9sc3MtcGxhdGZvcm0tYXBpOlxcXFwqL1wiLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICBdLFxuICAgICAgICB9LFxuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUlBTTVcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIkFnZW50Q29yZSBSdW50aW1lIGludm9rZSByZXF1aXJlcyB3aWxkY2FyZCBvbiBhZ2VudC1ydW50aW1lIHJlc291cmNlcyBzaW5jZSBhZ2VudCBJRHMgYXJlIGR5bmFtaWMgYW5kIGNyZWF0ZWQgYnkgd29ya3Nob3AgcGFydGljaXBhbnRzLlwiLFxuICAgICAgICAgIGFwcGxpZXNUbzogW1xuICAgICAgICAgICAge1xuICAgICAgICAgICAgICByZWdleDpcbiAgICAgICAgICAgICAgICBcIi9SZXNvdXJjZTo6YXJuOmF3czpiZWRyb2NrOi4qOi4qOmFnZW50LXJ1bnRpbWUvXFxcXCovXCIsXG4gICAgICAgICAgICB9LFxuICAgICAgICAgIF0sXG4gICAgICAgIH0sXG4gICAgICBdLFxuICAgICAgdHJ1ZVxuICAgICk7XG5cbiAgICAvLyBTdXBwcmVzcyBBUEkgR2F0ZXdheSBzZWN1cml0eSB3YXJuaW5ncyAtIHVzaW5nIElBTSBhdXRoZW50aWNhdGlvblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRoaXMuYXBpLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUNPRzRcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIlVzaW5nIElBTSBhdXRoZW50aWNhdGlvbiBpbnN0ZWFkIG9mIENvZ25pdG8gYXV0aG9yaXplci4gSUFNIGF1dGggaXMgZW5mb3JjZWQgdmlhIENvZ25pdG8gSWRlbnRpdHkgUG9vbCBjcmVkZW50aWFscyBmcm9tIHRoZSBXZWJVSSBzdGFjay5cIixcbiAgICAgICAgfSxcbiAgICAgICAge1xuICAgICAgICAgIGlkOiBcIkF3c1NvbHV0aW9ucy1BUElHM1wiLFxuICAgICAgICAgIHJlYXNvbjpcbiAgICAgICAgICAgIFwiV0FGIGlzIG5vdCByZXF1aXJlZCBmb3IgdGhpcyB3b3Jrc2hvcCBBUEkuIEFjY2VzcyBpcyByZXN0cmljdGVkIHZpYSBJQU0gYXV0aGVudGljYXRpb24gYW5kIHNjb3BlZCBDb2duaXRvIElkZW50aXR5IFBvb2wgcm9sZXMuXCIsXG4gICAgICAgIH0sXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtQVBJRzRcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIkFQSSB1c2VzIElBTSBhdXRoZW50aWNhdGlvbiB3aGljaCBwcm92aWRlcyBwcm9wZXIgYXV0aG9yaXphdGlvbi4gQWxsIG1ldGhvZHMgYXJlIHByb3RlY3RlZCB3aXRoIElBTSBhdXRoLlwiLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgLy8gU3VwcHJlc3MgTGFtYmRhIHJ1bnRpbWUgdmVyc2lvbiB3YXJuaW5nIOKAlCBQeXRob24gMy4xMyBpcyB0aGUgbGF0ZXN0IGF2YWlsYWJsZVxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRoaXMuYXBpTGFtYmRhLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUwxXCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJQeXRob24gMy4xMyBpcyB0aGUgbGF0ZXN0IHN0YWJsZSBydW50aW1lIHN1cHBvcnRlZCBieSBBV1MgTGFtYmRhIGF0IHRpbWUgb2YgZGVwbG95bWVudC5cIixcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgICB0cnVlXG4gICAgKTtcbiAgfVxufVxuIl19