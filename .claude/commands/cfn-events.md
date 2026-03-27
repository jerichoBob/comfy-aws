---
name: cfn-events
description: Show recent ComfyAwsStack events. Default 30, pass a number for more (e.g. /cfn-events 50).
model: inherit
allowed-tools: Bash(aws cloudformation:*)
argument-hint: "[count]"
---

# cfn-events

Deep-dive into `ComfyAwsStack` events. Most useful when debugging a `*_FAILED` state.

## Arguments

- **Optional count**: number of events to show (default: `30`)

## Instructions

### 1. Fetch events

```bash
aws cloudformation describe-stack-events \
  --stack-name ComfyAwsStack --region us-east-1 --profile personal \
  --query "StackEvents[:{{{args:-30}}}].{Time:Timestamp,Resource:LogicalResourceId,Status:ResourceStatus,Reason:ResourceStatusReason}" \
  --output table
```

If `{{args}}` is provided, use it as the count. Otherwise default to `30`.

### 2. Highlight failures

Scan the output for any rows with `*_FAILED` status and call them out explicitly:

```
FAILED RESOURCES:
- <ResourceName>: <Reason>
```

If there are no failures, confirm the stack is progressing normally and show the most recent active resource.
