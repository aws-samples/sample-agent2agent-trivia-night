#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { AwsSolutionsChecks } from "cdk-nag";
import { ApiStack } from "../lib/api-stack";
import { WebUiStack } from "../lib/webui-stack";

const app = new cdk.App();

// Use the account/region from CDK CLI context (respects --profile and --region flags)
// CDK_DEFAULT_REGION is set by the CDK CLI from the credential chain.
// DEPLOY_REGION is our explicit override from deploy.sh for deterministic targeting.
const env: cdk.Environment = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.DEPLOY_REGION || process.env.CDK_DEFAULT_REGION,
};

// Region suffix for stack names — makes multi-region deployments possible
// (CloudFront OAC names are derived from construct paths and are global)
const regionSuffix = env.region ? `-${env.region}` : "";
const apiStackName = `ApiStack${regionSuffix}`;
const webUiStackName = `WebUiStack${regionSuffix}`;

// Instantiate ApiStack — deploys API Gateway, Lambda, S3 Vectors, Bedrock permissions
// StackPrefix CfnParameter (default: "Workshop") is defined inside ApiStack
const apiStack = new ApiStack(app, apiStackName, { env });

// Instantiate WebUiStack — deploys S3, CloudFront, Cognito, Config Generator
// Pass API Gateway URL and ID from ApiStack for cross-stack wiring
const webUiStack = new WebUiStack(app, webUiStackName, {
  env,
  apiGatewayUrl: apiStack.api.url,
  apiGatewayId: apiStack.api.restApiId,
  stackPrefix: apiStack.stackPrefix,
});

// WebUiStack depends on ApiStack outputs
webUiStack.addDependency(apiStack);

// Add cdk-nag AWS Solutions checks to validate security best practices
cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));
