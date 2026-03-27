import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { ComputeConstruct } from "./constructs/compute";
import { NetworkConstruct } from "./constructs/network";
import { ServiceConstruct } from "./constructs/service";
import { StorageConstruct } from "./constructs/storage";

export class ComfyAwsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const network = new NetworkConstruct(this, "Network");
    const storage = new StorageConstruct(this, "Storage");
    const compute = new ComputeConstruct(this, "Compute", {
      vpc: network.vpc,
      securityGroup: network.ecsSecurityGroup,
      s3BucketArn: storage.bucket.bucketArn,
      dynamoTableArn: storage.table.tableArn,
    });
    new ServiceConstruct(this, "Service", {
      cluster: compute.cluster,
      vpc: network.vpc,
      ecsSecurityGroup: network.ecsSecurityGroup,
      bucket: storage.bucket,
      table: storage.table,
      comfyuiImageUri: this.node.tryGetContext("comfyuiImage"),
      apiImageUri: this.node.tryGetContext("apiImage"),
    });
  }
}
