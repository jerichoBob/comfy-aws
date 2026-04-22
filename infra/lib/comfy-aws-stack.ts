import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { CdnConstruct } from "./constructs/cdn";
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

    // CloudFront CDN for output delivery.
    // Requires operator-generated RSA-2048 key pair passed via context:
    //   cdk deploy -c cfPublicKey="$(cat cf_public.pem)" -c cfPrivateKey="$(cat cf_private.pem)"
    // Generate with: openssl genrsa -out cf_private.pem 2048 && openssl rsa -pubout -in cf_private.pem -out cf_public.pem
    const cfPublicKey = this.node.tryGetContext("cfPublicKey") as
      | string
      | undefined;
    const cfPrivateKey = this.node.tryGetContext("cfPrivateKey") as
      | string
      | undefined;

    let cdnDomain: string | undefined;
    let cdnKeyPairId: string | undefined;

    if (cfPublicKey && cfPrivateKey) {
      const cdn = new CdnConstruct(this, "Cdn", {
        bucket: storage.bucket,
        publicKeyPem: cfPublicKey,
        privateKeyPem: cfPrivateKey,
      });
      cdnDomain = cdn.domainName;
      cdnKeyPairId = cdn.keyPairId;
    }

    new ServiceConstruct(this, "Service", {
      cluster: compute.cluster,
      vpc: network.vpc,
      ecsSecurityGroup: network.ecsSecurityGroup,
      bucket: storage.bucket,
      table: storage.table,
      comfyuiImageUri: this.node.tryGetContext("comfyuiImage"),
      apiImageUri: this.node.tryGetContext("apiImage"),
      cdnDomain,
      cdnKeyPairId,
    });
  }
}
