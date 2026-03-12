import * as cdk from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { AwsSolutionsChecks } from "cdk-nag";
import { Annotations, Match } from "aws-cdk-lib/assertions";
import { ApiStack } from "../lib/api-stack";
import { WebUiStack } from "../lib/webui-stack";
import * as fs from "fs";
import * as path from "path";

/**
 * CDK snapshot and cdk-nag compliance tests for ApiStack and WebUiStack.
 *
 * Validates: Requirements 9.7, 10.8
 */

// Ensure the web-ui/build directory exists for WebUiStack synthesis
// (BucketDeployment requires the asset path to exist)
const webUiBuildDir = path.resolve(__dirname, "../../web-ui/build");
beforeAll(() => {
  if (!fs.existsSync(webUiBuildDir)) {
    fs.mkdirSync(webUiBuildDir, { recursive: true });
    // Create a minimal index.html so the asset is non-empty
    fs.writeFileSync(
      path.join(webUiBuildDir, "index.html"),
      "<html><body>placeholder</body></html>"
    );
  }
});

/**
 * Helper: create a fresh CDK app with both stacks wired together,
 * mirroring bin/app.ts.
 */
function createStacks(enableNag = false) {
  const app = new cdk.App();

  if (enableNag) {
    cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: true }));
  }

  const apiStack = new ApiStack(app, "TestApiStack");

  const webUiStack = new WebUiStack(app, "TestWebUiStack", {
    apiGatewayUrl: apiStack.api.url,
    apiGatewayId: apiStack.api.restApiId,
    stackPrefix: apiStack.stackPrefix,
  });

  webUiStack.addDependency(apiStack);

  return { app, apiStack, webUiStack };
}

// ---------------------------------------------------------------------------
// Snapshot Tests
// ---------------------------------------------------------------------------
describe("Snapshot tests", () => {
  test("ApiStack matches snapshot", () => {
    const { apiStack } = createStacks();
    const template = Template.fromStack(apiStack);
    expect(template.toJSON()).toMatchSnapshot();
  });

  test("WebUiStack matches snapshot", () => {
    const { webUiStack } = createStacks();
    const template = Template.fromStack(webUiStack);
    expect(template.toJSON()).toMatchSnapshot();
  });
});

// ---------------------------------------------------------------------------
// cdk-nag AwsSolutions Compliance Tests
// ---------------------------------------------------------------------------
describe("cdk-nag AwsSolutions compliance", () => {
  let apiStack: ApiStack;
  let webUiStack: WebUiStack;

  beforeAll(() => {
    const stacks = createStacks(true);
    apiStack = stacks.apiStack;
    webUiStack = stacks.webUiStack;

    // Force synthesis so cdk-nag aspects run
    stacks.app.synth();
  });

  test("ApiStack has no unsuppressed cdk-nag errors", () => {
    const errors = Annotations.fromStack(apiStack).findError(
      "*",
      Match.stringLikeRegexp("AwsSolutions-.*")
    );
    expect(errors).toHaveLength(0);
  });

  test("ApiStack has no unsuppressed cdk-nag warnings", () => {
    const warnings = Annotations.fromStack(apiStack).findWarning(
      "*",
      Match.stringLikeRegexp("AwsSolutions-.*")
    );
    expect(warnings).toHaveLength(0);
  });

  test("WebUiStack has no unsuppressed cdk-nag errors", () => {
    const errors = Annotations.fromStack(webUiStack).findError(
      "*",
      Match.stringLikeRegexp("AwsSolutions-.*")
    );
    expect(errors).toHaveLength(0);
  });

  test("WebUiStack has no unsuppressed cdk-nag warnings", () => {
    const warnings = Annotations.fromStack(webUiStack).findWarning(
      "*",
      Match.stringLikeRegexp("AwsSolutions-.*")
    );
    expect(warnings).toHaveLength(0);
  });
});
