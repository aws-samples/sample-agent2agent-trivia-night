# Agent2Agent-Trivia-Night

## Summary

Code examples for the Agent2Agent Trivia Night workshop

## Getting Started

### Overview

If you are attending an AWS hosted event, you will have access to an AWS account with any optional pre-provisioned infrastructure and IAM policies needed to complete this workshop. The goal of this section is to help you access this AWS account.

### Launch Visual Studio Code - Open Source

After joining the event, you should see the page with event information and workshop details. You should also see a section titled "Outputs". Choose the URL value to launch Visual Studio Code - Open Source (Code-OSS) in your participant AWS account.

### Download the Workshop Contents

### Install dependencies

#### Install uv

```bash
curl -LsSf <https://astral.sh/uv/install.sh> | sh
uv --version
```

#### Install Amazon Bedrock AgentCore CLI

```bash
curl -o- <https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh> | bash
\. "$HOME/.nvm/nvm.sh"
nvm install 24
node -v # Should print "v24.14.0" or greater.
npm -v # Should print "11.9.0" or greater.
npm install -g @aws/agentcore
agentcore --version # Should print "0.3.0-preview.3.0" or greater
```

#### Install Kiro CLI

```bash
curl --proto '=https' --tlsv1.2 -sSf '<https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-aarch64-linux.zip>' -o 'kirocli.zip'
unzip kirocli.zip
./kirocli/install.sh
kiro-cli login --use-device-flow

# Open the awsapps.con URL in your browser, confirm the login code, and approve Kiro CLI access

kiro-cli --version
rm kirocli.zip
rm -rf kirocli/
```

**Congratulations!!** You have successfully downloaded the content of this workshop. You can move to Lab 1.

### Best Practices

- Do not upload any personal or confidential information in the account.
- The AWS account will only be available for the duration of this workshop and you will not be able to retain access after the workshop is complete. Backup any materials you wish to keep access to after the workshop.
- Any pre-provisioned infrastructure will be deployed to a specific region. Check your workshop content to determine whether other regions will be used.

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
