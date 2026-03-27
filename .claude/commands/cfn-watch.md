---
name: cfn-watch
description: Poll ComfyAwsStack every 15s until it reaches a stable state, then summarize.
model: inherit
allowed-tools: Bash(aws cloudformation:*)
---

# cfn-watch

Watch `ComfyAwsStack` until it finishes, printing status each poll.

## Instructions

### 1. Poll until stable

Run this loop — it prints a timestamped status line every 15 seconds and exits when the stack reaches a terminal state:

```bash
STABLE="CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE UPDATE_ROLLBACK_COMPLETE CREATE_FAILED ROLLBACK_FAILED DELETE_COMPLETE DELETE_FAILED"
while true; do
  STATUS=$(aws cloudformation describe-stacks \
    --stack-name ComfyAwsStack --region us-east-1 --profile personal \
    --query 'Stacks[0].StackStatus' --output text 2>&1)
  echo "$(date '+%H:%M:%S')  $STATUS"
  for s in $STABLE; do
    if [ "$STATUS" = "$s" ]; then
      echo "Stack settled: $STATUS"
      exit 0
    fi
  done
  sleep 15
done
```

### 2. Final summary

Once settled, run `/cfn-status` to show the last 10 events and interpret the outcome.

Tell the user whether the deploy succeeded, rolled back, or failed — and what to do next.
