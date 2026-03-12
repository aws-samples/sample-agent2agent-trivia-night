import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { NagSuppressions } from "cdk-nag";

export interface WebUiStackProps extends cdk.StackProps {
  /** API Gateway URL from ApiStack */
  apiGatewayUrl: string;
  /** API Gateway REST API ID from ApiStack */
  apiGatewayId: string;
  /** StackPrefix CfnParameter for cross-stack naming with existing workshop templates */
  stackPrefix: cdk.CfnParameter;
}

export class WebUiStack extends cdk.Stack {
  public readonly bucket: s3.Bucket;
  public readonly distribution: cloudfront.Distribution;
  public readonly userPool: cognito.UserPool;
  public readonly userPoolClient: cognito.UserPoolClient;
  public readonly identityPool: cognito.CfnIdentityPool;

  constructor(scope: Construct, id: string, props: WebUiStackProps) {
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
      assumedBy: new iam.FederatedPrincipal(
        "cognito-identity.amazonaws.com",
        {
          StringEquals: {
            "cognito-identity.amazonaws.com:aud": this.identityPool.ref,
          },
          "ForAnyValue:StringLike": {
            "cognito-identity.amazonaws.com:amr": "authenticated",
          },
        },
        "sts:AssumeRoleWithWebIdentity"
      ),
      description:
        "IAM role for authenticated Cognito users - LSS Platform API access only",
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
    new cognito.CfnIdentityPoolRoleAttachment(
      this,
      "IdentityPoolRoleAttachment",
      {
        identityPoolId: this.identityPool.ref,
        roles: {
          authenticated: authenticatedRole.roleArn,
        },
      }
    );

    // -------------------------------------------------------------------------
    // S3 Bucket Deployment — deploy React app build output
    // -------------------------------------------------------------------------
    const webUIDeployment = new s3deploy.BucketDeployment(
      this,
      "WebUIDeployment",
      {
        sources: [s3deploy.Source.asset("../web-ui/build")],
        destinationBucket: this.bucket,
        distribution: this.distribution,
        distributionPaths: ["/*"],
        prune: true,
      }
    );

    // -------------------------------------------------------------------------
    // Config Generator Lambda — writes aws-config.js to S3
    // -------------------------------------------------------------------------
    const configGeneratorFunction = new lambda.Function(
      this,
      "ConfigGenerator",
      {
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
      }
    );

    // Grant permissions to Config Generator Lambda
    this.bucket.grantWrite(configGeneratorFunction);
    configGeneratorFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["cloudfront:CreateInvalidation"],
        resources: [
          `arn:aws:cloudfront::${this.account}:distribution/${this.distribution.distributionId}`,
        ],
      })
    );

    // Custom resource to trigger Config Generator
    const configGeneratorResource = new cdk.CustomResource(
      this,
      "ConfigGeneratorResource",
      {
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
      }
    );

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
      description:
        "Cognito User Pool console URL - use this to add users for Web UI login",
    });

    new cdk.CfnOutput(this, "CognitoUserPoolId", {
      value: this.userPool.userPoolId,
      description: "Cognito User Pool ID",
    });

    // -------------------------------------------------------------------------
    // cdk-nag AwsSolutions Suppressions
    // -------------------------------------------------------------------------

    // Authenticated role — wildcard on API Gateway paths/methods
    NagSuppressions.addResourceSuppressions(
      authenticatedRole,
      [
        {
          id: "AwsSolutions-IAM5",
          reason:
            "Wildcard permission needed for API Gateway paths and methods. Users need to access various LSS Platform API endpoints (GET, POST, PUT, DELETE on /agents/*, /chat). Scoped to the specific API Gateway only.",
          appliesTo: [
            `Resource::arn:aws:execute-api:${this.region}:${this.account}:${props.apiGatewayId}/*/*`,
            {
              regex:
                "/Resource::arn:aws:execute-api:.*:.*:.*\\/\\*\\/\\*/",
            },
          ],
        },
      ],
      true
    );

    // CloudFront distribution
    NagSuppressions.addResourceSuppressions(
      this.distribution,
      [
        {
          id: "AwsSolutions-CFR1",
          reason:
            "Geo restriction not required for this workshop application. Users may access from various global locations.",
        },
        {
          id: "AwsSolutions-CFR2",
          reason:
            "WAF not required for this workshop web UI serving static content. The application is behind Cognito authentication.",
        },
        {
          id: "AwsSolutions-CFR4",
          reason:
            "Using default CloudFront certificate with TLS 1.2 minimum protocol version (TLS_V1_2_2021). Custom domain can be added later if needed.",
        },
      ],
      true
    );

    // WebUI S3 bucket
    NagSuppressions.addResourceSuppressions(
      this.bucket,
      [
        {
          id: "AwsSolutions-S1",
          reason:
            "Access logging not required for static website hosting bucket. CloudFront distribution logging is enabled instead.",
        },
        {
          id: "AwsSolutions-S5",
          reason:
            "This bucket uses S3BucketOrigin.withOriginAccessControl() which automatically configures CloudFront OAC — the recommended modern approach.",
        },
      ],
      true
    );

    // CloudFront logs bucket
    NagSuppressions.addResourceSuppressions(
      cloudFrontLogsBucket,
      [
        {
          id: "AwsSolutions-S1",
          reason:
            "This is the CloudFront access logs bucket itself. Enabling access logging on a logs bucket would create circular dependency.",
        },
        {
          id: "AwsSolutions-S2",
          reason:
            "CloudFront logs bucket requires specific ACL permissions for CloudFront service to write logs. Not publicly accessible.",
        },
      ],
      true
    );

    // Cognito User Pool
    NagSuppressions.addResourceSuppressions(
      this.userPool,
      [
        {
          id: "AwsSolutions-COG2",
          reason:
            "MFA not enforced for this workshop application. Users are pre-created by the instructor and additional MFA would create friction in a time-limited workshop.",
        },
        {
          id: "AwsSolutions-COG3",
          reason:
            "Advanced Security Mode requires Cognito Plus feature plan with additional costs. Standard security features are adequate for this workshop.",
        },
      ],
      true
    );

    // Config Generator Lambda
    NagSuppressions.addResourceSuppressions(
      configGeneratorFunction,
      [
        {
          id: "AwsSolutions-IAM4",
          reason:
            "Lambda execution role uses AWS managed policy for basic execution permissions.",
          appliesTo: [
            "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
          ],
        },
        {
          id: "AwsSolutions-L1",
          reason:
            "Using Python 3.13 runtime which is the latest stable version supported by AWS Lambda.",
        },
      ],
      true
    );

    // Config Generator Lambda S3 write policy
    NagSuppressions.addResourceSuppressionsByPath(
      this,
      `/${id}/ConfigGenerator/ServiceRole/DefaultPolicy/Resource`,
      [
        {
          id: "AwsSolutions-IAM5",
          reason:
            "Lambda function needs S3 write permissions to upload the config file. Permissions are scoped to the specific S3 bucket.",
          appliesTo: [
            "Action::s3:Abort*",
            "Action::s3:DeleteObject*",
            {
              regex: "/Resource::.*WebUIBucket.*.Arn.*\\/\\*/",
            },
          ],
        },
      ],
      true
    );

    // CDK BucketDeployment custom resource suppressions
    NagSuppressions.addResourceSuppressionsByPath(
      this,
      `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/ServiceRole/Resource`,
      [
        {
          id: "AwsSolutions-IAM4",
          reason:
            "AWS managed policy AWSLambdaBasicExecutionRole is required for CDK BucketDeployment custom resource.",
          appliesTo: [
            "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
          ],
        },
      ],
      true
    );

    NagSuppressions.addResourceSuppressionsByPath(
      this,
      `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/ServiceRole/DefaultPolicy/Resource`,
      [
        {
          id: "AwsSolutions-IAM5",
          reason:
            "Wildcard permissions required for CDK BucketDeployment custom resource to manage S3 objects and CloudFront invalidation.",
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
      ],
      true
    );

    NagSuppressions.addResourceSuppressionsByPath(
      this,
      `/${id}/Custom::CDKBucketDeployment8693BB64968944B69AAFB0CC9EB8756C/Resource`,
      [
        {
          id: "AwsSolutions-L1",
          reason:
            "CDK BucketDeployment custom resource uses the latest available runtime managed by CDK. Runtime version is controlled by the CDK framework.",
        },
      ],
      true
    );
  }
}
