---
name: cfn-status
description: Show ComfyAwsStack status and last 10 events with interpreted advice.
model: inherit
allowed-tools: Bash(aws cloudformation:*)
---

# cfn-status

Check the current state of `ComfyAwsStack` and surface any issues.

## Instructions

### 1. Get stack status

```bash
aws cloudformation describe-stacks \
  --stack-name ComfyAwsStack --region us-east-1 --profile personal \
  --query 'Stacks[0].{Status:StackStatus,Reason:StackStatusReason}' \
  --output table
```

### 2. Get last 10 events

```bash
aws cloudformation describe-stack-events \
  --stack-name ComfyAwsStack --region us-east-1 --profile personal \
  --query 'StackEvents[:10].{Time:Timestamp,Resource:LogicalResourceId,Status:ResourceStatus,Reason:ResourceStatusReason}' \
  --output table
```

### 3. Interpret and advise

Based on `StackStatus`, tell the user:

| Status                                                 | Meaning             | Advice                                                                                               |
| ------------------------------------------------------ | ------------------- | ---------------------------------------------------------------------------------------------------- |
| `CREATE_COMPLETE` / `UPDATE_COMPLETE`                  | Healthy             | Safe to deploy again                                                                                 |
| `UPDATE_ROLLBACK_COMPLETE` / `ROLLBACK_COMPLETE`       | Rolled back cleanly | Safe to re-deploy; check events for root cause                                                       |
| `CREATE_IN_PROGRESS` / `UPDATE_IN_PROGRESS`            | Still running       | Wait — CloudFormation runs independently of CDK process                                              |
| `ROLLBACK_IN_PROGRESS` / `UPDATE_ROLLBACK_IN_PROGRESS` | Rolling back        | Wait for it to complete                                                                              |
| `UPDATE_ROLLBACK_FAILED`                               | Stuck               | Run `/cfn-events` to find the stuck resource; may need `aws cloudformation continue-update-rollback` |
| `CREATE_FAILED` / `ROLLBACK_FAILED`                    | Hard failure        | Investigate with `/cfn-events`; may need manual resource cleanup                                     |

If any events show `*_FAILED` status, highlight the resource name and reason clearly.
