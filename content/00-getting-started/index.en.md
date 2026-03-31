---
title: "Getting Started at an AWS Instructor-Led Workshop"
weight: 10
---

## Overview

If you are attending an AWS hosted event, you will have access to an AWS account with any optional pre-provisioned infrastructure and IAM policies needed to complete this workshop. The goal of this section is to help you access this AWS account.

## Launch Visual Studio Code - Open Source

After joining the event, you should see the page with event information and workshop details. You should also see a section titled **Event outputs**. Select the **CodeEditorURL** value to launch Visual Studio Code - Open Source (Code-OSS) in your participant AWS account.

![Event Outputs](/static/code_editor_url.png)

![Code Editor](/static/vs-code-01.png)

Your Code Editor environment has **uv**, **npm**, **Kiro CLI**, and **AgentCore Starter Toolkit CLI** preinstalled.

## Login to Kiro CLI

To log in to Kiro CLI, open the *Terminal* tab on Code Editor and type the following command:

:::code{showCopyAction=true language=bash}
kiro-cli login --use-device-flow
:::

When asked about login method, select *Use for Free with Builder ID*.

Open the URL provided in a new browser tab. If you have an **AWS Builder ID**, enter your email and password when asked. If you don't have one, you can create one for free by simply entering an email address and providing your name.

Once authenticated, you will be redirected to a page to confirm the authorization request. Check if the code presented is the same from the terminal and click **Confirm and continue**. When asked to allow Kiro CLI to access your data, click **Allow access**.

Once you see the confirmation box saying **Request approved**, you can close this browser tab and return to Code Editor window. You are now logged into Kiro.

![Kiro CLI](/static/kiro-cli-01.png)

**Congratulations!!** You have successfully set up your environment. You can move to [Lab 1](/01-first-agent).

## Best Practices

- Do not upload any personal or confidential information in the account.
- The AWS account will only be available for the duration of this workshop and you will not be able to retain access after the workshop is complete. Backup any materials you wish to keep access to after the workshop.
- Any pre-provisioned infrastructure will be deployed to a specific region. Check your workshop content to determine whether other regions will be used.
