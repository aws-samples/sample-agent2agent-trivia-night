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

## Exercise 1: Deploy your first orchestreation agent

### 1. Generate agent scaffold using the AgentCore CLI

```bash
agentcore create --name OrchestratorAgent --defaults
```

### 2. Test the agent locally

```bash
cd OrchestratorAgent
agentcore dev
```

```bash
Dev Server

Agent: OrchestratorAgent
Provider: Bedrock
Server: <http://localhost:8081/invocations>
Status: running
Log: agentcore/.cli/logs/dev/dev-20260304-181907.log

> Hello

Hello! How can I help you today?

> What is 2+2?

2 + 2 = **4**
```

### 3. Deploy the agent to AgentCore Runtime

**Note**: If this is your first time deploying an agent in this AWS account, you will need to confirm the one-time CDK bootstrapping process.

```bash
agentcore deploy
```

### 4. Invoke agent

```bash
agentcore invoke
```

### 5. Explore agent code

#### 5.1. Start Kiro CLI

```bash
kiro-cli
```

#### 5.2. Use Kiro to understand the default agent code

```bash
> Explain the agent code in main.py

I'll read the main.py file to explain the agent code.
```

#### 5.3. Update the system prompt for your trivia use case

```bash
> Update the system prompt for the agent to say it is intended to help answer trivia questions about life science, AI, and cloud computing topics.
```

Review the suggest changes and approve. When the updates are complete, exist Kiro CLI by pressing **Ctrl/Cmd + C**.

### 6. Test agent updates locally

```bash
agentcore dev
```

```bash
Dev Server

Agent: OrchestratorAgent
Server: <http://localhost:8081/invocations>
Status: running
Log: agentcore/.cli/logs/dev/dev-20260303-202926.log

> Hello

Hello! 👋 I'm here to help you with trivia questions about life science, AI, and cloud computing topics.

Feel free to ask me anything related to:

- **Life sciences** (biology, genetics, medicine, etc.)
- **Artificial Intelligence** (machine learning, neural networks, AI applications, etc.)
- **Cloud computing** (AWS, Azure, GCP, cloud architecture, etc.)
  
 What would you like to know about today?
```

### 7. Deploy updated agent to AgentCore Runtime

```bash
agentcore deploy
```

## Exercise 2: Connect to a subagent using MCP

TBD

## Exercise 3: Connect to a subagent using A2A

TBD

## Exercise 4: Build your trivia team

TBD

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
