import * as cdk from "aws-cdk-lib";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";

export interface CdnConstructProps {
  bucket: s3.Bucket;
  /** Pre-generated RSA-2048 private key PEM (generate once, store securely). */
  privateKeyPem: string;
  /** Matching RSA-2048 public key PEM for CloudFront key group. */
  publicKeyPem: string;
}

export class CdnConstruct extends Construct {
  public readonly distribution: cloudfront.Distribution;
  public readonly keyPairId: string;
  public readonly domainName: string;

  constructor(scope: Construct, id: string, props: CdnConstructProps) {
    super(scope, id);

    // Origin Access Control — grants CloudFront access to S3 without making the bucket public
    const oac = new cloudfront.S3OriginAccessControl(this, "OAC", {
      signing: cloudfront.Signing.SIGV4_NO_OVERRIDE,
    });

    // CloudFront public key + key group for signed URLs
    const publicKey = new cloudfront.PublicKey(this, "PublicKey", {
      encodedKey: props.publicKeyPem,
    });
    const keyGroup = new cloudfront.KeyGroup(this, "KeyGroup", {
      items: [publicKey],
    });

    // Distribution: outputs/* only, signed URLs required
    this.distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(props.bucket, { originAccessControl: oac }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        trustedKeyGroups: [keyGroup],
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100,
    });

    // Lock down S3 bucket: deny direct GetObject on outputs/* — only CloudFront OAC allowed
    props.bucket.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: "DenyDirectOutputAccess",
        effect: iam.Effect.DENY,
        principals: [new iam.StarPrincipal()],
        actions: ["s3:GetObject"],
        resources: [props.bucket.arnForObjects("outputs/*")],
        conditions: {
          StringNotEquals: {
            "aws:SourceArn": `arn:aws:cloudfront::${cdk.Stack.of(this).account}:distribution/${this.distribution.distributionId}`,
          },
        },
      })
    );

    // Store private key PEM in SSM for the API to fetch at startup
    new ssm.StringParameter(this, "PrivateKeyParam", {
      parameterName: "/comfy-aws/cloudfront-private-key",
      stringValue: props.privateKeyPem,
      description: "CloudFront RSA private key for signed URL generation",
    });

    this.keyPairId = publicKey.publicKeyId;
    this.domainName = this.distribution.domainName;

    new cdk.CfnOutput(this, "CloudFrontDomain", { value: this.domainName });
    new cdk.CfnOutput(this, "CloudFrontKeyPairId", { value: this.keyPairId });
  }
}
