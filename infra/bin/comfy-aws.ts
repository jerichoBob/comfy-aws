#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { ComfyAwsStack } from "../lib/comfy-aws-stack";

const app = new cdk.App();

new ComfyAwsStack(app, "ComfyAwsStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
  },
});
