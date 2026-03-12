"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.WebUiStack = void 0;
const cdk = require("aws-cdk-lib");
const s3 = require("aws-cdk-lib/aws-s3");
const s3deploy = require("aws-cdk-lib/aws-s3-deployment");
const cloudfront = require("aws-cdk-lib/aws-cloudfront");
const origins = require("aws-cdk-lib/aws-cloudfront-origins");
const cognito = require("aws-cdk-lib/aws-cognito");
const iam = require("aws-cdk-lib/aws-iam");
const lambda = require("aws-cdk-lib/aws-lambda");
const cdk_nag_1 = require("cdk-nag");
class WebUiStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        // -------------------------------------------------------------------------
        // S3 Bucket — static web hosting (public access blocked, S3-managed encryption)
        // -------------------------------------------------------------------------
        this.bucket = new s3.Bucket(this, "WebUIBucket", {
            bucketName: `lss-platform-webui-${this.account}-${this.region}`,
            websiteIndexDocument: "index.html",
            websiteErrorDocument: "index.html", // SPA routing support
            publicReadAccess: false,
            blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
            accessControl: s3.BucketAccessControl.PRIVATE,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
            enforceSSL: true,
        });
        // -------------------------------------------------------------------------
        // CloudFront logs bucket
        // -------------------------------------------------------------------------
        const cloudFrontLogsBucket = new s3.Bucket(this, "CloudFrontLogsBucket", {
            bucketName: `lss-platform-cf-logs-${this.account}-${this.region}`,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
            encryption: s3.BucketEncryption.S3_MANAGED,
            enforceSSL: true,
            blockPublicAccess: new s3.BlockPublicAccess({
                blockPublicAcls: false,
                blockPublicPolicy: true,
                ignorePublicAcls: false,
                restrictPublicBuckets: true,
            }),
            objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
            lifecycleRules: [
                {
                    id: "DeleteOldLogs",
                    enabled: true,
                    expiration: cdk.Duration.days(90),
                },
            ],
        });
        // -------------------------------------------------------------------------
        // CloudFront Distribution — OAC, HTTPS/TLS 1.2
        // -------------------------------------------------------------------------
        this.distribution = new cloudfront.Distribution(this, "WebUIDistribution", {
            comment: "LSS Workshop Platform Web UI Distribution",
            defaultRootObject: "index.html",
            priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
            minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            enableLogging: true,
            logBucket: cloudFrontLogsBucket,
            logFilePrefix: "cloudfront-logs/",
            defaultBehavior: {
                origin: origins.S3BucketOrigin.withOriginAccessControl(this.bucket),
                viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD,
                compress: true,
                cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
            },
            errorResponses: [
                {
                    httpStatus: 404,
                    responseHttpStatus: 200,
                    responsePagePath: "/index.html",
                    ttl: cdk.Duration.minutes(5),
                },
                {
                    httpStatus: 403,
                    responseHttpStatus: 200,
                    responsePagePath: "/index.html",
                    ttl: cdk.Duration.minutes(5),
                },
            ],
        });
        // -------------------------------------------------------------------------
        // Cognito User Pool — self-signup disabled, email sign-in, strong password
        // -------------------------------------------------------------------------
        this.userPool = new cognito.UserPool(this, "UserPool", {
            userPoolName: "lss-platform-users",
            selfSignUpEnabled: false,
            signInAliases: {
                email: true,
                username: true,
            },
            autoVerify: {
                email: true,
            },
            standardAttributes: {
                email: {
                    required: true,
                    mutable: true,
                },
                givenName: {
                    required: true,
                    mutable: true,
                },
                familyName: {
                    required: true,
                    mutable: true,
                },
            },
            passwordPolicy: {
                minLength: 8,
                requireLowercase: true,
                requireUppercase: true,
                requireDigits: true,
                requireSymbols: true,
            },
            accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
            removalPolicy: cdk.RemovalPolicy.DESTROY,
        });
        // -------------------------------------------------------------------------
        // Cognito User Pool Client — SRP auth, authorization code grant
        // -------------------------------------------------------------------------
        this.userPoolClient = new cognito.UserPoolClient(this, "UserPoolClient", {
            userPool: this.userPool,
            userPoolClientName: "lss-platform-web-client",
            generateSecret: false, // Public client for SPA
            authFlows: {
                userSrp: true,
                userPassword: false,
                adminUserPassword: false,
                custom: false,
            },
            oAuth: {
                flows: {
                    authorizationCodeGrant: true,
                    implicitCodeGrant: false,
                },
                scopes: [
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.PROFILE,
                ],
                callbackUrls: [
                    `https://${this.distribution.distributionDomainName}`,
                    `https://${this.distribution.distributionDomainName}/`,
                    "http://localhost:3000",
                    "http://localhost:3000/",
                ],
                logoutUrls: [
                    `https://${this.distribution.distributionDomainName}`,
                    `https://${this.distribution.distributionDomainName}/`,
                    "http://localhost:3000",
                    "http://localhost:3000/",
                ],
            },
            supportedIdentityProviders: [
                cognito.UserPoolClientIdentityProvider.COGNITO,
            ],
            refreshTokenValidity: cdk.Duration.days(30),
            accessTokenValidity: cdk.Duration.hours(1),
            idTokenValidity: cdk.Duration.hours(1),
            preventUserExistenceErrors: true,
        });
        // Cognito User Pool Domain for hosted UI
        const domainPrefix = `lss-platform-${cdk.Names.uniqueId(this)
            .toLowerCase()
            .substring(0, 8)}`;
        const userPoolDomain = new cognito.UserPoolDomain(this, "UserPoolDomain", {
            userPool: this.userPool,
            cognitoDomain: {
                domainPrefix: domainPrefix,
            },
        });
        // -------------------------------------------------------------------------
        // Cognito Identity Pool — authenticated role with execute-api:Invoke
        // -------------------------------------------------------------------------
        this.identityPool = new cognito.CfnIdentityPool(this, "IdentityPool", {
            identityPoolName: "lss-platform-identity-pool",
            allowUnauthenticatedIdentities: false,
            cognitoIdentityProviders: [
                {
                    clientId: this.userPoolClient.userPoolClientId,
                    providerName: this.userPool.userPoolProviderName,
                },
            ],
        });
        // IAM role for authenticated users — scoped to API Gateway
        const authenticatedRole = new iam.Role(this, "AuthenticatedRole", {
            assumedBy: new iam.FederatedPrincipal("cognito-identity.amazonaws.com", {
                StringEquals: {
                    "cognito-identity.amazonaws.com:aud": this.identityPool.ref,
                },
                "ForAnyValue:StringLike": {
                    "cognito-identity.amazonaws.com:amr": "authenticated",
                },
            }, "sts:AssumeRoleWithWebIdentity"),
            description: "IAM role for authenticated Cognito users - LSS Platform API access only",
            inlinePolicies: {
                LssPlatformApiAccess: new iam.PolicyDocument({
                    statements: [
                        new iam.PolicyStatement({
                            effect: iam.Effect.ALLOW,
                            actions: ["execute-api:Invoke"],
                            resources: [
                                `arn:aws:execute-api:${this.region}:${this.account}:${props.apiGatewayId}/*/*`,
                            ],
                        }),
                    ],
                }),
            },
        });
        // Attach role to Identity Pool
        new cognito.CfnIdentityPoolRoleAttachment(this, "IdentityPoolRoleAttachment", {
            identityPoolId: this.identityPool.ref,
            roles: {
                authenticated: authenticatedRole.roleArn,
            },
        });
        // -------------------------------------------------------------------------
        // S3 Bucket Deployment — deploy React app build output
        // -------------------------------------------------------------------------
        const webUIDeployment = new s3deploy.BucketDeployment(this, "WebUIDeployment", {
            sources: [s3deploy.Source.asset("../web-ui/build")],
            destinationBucket: this.bucket,
            distribution: this.distribution,
            distributionPaths: ["/*"],
            prune: true,
        });
        // -------------------------------------------------------------------------
        // Config Generator Lambda — writes aws-config.js to S3
        // -------------------------------------------------------------------------
        const configGeneratorFunction = new lambda.Function(this, "ConfigGenerator", {
            runtime: lambda.Runtime.PYTHON_3_13,
            handler: "index.handler",
            code: lambda.Code.fromInline(`
import json
import boto3
import cfnresponse
import logging
import hashlib

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    logger.info('Incoming event: %s', json.dumps(event, indent=2, default=str))

    response_data = {}

    try:
        s3_client = boto3.client('s3')
        cloudfront_client = boto3.client('cloudfront')

        request_type = event['RequestType']
        resource_props = event.get('ResourceProperties', {})

        config_data = {
            'Region': resource_props.get('Region'),
            'UserPoolId': resource_props.get('UserPoolId'),
            'UserPoolClientId': resource_props.get('UserPoolClientId'),
            'IdentityPoolId': resource_props.get('IdentityPoolId'),
            'ApiGatewayUrl': resource_props.get('ApiGatewayUrl'),
            'CognitoDomain': resource_props.get('CognitoDomain'),
            'Version': resource_props.get('Version'),
        }

        config_string = json.dumps(config_data, sort_keys=True)
        deployment_hash = hashlib.sha256(config_string.encode()).hexdigest()[:16]
        physical_resource_id = f'ConfigGenerator-{deployment_hash}'
        response_data['DeploymentHash'] = deployment_hash

        if request_type == 'Delete':
            logger.info('Delete request - config file preserved')
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data, physical_resource_id)
            return

        if request_type in ('Create', 'Update'):
            config_content = f"""window.AWS_CONFIG = {{
  region: "{resource_props.get('Region')}",
  userPoolId: "{resource_props.get('UserPoolId')}",
  userPoolWebClientId: "{resource_props.get('UserPoolClientId')}",
  identityPoolId: "{resource_props.get('IdentityPoolId')}",
  apiGatewayUrl: "{resource_props.get('ApiGatewayUrl')}",
  cognitoDomain: "{resource_props.get('CognitoDomain')}"
}};
"""
            s3_client.put_object(
                Bucket=resource_props.get('BucketName'),
                Key='aws-config.js',
                Body=config_content,
                ContentType='application/javascript',
                CacheControl='no-cache',
            )
            logger.info('Config file %sd successfully', request_type.lower())

            if resource_props.get('DistributionId'):
                cloudfront_client.create_invalidation(
                    DistributionId=resource_props.get('DistributionId'),
                    InvalidationBatch={
                        'CallerReference': str(context.aws_request_id),
                        'Paths': {'Quantity': 1, 'Items': ['/aws-config.js']},
                    },
                )
                logger.info('CloudFront invalidation created')

            response_data['Message'] = f'Config file {request_type.lower()}d successfully'
            cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data, physical_resource_id)
        else:
            logger.error('Unknown request type: %s', request_type)
            response_data['Error'] = f'Unknown request type: {request_type}'
            cfnresponse.send(event, context, cfnresponse.FAILED, response_data, physical_resource_id)

    except Exception as e:
        logger.error('Error: %s', str(e))
        response_data['Error'] = str(e)
        fallback_id = f'ConfigGenerator-{context.aws_request_id[:16]}'
        cfnresponse.send(event, context, cfnresponse.FAILED, response_data, fallback_id)
`),
            timeout: cdk.Duration.minutes(5),
            description: "Generates aws-config.js and writes it to the WebUI S3 bucket",
        });
        // Grant permissions to Config Generator Lambda
        this.bucket.grantWrite(configGeneratorFunction);
        configGeneratorFunction.addToRolePolicy(new iam.PolicyStatement({
            effect: iam.Effect.ALLOW,
            actions: ["cloudfront:CreateInvalidation"],
            resources: [
                `arn:aws:cloudfront::${this.account}:distribution/${this.distribution.distributionId}`,
            ],
        }));
        // Custom resource to trigger Config Generator
        const configGeneratorResource = new cdk.CustomResource(this, "ConfigGeneratorResource", {
            serviceToken: configGeneratorFunction.functionArn,
            properties: {
                BucketName: this.bucket.bucketName,
                DistributionId: this.distribution.distributionId,
                Region: this.region,
                UserPoolId: this.userPool.userPoolId,
                UserPoolClientId: this.userPoolClient.userPoolClientId,
                IdentityPoolId: this.identityPool.ref,
                ApiGatewayUrl: props.apiGatewayUrl,
                CognitoDomain: `${userPoolDomain.domainName}.auth.${this.region}.amazoncognito.com`,
                Version: "1.0",
                DeploymentTimestamp: Date.now().toString(),
            },
        });
        // Ensure config is generated after the main web UI deployment
        configGeneratorResource.node.addDependency(webUIDeployment);
        // -------------------------------------------------------------------------
        // CloudFormation Outputs
        // -------------------------------------------------------------------------
        new cdk.CfnOutput(this, "CloudFrontUrl", {
            value: `https://${this.distribution.distributionDomainName}`,
            description: "LSS Workshop Platform Web UI URL",
        });
        new cdk.CfnOutput(this, "CognitoUserPoolConsoleUrl", {
            value: `https://${this.region}.console.aws.amazon.com/cognito/v2/idp/user-pools/${this.userPool.userPoolId}/users?region=${this.region}`,
            description: "Cognito User Pool console URL - use this to add users for Web UI login",
        });
        // -------------------------------------------------------------------------
        // cdk-nag AwsSolutions Suppressions
        // -------------------------------------------------------------------------
        // Authenticated role — wildcard on API Gateway paths/methods
        cdk_nag_1.NagSuppressions.addResourceSuppressions(authenticatedRole, [
            {
                id: "AwsSolutions-IAM5",
                reason: "Wildcard permission needed for API Gateway paths and methods. Users need to access various LSS Platform API endpoints (GET, POST, PUT, DELETE on /agents/*, /chat). Scoped to the specific API Gateway only.",
                appliesTo: [
                    `Resource::arn:aws:execute-api:${this.region}:${this.account}:${props.apiGatewayId}/*/*`,
                    {
                        regex: "/Resource::arn:aws:execute-api:.*:.*:.*\\/\\*\\/\\*/",
                    },
                ],
            },
        ], true);
        // CloudFront distribution
        cdk_nag_1.NagSuppressions.addResourceSuppressions(this.distribution, [
            {
                id: "AwsSolutions-CFR1",
                reason: "Geo restriction not required for this workshop application. Users may access from various global locations.",
            },
            {
                id: "AwsSolutions-CFR2",
                reason: "WAF not required for this workshop web UI serving static content. The application is behind Cognito authentication.",
            },
            {
                id: "AwsSolutions-CFR4",
                reason: "Using default CloudFront certificate with TLS 1.2 minimum protocol version (TLS_V1_2_2021). Custom domain can be added later if needed.",
            },
        ], true);
        // WebUI S3 bucket
        cdk_nag_1.NagSuppressions.addResourceSuppressions(this.bucket, [
            {
                id: "AwsSolutions-S1",
                reason: "Access logging not required for static website hosting bucket. CloudFront distribution logging is enabled instead.",
            },
            {
                id: "AwsSolutions-S5",
                reason: "This bucket uses S3BucketOrigin.withOriginAccessControl() which automatically configures CloudFront OAC — the recommended modern approach.",
            },
        ], true);
        // CloudFront logs bucket
        cdk_nag_1.NagSuppressions.addResourceSuppressions(cloudFrontLogsBucket, [
            {
                id: "AwsSolutions-S1",
                reason: "This is the CloudFront access logs bucket itself. Enabling access logging on a logs bucket would create circular dependency.",
            },
            {
                id: "AwsSolutions-S2",
                reason: "CloudFront logs bucket requires specific ACL permissions for CloudFront service to write logs. Not publicly accessible.",
            },
        ], true);
        // Cognito User Pool
        cdk_nag_1.NagSuppressions.addResourceSuppressions(this.userPool, [
            {
                id: "AwsSolutions-COG2",
                reason: "MFA not enforced for this workshop application. Users are pre-created by the instructor and additional MFA would create friction in a time-limited workshop.",
            },
            {
                id: "AwsSolutions-COG3",
                reason: "Advanced Security Mode requires Cognito Plus feature plan with additional costs. Standard security features are adequate for this workshop.",
            },
        ], true);
        // Config Generator Lambda
        cdk_nag_1.NagSuppressions.addResourceSuppressions(configGeneratorFunction, [
            {
                id: "AwsSolutions-IAM4",
                reason: "Lambda execution role uses AWS managed policy for basic execution permissions.",
                appliesTo: [
                    "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                ],
            },
            {
                id: "AwsSolutions-L1",
                reason: "Using Python 3.13 runtime which is the latest stable version supported by AWS Lambda.",
            },
        ], true);
        // Config Generator Lambda S3 write policy
        cdk_nag_1.NagSuppressions.addResourceSuppressionsByPath(this, `/${id}/ConfigGenerator/ServiceRole/DefaultPolicy/Resource`, [
            {
                id: "AwsSolutions-IAM5",
                reason: "Lambda function needs S3 write permissions to upload the config file. Permissions are scoped to the specific S3 bucket.",
                appliesTo: [
                    "Action::s3:Abort*",
                    "Action::s3:DeleteObject*",
                    {
                        regex: "/Resource::.*WebUIBucket.*.Arn.*\\/\\*/",
                    },
                ],
            },
        ], true);
        // CDK BucketDeployment custom resource suppressions
        cdk_nag_1.NagSuppressions.addResourceSuppressionsByPath(this, `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/ServiceRole/Resource`, [
            {
                id: "AwsSolutions-IAM4",
                reason: "AWS managed policy AWSLambdaBasicExecutionRole is required for CDK BucketDeployment custom resource.",
                appliesTo: [
                    "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                ],
            },
        ], true);
        cdk_nag_1.NagSuppressions.addResourceSuppressionsByPath(this, `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/ServiceRole/DefaultPolicy/Resource`, [
            {
                id: "AwsSolutions-IAM5",
                reason: "Wildcard permissions required for CDK BucketDeployment custom resource to manage S3 objects and CloudFront invalidation.",
                appliesTo: [
                    "Action::s3:GetBucket*",
                    "Action::s3:GetObject*",
                    "Action::s3:List*",
                    "Action::s3:Abort*",
                    "Action::s3:DeleteObject*",
                    "Resource::*",
                    {
                        regex: "/Resource::arn:.*:s3:::cdk-.*-assets-.*/",
                    },
                    {
                        regex: "/Resource::.*WebUIBucket.*.Arn.*\\/\\*/",
                    },
                ],
            },
        ], true);
        cdk_nag_1.NagSuppressions.addResourceSuppressionsByPath(this, `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/Resource`, [
            {
                id: "AwsSolutions-L1",
                reason: "CDK BucketDeployment custom resource uses the latest available runtime managed by CDK. Runtime version is controlled by the CDK framework.",
            },
        ], true);
    }
}
exports.WebUiStack = WebUiStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoid2VidWktc3RhY2suanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyJ3ZWJ1aS1zdGFjay50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiOzs7QUFBQSxtQ0FBbUM7QUFFbkMseUNBQXlDO0FBQ3pDLDBEQUEwRDtBQUMxRCx5REFBeUQ7QUFDekQsOERBQThEO0FBQzlELG1EQUFtRDtBQUNuRCwyQ0FBMkM7QUFDM0MsaURBQWlEO0FBQ2pELHFDQUEwQztBQVcxQyxNQUFhLFVBQVcsU0FBUSxHQUFHLENBQUMsS0FBSztJQU92QyxZQUFZLEtBQWdCLEVBQUUsRUFBVSxFQUFFLEtBQXNCO1FBQzlELEtBQUssQ0FBQyxLQUFLLEVBQUUsRUFBRSxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBRXhCLDRFQUE0RTtRQUM1RSxnRkFBZ0Y7UUFDaEYsNEVBQTRFO1FBQzVFLElBQUksQ0FBQyxNQUFNLEdBQUcsSUFBSSxFQUFFLENBQUMsTUFBTSxDQUFDLElBQUksRUFBRSxhQUFhLEVBQUU7WUFDL0MsVUFBVSxFQUFFLHNCQUFzQixJQUFJLENBQUMsT0FBTyxJQUFJLElBQUksQ0FBQyxNQUFNLEVBQUU7WUFDL0Qsb0JBQW9CLEVBQUUsWUFBWTtZQUNsQyxvQkFBb0IsRUFBRSxZQUFZLEVBQUUsc0JBQXNCO1lBQzFELGdCQUFnQixFQUFFLEtBQUs7WUFDdkIsaUJBQWlCLEVBQUUsRUFBRSxDQUFDLGlCQUFpQixDQUFDLFNBQVM7WUFDakQsYUFBYSxFQUFFLEVBQUUsQ0FBQyxtQkFBbUIsQ0FBQyxPQUFPO1lBQzdDLGFBQWEsRUFBRSxHQUFHLENBQUMsYUFBYSxDQUFDLE9BQU87WUFDeEMsaUJBQWlCLEVBQUUsSUFBSTtZQUN2QixVQUFVLEVBQUUsRUFBRSxDQUFDLGdCQUFnQixDQUFDLFVBQVU7WUFDMUMsVUFBVSxFQUFFLElBQUk7U0FDakIsQ0FBQyxDQUFDO1FBRUgsNEVBQTRFO1FBQzVFLHlCQUF5QjtRQUN6Qiw0RUFBNEU7UUFDNUUsTUFBTSxvQkFBb0IsR0FBRyxJQUFJ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Iiwic291cmNlc0NvbnRlbnQiOlsiaW1wb3J0ICogYXMgY2RrIGZyb20gXCJhd3MtY2RrLWxpYlwiO1xuaW1wb3J0IHsgQ29uc3RydWN0IH0gZnJvbSBcImNvbnN0cnVjdHNcIjtcbmltcG9ydCAqIGFzIHMzIGZyb20gXCJhd3MtY2RrLWxpYi9hd3MtczNcIjtcbmltcG9ydCAqIGFzIHMzZGVwbG95IGZyb20gXCJhd3MtY2RrLWxpYi9hd3MtczMtZGVwbG95bWVudFwiO1xuaW1wb3J0ICogYXMgY2xvdWRmcm9udCBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWNsb3VkZnJvbnRcIjtcbmltcG9ydCAqIGFzIG9yaWdpbnMgZnJvbSBcImF3cy1jZGstbGliL2F3cy1jbG91ZGZyb250LW9yaWdpbnNcIjtcbmltcG9ydCAqIGFzIGNvZ25pdG8gZnJvbSBcImF3cy1jZGstbGliL2F3cy1jb2duaXRvXCI7XG5pbXBvcnQgKiBhcyBpYW0gZnJvbSBcImF3cy1jZGstbGliL2F3cy1pYW1cIjtcbmltcG9ydCAqIGFzIGxhbWJkYSBmcm9tIFwiYXdzLWNkay1saWIvYXdzLWxhbWJkYVwiO1xuaW1wb3J0IHsgTmFnU3VwcHJlc3Npb25zIH0gZnJvbSBcImNkay1uYWdcIjtcblxuZXhwb3J0IGludGVyZmFjZSBXZWJVaVN0YWNrUHJvcHMgZXh0ZW5kcyBjZGsuU3RhY2tQcm9wcyB7XG4gIC8qKiBBUEkgR2F0ZXdheSBVUkwgZnJvbSBBcGlTdGFjayAqL1xuICBhcGlHYXRld2F5VXJsOiBzdHJpbmc7XG4gIC8qKiBBUEkgR2F0ZXdheSBSRVNUIEFQSSBJRCBmcm9tIEFwaVN0YWNrICovXG4gIGFwaUdhdGV3YXlJZDogc3RyaW5nO1xuICAvKiogU3RhY2tQcmVmaXggQ2ZuUGFyYW1ldGVyIGZvciBjcm9zcy1zdGFjayBuYW1pbmcgd2l0aCBleGlzdGluZyB3b3Jrc2hvcCB0ZW1wbGF0ZXMgKi9cbiAgc3RhY2tQcmVmaXg6IGNkay5DZm5QYXJhbWV0ZXI7XG59XG5cbmV4cG9ydCBjbGFzcyBXZWJVaVN0YWNrIGV4dGVuZHMgY2RrLlN0YWNrIHtcbiAgcHVibGljIHJlYWRvbmx5IGJ1Y2tldDogczMuQnVja2V0O1xuICBwdWJsaWMgcmVhZG9ubHkgZGlzdHJpYnV0aW9uOiBjbG91ZGZyb250LkRpc3RyaWJ1dGlvbjtcbiAgcHVibGljIHJlYWRvbmx5IHVzZXJQb29sOiBjb2duaXRvLlVzZXJQb29sO1xuICBwdWJsaWMgcmVhZG9ubHkgdXNlclBvb2xDbGllbnQ6IGNvZ25pdG8uVXNlclBvb2xDbGllbnQ7XG4gIHB1YmxpYyByZWFkb25seSBpZGVudGl0eVBvb2w6IGNvZ25pdG8uQ2ZuSWRlbnRpdHlQb29sO1xuXG4gIGNvbnN0cnVjdG9yKHNjb3BlOiBDb25zdHJ1Y3QsIGlkOiBzdHJpbmcsIHByb3BzOiBXZWJVaVN0YWNrUHJvcHMpIHtcbiAgICBzdXBlcihzY29wZSwgaWQsIHByb3BzKTtcblxuICAgIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyBTMyBCdWNrZXQg4oCUIHN0YXRpYyB3ZWIgaG9zdGluZyAocHVibGljIGFjY2VzcyBibG9ja2VkLCBTMy1tYW5hZ2VkIGVuY3J5cHRpb24pXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIHRoaXMuYnVja2V0ID0gbmV3IHMzLkJ1Y2tldCh0aGlzLCBcIldlYlVJQnVja2V0XCIsIHtcbiAgICAgIGJ1Y2tldE5hbWU6IGBsc3MtcGxhdGZvcm0td2VidWktJHt0aGlzLmFjY291bnR9LSR7dGhpcy5yZWdpb259YCxcbiAgICAgIHdlYnNpdGVJbmRleERvY3VtZW50OiBcImluZGV4Lmh0bWxcIixcbiAgICAgIHdlYnNpdGVFcnJvckRvY3VtZW50OiBcImluZGV4Lmh0bWxcIiwgLy8gU1BBIHJvdXRpbmcgc3VwcG9ydFxuICAgICAgcHVibGljUmVhZEFjY2VzczogZmFsc2UsXG4gICAgICBibG9ja1B1YmxpY0FjY2VzczogczMuQmxvY2tQdWJsaWNBY2Nlc3MuQkxPQ0tfQUxMLFxuICAgICAgYWNjZXNzQ29udHJvbDogczMuQnVja2V0QWNjZXNzQ29udHJvbC5QUklWQVRFLFxuICAgICAgcmVtb3ZhbFBvbGljeTogY2RrLlJlbW92YWxQb2xpY3kuREVTVFJPWSxcbiAgICAgIGF1dG9EZWxldGVPYmplY3RzOiB0cnVlLFxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgZW5mb3JjZVNTTDogdHJ1ZSxcbiAgICB9KTtcblxuICAgIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyBDbG91ZEZyb250IGxvZ3MgYnVja2V0XG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIGNvbnN0IGNsb3VkRnJvbnRMb2dzQnVja2V0ID0gbmV3IHMzLkJ1Y2tldCh0aGlzLCBcIkNsb3VkRnJvbnRMb2dzQnVja2V0XCIsIHtcbiAgICAgIGJ1Y2tldE5hbWU6IGBsc3MtcGxhdGZvcm0tY2YtbG9ncy0ke3RoaXMuYWNjb3VudH0tJHt0aGlzLnJlZ2lvbn1gLFxuICAgICAgcmVtb3ZhbFBvbGljeTogY2RrLlJlbW92YWxQb2xpY3kuREVTVFJPWSxcbiAgICAgIGF1dG9EZWxldGVPYmplY3RzOiB0cnVlLFxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgZW5mb3JjZVNTTDogdHJ1ZSxcbiAgICAgIGJsb2NrUHVibGljQWNjZXNzOiBuZXcgczMuQmxvY2tQdWJsaWNBY2Nlc3Moe1xuICAgICAgICBibG9ja1B1YmxpY0FjbHM6IGZhbHNlLFxuICAgICAgICBibG9ja1B1YmxpY1BvbGljeTogdHJ1ZSxcbiAgICAgICAgaWdub3JlUHVibGljQWNsczogZmFsc2UsXG4gICAgICAgIHJlc3RyaWN0UHVibGljQnVja2V0czogdHJ1ZSxcbiAgICAgIH0pLFxuICAgICAgb2JqZWN0T3duZXJzaGlwOiBzMy5PYmplY3RPd25lcnNoaXAuQlVDS0VUX09XTkVSX1BSRUZFUlJFRCxcbiAgICAgIGxpZmVjeWNsZVJ1bGVzOiBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJEZWxldGVPbGRMb2dzXCIsXG4gICAgICAgICAgZW5hYmxlZDogdHJ1ZSxcbiAgICAgICAgICBleHBpcmF0aW9uOiBjZGsuRHVyYXRpb24uZGF5cyg5MCksXG4gICAgICAgIH0sXG4gICAgICBdLFxuICAgIH0pO1xuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIC8vIENsb3VkRnJvbnQgRGlzdHJpYnV0aW9uIOKAlCBPQUMsIEhUVFBTL1RMUyAxLjJcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgdGhpcy5kaXN0cmlidXRpb24gPSBuZXcgY2xvdWRmcm9udC5EaXN0cmlidXRpb24odGhpcywgXCJXZWJVSURpc3RyaWJ1dGlvblwiLCB7XG4gICAgICBjb21tZW50OiBcIkxTUyBXb3Jrc2hvcCBQbGF0Zm9ybSBXZWIgVUkgRGlzdHJpYnV0aW9uXCIsXG4gICAgICBkZWZhdWx0Um9vdE9iamVjdDogXCJpbmRleC5odG1sXCIsXG4gICAgICBwcmljZUNsYXNzOiBjbG91ZGZyb250LlByaWNlQ2xhc3MuUFJJQ0VfQ0xBU1NfMTAwLFxuICAgICAgbWluaW11bVByb3RvY29sVmVyc2lvbjogY2xvdWRmcm9udC5TZWN1cml0eVBvbGljeVByb3RvY29sLlRMU19WMV8yXzIwMjEsXG4gICAgICBlbmFibGVMb2dnaW5nOiB0cnVlLFxuICAgICAgbG9nQnVja2V0OiBjbG91ZEZyb250TG9nc0J1Y2tldCxcbiAgICAgIGxvZ0ZpbGVQcmVmaXg6IFwiY2xvdWRmcm9udC1sb2dzL1wiLFxuICAgICAgZGVmYXVsdEJlaGF2aW9yOiB7XG4gICAgICAgIG9yaWdpbjogb3JpZ2lucy5TM0J1Y2tldE9yaWdpbi53aXRoT3JpZ2luQWNjZXNzQ29udHJvbCh0aGlzLmJ1Y2tldCksXG4gICAgICAgIHZpZXdlclByb3RvY29sUG9saWN5OiBjbG91ZGZyb250LlZpZXdlclByb3RvY29sUG9saWN5LlJFRElSRUNUX1RPX0hUVFBTLFxuICAgICAgICBhbGxvd2VkTWV0aG9kczogY2xvdWRmcm9udC5BbGxvd2VkTWV0aG9kcy5BTExPV19HRVRfSEVBRCxcbiAgICAgICAgY2FjaGVkTWV0aG9kczogY2xvdWRmcm9udC5DYWNoZWRNZXRob2RzLkNBQ0hFX0dFVF9IRUFELFxuICAgICAgICBjb21wcmVzczogdHJ1ZSxcbiAgICAgICAgY2FjaGVQb2xpY3k6IGNsb3VkZnJvbnQuQ2FjaGVQb2xpY3kuQ0FDSElOR19PUFRJTUlaRUQsXG4gICAgICB9LFxuICAgICAgZXJyb3JSZXNwb25zZXM6IFtcbiAgICAgICAge1xuICAgICAgICAgIGh0dHBTdGF0dXM6IDQwNCxcbiAgICAgICAgICByZXNwb25zZUh0dHBTdGF0dXM6IDIwMCxcbiAgICAgICAgICByZXNwb25zZVBhZ2VQYXRoOiBcIi9pbmRleC5odG1sXCIsXG4gICAgICAgICAgdHRsOiBjZGsuRHVyYXRpb24ubWludXRlcyg1KSxcbiAgICAgICAgfSxcbiAgICAgICAge1xuICAgICAgICAgIGh0dHBTdGF0dXM6IDQwMyxcbiAgICAgICAgICByZXNwb25zZUh0dHBTdGF0dXM6IDIwMCxcbiAgICAgICAgICByZXNwb25zZVBhZ2VQYXRoOiBcIi9pbmRleC5odG1sXCIsXG4gICAgICAgICAgdHRsOiBjZGsuRHVyYXRpb24ubWludXRlcyg1KSxcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgfSk7XG5cbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgLy8gQ29nbml0byBVc2VyIFBvb2wg4oCUIHNlbGYtc2lnbnVwIGRpc2FibGVkLCBlbWFpbCBzaWduLWluLCBzdHJvbmcgcGFzc3dvcmRcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgdGhpcy51c2VyUG9vbCA9IG5ldyBjb2duaXRvLlVzZXJQb29sKHRoaXMsIFwiVXNlclBvb2xcIiwge1xuICAgICAgdXNlclBvb2xOYW1lOiBcImxzcy1wbGF0Zm9ybS11c2Vyc1wiLFxuICAgICAgc2VsZlNpZ25VcEVuYWJsZWQ6IGZhbHNlLFxuICAgICAgc2lnbkluQWxpYXNlczoge1xuICAgICAgICBlbWFpbDogdHJ1ZSxcbiAgICAgICAgdXNlcm5hbWU6IHRydWUsXG4gICAgICB9LFxuICAgICAgYXV0b1ZlcmlmeToge1xuICAgICAgICBlbWFpbDogdHJ1ZSxcbiAgICAgIH0sXG4gICAgICBzdGFuZGFyZEF0dHJpYnV0ZXM6IHtcbiAgICAgICAgZW1haWw6IHtcbiAgICAgICAgICByZXF1aXJlZDogdHJ1ZSxcbiAgICAgICAgICBtdXRhYmxlOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgICBnaXZlbk5hbWU6IHtcbiAgICAgICAgICByZXF1aXJlZDogdHJ1ZSxcbiAgICAgICAgICBtdXRhYmxlOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgICBmYW1pbHlOYW1lOiB7XG4gICAgICAgICAgcmVxdWlyZWQ6IHRydWUsXG4gICAgICAgICAgbXV0YWJsZTogdHJ1ZSxcbiAgICAgICAgfSxcbiAgICAgIH0sXG4gICAgICBwYXNzd29yZFBvbGljeToge1xuICAgICAgICBtaW5MZW5ndGg6IDgsXG4gICAgICAgIHJlcXVpcmVMb3dlcmNhc2U6IHRydWUsXG4gICAgICAgIHJlcXVpcmVVcHBlcmNhc2U6IHRydWUsXG4gICAgICAgIHJlcXVpcmVEaWdpdHM6IHRydWUsXG4gICAgICAgIHJlcXVpcmVTeW1ib2xzOiB0cnVlLFxuICAgICAgfSxcbiAgICAgIGFjY291bnRSZWNvdmVyeTogY29nbml0by5BY2NvdW50UmVjb3ZlcnkuRU1BSUxfT05MWSxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgfSk7XG5cbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgLy8gQ29nbml0byBVc2VyIFBvb2wgQ2xpZW50IOKAlCBTUlAgYXV0aCwgYXV0aG9yaXphdGlvbiBjb2RlIGdyYW50XG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIHRoaXMudXNlclBvb2xDbGllbnQgPSBuZXcgY29nbml0by5Vc2VyUG9vbENsaWVudCh0aGlzLCBcIlVzZXJQb29sQ2xpZW50XCIsIHtcbiAgICAgIHVzZXJQb29sOiB0aGlzLnVzZXJQb29sLFxuICAgICAgdXNlclBvb2xDbGllbnROYW1lOiBcImxzcy1wbGF0Zm9ybS13ZWItY2xpZW50XCIsXG4gICAgICBnZW5lcmF0ZVNlY3JldDogZmFsc2UsIC8vIFB1YmxpYyBjbGllbnQgZm9yIFNQQVxuICAgICAgYXV0aEZsb3dzOiB7XG4gICAgICAgIHVzZXJTcnA6IHRydWUsXG4gICAgICAgIHVzZXJQYXNzd29yZDogZmFsc2UsXG4gICAgICAgIGFkbWluVXNlclBhc3N3b3JkOiBmYWxzZSxcbiAgICAgICAgY3VzdG9tOiBmYWxzZSxcbiAgICAgIH0sXG4gICAgICBvQXV0aDoge1xuICAgICAgICBmbG93czoge1xuICAgICAgICAgIGF1dGhvcml6YXRpb25Db2RlR3JhbnQ6IHRydWUsXG4gICAgICAgICAgaW1wbGljaXRDb2RlR3JhbnQ6IGZhbHNlLFxuICAgICAgICB9LFxuICAgICAgICBzY29wZXM6IFtcbiAgICAgICAgICBjb2duaXRvLk9BdXRoU2NvcGUuRU1BSUwsXG4gICAgICAgICAgY29nbml0by5PQXV0aFNjb3BlLk9QRU5JRCxcbiAgICAgICAgICBjb2duaXRvLk9BdXRoU2NvcGUuUFJPRklMRSxcbiAgICAgICAgXSxcbiAgICAgICAgY2FsbGJhY2tVcmxzOiBbXG4gICAgICAgICAgYGh0dHBzOi8vJHt0aGlzLmRpc3RyaWJ1dGlvbi5kaXN0cmlidXRpb25Eb21haW5OYW1lfWAsXG4gICAgICAgICAgYGh0dHBzOi8vJHt0aGlzLmRpc3RyaWJ1dGlvbi5kaXN0cmlidXRpb25Eb21haW5OYW1lfS9gLFxuICAgICAgICAgIFwiaHR0cDovL2xvY2FsaG9zdDozMDAwXCIsXG4gICAgICAgICAgXCJodHRwOi8vbG9jYWxob3N0OjMwMDAvXCIsXG4gICAgICAgIF0sXG4gICAgICAgIGxvZ291dFVybHM6IFtcbiAgICAgICAgICBgaHR0cHM6Ly8ke3RoaXMuZGlzdHJpYnV0aW9uLmRpc3RyaWJ1dGlvbkRvbWFpbk5hbWV9YCxcbiAgICAgICAgICBgaHR0cHM6Ly8ke3RoaXMuZGlzdHJpYnV0aW9uLmRpc3RyaWJ1dGlvbkRvbWFpbk5hbWV9L2AsXG4gICAgICAgICAgXCJodHRwOi8vbG9jYWxob3N0OjMwMDBcIixcbiAgICAgICAgICBcImh0dHA6Ly9sb2NhbGhvc3Q6MzAwMC9cIixcbiAgICAgICAgXSxcbiAgICAgIH0sXG4gICAgICBzdXBwb3J0ZWRJZGVudGl0eVByb3ZpZGVyczogW1xuICAgICAgICBjb2duaXRvLlVzZXJQb29sQ2xpZW50SWRlbnRpdHlQcm92aWRlci5DT0dOSVRPLFxuICAgICAgXSxcbiAgICAgIHJlZnJlc2hUb2tlblZhbGlkaXR5OiBjZGsuRHVyYXRpb24uZGF5cygzMCksXG4gICAgICBhY2Nlc3NUb2tlblZhbGlkaXR5OiBjZGsuRHVyYXRpb24uaG91cnMoMSksXG4gICAgICBpZFRva2VuVmFsaWRpdHk6IGNkay5EdXJhdGlvbi5ob3VycygxKSxcbiAgICAgIHByZXZlbnRVc2VyRXhpc3RlbmNlRXJyb3JzOiB0cnVlLFxuICAgIH0pO1xuXG4gICAgLy8gQ29nbml0byBVc2VyIFBvb2wgRG9tYWluIGZvciBob3N0ZWQgVUlcbiAgICBjb25zdCBkb21haW5QcmVmaXggPSBgbHNzLXBsYXRmb3JtLSR7Y2RrLk5hbWVzLnVuaXF1ZUlkKHRoaXMpXG4gICAgICAudG9Mb3dlckNhc2UoKVxuICAgICAgLnN1YnN0cmluZygwLCA4KX1gO1xuICAgIGNvbnN0IHVzZXJQb29sRG9tYWluID0gbmV3IGNvZ25pdG8uVXNlclBvb2xEb21haW4odGhpcywgXCJVc2VyUG9vbERvbWFpblwiLCB7XG4gICAgICB1c2VyUG9vbDogdGhpcy51c2VyUG9vbCxcbiAgICAgIGNvZ25pdG9Eb21haW46IHtcbiAgICAgICAgZG9tYWluUHJlZml4OiBkb21haW5QcmVmaXgsXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIC8vIENvZ25pdG8gSWRlbnRpdHkgUG9vbCDigJQgYXV0aGVudGljYXRlZCByb2xlIHdpdGggZXhlY3V0ZS1hcGk6SW52b2tlXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIHRoaXMuaWRlbnRpdHlQb29sID0gbmV3IGNvZ25pdG8uQ2ZuSWRlbnRpdHlQb29sKHRoaXMsIFwiSWRlbnRpdHlQb29sXCIsIHtcbiAgICAgIGlkZW50aXR5UG9vbE5hbWU6IFwibHNzLXBsYXRmb3JtLWlkZW50aXR5LXBvb2xcIixcbiAgICAgIGFsbG93VW5hdXRoZW50aWNhdGVkSWRlbnRpdGllczogZmFsc2UsXG4gICAgICBjb2duaXRvSWRlbnRpdHlQcm92aWRlcnM6IFtcbiAgICAgICAge1xuICAgICAgICAgIGNsaWVudElkOiB0aGlzLnVzZXJQb29sQ2xpZW50LnVzZXJQb29sQ2xpZW50SWQsXG4gICAgICAgICAgcHJvdmlkZXJOYW1lOiB0aGlzLnVzZXJQb29sLnVzZXJQb29sUHJvdmlkZXJOYW1lLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIElBTSByb2xlIGZvciBhdXRoZW50aWNhdGVkIHVzZXJzIOKAlCBzY29wZWQgdG8gQVBJIEdhdGV3YXlcbiAgICBjb25zdCBhdXRoZW50aWNhdGVkUm9sZSA9IG5ldyBpYW0uUm9sZSh0aGlzLCBcIkF1dGhlbnRpY2F0ZWRSb2xlXCIsIHtcbiAgICAgIGFzc3VtZWRCeTogbmV3IGlhbS5GZWRlcmF0ZWRQcmluY2lwYWwoXG4gICAgICAgIFwiY29nbml0by1pZGVudGl0eS5hbWF6b25hd3MuY29tXCIsXG4gICAgICAgIHtcbiAgICAgICAgICBTdHJpbmdFcXVhbHM6IHtcbiAgICAgICAgICAgIFwiY29nbml0by1pZGVudGl0eS5hbWF6b25hd3MuY29tOmF1ZFwiOiB0aGlzLmlkZW50aXR5UG9vbC5yZWYsXG4gICAgICAgICAgfSxcbiAgICAgICAgICBcIkZvckFueVZhbHVlOlN0cmluZ0xpa2VcIjoge1xuICAgICAgICAgICAgXCJjb2duaXRvLWlkZW50aXR5LmFtYXpvbmF3cy5jb206YW1yXCI6IFwiYXV0aGVudGljYXRlZFwiLFxuICAgICAgICAgIH0sXG4gICAgICAgIH0sXG4gICAgICAgIFwic3RzOkFzc3VtZVJvbGVXaXRoV2ViSWRlbnRpdHlcIlxuICAgICAgKSxcbiAgICAgIGRlc2NyaXB0aW9uOlxuICAgICAgICBcIklBTSByb2xlIGZvciBhdXRoZW50aWNhdGVkIENvZ25pdG8gdXNlcnMgLSBMU1MgUGxhdGZvcm0gQVBJIGFjY2VzcyBvbmx5XCIsXG4gICAgICBpbmxpbmVQb2xpY2llczoge1xuICAgICAgICBMc3NQbGF0Zm9ybUFwaUFjY2VzczogbmV3IGlhbS5Qb2xpY3lEb2N1bWVudCh7XG4gICAgICAgICAgc3RhdGVtZW50czogW1xuICAgICAgICAgICAgbmV3IGlhbS5Qb2xpY3lTdGF0ZW1lbnQoe1xuICAgICAgICAgICAgICBlZmZlY3Q6IGlhbS5FZmZlY3QuQUxMT1csXG4gICAgICAgICAgICAgIGFjdGlvbnM6IFtcImV4ZWN1dGUtYXBpOkludm9rZVwiXSxcbiAgICAgICAgICAgICAgcmVzb3VyY2VzOiBbXG4gICAgICAgICAgICAgICAgYGFybjphd3M6ZXhlY3V0ZS1hcGk6JHt0aGlzLnJlZ2lvbn06JHt0aGlzLmFjY291bnR9OiR7cHJvcHMuYXBpR2F0ZXdheUlkfS8qLypgLFxuICAgICAgICAgICAgICBdLFxuICAgICAgICAgICAgfSksXG4gICAgICAgICAgXSxcbiAgICAgICAgfSksXG4gICAgICB9LFxuICAgIH0pO1xuXG4gICAgLy8gQXR0YWNoIHJvbGUgdG8gSWRlbnRpdHkgUG9vbFxuICAgIG5ldyBjb2duaXRvLkNmbklkZW50aXR5UG9vbFJvbGVBdHRhY2htZW50KFxuICAgICAgdGhpcyxcbiAgICAgIFwiSWRlbnRpdHlQb29sUm9sZUF0dGFjaG1lbnRcIixcbiAgICAgIHtcbiAgICAgICAgaWRlbnRpdHlQb29sSWQ6IHRoaXMuaWRlbnRpdHlQb29sLnJlZixcbiAgICAgICAgcm9sZXM6IHtcbiAgICAgICAgICBhdXRoZW50aWNhdGVkOiBhdXRoZW50aWNhdGVkUm9sZS5yb2xlQXJuLFxuICAgICAgICB9LFxuICAgICAgfVxuICAgICk7XG5cbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgLy8gUzMgQnVja2V0IERlcGxveW1lbnQg4oCUIGRlcGxveSBSZWFjdCBhcHAgYnVpbGQgb3V0cHV0XG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIGNvbnN0IHdlYlVJRGVwbG95bWVudCA9IG5ldyBzM2RlcGxveS5CdWNrZXREZXBsb3ltZW50KFxuICAgICAgdGhpcyxcbiAgICAgIFwiV2ViVUlEZXBsb3ltZW50XCIsXG4gICAgICB7XG4gICAgICAgIHNvdXJjZXM6IFtzM2RlcGxveS5Tb3VyY2UuYXNzZXQoXCIuLi93ZWItdWkvYnVpbGRcIildLFxuICAgICAgICBkZXN0aW5hdGlvbkJ1Y2tldDogdGhpcy5idWNrZXQsXG4gICAgICAgIGRpc3RyaWJ1dGlvbjogdGhpcy5kaXN0cmlidXRpb24sXG4gICAgICAgIGRpc3RyaWJ1dGlvblBhdGhzOiBbXCIvKlwiXSxcbiAgICAgICAgcHJ1bmU6IHRydWUsXG4gICAgICB9XG4gICAgKTtcblxuICAgIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyBDb25maWcgR2VuZXJhdG9yIExhbWJkYSDigJQgd3JpdGVzIGF3cy1jb25maWcuanMgdG8gUzNcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgY29uc3QgY29uZmlnR2VuZXJhdG9yRnVuY3Rpb24gPSBuZXcgbGFtYmRhLkZ1bmN0aW9uKFxuICAgICAgdGhpcyxcbiAgICAgIFwiQ29uZmlnR2VuZXJhdG9yXCIsXG4gICAgICB7XG4gICAgICAgIHJ1bnRpbWU6IGxhbWJkYS5SdW50aW1lLlBZVEhPTl8zXzEzLFxuICAgICAgICBoYW5kbGVyOiBcImluZGV4LmhhbmRsZXJcIixcbiAgICAgICAgY29kZTogbGFtYmRhLkNvZGUuZnJvbUlubGluZShgXG5pbXBvcnQganNvblxuaW1wb3J0IGJvdG8zXG5pbXBvcnQgY2ZucmVzcG9uc2VcbmltcG9ydCBsb2dnaW5nXG5pbXBvcnQgaGFzaGxpYlxuXG5sb2dnZXIgPSBsb2dnaW5nLmdldExvZ2dlcigpXG5sb2dnZXIuc2V0TGV2ZWwobG9nZ2luZy5JTkZPKVxuXG5kZWYgaGFuZGxlcihldmVudCwgY29udGV4dCk6XG4gICAgbG9nZ2VyLmluZm8oJ0luY29taW5nIGV2ZW50OiAlcycsIGpzb24uZHVtcHMoZXZlbnQsIGluZGVudD0yLCBkZWZhdWx0PXN0cikpXG5cbiAgICByZXNwb25zZV9kYXRhID0ge31cblxuICAgIHRyeTpcbiAgICAgICAgczNfY2xpZW50ID0gYm90bzMuY2xpZW50KCdzMycpXG4gICAgICAgIGNsb3VkZnJvbnRfY2xpZW50ID0gYm90bzMuY2xpZW50KCdjbG91ZGZyb250JylcblxuICAgICAgICByZXF1ZXN0X3R5cGUgPSBldmVudFsnUmVxdWVzdFR5cGUnXVxuICAgICAgICByZXNvdXJjZV9wcm9wcyA9IGV2ZW50LmdldCgnUmVzb3VyY2VQcm9wZXJ0aWVzJywge30pXG5cbiAgICAgICAgY29uZmlnX2RhdGEgPSB7XG4gICAgICAgICAgICAnUmVnaW9uJzogcmVzb3VyY2VfcHJvcHMuZ2V0KCdSZWdpb24nKSxcbiAgICAgICAgICAgICdVc2VyUG9vbElkJzogcmVzb3VyY2VfcHJvcHMuZ2V0KCdVc2VyUG9vbElkJyksXG4gICAgICAgICAgICAnVXNlclBvb2xDbGllbnRJZCc6IHJlc291cmNlX3Byb3BzLmdldCgnVXNlclBvb2xDbGllbnRJZCcpLFxuICAgICAgICAgICAgJ0lkZW50aXR5UG9vbElkJzogcmVzb3VyY2VfcHJvcHMuZ2V0KCdJZGVudGl0eVBvb2xJZCcpLFxuICAgICAgICAgICAgJ0FwaUdhdGV3YXlVcmwnOiByZXNvdXJjZV9wcm9wcy5nZXQoJ0FwaUdhdGV3YXlVcmwnKSxcbiAgICAgICAgICAgICdDb2duaXRvRG9tYWluJzogcmVzb3VyY2VfcHJvcHMuZ2V0KCdDb2duaXRvRG9tYWluJyksXG4gICAgICAgICAgICAnVmVyc2lvbic6IHJlc291cmNlX3Byb3BzLmdldCgnVmVyc2lvbicpLFxuICAgICAgICB9XG5cbiAgICAgICAgY29uZmlnX3N0cmluZyA9IGpzb24uZHVtcHMoY29uZmlnX2RhdGEsIHNvcnRfa2V5cz1UcnVlKVxuICAgICAgICBkZXBsb3ltZW50X2hhc2ggPSBoYXNobGliLnNoYTI1Nihjb25maWdfc3RyaW5nLmVuY29kZSgpKS5oZXhkaWdlc3QoKVs6MTZdXG4gICAgICAgIHBoeXNpY2FsX3Jlc291cmNlX2lkID0gZidDb25maWdHZW5lcmF0b3Ite2RlcGxveW1lbnRfaGFzaH0nXG4gICAgICAgIHJlc3BvbnNlX2RhdGFbJ0RlcGxveW1lbnRIYXNoJ10gPSBkZXBsb3ltZW50X2hhc2hcblxuICAgICAgICBpZiByZXF1ZXN0X3R5cGUgPT0gJ0RlbGV0ZSc6XG4gICAgICAgICAgICBsb2dnZXIuaW5mbygnRGVsZXRlIHJlcXVlc3QgLSBjb25maWcgZmlsZSBwcmVzZXJ2ZWQnKVxuICAgICAgICAgICAgY2ZucmVzcG9uc2Uuc2VuZChldmVudCwgY29udGV4dCwgY2ZucmVzcG9uc2UuU1VDQ0VTUywgcmVzcG9uc2VfZGF0YSwgcGh5c2ljYWxfcmVzb3VyY2VfaWQpXG4gICAgICAgICAgICByZXR1cm5cblxuICAgICAgICBpZiByZXF1ZXN0X3R5cGUgaW4gKCdDcmVhdGUnLCAnVXBkYXRlJyk6XG4gICAgICAgICAgICBjb25maWdfY29udGVudCA9IGZcIlwiXCJ3aW5kb3cuQVdTX0NPTkZJRyA9IHt7XG4gIHJlZ2lvbjogXCJ7cmVzb3VyY2VfcHJvcHMuZ2V0KCdSZWdpb24nKX1cIixcbiAgdXNlclBvb2xJZDogXCJ7cmVzb3VyY2VfcHJvcHMuZ2V0KCdVc2VyUG9vbElkJyl9XCIsXG4gIHVzZXJQb29sV2ViQ2xpZW50SWQ6IFwie3Jlc291cmNlX3Byb3BzLmdldCgnVXNlclBvb2xDbGllbnRJZCcpfVwiLFxuICBpZGVudGl0eVBvb2xJZDogXCJ7cmVzb3VyY2VfcHJvcHMuZ2V0KCdJZGVudGl0eVBvb2xJZCcpfVwiLFxuICBhcGlHYXRld2F5VXJsOiBcIntyZXNvdXJjZV9wcm9wcy5nZXQoJ0FwaUdhdGV3YXlVcmwnKX1cIixcbiAgY29nbml0b0RvbWFpbjogXCJ7cmVzb3VyY2VfcHJvcHMuZ2V0KCdDb2duaXRvRG9tYWluJyl9XCJcbn19O1xuXCJcIlwiXG4gICAgICAgICAgICBzM19jbGllbnQucHV0X29iamVjdChcbiAgICAgICAgICAgICAgICBCdWNrZXQ9cmVzb3VyY2VfcHJvcHMuZ2V0KCdCdWNrZXROYW1lJyksXG4gICAgICAgICAgICAgICAgS2V5PSdhd3MtY29uZmlnLmpzJyxcbiAgICAgICAgICAgICAgICBCb2R5PWNvbmZpZ19jb250ZW50LFxuICAgICAgICAgICAgICAgIENvbnRlbnRUeXBlPSdhcHBsaWNhdGlvbi9qYXZhc2NyaXB0JyxcbiAgICAgICAgICAgICAgICBDYWNoZUNvbnRyb2w9J25vLWNhY2hlJyxcbiAgICAgICAgICAgIClcbiAgICAgICAgICAgIGxvZ2dlci5pbmZvKCdDb25maWcgZmlsZSAlc2Qgc3VjY2Vzc2Z1bGx5JywgcmVxdWVzdF90eXBlLmxvd2VyKCkpXG5cbiAgICAgICAgICAgIGlmIHJlc291cmNlX3Byb3BzLmdldCgnRGlzdHJpYnV0aW9uSWQnKTpcbiAgICAgICAgICAgICAgICBjbG91ZGZyb250X2NsaWVudC5jcmVhdGVfaW52YWxpZGF0aW9uKFxuICAgICAgICAgICAgICAgICAgICBEaXN0cmlidXRpb25JZD1yZXNvdXJjZV9wcm9wcy5nZXQoJ0Rpc3RyaWJ1dGlvbklkJyksXG4gICAgICAgICAgICAgICAgICAgIEludmFsaWRhdGlvbkJhdGNoPXtcbiAgICAgICAgICAgICAgICAgICAgICAgICdDYWxsZXJSZWZlcmVuY2UnOiBzdHIoY29udGV4dC5hd3NfcmVxdWVzdF9pZCksXG4gICAgICAgICAgICAgICAgICAgICAgICAnUGF0aHMnOiB7J1F1YW50aXR5JzogMSwgJ0l0ZW1zJzogWycvYXdzLWNvbmZpZy5qcyddfSxcbiAgICAgICAgICAgICAgICAgICAgfSxcbiAgICAgICAgICAgICAgICApXG4gICAgICAgICAgICAgICAgbG9nZ2VyLmluZm8oJ0Nsb3VkRnJvbnQgaW52YWxpZGF0aW9uIGNyZWF0ZWQnKVxuXG4gICAgICAgICAgICByZXNwb25zZV9kYXRhWydNZXNzYWdlJ10gPSBmJ0NvbmZpZyBmaWxlIHtyZXF1ZXN0X3R5cGUubG93ZXIoKX1kIHN1Y2Nlc3NmdWxseSdcbiAgICAgICAgICAgIGNmbnJlc3BvbnNlLnNlbmQoZXZlbnQsIGNvbnRleHQsIGNmbnJlc3BvbnNlLlNVQ0NFU1MsIHJlc3BvbnNlX2RhdGEsIHBoeXNpY2FsX3Jlc291cmNlX2lkKVxuICAgICAgICBlbHNlOlxuICAgICAgICAgICAgbG9nZ2VyLmVycm9yKCdVbmtub3duIHJlcXVlc3QgdHlwZTogJXMnLCByZXF1ZXN0X3R5cGUpXG4gICAgICAgICAgICByZXNwb25zZV9kYXRhWydFcnJvciddID0gZidVbmtub3duIHJlcXVlc3QgdHlwZToge3JlcXVlc3RfdHlwZX0nXG4gICAgICAgICAgICBjZm5yZXNwb25zZS5zZW5kKGV2ZW50LCBjb250ZXh0LCBjZm5yZXNwb25zZS5GQUlMRUQsIHJlc3BvbnNlX2RhdGEsIHBoeXNpY2FsX3Jlc291cmNlX2lkKVxuXG4gICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOlxuICAgICAgICBsb2dnZXIuZXJyb3IoJ0Vycm9yOiAlcycsIHN0cihlKSlcbiAgICAgICAgcmVzcG9uc2VfZGF0YVsnRXJyb3InXSA9IHN0cihlKVxuICAgICAgICBmYWxsYmFja19pZCA9IGYnQ29uZmlnR2VuZXJhdG9yLXtjb250ZXh0LmF3c19yZXF1ZXN0X2lkWzoxNl19J1xuICAgICAgICBjZm5yZXNwb25zZS5zZW5kKGV2ZW50LCBjb250ZXh0LCBjZm5yZXNwb25zZS5GQUlMRUQsIHJlc3BvbnNlX2RhdGEsIGZhbGxiYWNrX2lkKVxuYCksXG4gICAgICAgIHRpbWVvdXQ6IGNkay5EdXJhdGlvbi5taW51dGVzKDUpLFxuICAgICAgICBkZXNjcmlwdGlvbjogXCJHZW5lcmF0ZXMgYXdzLWNvbmZpZy5qcyBhbmQgd3JpdGVzIGl0IHRvIHRoZSBXZWJVSSBTMyBidWNrZXRcIixcbiAgICAgIH1cbiAgICApO1xuXG4gICAgLy8gR3JhbnQgcGVybWlzc2lvbnMgdG8gQ29uZmlnIEdlbmVyYXRvciBMYW1iZGFcbiAgICB0aGlzLmJ1Y2tldC5ncmFudFdyaXRlKGNvbmZpZ0dlbmVyYXRvckZ1bmN0aW9uKTtcbiAgICBjb25maWdHZW5lcmF0b3JGdW5jdGlvbi5hZGRUb1JvbGVQb2xpY3koXG4gICAgICBuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICAgIGVmZmVjdDogaWFtLkVmZmVjdC5BTExPVyxcbiAgICAgICAgYWN0aW9uczogW1wiY2xvdWRmcm9udDpDcmVhdGVJbnZhbGlkYXRpb25cIl0sXG4gICAgICAgIHJlc291cmNlczogW1xuICAgICAgICAgIGBhcm46YXdzOmNsb3VkZnJvbnQ6OiR7dGhpcy5hY2NvdW50fTpkaXN0cmlidXRpb24vJHt0aGlzLmRpc3RyaWJ1dGlvbi5kaXN0cmlidXRpb25JZH1gLFxuICAgICAgICBdLFxuICAgICAgfSlcbiAgICApO1xuXG4gICAgLy8gQ3VzdG9tIHJlc291cmNlIHRvIHRyaWdnZXIgQ29uZmlnIEdlbmVyYXRvclxuICAgIGNvbnN0IGNvbmZpZ0dlbmVyYXRvclJlc291cmNlID0gbmV3IGNkay5DdXN0b21SZXNvdXJjZShcbiAgICAgIHRoaXMsXG4gICAgICBcIkNvbmZpZ0dlbmVyYXRvclJlc291cmNlXCIsXG4gICAgICB7XG4gICAgICAgIHNlcnZpY2VUb2tlbjogY29uZmlnR2VuZXJhdG9yRnVuY3Rpb24uZnVuY3Rpb25Bcm4sXG4gICAgICAgIHByb3BlcnRpZXM6IHtcbiAgICAgICAgICBCdWNrZXROYW1lOiB0aGlzLmJ1Y2tldC5idWNrZXROYW1lLFxuICAgICAgICAgIERpc3RyaWJ1dGlvbklkOiB0aGlzLmRpc3RyaWJ1dGlvbi5kaXN0cmlidXRpb25JZCxcbiAgICAgICAgICBSZWdpb246IHRoaXMucmVnaW9uLFxuICAgICAgICAgIFVzZXJQb29sSWQ6IHRoaXMudXNlclBvb2wudXNlclBvb2xJZCxcbiAgICAgICAgICBVc2VyUG9vbENsaWVudElkOiB0aGlzLnVzZXJQb29sQ2xpZW50LnVzZXJQb29sQ2xpZW50SWQsXG4gICAgICAgICAgSWRlbnRpdHlQb29sSWQ6IHRoaXMuaWRlbnRpdHlQb29sLnJlZixcbiAgICAgICAgICBBcGlHYXRld2F5VXJsOiBwcm9wcy5hcGlHYXRld2F5VXJsLFxuICAgICAgICAgIENvZ25pdG9Eb21haW46IGAke3VzZXJQb29sRG9tYWluLmRvbWFpbk5hbWV9LmF1dGguJHt0aGlzLnJlZ2lvbn0uYW1hem9uY29nbml0by5jb21gLFxuICAgICAgICAgIFZlcnNpb246IFwiMS4wXCIsXG4gICAgICAgICAgRGVwbG95bWVudFRpbWVzdGFtcDogRGF0ZS5ub3coKS50b1N0cmluZygpLFxuICAgICAgICB9LFxuICAgICAgfVxuICAgICk7XG5cbiAgICAvLyBFbnN1cmUgY29uZmlnIGlzIGdlbmVyYXRlZCBhZnRlciB0aGUgbWFpbiB3ZWIgVUkgZGVwbG95bWVudFxuICAgIGNvbmZpZ0dlbmVyYXRvclJlc291cmNlLm5vZGUuYWRkRGVwZW5kZW5jeSh3ZWJVSURlcGxveW1lbnQpO1xuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIC8vIENsb3VkRm9ybWF0aW9uIE91dHB1dHNcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgXCJDbG91ZEZyb250VXJsXCIsIHtcbiAgICAgIHZhbHVlOiBgaHR0cHM6Ly8ke3RoaXMuZGlzdHJpYnV0aW9uLmRpc3RyaWJ1dGlvbkRvbWFpbk5hbWV9YCxcbiAgICAgIGRlc2NyaXB0aW9uOiBcIkxTUyBXb3Jrc2hvcCBQbGF0Zm9ybSBXZWIgVUkgVVJMXCIsXG4gICAgfSk7XG5cbiAgICBuZXcgY2RrLkNmbk91dHB1dCh0aGlzLCBcIkNvZ25pdG9Vc2VyUG9vbENvbnNvbGVVcmxcIiwge1xuICAgICAgdmFsdWU6IGBodHRwczovLyR7dGhpcy5yZWdpb259LmNvbnNvbGUuYXdzLmFtYXpvbi5jb20vY29nbml0by92Mi9pZHAvdXNlci1wb29scy8ke3RoaXMudXNlclBvb2wudXNlclBvb2xJZH0vdXNlcnM/cmVnaW9uPSR7dGhpcy5yZWdpb259YCxcbiAgICAgIGRlc2NyaXB0aW9uOlxuICAgICAgICBcIkNvZ25pdG8gVXNlciBQb29sIGNvbnNvbGUgVVJMIC0gdXNlIHRoaXMgdG8gYWRkIHVzZXJzIGZvciBXZWIgVUkgbG9naW5cIixcbiAgICB9KTtcblxuICAgIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyBjZGstbmFnIEF3c1NvbHV0aW9ucyBTdXBwcmVzc2lvbnNcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG5cbiAgICAvLyBBdXRoZW50aWNhdGVkIHJvbGUg4oCUIHdpbGRjYXJkIG9uIEFQSSBHYXRld2F5IHBhdGhzL21ldGhvZHNcbiAgICBOYWdTdXBwcmVzc2lvbnMuYWRkUmVzb3VyY2VTdXBwcmVzc2lvbnMoXG4gICAgICBhdXRoZW50aWNhdGVkUm9sZSxcbiAgICAgIFtcbiAgICAgICAge1xuICAgICAgICAgIGlkOiBcIkF3c1NvbHV0aW9ucy1JQU01XCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJXaWxkY2FyZCBwZXJtaXNzaW9uIG5lZWRlZCBmb3IgQVBJIEdhdGV3YXkgcGF0aHMgYW5kIG1ldGhvZHMuIFVzZXJzIG5lZWQgdG8gYWNjZXNzIHZhcmlvdXMgTFNTIFBsYXRmb3JtIEFQSSBlbmRwb2ludHMgKEdFVCwgUE9TVCwgUFVULCBERUxFVEUgb24gL2FnZW50cy8qLCAvY2hhdCkuIFNjb3BlZCB0byB0aGUgc3BlY2lmaWMgQVBJIEdhdGV3YXkgb25seS5cIixcbiAgICAgICAgICBhcHBsaWVzVG86IFtcbiAgICAgICAgICAgIGBSZXNvdXJjZTo6YXJuOmF3czpleGVjdXRlLWFwaToke3RoaXMucmVnaW9ufToke3RoaXMuYWNjb3VudH06JHtwcm9wcy5hcGlHYXRld2F5SWR9LyovKmAsXG4gICAgICAgICAgICB7XG4gICAgICAgICAgICAgIHJlZ2V4OlxuICAgICAgICAgICAgICAgIFwiL1Jlc291cmNlOjphcm46YXdzOmV4ZWN1dGUtYXBpOi4qOi4qOi4qXFxcXC9cXFxcKlxcXFwvXFxcXCovXCIsXG4gICAgICAgICAgICB9LFxuICAgICAgICAgIF0sXG4gICAgICAgIH0sXG4gICAgICBdLFxuICAgICAgdHJ1ZVxuICAgICk7XG5cbiAgICAvLyBDbG91ZEZyb250IGRpc3RyaWJ1dGlvblxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRoaXMuZGlzdHJpYnV0aW9uLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUNGUjFcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIkdlbyByZXN0cmljdGlvbiBub3QgcmVxdWlyZWQgZm9yIHRoaXMgd29ya3Nob3AgYXBwbGljYXRpb24uIFVzZXJzIG1heSBhY2Nlc3MgZnJvbSB2YXJpb3VzIGdsb2JhbCBsb2NhdGlvbnMuXCIsXG4gICAgICAgIH0sXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtQ0ZSMlwiLFxuICAgICAgICAgIHJlYXNvbjpcbiAgICAgICAgICAgIFwiV0FGIG5vdCByZXF1aXJlZCBmb3IgdGhpcyB3b3Jrc2hvcCB3ZWIgVUkgc2VydmluZyBzdGF0aWMgY29udGVudC4gVGhlIGFwcGxpY2F0aW9uIGlzIGJlaGluZCBDb2duaXRvIGF1dGhlbnRpY2F0aW9uLlwiLFxuICAgICAgICB9LFxuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUNGUjRcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIlVzaW5nIGRlZmF1bHQgQ2xvdWRGcm9udCBjZXJ0aWZpY2F0ZSB3aXRoIFRMUyAxLjIgbWluaW11bSBwcm90b2NvbCB2ZXJzaW9uIChUTFNfVjFfMl8yMDIxKS4gQ3VzdG9tIGRvbWFpbiBjYW4gYmUgYWRkZWQgbGF0ZXIgaWYgbmVlZGVkLlwiLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgLy8gV2ViVUkgUzMgYnVja2V0XG4gICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zKFxuICAgICAgdGhpcy5idWNrZXQsXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtUzFcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIkFjY2VzcyBsb2dnaW5nIG5vdCByZXF1aXJlZCBmb3Igc3RhdGljIHdlYnNpdGUgaG9zdGluZyBidWNrZXQuIENsb3VkRnJvbnQgZGlzdHJpYnV0aW9uIGxvZ2dpbmcgaXMgZW5hYmxlZCBpbnN0ZWFkLlwiLFxuICAgICAgICB9LFxuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLVM1XCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJUaGlzIGJ1Y2tldCB1c2VzIFMzQnVja2V0T3JpZ2luLndpdGhPcmlnaW5BY2Nlc3NDb250cm9sKCkgd2hpY2ggYXV0b21hdGljYWxseSBjb25maWd1cmVzIENsb3VkRnJvbnQgT0FDIOKAlCB0aGUgcmVjb21tZW5kZWQgbW9kZXJuIGFwcHJvYWNoLlwiLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgLy8gQ2xvdWRGcm9udCBsb2dzIGJ1Y2tldFxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIGNsb3VkRnJvbnRMb2dzQnVja2V0LFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLVMxXCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJUaGlzIGlzIHRoZSBDbG91ZEZyb250IGFjY2VzcyBsb2dzIGJ1Y2tldCBpdHNlbGYuIEVuYWJsaW5nIGFjY2VzcyBsb2dnaW5nIG9uIGEgbG9ncyBidWNrZXQgd291bGQgY3JlYXRlIGNpcmN1bGFyIGRlcGVuZGVuY3kuXCIsXG4gICAgICAgIH0sXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtUzJcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIkNsb3VkRnJvbnQgbG9ncyBidWNrZXQgcmVxdWlyZXMgc3BlY2lmaWMgQUNMIHBlcm1pc3Npb25zIGZvciBDbG91ZEZyb250IHNlcnZpY2UgdG8gd3JpdGUgbG9ncy4gTm90IHB1YmxpY2x5IGFjY2Vzc2libGUuXCIsXG4gICAgICAgIH0sXG4gICAgICBdLFxuICAgICAgdHJ1ZVxuICAgICk7XG5cbiAgICAvLyBDb2duaXRvIFVzZXIgUG9vbFxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9ucyhcbiAgICAgIHRoaXMudXNlclBvb2wsXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtQ09HMlwiLFxuICAgICAgICAgIHJlYXNvbjpcbiAgICAgICAgICAgIFwiTUZBIG5vdCBlbmZvcmNlZCBmb3IgdGhpcyB3b3Jrc2hvcCBhcHBsaWNhdGlvbi4gVXNlcnMgYXJlIHByZS1jcmVhdGVkIGJ5IHRoZSBpbnN0cnVjdG9yIGFuZCBhZGRpdGlvbmFsIE1GQSB3b3VsZCBjcmVhdGUgZnJpY3Rpb24gaW4gYSB0aW1lLWxpbWl0ZWQgd29ya3Nob3AuXCIsXG4gICAgICAgIH0sXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtQ09HM1wiLFxuICAgICAgICAgIHJlYXNvbjpcbiAgICAgICAgICAgIFwiQWR2YW5jZWQgU2VjdXJpdHkgTW9kZSByZXF1aXJlcyBDb2duaXRvIFBsdXMgZmVhdHVyZSBwbGFuIHdpdGggYWRkaXRpb25hbCBjb3N0cy4gU3RhbmRhcmQgc2VjdXJpdHkgZmVhdHVyZXMgYXJlIGFkZXF1YXRlIGZvciB0aGlzIHdvcmtzaG9wLlwiLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgLy8gQ29uZmlnIEdlbmVyYXRvciBMYW1iZGFcbiAgICBOYWdTdXBwcmVzc2lvbnMuYWRkUmVzb3VyY2VTdXBwcmVzc2lvbnMoXG4gICAgICBjb25maWdHZW5lcmF0b3JGdW5jdGlvbixcbiAgICAgIFtcbiAgICAgICAge1xuICAgICAgICAgIGlkOiBcIkF3c1NvbHV0aW9ucy1JQU00XCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJMYW1iZGEgZXhlY3V0aW9uIHJvbGUgdXNlcyBBV1MgbWFuYWdlZCBwb2xpY3kgZm9yIGJhc2ljIGV4ZWN1dGlvbiBwZXJtaXNzaW9ucy5cIixcbiAgICAgICAgICBhcHBsaWVzVG86IFtcbiAgICAgICAgICAgIFwiUG9saWN5Ojphcm46PEFXUzo6UGFydGl0aW9uPjppYW06OmF3czpwb2xpY3kvc2VydmljZS1yb2xlL0FXU0xhbWJkYUJhc2ljRXhlY3V0aW9uUm9sZVwiLFxuICAgICAgICAgIF0sXG4gICAgICAgIH0sXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtTDFcIixcbiAgICAgICAgICByZWFzb246XG4gICAgICAgICAgICBcIlVzaW5nIFB5dGhvbiAzLjEzIHJ1bnRpbWUgd2hpY2ggaXMgdGhlIGxhdGVzdCBzdGFibGUgdmVyc2lvbiBzdXBwb3J0ZWQgYnkgQVdTIExhbWJkYS5cIixcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgICB0cnVlXG4gICAgKTtcblxuICAgIC8vIENvbmZpZyBHZW5lcmF0b3IgTGFtYmRhIFMzIHdyaXRlIHBvbGljeVxuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9uc0J5UGF0aChcbiAgICAgIHRoaXMsXG4gICAgICBgLyR7aWR9L0NvbmZpZ0dlbmVyYXRvci9TZXJ2aWNlUm9sZS9EZWZhdWx0UG9saWN5L1Jlc291cmNlYCxcbiAgICAgIFtcbiAgICAgICAge1xuICAgICAgICAgIGlkOiBcIkF3c1NvbHV0aW9ucy1JQU01XCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJMYW1iZGEgZnVuY3Rpb24gbmVlZHMgUzMgd3JpdGUgcGVybWlzc2lvbnMgdG8gdXBsb2FkIHRoZSBjb25maWcgZmlsZS4gUGVybWlzc2lvbnMgYXJlIHNjb3BlZCB0byB0aGUgc3BlY2lmaWMgUzMgYnVja2V0LlwiLFxuICAgICAgICAgIGFwcGxpZXNUbzogW1xuICAgICAgICAgICAgXCJBY3Rpb246OnMzOkFib3J0KlwiLFxuICAgICAgICAgICAgXCJBY3Rpb246OnMzOkRlbGV0ZU9iamVjdCpcIixcbiAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgcmVnZXg6IFwiL1Jlc291cmNlOjouKldlYlVJQnVja2V0LiouQXJuLipcXFxcL1xcXFwqL1wiLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICBdLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgLy8gQ0RLIEJ1Y2tldERlcGxveW1lbnQgY3VzdG9tIHJlc291cmNlIHN1cHByZXNzaW9uc1xuICAgIE5hZ1N1cHByZXNzaW9ucy5hZGRSZXNvdXJjZVN1cHByZXNzaW9uc0J5UGF0aChcbiAgICAgIHRoaXMsXG4gICAgICBgLyR7aWR9L0N1c3RvbTo6Q0RLQnVja2V0RGVwbG95bWVudDg2OTNCQjY0OTY4OTQ0QjY5QUFGQjBDQzlFQjg3NTZDL1NlcnZpY2VSb2xlL1Jlc291cmNlYCxcbiAgICAgIFtcbiAgICAgICAge1xuICAgICAgICAgIGlkOiBcIkF3c1NvbHV0aW9ucy1JQU00XCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJBV1MgbWFuYWdlZCBwb2xpY3kgQVdTTGFtYmRhQmFzaWNFeGVjdXRpb25Sb2xlIGlzIHJlcXVpcmVkIGZvciBDREsgQnVja2V0RGVwbG95bWVudCBjdXN0b20gcmVzb3VyY2UuXCIsXG4gICAgICAgICAgYXBwbGllc1RvOiBbXG4gICAgICAgICAgICBcIlBvbGljeTo6YXJuOjxBV1M6OlBhcnRpdGlvbj46aWFtOjphd3M6cG9saWN5L3NlcnZpY2Utcm9sZS9BV1NMYW1iZGFCYXNpY0V4ZWN1dGlvblJvbGVcIixcbiAgICAgICAgICBdLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zQnlQYXRoKFxuICAgICAgdGhpcyxcbiAgICAgIGAvJHtpZH0vQ3VzdG9tOjpDREtCdWNrZXREZXBsb3ltZW50ODY5M0JCNjQ5Njg5NDRCNjlBQUZCMENDOUVCODc1NkMvU2VydmljZVJvbGUvRGVmYXVsdFBvbGljeS9SZXNvdXJjZWAsXG4gICAgICBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogXCJBd3NTb2x1dGlvbnMtSUFNNVwiLFxuICAgICAgICAgIHJlYXNvbjpcbiAgICAgICAgICAgIFwiV2lsZGNhcmQgcGVybWlzc2lvbnMgcmVxdWlyZWQgZm9yIENESyBCdWNrZXREZXBsb3ltZW50IGN1c3RvbSByZXNvdXJjZSB0byBtYW5hZ2UgUzMgb2JqZWN0cyBhbmQgQ2xvdWRGcm9udCBpbnZhbGlkYXRpb24uXCIsXG4gICAgICAgICAgYXBwbGllc1RvOiBbXG4gICAgICAgICAgICBcIkFjdGlvbjo6czM6R2V0QnVja2V0KlwiLFxuICAgICAgICAgICAgXCJBY3Rpb246OnMzOkdldE9iamVjdCpcIixcbiAgICAgICAgICAgIFwiQWN0aW9uOjpzMzpMaXN0KlwiLFxuICAgICAgICAgICAgXCJBY3Rpb246OnMzOkFib3J0KlwiLFxuICAgICAgICAgICAgXCJBY3Rpb246OnMzOkRlbGV0ZU9iamVjdCpcIixcbiAgICAgICAgICAgIFwiUmVzb3VyY2U6OipcIixcbiAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgcmVnZXg6IFwiL1Jlc291cmNlOjphcm46Lio6czM6OjpjZGstLiotYXNzZXRzLS4qL1wiLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICAgIHtcbiAgICAgICAgICAgICAgcmVnZXg6IFwiL1Jlc291cmNlOjouKldlYlVJQnVja2V0LiouQXJuLipcXFxcL1xcXFwqL1wiLFxuICAgICAgICAgICAgfSxcbiAgICAgICAgICBdLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICAgIHRydWVcbiAgICApO1xuXG4gICAgTmFnU3VwcHJlc3Npb25zLmFkZFJlc291cmNlU3VwcHJlc3Npb25zQnlQYXRoKFxuICAgICAgdGhpcyxcbiAgICAgIGAvJHtpZH0vQ3VzdG9tOjpDREtCdWNrZXREZXBsb3ltZW50ODY5M0JCNjQ5Njg5NDRCNjlBQUZCMENDOUVCODc1NkMvUmVzb3VyY2VgLFxuICAgICAgW1xuICAgICAgICB7XG4gICAgICAgICAgaWQ6IFwiQXdzU29sdXRpb25zLUwxXCIsXG4gICAgICAgICAgcmVhc29uOlxuICAgICAgICAgICAgXCJDREsgQnVja2V0RGVwbG95bWVudCBjdXN0b20gcmVzb3VyY2UgdXNlcyB0aGUgbGF0ZXN0IGF2YWlsYWJsZSBydW50aW1lIG1hbmFnZWQgYnkgQ0RLLiBSdW50aW1lIHZlcnNpb24gaXMgY29udHJvbGxlZCBieSB0aGUgQ0RLIGZyYW1ld29yay5cIixcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgICB0cnVlXG4gICAgKTtcbiAgfVxufVxuIl19