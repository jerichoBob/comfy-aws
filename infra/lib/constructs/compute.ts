import * as cdk from "aws-cdk-lib";
import * as autoscaling from "aws-cdk-lib/aws-autoscaling";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as iam from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

export interface ComputeConstructProps {
  vpc: ec2.Vpc;
  securityGroup: ec2.SecurityGroup;
  s3BucketArn: string;
  dynamoTableArn: string;
}

export class ComputeConstruct extends Construct {
  public readonly cluster: ecs.Cluster;
  public readonly instanceRole: iam.Role;

  constructor(scope: Construct, id: string, props: ComputeConstructProps) {
    super(scope, id);

    this.cluster = new ecs.Cluster(this, "Cluster", {
      vpc: props.vpc,
      clusterName: "comfy-aws",
    });

    // Instance profile role with permissions for ECS + S3 + DynamoDB
    this.instanceRole = new iam.Role(this, "InstanceRole", {
      assumedBy: new iam.ServicePrincipal("ec2.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AmazonEC2ContainerServiceforEC2Role",
        ),
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "AmazonSSMManagedInstanceCore",
        ),
      ],
    });

    // S3: read models, read/write outputs
    this.instanceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:GetObject", "s3:ListBucket"],
        resources: [props.s3BucketArn, `${props.s3BucketArn}/models/*`],
      }),
    );
    this.instanceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
        resources: [`${props.s3BucketArn}/outputs/*`],
      }),
    );

    // DynamoDB full access on the jobs table
    this.instanceRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:*"],
        resources: [props.dynamoTableArn, `${props.dynamoTableArn}/index/*`],
      }),
    );

    // User data: format + mount 200GB EBS data volume at /data
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      "#!/bin/bash",
      "set -e",
      // Wait for data volume to appear (second EBS)
      "while [ ! -b /dev/nvme1n1 ] && [ ! -b /dev/xvdb ]; do sleep 1; done",
      "DATA_DEV=$([ -b /dev/nvme1n1 ] && echo /dev/nvme1n1 || echo /dev/xvdb)",
      "if ! blkid $DATA_DEV; then mkfs -t xfs $DATA_DEV; fi",
      "mkdir -p /data/models/checkpoints /data/models/loras /data/models/vaes",
      'grep -q /data /etc/fstab || echo "$DATA_DEV /data xfs defaults,nofail 0 2" >> /etc/fstab',
      "mount -a || true",
      // ECS config
      `echo ECS_CLUSTER=comfy-aws >> /etc/ecs/ecs.config`,
      "echo ECS_ENABLE_SPOT_INSTANCE_DRAINING=true >> /etc/ecs/ecs.config",
    );

    const launchTemplate = new ec2.LaunchTemplate(this, "LaunchTemplate", {
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.G4DN,
        ec2.InstanceSize.XLARGE,
      ),
      machineImage: ecs.EcsOptimizedImage.amazonLinux2(ecs.AmiHardwareType.GPU),
      userData,
      role: this.instanceRole,
      securityGroup: props.securityGroup,
      blockDevices: [
        {
          // Root volume: 100GB gp3
          deviceName: "/dev/xvda",
          volume: autoscaling.BlockDeviceVolume.ebs(100, {
            volumeType: autoscaling.EbsDeviceVolumeType.GP3,
            deleteOnTermination: true,
          }),
        },
        {
          // Data volume: 200GB gp3 for models
          deviceName: "/dev/xvdb",
          volume: autoscaling.BlockDeviceVolume.ebs(200, {
            volumeType: autoscaling.EbsDeviceVolumeType.GP3,
            deleteOnTermination: true,
          }),
        },
      ],
    });

    const asg = new autoscaling.AutoScalingGroup(this, "Asg", {
      vpc: props.vpc,
      mixedInstancesPolicy: {
        launchTemplate,
        instancesDistribution: {
          onDemandPercentageAboveBaseCapacity: 0,
          spotAllocationStrategy:
            autoscaling.SpotAllocationStrategy.LOWEST_PRICE,
        },
      },
      minCapacity: 0,
      maxCapacity: 1,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
    });

    const capacityProvider = new ecs.AsgCapacityProvider(
      this,
      "CapacityProvider",
      {
        autoScalingGroup: asg,
        enableManagedTerminationProtection: false,
      },
    );
    this.cluster.addAsgCapacityProvider(capacityProvider);

    new cdk.CfnOutput(this, "ClusterName", {
      value: this.cluster.clusterName,
    });
  }
}
