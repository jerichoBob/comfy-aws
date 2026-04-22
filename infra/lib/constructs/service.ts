import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import * as path from "path";

export interface ServiceConstructProps {
  cluster: ecs.Cluster;
  vpc: ec2.Vpc;
  ecsSecurityGroup: ec2.SecurityGroup;
  bucket: s3.Bucket;
  table: dynamodb.Table;
  /** Pre-built image URIs — pass via `cdk deploy -c comfyuiImage=... -c apiImage=...`
   *  If omitted, images are built from source (requires Docker + internet). */
  comfyuiImageUri?: string;
  apiImageUri?: string;
  /** CloudFront domain name for signed URL generation (optional). */
  cdnDomain?: string;
  /** CloudFront key pair ID for signed URL generation (optional). */
  cdnKeyPairId?: string;
}

export class ServiceConstruct extends Construct {
  constructor(scope: Construct, id: string, props: ServiceConstructProps) {
    super(scope, id);

    const logGroup = new logs.LogGroup(this, "LogGroup", {
      logGroupName: "/comfy-aws/ecs",
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // Task role: allows containers to call S3 + DynamoDB
    const taskRole = new iam.Role(this, "TaskRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
    });
    props.bucket.grantRead(taskRole, "models/*");
    props.bucket.grantReadWrite(taskRole, "outputs/*");
    props.table.grantFullAccess(taskRole);

    // Also grant CloudWatch metrics publishing
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["cloudwatch:PutMetricData"],
        resources: ["*"],
      }),
    );

    // Grant SSM access for CloudFront private key (only when CDN is configured)
    if (props.cdnDomain) {
      taskRole.addToPolicy(
        new iam.PolicyStatement({
          actions: ["ssm:GetParameter"],
          resources: [
            `arn:aws:ssm:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:parameter/comfy-aws/cloudfront-private-key`,
          ],
        }),
      );
    }

    // Execution role: allows ECS agent to pull SSM secrets at task start
    const executionRole = new iam.Role(this, "ExecutionRole", {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AmazonECSTaskExecutionRolePolicy",
        ),
      ],
    });
    executionRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["ssm:GetParameters"],
        resources: [
          `arn:aws:ssm:${cdk.Stack.of(this).region}:${cdk.Stack.of(this).account}:parameter/comfy-aws/api-keys`,
        ],
      }),
    );

    const taskDef = new ecs.Ec2TaskDefinition(this, "TaskDef", {
      taskRole,
      executionRole,
      networkMode: ecs.NetworkMode.HOST,
    });

    // model-sync init container: aws s3 sync models into /data
    const modelSync = taskDef.addContainer("model-sync", {
      image: ecs.ContainerImage.fromRegistry("amazon/aws-cli:2.17.0"),
      essential: false,
      command: [
        "s3",
        "sync",
        `s3://${props.bucket.bucketName}/models/`,
        "/data/models/",
        "--exact-timestamps",
      ],
      environment: {
        AWS_DEFAULT_REGION: cdk.Stack.of(this).region,
      },
      logging: ecs.LogDrivers.awsLogs({
        logGroup,
        streamPrefix: "model-sync",
      }),
      memoryReservationMiB: 128,
    });
    modelSync.addMountPoints({
      containerPath: "/data",
      sourceVolume: "data",
      readOnly: false,
    });

    // ComfyUI container
    const comfyui = taskDef.addContainer("comfyui", {
      image: props.comfyuiImageUri
        ? ecs.ContainerImage.fromRegistry(props.comfyuiImageUri)
        : ecs.ContainerImage.fromAsset(
            path.join(__dirname, "../../../docker/comfyui"),
            { platform: ecr_assets.Platform.LINUX_AMD64 },
          ),
      essential: true,
      // Override CMD to remove --cpu for GPU in production
      command: ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188"],
      portMappings: [{ containerPort: 8188, hostPort: 8188 }],
      logging: ecs.LogDrivers.awsLogs({
        logGroup,
        streamPrefix: "comfyui",
      }),
      memoryReservationMiB: 8192,
      gpuCount: 1,
    });
    comfyui.addMountPoints({
      containerPath: "/app/models",
      sourceVolume: "data",
      readOnly: false,
    });

    // API sidecar container
    const apiContainer = taskDef.addContainer("api", {
      image: props.apiImageUri
        ? ecs.ContainerImage.fromRegistry(props.apiImageUri)
        : ecs.ContainerImage.fromAsset(path.join(__dirname, "../../../api"), {
            platform: ecr_assets.Platform.LINUX_AMD64,
          }),
      essential: true,
      portMappings: [{ containerPort: 8000, hostPort: 8000 }],
      environment: {
        COMFYUI_URL: "http://localhost:8188",
        S3_BUCKET: props.bucket.bucketName,
        DYNAMO_TABLE: props.table.tableName,
        AWS_DEFAULT_REGION: cdk.Stack.of(this).region,
        ...(props.cdnDomain ? { CLOUDFRONT_DOMAIN: props.cdnDomain } : {}),
        ...(props.cdnKeyPairId
          ? { CLOUDFRONT_KEY_PAIR_ID: props.cdnKeyPairId }
          : {}),
      },
      secrets: {
        // Operator sets this SSM parameter before deploying.
        // Comma-separated keys, e.g. "key-abc123,key-def456".
        // Empty string (default) disables auth entirely.
        API_KEYS: ecs.Secret.fromSsmParameter(
          ssm.StringParameter.fromStringParameterName(
            this,
            "ApiKeysParam",
            "/comfy-aws/api-keys",
          ),
        ),
      },
      logging: ecs.LogDrivers.awsLogs({
        logGroup,
        streamPrefix: "api",
      }),
      healthCheck: {
        command: [
          "CMD-SHELL",
          "curl -f http://localhost:8000/health || exit 1",
        ],
        interval: cdk.Duration.seconds(15),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      memoryReservationMiB: 1024,
    });

    // /data EBS volume (mounted from host)
    taskDef.addVolume({ name: "data", host: { sourcePath: "/data" } });

    new ecs.Ec2Service(this, "Service", {
      cluster: props.cluster,
      taskDefinition: taskDef,
      desiredCount: 0,
      enableExecuteCommand: true,
    });

    // No ALB — access the API directly via the instance's public IP on port 8000.
    // After spin-up, find the IP with:
    //   aws ec2 describe-instances --filters Name=tag:aws:autoscaling:groupName,Values=<asg-name> \
    //     --query 'Reservations[].Instances[].PublicIpAddress' --output text
    new cdk.CfnOutput(this, "ApiAccessNote", {
      value: "curl http://<instance-public-ip>:8000/health",
      description:
        "Get instance IP: aws ec2 describe-instances --filters Name=instance-state-name,Values=running --query Reservations[].Instances[].PublicIpAddress --output text",
    });
  }
}
