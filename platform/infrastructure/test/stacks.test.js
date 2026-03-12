"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const cdk = require("aws-cdk-lib");
const assertions_1 = require("aws-cdk-lib/assertions");
const cdk_nag_1 = require("cdk-nag");
const assertions_2 = require("aws-cdk-lib/assertions");
const api_stack_1 = require("../lib/api-stack");
const webui_stack_1 = require("../lib/webui-stack");
const fs = require("fs");
const path = require("path");
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
        fs.writeFileSync(path.join(webUiBuildDir, "index.html"), "<html><body>placeholder</body></html>");
    }
});
/**
 * Helper: create a fresh CDK app with both stacks wired together,
 * mirroring bin/app.ts.
 */
function createStacks(enableNag = false) {
    const app = new cdk.App();
    if (enableNag) {
        cdk.Aspects.of(app).add(new cdk_nag_1.AwsSolutionsChecks({ verbose: true }));
    }
    const apiStack = new api_stack_1.ApiStack(app, "TestApiStack");
    const webUiStack = new webui_stack_1.WebUiStack(app, "TestWebUiStack", {
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
        const template = assertions_1.Template.fromStack(apiStack);
        expect(template.toJSON()).toMatchSnapshot();
    });
    test("WebUiStack matches snapshot", () => {
        const { webUiStack } = createStacks();
        const template = assertions_1.Template.fromStack(webUiStack);
        expect(template.toJSON()).toMatchSnapshot();
    });
});
// ---------------------------------------------------------------------------
// cdk-nag AwsSolutions Compliance Tests
// ---------------------------------------------------------------------------
describe("cdk-nag AwsSolutions compliance", () => {
    let apiStack;
    let webUiStack;
    beforeAll(() => {
        const stacks = createStacks(true);
        apiStack = stacks.apiStack;
        webUiStack = stacks.webUiStack;
        // Force synthesis so cdk-nag aspects run
        stacks.app.synth();
    });
    test("ApiStack has no unsuppressed cdk-nag errors", () => {
        const errors = assertions_2.Annotations.fromStack(apiStack).findError("*", assertions_2.Match.stringLikeRegexp("AwsSolutions-.*"));
        expect(errors).toHaveLength(0);
    });
    test("ApiStack has no unsuppressed cdk-nag warnings", () => {
        const warnings = assertions_2.Annotations.fromStack(apiStack).findWarning("*", assertions_2.Match.stringLikeRegexp("AwsSolutions-.*"));
        expect(warnings).toHaveLength(0);
    });
    test("WebUiStack has no unsuppressed cdk-nag errors", () => {
        const errors = assertions_2.Annotations.fromStack(webUiStack).findError("*", assertions_2.Match.stringLikeRegexp("AwsSolutions-.*"));
        expect(errors).toHaveLength(0);
    });
    test("WebUiStack has no unsuppressed cdk-nag warnings", () => {
        const warnings = assertions_2.Annotations.fromStack(webUiStack).findWarning("*", assertions_2.Match.stringLikeRegexp("AwsSolutions-.*"));
        expect(warnings).toHaveLength(0);
    });
});
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoic3RhY2tzLnRlc3QuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyJzdGFja3MudGVzdC50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiOztBQUFBLG1DQUFtQztBQUNuQyx1REFBa0Q7QUFDbEQscUNBQTZDO0FBQzdDLHVEQUE0RDtBQUM1RCxnREFBNEM7QUFDNUMsb0RBQWdEO0FBQ2hELHlCQUF5QjtBQUN6Qiw2QkFBNkI7QUFFN0I7Ozs7R0FJRztBQUVILG9FQUFvRTtBQUNwRSxzREFBc0Q7QUFDdEQsTUFBTSxhQUFhLEdBQUcsSUFBSSxDQUFDLE9BQU8sQ0FBQyxTQUFTLEVBQUUsb0JBQW9CLENBQUMsQ0FBQztBQUNwRSxTQUFTLENBQUMsR0FBRyxFQUFFO0lBQ2IsSUFBSSxDQUFDLEVBQUUsQ0FBQyxVQUFVLENBQUMsYUFBYSxDQUFDLEVBQUUsQ0FBQztRQUNsQyxFQUFFLENBQUMsU0FBUyxDQUFDLGFBQWEsRUFBRSxFQUFFLFNBQVMsRUFBRSxJQUFJLEVBQUUsQ0FBQyxDQUFDO1FBQ2pELHdEQUF3RDtRQUN4RCxFQUFFLENBQUMsYUFBYSxDQUNkLElBQUksQ0FBQyxJQUFJLENBQUMsYUFBYSxFQUFFLFlBQVksQ0FBQyxFQUN0Qyx1Q0FBdUMsQ0FDeEMsQ0FBQztJQUNKLENBQUM7QUFDSCxDQUFDLENBQUMsQ0FBQztBQUVIOzs7R0FHRztBQUNILFNBQVMsWUFBWSxDQUFDLFNBQVMsR0FBRyxLQUFLO0lBQ3JDLE1BQU0sR0FBRyxHQUFHLElBQUksR0FBRyxDQUFDLEdBQUcsRUFBRSxDQUFDO0lBRTFCLElBQUksU0FBUyxFQUFFLENBQUM7UUFDZCxHQUFHLENBQUMsT0FBTyxDQUFDLEVBQUUsQ0FBQyxHQUFHLENBQUMsQ0FBQyxHQUFHLENBQUMsSUFBSSw0QkFBa0IsQ0FBQyxFQUFFLE9BQU8sRUFBRSxJQUFJLEVBQUUsQ0FBQyxDQUFDLENBQUM7SUFDckUsQ0FBQztJQUVELE1BQU0sUUFBUSxHQUFHLElBQUksb0JBQVEsQ0FBQyxHQUFHLEVBQUUs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aUIsQ0FBQyxDQUMxQyxDQUFDO1FBQ0YsTUFBTSxDQUFDLE1BQU0sQ0FBQyxDQUFDLFlBQVksQ0FBQyxDQUFDLENBQUMsQ0FBQztJQUNqQyxDQUFDLENBQUMsQ0FBQztJQUVILElBQUksQ0FBQyxpREFBaUQsRUFBRSxHQUFHLEVBQUU7UUFDM0QsTUFBTSxRQUFRLEdBQUcsd0JBQVcsQ0FBQyxTQUFTLENBQUMsVUFBVSxDQUFDLENBQUMsV0FBVyxDQUM1RCxHQUFHLEVBQ0gsa0JBQUssQ0FBQyxnQkFBZ0IsQ0FBQyxpQkFBaUIsQ0FBQyxDQUMxQyxDQUFDO1FBQ0YsTUFBTSxDQUFDLFFBQVEsQ0FBQyxDQUFDLFlBQVksQ0FBQyxDQUFDLENBQUMsQ0FBQztJQUNuQyxDQUFDLENBQUMsQ0FBQztBQUNMLENBQUMsQ0FBQyxDQUFDIiwic291cmNlc0NvbnRlbnQiOlsiaW1wb3J0ICogYXMgY2RrIGZyb20gXCJhd3MtY2RrLWxpYlwiO1xuaW1wb3J0IHsgVGVtcGxhdGUgfSBmcm9tIFwiYXdzLWNkay1saWIvYXNzZXJ0aW9uc1wiO1xuaW1wb3J0IHsgQXdzU29sdXRpb25zQ2hlY2tzIH0gZnJvbSBcImNkay1uYWdcIjtcbmltcG9ydCB7IEFubm90YXRpb25zLCBNYXRjaCB9IGZyb20gXCJhd3MtY2RrLWxpYi9hc3NlcnRpb25zXCI7XG5pbXBvcnQgeyBBcGlTdGFjayB9IGZyb20gXCIuLi9saWIvYXBpLXN0YWNrXCI7XG5pbXBvcnQgeyBXZWJVaVN0YWNrIH0gZnJvbSBcIi4uL2xpYi93ZWJ1aS1zdGFja1wiO1xuaW1wb3J0ICogYXMgZnMgZnJvbSBcImZzXCI7XG5pbXBvcnQgKiBhcyBwYXRoIGZyb20gXCJwYXRoXCI7XG5cbi8qKlxuICogQ0RLIHNuYXBzaG90IGFuZCBjZGstbmFnIGNvbXBsaWFuY2UgdGVzdHMgZm9yIEFwaVN0YWNrIGFuZCBXZWJVaVN0YWNrLlxuICpcbiAqIFZhbGlkYXRlczogUmVxdWlyZW1lbnRzIDkuNywgMTAuOFxuICovXG5cbi8vIEVuc3VyZSB0aGUgd2ViLXVpL2J1aWxkIGRpcmVjdG9yeSBleGlzdHMgZm9yIFdlYlVpU3RhY2sgc3ludGhlc2lzXG4vLyAoQnVja2V0RGVwbG95bWVudCByZXF1aXJlcyB0aGUgYXNzZXQgcGF0aCB0byBleGlzdClcbmNvbnN0IHdlYlVpQnVpbGREaXIgPSBwYXRoLnJlc29sdmUoX19kaXJuYW1lLCBcIi4uLy4uL3dlYi11aS9idWlsZFwiKTtcbmJlZm9yZUFsbCgoKSA9PiB7XG4gIGlmICghZnMuZXhpc3RzU3luYyh3ZWJVaUJ1aWxkRGlyKSkge1xuICAgIGZzLm1rZGlyU3luYyh3ZWJVaUJ1aWxkRGlyLCB7IHJlY3Vyc2l2ZTogdHJ1ZSB9KTtcbiAgICAvLyBDcmVhdGUgYSBtaW5pbWFsIGluZGV4Lmh0bWwgc28gdGhlIGFzc2V0IGlzIG5vbi1lbXB0eVxuICAgIGZzLndyaXRlRmlsZVN5bmMoXG4gICAgICBwYXRoLmpvaW4od2ViVWlCdWlsZERpciwgXCJpbmRleC5odG1sXCIpLFxuICAgICAgXCI8aHRtbD48Ym9keT5wbGFjZWhvbGRlcjwvYm9keT48L2h0bWw+XCJcbiAgICApO1xuICB9XG59KTtcblxuLyoqXG4gKiBIZWxwZXI6IGNyZWF0ZSBhIGZyZXNoIENESyBhcHAgd2l0aCBib3RoIHN0YWNrcyB3aXJlZCB0b2dldGhlcixcbiAqIG1pcnJvcmluZyBiaW4vYXBwLnRzLlxuICovXG5mdW5jdGlvbiBjcmVhdGVTdGFja3MoZW5hYmxlTmFnID0gZmFsc2UpIHtcbiAgY29uc3QgYXBwID0gbmV3IGNkay5BcHAoKTtcblxuICBpZiAoZW5hYmxlTmFnKSB7XG4gICAgY2RrLkFzcGVjdHMub2YoYXBwKS5hZGQobmV3IEF3c1NvbHV0aW9uc0NoZWNrcyh7IHZlcmJvc2U6IHRydWUgfSkpO1xuICB9XG5cbiAgY29uc3QgYXBpU3RhY2sgPSBuZXcgQXBpU3RhY2soYXBwLCBcIlRlc3RBcGlTdGFja1wiKTtcblxuICBjb25zdCB3ZWJVaVN0YWNrID0gbmV3IFdlYlVpU3RhY2soYXBwLCBcIlRlc3RXZWJVaVN0YWNrXCIsIHtcbiAgICBhcGlHYXRld2F5VXJsOiBhcGlTdGFjay5hcGkudXJsLFxuICAgIGFwaUdhdGV3YXlJZDogYXBpU3RhY2suYXBpLnJlc3RBcGlJZCxcbiAgICBzdGFja1ByZWZpeDogYXBpU3RhY2suc3RhY2tQcmVmaXgsXG4gIH0pO1xuXG4gIHdlYlVpU3RhY2suYWRkRGVwZW5kZW5jeShhcGlTdGFjayk7XG5cbiAgcmV0dXJuIHsgYXBwLCBhcGlTdGFjaywgd2ViVWlTdGFjayB9O1xufVxuXG4vLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbi8vIFNuYXBzaG90IFRlc3RzXG4vLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbmRlc2NyaWJlKFwiU25hcHNob3QgdGVzdHNcIiwgKCkgPT4ge1xuICB0ZXN0KFwiQXBpU3RhY2sgbWF0Y2hlcyBzbmFwc2hvdFwiLCAoKSA9PiB7XG4gICAgY29uc3QgeyBhcGlTdGFjayB9ID0gY3JlYXRlU3RhY2tzKCk7XG4gICAgY29uc3QgdGVtcGxhdGUgPSBUZW1wbGF0ZS5mcm9tU3RhY2soYXBpU3RhY2spO1xuICAgIGV4cGVjdCh0ZW1wbGF0ZS50b0pTT04oKSkudG9NYXRjaFNuYXBzaG90KCk7XG4gIH0pO1xuXG4gIHRlc3QoXCJXZWJVaVN0YWNrIG1hdGNoZXMgc25hcHNob3RcIiwgKCkgPT4ge1xuICAgIGNvbnN0IHsgd2ViVWlTdGFjayB9ID0gY3JlYXRlU3RhY2tzKCk7XG4gICAgY29uc3QgdGVtcGxhdGUgPSBUZW1wbGF0ZS5mcm9tU3RhY2sod2ViVWlTdGFjayk7XG4gICAgZXhwZWN0KHRlbXBsYXRlLnRvSlNPTigpKS50b01hdGNoU25hcHNob3QoKTtcbiAgfSk7XG59KTtcblxuLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4vLyBjZGstbmFnIEF3c1NvbHV0aW9ucyBDb21wbGlhbmNlIFRlc3RzXG4vLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbmRlc2NyaWJlKFwiY2RrLW5hZyBBd3NTb2x1dGlvbnMgY29tcGxpYW5jZVwiLCAoKSA9PiB7XG4gIGxldCBhcGlTdGFjazogQXBpU3RhY2s7XG4gIGxldCB3ZWJVaVN0YWNrOiBXZWJVaVN0YWNrO1xuXG4gIGJlZm9yZUFsbCgoKSA9PiB7XG4gICAgY29uc3Qgc3RhY2tzID0gY3JlYXRlU3RhY2tzKHRydWUpO1xuICAgIGFwaVN0YWNrID0gc3RhY2tzLmFwaVN0YWNrO1xuICAgIHdlYlVpU3RhY2sgPSBzdGFja3Mud2ViVWlTdGFjaztcblxuICAgIC8vIEZvcmNlIHN5bnRoZXNpcyBzbyBjZGstbmFnIGFzcGVjdHMgcnVuXG4gICAgc3RhY2tzLmFwcC5zeW50aCgpO1xuICB9KTtcblxuICB0ZXN0KFwiQXBpU3RhY2sgaGFzIG5vIHVuc3VwcHJlc3NlZCBjZGstbmFnIGVycm9yc1wiLCAoKSA9PiB7XG4gICAgY29uc3QgZXJyb3JzID0gQW5ub3RhdGlvbnMuZnJvbVN0YWNrKGFwaVN0YWNrKS5maW5kRXJyb3IoXG4gICAgICBcIipcIixcbiAgICAgIE1hdGNoLnN0cmluZ0xpa2VSZWdleHAoXCJBd3NTb2x1dGlvbnMtLipcIilcbiAgICApO1xuICAgIGV4cGVjdChlcnJvcnMpLnRvSGF2ZUxlbmd0aCgwKTtcbiAgfSk7XG5cbiAgdGVzdChcIkFwaVN0YWNrIGhhcyBubyB1bnN1cHByZXNzZWQgY2RrLW5hZyB3YXJuaW5nc1wiLCAoKSA9PiB7XG4gICAgY29uc3Qgd2FybmluZ3MgPSBBbm5vdGF0aW9ucy5mcm9tU3RhY2soYXBpU3RhY2spLmZpbmRXYXJuaW5nKFxuICAgICAgXCIqXCIsXG4gICAgICBNYXRjaC5zdHJpbmdMaWtlUmVnZXhwKFwiQXdzU29sdXRpb25zLS4qXCIpXG4gICAgKTtcbiAgICBleHBlY3Qod2FybmluZ3MpLnRvSGF2ZUxlbmd0aCgwKTtcbiAgfSk7XG5cbiAgdGVzdChcIldlYlVpU3RhY2sgaGFzIG5vIHVuc3VwcHJlc3NlZCBjZGstbmFnIGVycm9yc1wiLCAoKSA9PiB7XG4gICAgY29uc3QgZXJyb3JzID0gQW5ub3RhdGlvbnMuZnJvbVN0YWNrKHdlYlVpU3RhY2spLmZpbmRFcnJvcihcbiAgICAgIFwiKlwiLFxuICAgICAgTWF0Y2guc3RyaW5nTGlrZVJlZ2V4cChcIkF3c1NvbHV0aW9ucy0uKlwiKVxuICAgICk7XG4gICAgZXhwZWN0KGVycm9ycykudG9IYXZlTGVuZ3RoKDApO1xuICB9KTtcblxuICB0ZXN0KFwiV2ViVWlTdGFjayBoYXMgbm8gdW5zdXBwcmVzc2VkIGNkay1uYWcgd2FybmluZ3NcIiwgKCkgPT4ge1xuICAgIGNvbnN0IHdhcm5pbmdzID0gQW5ub3RhdGlvbnMuZnJvbVN0YWNrKHdlYlVpU3RhY2spLmZpbmRXYXJuaW5nKFxuICAgICAgXCIqXCIsXG4gICAgICBNYXRjaC5zdHJpbmdMaWtlUmVnZXhwKFwiQXdzU29sdXRpb25zLS4qXCIpXG4gICAgKTtcbiAgICBleHBlY3Qod2FybmluZ3MpLnRvSGF2ZUxlbmd0aCgwKTtcbiAgfSk7XG59KTtcbiJdfQ==