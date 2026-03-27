import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Construct } from "constructs";

export interface NetworkConstructProps {
  vpcCidr?: string;
}

export class NetworkConstruct extends Construct {
  public readonly vpc: ec2.Vpc;
  public readonly ecsSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkConstructProps = {}) {
    super(scope, id);

    // Public subnets only — no NAT gateway, no idle cost.
    // Instances get public IPs directly; security group restricts inbound.
    this.vpc = new ec2.Vpc(this, "Vpc", {
      ipAddresses: ec2.IpAddresses.cidr(props.vpcCidr ?? "10.0.0.0/16"),
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: "Public",
          subnetType: ec2.SubnetType.PUBLIC,
        },
      ],
    });

    // ECS security group: allow API port from anywhere, block ComfyUI externally
    this.ecsSecurityGroup = new ec2.SecurityGroup(this, "EcsSg", {
      vpc: this.vpc,
      description: "ECS task security group",
      allowAllOutbound: true,
    });
    this.ecsSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(8000),
      "Allow API from internet"
    );
    // ComfyUI port 8188 is intentionally NOT opened — sidecar on localhost only

    new cdk.CfnOutput(this, "VpcId", { value: this.vpc.vpcId });
  }
}
