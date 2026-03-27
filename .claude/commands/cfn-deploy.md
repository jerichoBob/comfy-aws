---
name: cfn-deploy
description: Deploy ComfyAwsStack via CDK, then show final stack status.
model: inherit
allowed-tools: Bash(.claude/scripts/cfn-deploy.sh:*), Bash(aws cloudformation:*)
---

# cfn-deploy

Run the CDK deploy for `ComfyAwsStack` and report the outcome.

## Instructions

### 1. Run the deploy script

```bash
.claude/scripts/cfn-deploy.sh
```

Stream all output to the user as it appears. CDK deploy can take several minutes — keep the user informed.

### 2. After completion

Run `/cfn-status` to show the final stack state and interpret the result.

If the script exits non-zero, highlight the error and suggest next steps (e.g. `/cfn-events` to investigate a rollback).
