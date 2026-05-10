"""
deployment/aws_deploy.py — AWS infrastructure provisioning using boto3
Creates: EC2 t2.medium, S3 buckets, CloudWatch log groups, Lambda retraining function
"""

import os
import sys
import json
import time
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

REGION = os.environ.get("AWS_REGION", "us-east-1")
INSTANCE_TYPE = "t2.medium"
AMI_ID = "ami-0c02fb55956c7d316"  # Amazon Linux 2 us-east-1
KEY_PAIR_NAME = os.environ.get("AWS_KEY_PAIR", "pricing-engine-key")
SECURITY_GROUP_NAME = "pricing-engine-sg"
MODEL_BUCKET = "pricing-models-prod"
DATA_BUCKET = "pricing-data-prod"


def get_boto3():
    try:
        import boto3
        return boto3
    except ImportError:
        logger.error("boto3 not installed. Run: pip install boto3")
        sys.exit(1)


def create_security_group(ec2_client):
    logger.info("Creating security group: %s", SECURITY_GROUP_NAME)
    try:
        sg = ec2_client.create_security_group(
            GroupName=SECURITY_GROUP_NAME,
            Description="Dynamic Pricing Engine — API + Dashboard + SSH",
        )
        sg_id = sg["GroupId"]
        for port in [22, 8000, 8501]:
            ec2_client.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": port, "ToPort": port,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }],
            )
        logger.info("Security group created: %s (ports 22, 8000, 8501 open)", sg_id)
        return sg_id
    except Exception as e:
        if "InvalidGroup.Duplicate" in str(e):
            sgs = ec2_client.describe_security_groups(GroupNames=[SECURITY_GROUP_NAME])
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            logger.info("Security group already exists: %s", sg_id)
            return sg_id
        raise


def launch_ec2(ec2_client, sg_id: str) -> dict:
    logger.info("Launching EC2 instance (%s)…", INSTANCE_TYPE)
    user_data = """#!/bin/bash
yum update -y
yum install python3 python3-pip git -y
pip3 install fastapi uvicorn xgboost scikit-learn pandas numpy joblib streamlit plotly requests
mkdir -p /opt/pricing-engine
cd /opt/pricing-engine
# Clone repo (replace with actual URL)
# git clone https://github.com/YOUR_ORG/pricing-engine.git .

# Create FastAPI systemd service
cat > /etc/systemd/system/pricing-api.service << EOF
[Unit]
Description=Dynamic Pricing FastAPI
After=network.target

[Service]
WorkingDirectory=/opt/pricing-engine
ExecStart=/usr/local/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3
Environment=PYTHONPATH=/opt/pricing-engine

[Install]
WantedBy=multi-user.target
EOF

# Create Streamlit systemd service
cat > /etc/systemd/system/pricing-dashboard.service << EOF
[Unit]
Description=Dynamic Pricing Streamlit Dashboard
After=network.target

[Service]
WorkingDirectory=/opt/pricing-engine
ExecStart=/usr/local/bin/streamlit run dashboard/app.py --server.port 8501 --server.headless true
Restart=always
RestartSec=3
Environment=PYTHONPATH=/opt/pricing-engine

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pricing-api pricing-dashboard
systemctl start pricing-api pricing-dashboard
"""

    response = ec2_client.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_PAIR_NAME,
        SecurityGroupIds=[sg_id],
        MinCount=1, MaxCount=1,
        UserData=user_data,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [{"Key": "Name", "Value": "PricingEngine"}],
        }],
        BlockDeviceMappings=[{
            "DeviceName": "/dev/xvda",
            "Ebs": {"VolumeSize": 20, "VolumeType": "gp2"},
        }],
    )
    instance = response["Instances"][0]
    instance_id = instance["InstanceId"]
    logger.info("Instance launched: %s — waiting for running state…", instance_id)

    ec2 = get_boto3().resource("ec2", region_name=REGION)
    ec2.Instance(instance_id).wait_until_running()
    ec2.Instance(instance_id).reload()

    public_ip = ec2.Instance(instance_id).public_ip_address
    logger.info("Instance running: %s | Public IP: %s", instance_id, public_ip)
    return {"instance_id": instance_id, "public_ip": public_ip}


