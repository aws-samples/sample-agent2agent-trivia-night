# Agent2Agent-Trivia-Night

## Summary

Code examples for the Agent2Agent Trivia Night workshop

## Getting Started

### Overview

You need to use your own AWS Account to perform the next steps. This may incur some charges. Please note the clean-up step below to minimize these charges.

If you are completing this workshop at an AWS Instructor-led event, you do NOT need to complete these steps.

### Deploy workshop infrastructure

Follow these steps to deploy the supporting infrastructure for this workshop into your own AWS account. This will incur charges. Before beginning, verify that you have [valid AWS credentials](https://docs.aws.amazon.com/cli/v1/userguide/cli-chap-configure.html#configure-precedence) set in your environment.

1. Download the example code to your local computer by opening a terminal and running the following command.

```bash
git clone https://github.com/aws-samples/sample-agent2agent-trivia-night.git
cd sample-agent2agent-trivia-night
```

2. Run `./scripts/deploy.sh` to deploy the necessary infrastructure for this workshop into your AWS account. The script will print the required **CodeEditorURL**, **PlatformURL**, **PlatformUsername**, and **PlatformPassword** values to your terminal for later use.

3. Follow the remaining insructions on the [AWS Instructor-Led Workshop](/getting-started/aws-instructor-led-workshop) page, to continue with workshop setup

### Clean up

When finished with the workshop, run `./scripts/destroy.sh` on your local computer to delete all workshop resources and stop charges.

### Workshop Costs

The estimated cost to complete these workshop in your own AWS account is approximately $3.00.

## Next steps

Navigate to [Workshop Studio](https://catalog.us-east-1.prod.workshops.aws/workshops/de81ded2-745f-4bef-88ef-578d00e1b1f7) to complete the hands-on labs in your own AWS account.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