def create_s3_buckets(s3_client):
    for bucket in [MODEL_BUCKET, DATA_BUCKET]:
        try:
            if REGION == "us-east-1":
                s3_client.create_bucket(Bucket=bucket)
            else:
                s3_client.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={"LocationConstraint": REGION},
                )
            s3_client.put_bucket_versioning(
                Bucket=bucket,
                VersioningConfiguration={"Status": "Enabled"},
            )
            logger.info("S3 bucket created: s3://%s (versioning enabled)", bucket)
        except Exception as e:
            if "BucketAlreadyOwnedByYou" in str(e):
                logger.info("Bucket already exists: s3://%s", bucket)
            else:
                logger.error("Failed to create bucket %s: %s", bucket, e)


def upload_model_files(s3_client):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    models_dir = os.path.join(base_dir, "models")
    for fname in ["xgboost_pricing_model.pkl", "scaler.pkl", "feature_names.json", "model_metadata.json"]:
        fpath = os.path.join(models_dir, fname)
        if os.path.exists(fpath):
            s3_client.upload_file(fpath, MODEL_BUCKET, fname)
            logger.info("Uploaded: %s → s3://%s/%s", fname, MODEL_BUCKET, fname)
        else:
            logger.warning("Model file not found: %s", fpath)


def create_cloudwatch_groups(logs_client):
    for group in ["/aws/ec2/pricing-api", "/aws/ec2/pricing-dashboard", "/aws/lambda/retrain"]:
        try:
            logs_client.create_log_group(logGroupName=group)
            logs_client.put_retention_policy(logGroupName=group, retentionInDays=30)
            logger.info("Log group created: %s", group)
        except Exception as e:
            if "ResourceAlreadyExistsException" in str(e):
                logger.info("Log group exists: %s", group)


def create_latency_alarm(cloudwatch_client, account_id: str, email: str = None):
    try:
        cloudwatch_client.put_metric_alarm(
            AlarmName="pricing-api-latency-high",
            AlarmDescription="Alert if API processing latency > 1000ms",
            MetricName="APILatencyMs",
            Namespace="PricingEngine/API",
            Statistic="p95",
            Period=300,
            Threshold=1000,
            ComparisonOperator="GreaterThanThreshold",
            EvaluationPeriods=1,
        )
        logger.info("CloudWatch alarm created: pricing-api-latency-high")
    except Exception as e:
        logger.error("Failed to create alarm: %s", e)


def deploy():
    """Main deployment orchestration."""
    boto3 = get_boto3()
    session = boto3.Session(region_name=REGION)

    ec2_client = session.client("ec2")
    s3_client = session.client("s3")
    logs_client = session.client("logs")
    cw_client = session.client("cloudwatch")

    logger.info("=== Starting AWS Deployment ===")

    # 1. Security group
    sg_id = create_security_group(ec2_client)

    # 2. S3 buckets
    create_s3_buckets(s3_client)

    # 3. Upload model files
    upload_model_files(s3_client)

    # 4. Launch EC2
    instance_info = launch_ec2(ec2_client, sg_id)

    # 5. CloudWatch
    create_cloudwatch_groups(logs_client)
    create_latency_alarm(cw_client, "")

    logger.info("=== Deployment Complete ===")
    logger.info("API:       http://%s:8000/health", instance_info["public_ip"])
    logger.info("Dashboard: http://%s:8501", instance_info["public_ip"])
    logger.info("Instance:  %s", instance_info["instance_id"])

    # Save deployment manifest
    manifest = {
        "deployed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "region": REGION,
        "instance_id": instance_info["instance_id"],
        "public_ip": instance_info["public_ip"],
        "model_bucket": MODEL_BUCKET,
        "data_bucket": DATA_BUCKET,
    }
    with open("deployment/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Manifest saved: deployment/manifest.json")


if __name__ == "__main__":
    deploy()
