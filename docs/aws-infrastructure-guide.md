# AWS Infrastructure Setup Guide: College Management System

This comprehensive, step-by-step production runbook details the manual provisioning of the AWS infrastructure required to host the **College Management System (CMS)**. The system is built on a high-performance Python/Flask stack using Gunicorn with Eventlet asynchronous workers for real-time WebSocket communication, backed by Amazon DynamoDB for persistence, Amazon S3 for media and bulk document storage, and Amazon CloudWatch for unified observability.

---

## Architecture Overview

```
                      INTERNET
                         │
                 [ Route 53 DNS ]
                         │
                 [ Elastic IP ]
                         │
         ┌───────────────▼───────────────┐
         │ VPC: cms-vpc (10.0.0.0/16)    │
         │                               │
         │  [ Internet Gateway: cms-igw ]│
         │               │               │
         │  ┌────────────▼────────────┐  │
         │  │ Public Subnet (10.0.1.0)│  │
         │  │                         │  │
         │  │   EC2: cms-app-server   │  │
         │  │   ┌──────────────────┐  │  │
         │  │   │  Nginx (:80/:443)│  │  │
         │  │   └────────┬─────────┘  │  │
         │  │            │ proxy      │  │
         │  │   ┌────────▼─────────┐  │  │
         │  │   │ Gunicorn+Eventlet│  │  │
         │  │   │ Flask (:5000)    │  │  │
         │  │   └────────┬─────────┘  │  │
         │  │            │            │  │
         │  │      IAM Profile        │  │
         │  │   (CMS-EC2-Profile)     │  │
         │  └────────────┬────────────┘  │
         │               │               │
         │    VPC Gateway Endpoints      │
         │    ┌──────────┴──────────┐    │
         └────┼─────────────────────┼────┘
              │                     │
     ┌────────▼────────┐   ┌────────▼────────┐
     │ Amazon DynamoDB │   │    Amazon S3    │
     │   (8 Tables)    │   │ cms-college-data│
     └─────────────────┘   └─────────────────┘
```

### Global Parameters Used in This Guide
- **Region**: `us-east-1` (N. Virginia)
- **VPC CIDR**: `10.0.0.0/16`
- **Public Subnet CIDR**: `10.0.1.0/24` (Availability Zone: `us-east-1a`)
- **EC2 Instance Type**: `t3.small` (Amazon Linux 2023)
- **S3 Bucket**: `cms-college-data-{ACCOUNT_ID}`

---

## Step 1: Create Virtual Private Cloud (VPC)

The application resides within an isolated VPC providing a dedicated network boundary with custom DNS resolution.

### 1.1 AWS Management Console
1. Open the **AWS Management Console** and navigate to **VPC** (`Services > Networking & Content Delivery > VPC`).
2. In the navigation pane on the left, click **Your VPCs**, then click **Create VPC**.
3. Under **VPC settings**:
   - Select **VPC only**.
   - **Name tag**: Enter `cms-vpc`.
   - **IPv4 CIDR block**: Select **IPv4 CIDR manual input** and enter `10.0.0.0/16`.
   - **IPv6 CIDR block**: Select **No IPv6 CIDR block**.
   - **Tenancy**: Select **Default**.
4. Click **Create VPC**.
5. Select the newly created `cms-vpc` in the list:
   - Click the **Actions** dropdown button and select **Edit VPC settings**.
   - Under **DNS settings**, check **Enable DNS resolution**.
   - Check **Enable DNS hostnames**.
   - Click **Save changes**.

### 1.2 AWS CLI Commands
```bash
# 1. Create the VPC
VPC_ID=$(aws ec2 create-vpc \
  --cidr-block 10.0.0.0/16 \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=cms-vpc},{Key=Environment,Value=Production}]' \
  --query 'Vpc.VpcId' \
  --output text)

echo "Created VPC ID: ${VPC_ID}"

# 2. Enable DNS hostnames and DNS resolution
aws ec2 modify-vpc-attribute --vpc-id ${VPC_ID} --enable-dns-hostnames "{\"Value\":true}"
aws ec2 modify-vpc-attribute --vpc-id ${VPC_ID} --enable-dns-support "{\"Value\":true}"

# Verify VPC attributes
aws ec2 describe-vpc-attribute --vpc-id ${VPC_ID} --attribute enableDnsHostnames
aws ec2 describe-vpc-attribute --vpc-id ${VPC_ID} --attribute enableDnsSupport
```

---

## Step 2: Configure Public Subnet, Internet Gateway & Route Table

A public subnet with an attached Internet Gateway allows incoming web traffic (HTTP/HTTPS) and administrative SSH access.

### 2.1 AWS Management Console

#### A. Create the Public Subnet
1. In the VPC Console, click **Subnets** in the left menu, then click **Create subnet**.
2. **VPC ID**: Select `cms-vpc` (ID: `${VPC_ID}`).
3. Under **Subnet settings**:
   - **Subnet name**: Enter `cms-public-subnet`.
   - **Availability Zone**: Choose `us-east-1a`.
   - **IPv4 CIDR block**: Enter `10.0.1.0/24`.
4. Click **Create subnet**.
5. Select `cms-public-subnet` from the list:
   - Click **Actions** > **Edit subnet settings**.
   - Under **Auto-assign IP settings**, check **Enable auto-assign public IPv4 address**.
   - Click **Save**.

#### B. Create & Attach Internet Gateway
1. In the VPC Console, click **Internet gateways** in the left menu.
2. Click **Create internet gateway**.
3. **Name tag**: Enter `cms-igw`. Click **Create internet gateway**.
4. Click **Actions** > **Attach to VPC**.
5. Select `cms-vpc` and click **Attach internet gateway**.

#### C. Create & Associate Route Table
1. In the VPC Console, click **Route tables** in the left menu.
2. Click **Create route table**.
3. **Name**: Enter `cms-public-rt`.
4. **VPC**: Select `cms-vpc`. Click **Create route table**.
5. Select `cms-public-rt`:
   - Click the **Routes** tab, then click **Edit routes**.
   - Click **Add route**:
     - **Destination**: Enter `0.0.0.0/0`.
     - **Target**: Select **Internet Gateway**, then pick `cms-igw`.
   - Click **Save changes**.
   - Click the **Subnet associations** tab, then click **Edit subnet associations**.
   - Select `cms-public-subnet` and click **Save associations**.

### 2.2 AWS CLI Commands
```bash
# 1. Create Public Subnet
SUBNET_ID=$(aws ec2 create-subnet \
  --vpc-id ${VPC_ID} \
  --cidr-block 10.0.1.0/24 \
  --availability-zone us-east-1a \
  --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=cms-public-subnet}]' \
  --query 'Subnet.SubnetId' \
  --output text)

echo "Created Subnet ID: ${SUBNET_ID}"

# 2. Enable Auto-assign Public IP on Subnet
aws ec2 modify-subnet-attribute \
  --subnet-id ${SUBNET_ID} \
  --map-public-ip-on-launch

# 3. Create Internet Gateway and attach to VPC
IGW_ID=$(aws ec2 create-internet-gateway \
  --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=cms-igw}]' \
  --query 'InternetGateway.InternetGatewayId' \
  --output text)

aws ec2 attach-internet-gateway \
  --internet-gateway-id ${IGW_ID} \
  --vpc-id ${VPC_ID}

echo "Created and Attached IGW ID: ${IGW_ID}"

# 4. Create Custom Route Table
RT_ID=$(aws ec2 create-route-table \
  --vpc-id ${VPC_ID} \
  --tag-specifications 'ResourceType=route-table,Tags=[{Key=Name,Value=cms-public-rt}]' \
  --query 'RouteTable.RouteTableId' \
  --output text)

echo "Created Route Table ID: ${RT_ID}"

# 5. Add default route (0.0.0.0/0 -> IGW)
aws ec2 create-route \
  --route-table-id ${RT_ID} \
  --destination-cidr-block 0.0.0.0/0 \
  --gateway-id ${IGW_ID}

# 6. Associate Route Table with Public Subnet
aws ec2 associate-route-table \
  --subnet-id ${SUBNET_ID} \
  --route-table-id ${RT_ID}
```

---

## Step 3: Configure Security Group (`cms-ec2-sg`)

The security group acts as a virtual firewall controlling inbound and outbound traffic to the EC2 web server.

### 3.1 AWS Management Console
1. Navigate to **EC2 Console** > **Network & Security** > **Security Groups**.
2. Click **Create security group**.
3. **Basic details**:
   - **Security group name**: Enter `cms-ec2-sg`.
   - **Description**: Enter `Security group for College Management System EC2 instances`.
   - **VPC**: Select `cms-vpc`.
4. **Inbound rules**:
   - **Rule 1 (HTTP)**:
     - Type: `HTTP`, Port: `80`, Source: `Anywhere-IPv4` (`0.0.0.0/0`)
   - **Rule 2 (HTTP IPv6)**:
     - Type: `HTTP`, Port: `80`, Source: `Anywhere-IPv6` (`::/0`)
   - **Rule 3 (HTTPS)**:
     - Type: `HTTPS`, Port: `443`, Source: `Anywhere-IPv4` (`0.0.0.0/0`)
   - **Rule 4 (HTTPS IPv6)**:
     - Type: `HTTPS`, Port: `443`, Source: `Anywhere-IPv6` (`::/0`)
   - **Rule 5 (SSH)**:
     - Type: `SSH`, Port: `22`, Source: `My IP` (e.g. `203.0.113.25/32`)
5. **Outbound rules**:
   - Retain the default rule: All traffic, Destination `0.0.0.0/0`.
6. Add tag: `Name` = `cms-ec2-sg`.
7. Click **Create security group**.

### 3.2 AWS CLI Commands
```bash
# 1. Create the Security Group
SG_ID=$(aws ec2 create-security-group \
  --group-name cms-ec2-sg \
  --description "Security group for College Management System EC2 instances" \
  --vpc-id ${VPC_ID} \
  --tag-specifications 'ResourceType=security-group,Tags=[{Key=Name,Value=cms-ec2-sg}]' \
  --query 'GroupId' \
  --output text)

echo "Created Security Group ID: ${SG_ID}"

# 2. Authorize HTTP (port 80) from anywhere (IPv4 + IPv6)
aws ec2 authorize-security-group-ingress \
  --group-id ${SG_ID} \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id ${SG_ID} \
  --protocol tcp \
  --port 80 \
  --ipv6-cidr ::/0

# 3. Authorize HTTPS (port 443) from anywhere (IPv4 + IPv6)
aws ec2 authorize-security-group-ingress \
  --group-id ${SG_ID} \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id ${SG_ID} \
  --protocol tcp \
  --port 443 \
  --ipv6-cidr ::/0

# 4. Authorize SSH (port 22) from your administrative IP only
# Replace 203.0.113.25/32 with your actual public IP
MY_IP="203.0.113.25/32"
aws ec2 authorize-security-group-ingress \
  --group-id ${SG_ID} \
  --protocol tcp \
  --port 22 \
  --cidr ${MY_IP}
```

---

## Step 4: Provision VPC Gateway Endpoints (DynamoDB & S3)

VPC Gateway Endpoints allow your EC2 instances to communicate privately with Amazon DynamoDB and Amazon S3 over AWS internal network backbones.
- **Why Endpoints?**
  1. **Zero Data Egress Cost**: Gateway endpoints for S3 and DynamoDB are provided free of charge, eliminating data transfer costs across internet gateways.
  2. **Enhanced Security**: Traffic never leaves the Amazon internal network, preventing IP snooping and internet route spoofing.
  3. **High Performance**: Eliminates internet hops, delivering sub-millisecond latencies for DynamoDB queries.

### 4.1 AWS Management Console
1. Navigate to **VPC Console** > **Endpoints**.
2. Click **Create endpoint**.
3. **Name tag**: Enter `cms-s3-endpoint`.
4. **Service category**: Select **AWS services**.
5. In the Services search bar, search for `s3` and select the entry with **Type = Gateway** (Service Name: `com.amazonaws.us-east-1.s3`).
6. **VPC**: Select `cms-vpc`.
7. **Route tables**: Check the box for `cms-public-rt` (Route Table ID: `${RT_ID}`).
8. **Policy**: Select **Full access**. Click **Create endpoint**.
9. Repeat the process for DynamoDB:
   - Click **Create endpoint**.
   - **Name tag**: Enter `cms-dynamodb-endpoint`.
   - Search for `dynamodb` and select **Type = Gateway** (`com.amazonaws.us-east-1.dynamodb`).
   - **VPC**: Select `cms-vpc`.
   - **Route tables**: Check `cms-public-rt`.
   - **Policy**: Select **Full access**. Click **Create endpoint**.

### 4.2 AWS CLI Commands
```bash
# 1. Create S3 Gateway Endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id ${VPC_ID} \
  --service-name com.amazonaws.us-east-1.s3 \
  --route-table-ids ${RT_ID} \
  --tag-specifications 'ResourceType=vpc-endpoint,Tags=[{Key=Name,Value=cms-s3-endpoint}]'

# 2. Create DynamoDB Gateway Endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id ${VPC_ID} \
  --service-name com.amazonaws.us-east-1.dynamodb \
  --route-table-ids ${RT_ID} \
  --tag-specifications 'ResourceType=vpc-endpoint,Tags=[{Key=Name,Value=cms-dynamodb-endpoint}]'
```

---

## Step 5: Provision Amazon DynamoDB Tables (All 8 Tables)

All 8 application tables use **PAY_PER_REQUEST (On-Demand)** billing to eliminate idle capacity costs while automatically scaling during exam submission peaks. **Point-In-Time Recovery (PITR)** is enabled across all tables for ransomware and disaster recovery.

### Table Specifications Summary
| # | Table Name | Partition Key (PK) | Sort Key (SK) | Global Secondary Index (GSI) |
|---|---|---|---|---|
| 1 | `cms_users` | `username` (S) | *None* | `EmailIndex` (`email` [S]) |
| 2 | `cms_students` | `student_id` (S) | *None* | `DeptYearIndex` (`department` [S], `year` [S]) |
| 3 | `cms_attendance` | `student_id` (S) | `date_course` (S) | `CourseDateIndex` (`course_id` [S], `date` [S]) |
| 4 | `cms_results` | `student_id` (S) | `sem_subject` (S) | *None* |
| 5 | `cms_exams` | `exam_id` (S) | *None* | `StatusTimeIndex` (`status` [S], `start_time` [S]) |
| 6 | `cms_questions` | `exam_id` (S) | `question_id` (S) | *None* |
| 7 | `cms_submissions` | `exam_id` (S) | `student_id` (S) | *None* |
| 8 | `cms_audit_logs` | `log_date` (S) | `ts_id` (S) | *None* |

---

### 5.1 General Console Steps for Each Table
1. Open the **Amazon DynamoDB Console** (`Services > Databases > DynamoDB`).
2. Click **Tables** > **Create table**.
3. Enter the **Table name**, **Partition key**, and **Sort key** (if applicable).
4. Under **Table settings**, select **Customize settings**.
5. Under **Read/write capacity settings**, select **On-demand**.
6. Under **Global secondary indexes**, click **Create index** (if table requires a GSI):
   - Enter Partition key, Sort key (if applicable), and Index name.
   - Attribute projection: **All**. Click **Create index**.
7. Under **Encryption at rest**, retain **Owned by Amazon DynamoDB**.
8. Click **Create table**.
9. Once created, click on the table name, navigate to the **Backups** tab, and under **Point-in-time recovery (PITR)**, click **Edit** and choose **Turn on PITR**.

---

### 5.2 CLI Commands for Table Creation

#### Table 1: `cms_users`
```bash
aws dynamodb create-table \
  --table-name cms_users \
  --attribute-definitions \
      AttributeName=username,AttributeType=S \
      AttributeName=email,AttributeType=S \
  --key-schema \
      AttributeName=username,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
      "[{\"IndexName\": \"EmailIndex\", \"KeySchema\": [{\"AttributeName\": \"email\", \"KeyType\": \"HASH\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}]" \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_users \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 2: `cms_students`
```bash
aws dynamodb create-table \
  --table-name cms_students \
  --attribute-definitions \
      AttributeName=student_id,AttributeType=S \
      AttributeName=department,AttributeType=S \
      AttributeName=year,AttributeType=S \
  --key-schema \
      AttributeName=student_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
      "[{\"IndexName\": \"DeptYearIndex\", \"KeySchema\": [{\"AttributeName\": \"department\", \"KeyType\": \"HASH\"}, {\"AttributeName\": \"year\", \"KeyType\": \"RANGE\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}]" \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_students \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 3: `cms_attendance`
```bash
aws dynamodb create-table \
  --table-name cms_attendance \
  --attribute-definitions \
      AttributeName=student_id,AttributeType=S \
      AttributeName=date_course,AttributeType=S \
      AttributeName=course_id,AttributeType=S \
      AttributeName=date,AttributeType=S \
  --key-schema \
      AttributeName=student_id,KeyType=HASH \
      AttributeName=date_course,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
      "[{\"IndexName\": \"CourseDateIndex\", \"KeySchema\": [{\"AttributeName\": \"course_id\", \"KeyType\": \"HASH\"}, {\"AttributeName\": \"date\", \"KeyType\": \"RANGE\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}]" \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_attendance \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 4: `cms_results`
```bash
aws dynamodb create-table \
  --table-name cms_results \
  --attribute-definitions \
      AttributeName=student_id,AttributeType=S \
      AttributeName=sem_subject,AttributeType=S \
  --key-schema \
      AttributeName=student_id,KeyType=HASH \
      AttributeName=sem_subject,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_results \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 5: `cms_exams`
```bash
aws dynamodb create-table \
  --table-name cms_exams \
  --attribute-definitions \
      AttributeName=exam_id,AttributeType=S \
      AttributeName=status,AttributeType=S \
      AttributeName=start_time,AttributeType=S \
  --key-schema \
      AttributeName=exam_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
      "[{\"IndexName\": \"StatusTimeIndex\", \"KeySchema\": [{\"AttributeName\": \"status\", \"KeyType\": \"HASH\"}, {\"AttributeName\": \"start_time\", \"KeyType\": \"RANGE\"}], \"Projection\": {\"ProjectionType\": \"ALL\"}}]" \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_exams \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 6: `cms_questions`
```bash
aws dynamodb create-table \
  --table-name cms_questions \
  --attribute-definitions \
      AttributeName=exam_id,AttributeType=S \
      AttributeName=question_id,AttributeType=S \
  --key-schema \
      AttributeName=exam_id,KeyType=HASH \
      AttributeName=question_id,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_questions \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 7: `cms_submissions`
```bash
aws dynamodb create-table \
  --table-name cms_submissions \
  --attribute-definitions \
      AttributeName=exam_id,AttributeType=S \
      AttributeName=student_id,AttributeType=S \
  --key-schema \
      AttributeName=exam_id,KeyType=HASH \
      AttributeName=student_id,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_submissions \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

#### Table 8: `cms_audit_logs`
```bash
aws dynamodb create-table \
  --table-name cms_audit_logs \
  --attribute-definitions \
      AttributeName=log_date,AttributeType=S \
      AttributeName=ts_id,AttributeType=S \
  --key-schema \
      AttributeName=log_date,KeyType=HASH \
      AttributeName=ts_id,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=Project,Value=CMS Key=Environment,Value=Production

aws dynamodb update-continuous-backups \
  --table-name cms_audit_logs \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

---

## Step 6: Create and Configure Amazon S3 Bucket

The Amazon S3 bucket stores CSV bulk student data, exam questions, exported PDF grade sheets, and automated DynamoDB database backups.

### 6.1 AWS Management Console
1. Navigate to **Amazon S3 Console** (`Services > Storage > S3`).
2. Click **Create bucket**.
3. **General configuration**:
   - **Bucket name**: Enter `cms-college-data-YOUR_ACCOUNT_ID` (e.g., `cms-college-data-123456789012`).
   - **AWS Region**: Select `US East (N. Virginia) us-east-1`.
4. **Block Public Access settings for this bucket**:
   - Check **Block all public access** (leave all 4 sub-options checked).
5. **Bucket Versioning**: Select **Enable**.
6. **Default encryption**:
   - Encryption type: **Server-side encryption with Amazon S3 managed keys (SSE-S3)**.
   - Bucket Key: **Enable**.
7. Click **Create bucket**.
8. Configure Lifecycle Rules:
   - Select the bucket name and navigate to the **Management** tab.
   - Under **Lifecycle rules**, click **Create lifecycle rule**.
   - **Lifecycle rule name**: Enter `PurgeOldExportsAndImports`.
   - **Filter type**: Choose **Limit the scope of this rule using one or more filters**.
   - Under Prefix, configure rule actions:
     - Check **Expire current versions of objects**.
     - Days after object creation: Enter `90`.
     - Check **Permanently delete noncurrent versions of objects** (retention: 30 days).
   - Apply prefix filter: `exports/` (Repeat rule creation for `imports/`).
   - Click **Save**.
9. In the **Objects** tab, click **Create folder** to pre-create folders:
   - `exports/`
   - `imports/`
   - `results/`
   - `backups/`

### 6.2 AWS CLI Commands
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
BUCKET_NAME="cms-college-data-${ACCOUNT_ID}"
REGION="us-east-1"

# 1. Create S3 Bucket (us-east-1 does not require LocationConstraint)
aws s3api create-bucket \
  --bucket ${BUCKET_NAME} \
  --region ${REGION}

# 2. Block all public access
aws s3api put-public-access-block \
  --bucket ${BUCKET_NAME} \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# 3. Enable Bucket Versioning
aws s3api put-bucket-versioning \
  --bucket ${BUCKET_NAME} \
  --versioning-configuration Status=Enabled

# 4. Enable SSE-S3 Default Encryption
aws s3api put-bucket-encryption \
  --bucket ${BUCKET_NAME} \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        },
        "BucketKeyEnabled": true
      }
    ]
  }'

# 5. Apply Lifecycle Configuration (Expire exports/ and imports/ after 90 days)
cat <<EOF > /tmp/s3-lifecycle.json
{
  "Rules": [
    {
      "ID": "ExpireExportsAfter90Days",
      "Filter": {
        "Prefix": "exports/"
      },
      "Status": "Enabled",
      "Expiration": {
        "Days": 90
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    },
    {
      "ID": "ExpireImportsAfter90Days",
      "Filter": {
        "Prefix": "imports/"
      },
      "Status": "Enabled",
      "Expiration": {
        "Days": 90
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket ${BUCKET_NAME} \
  --lifecycle-configuration file:///tmp/s3-lifecycle.json

# 6. Initialize folder prefixes
aws s3api put-object --bucket ${BUCKET_NAME} --key exports/
aws s3api put-object --bucket ${BUCKET_NAME} --key imports/
aws s3api put-object --bucket ${BUCKET_NAME} --key results/
aws s3api put-object --bucket ${BUCKET_NAME} --key backups/
```

---

## Step 7: IAM Policy, IAM Role & EC2 Instance Profile

To maintain zero hardcoded credentials in application source code, the EC2 instance obtains short-lived temporary security credentials via an IAM Instance Profile.

### 7.1 AWS Management Console

#### A. Create the Customer Managed Policy
1. Navigate to **IAM Console** > **Policies** > **Create policy**.
2. Select the **JSON** tab and paste the exact content of [iam-policy.json](file:///C:/Users/kadali%20bharat/.gemini/antigravity/scratch/college-mgmt-system/docs/iam-policy.json), replacing `{ACCOUNT_ID}` with your AWS Account ID and `{REGION}` with `us-east-1`.
3. Click **Next**.
4. **Policy name**: Enter `CMS-EC2-Policy`.
5. **Description**: Enter `Least-privilege policy for College Management System EC2 instances`.
6. Click **Create policy**.

#### B. Create the IAM Role
1. In IAM Console, click **Roles** > **Create role**.
2. **Trusted entity type**: Select **AWS service**.
3. **Use case**: Select **EC2**. Click **Next**.
4. Under **Add permissions**, search for and check `CMS-EC2-Policy`.
5. Click **Next**.
6. **Role name**: Enter `CMS-EC2-Role`.
7. **Description**: Enter `Allows EC2 instances to access CMS DynamoDB tables and S3 bucket`.
8. Click **Create role**. (AWS automatically generates the matching Instance Profile `CMS-EC2-Role` or `CMS-EC2-Profile`).

### 7.2 AWS CLI Commands
```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
REGION="us-east-1"

# 1. Create temporary policy file with actual parameters
sed "s/{ACCOUNT_ID}/${ACCOUNT_ID}/g; s/{REGION}/${REGION}/g" docs/iam-policy.json > /tmp/rendered-iam-policy.json

# 2. Create the IAM Policy
POLICY_ARN=$(aws iam create-policy \
  --policy-name CMS-EC2-Policy \
  --policy-document file:///tmp/rendered-iam-policy.json \
  --description "Least-privilege policy for College Management System EC2 instances" \
  --query 'Policy.Arn' \
  --output text)

echo "Created IAM Policy: ${POLICY_ARN}"

# 3. Create EC2 AssumeRole Trust Document
cat <<EOF > /tmp/ec2-trust-policy.json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# 4. Create IAM Role
aws iam create-role \
  --role-name CMS-EC2-Role \
  --assume-role-policy-document file:///tmp/ec2-trust-policy.json \
  --description "Allows EC2 instances to access CMS DynamoDB and S3"

# 5. Attach Policy to Role
aws iam attach-role-policy \
  --role-name CMS-EC2-Role \
  --policy-arn ${POLICY_ARN}

# Also attach AWS managed CloudWatchAgentServerPolicy for unified CloudWatch Agent logging
aws iam attach-role-policy \
  --role-name CMS-EC2-Role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy

# 6. Create Instance Profile and Add Role
aws iam create-instance-profile \
  --instance-profile-name CMS-EC2-Profile

aws iam add-role-to-instance-profile \
  --instance-profile-name CMS-EC2-Profile \
  --role-name CMS-EC2-Role
```

---

## Step 8: Launch Amazon EC2 Instance & Allocate Elastic IP

### 8.1 AWS Management Console
1. Navigate to **EC2 Console** > **Instances** > **Launch instances**.
2. **Name**: `cms-app-server`.
3. **Application and OS Images (Amazon Machine Image)**:
   - Select **Amazon Linux**.
   - AMI: **Amazon Linux 2023 AMI** (`al2023-ami-*-kernel-*-x86_64`).
4. **Instance type**: `t3.small` (2 vCPU, 2 GiB RAM).
5. **Key pair (login)**:
   - Click **Create new key pair**.
   - Key pair name: `cms-keypair`.
   - Key pair type: `RSA`. Private key file format: `.pem`.
   - Click **Create key pair** and save `cms-keypair.pem` securely.
6. **Network settings** (Click **Edit**):
   - **VPC**: Select `cms-vpc`.
   - **Subnet**: Select `cms-public-subnet (us-east-1a)`.
   - **Auto-assign public IP**: Enable.
   - **Firewall (security groups)**: Choose **Select existing security group**, pick `cms-ec2-sg`.
7. **Configure storage**:
   - `1x 20 GiB gp3` (Root Volume), Delete on Termination: `Yes`.
8. **Advanced details**:
   - **IAM instance profile**: Select `CMS-EC2-Profile`.
   - **Metadata version (IMDSv2)**: Select **V2 only (token required)**.
   - **Metadata response hop limit**: `2`.
9. Click **Launch instance**.
10. Allocate and Associate Elastic IP:
    - In left menu, navigate to **Elastic IPs** > **Allocate Elastic IP address**.
    - Tag: `Name` = `cms-eip`. Click **Allocate**.
    - Select the new Elastic IP > **Actions** > **Associate Elastic IP address**.
    - **Resource type**: Instance.
    - **Instance**: Select `cms-app-server`.
    - Click **Associate**.

### 8.2 AWS CLI Commands
```bash
# 1. Create SSH Key Pair
aws ec2 create-key-pair \
  --key-name cms-keypair \
  --key-type rsa \
  --key-format pem \
  --query 'KeyMaterial' \
  --output text > cms-keypair.pem

chmod 400 cms-keypair.pem

# 2. Retrieve latest Amazon Linux 2023 AMI ID
AMI_ID=$(aws ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameter.Value' \
  --output text)

echo "Launching AMI: ${AMI_ID}"

# 3. Launch EC2 Instance with IMDSv2 strictly enforced
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id ${AMI_ID} \
  --instance-type t3.small \
  --key-name cms-keypair \
  --subnet-id ${SUBNET_ID} \
  --security-group-ids ${SG_ID} \
  --iam-instance-profile Name=CMS-EC2-Profile \
  --metadata-options "HttpTokens=required,HttpPutResponseHopLimit=2,HttpEndpoint=enabled" \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=cms-app-server}]' \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "Created EC2 Instance ID: ${INSTANCE_ID}"
echo "Waiting for instance to enter running state..."
aws ec2 wait instance-running --instance-ids ${INSTANCE_ID}

# 4. Allocate and Associate Elastic IP
ALLOC_ID=$(aws ec2 allocate-address \
  --domain vpc \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=cms-eip}]' \
  --query 'AllocationId' \
  --output text)

ELASTIC_IP=$(aws ec2 describe-addresses \
  --allocation-ids ${ALLOC_ID} \
  --query 'Addresses[0].PublicIp' \
  --output text)

aws ec2 associate-address \
  --instance-id ${INSTANCE_ID} \
  --allocation-id ${ALLOC_ID}

echo "Assigned Elastic IP: ${ELASTIC_IP}"
```

---

## Step 9: Server Setup Runbook (Post-SSH Commands)

Connect to the instance via SSH:
```bash
ssh -i cms-keypair.pem ec2-user@${ELASTIC_IP}
```

Execute the following end-to-end command sequence directly on the Amazon Linux 2023 server:

```bash
# ------------------------------------------------------------------------------
# 1. Update system packages
# ------------------------------------------------------------------------------
sudo dnf update -y

# ------------------------------------------------------------------------------
# 2. Install Python 3.11, pip, git, and Nginx
# ------------------------------------------------------------------------------
sudo dnf install -y python3.11 python3.11-pip python3.11-devel git nginx gcc libffi-devel openssl-devel

# Verify versions
python3.11 --version
git --version
nginx -v

# ------------------------------------------------------------------------------
# 3. Create dedicated system service account and application directories
# ------------------------------------------------------------------------------
sudo useradd -r -s /sbin/nologin -d /opt/college-mgmt cms
sudo mkdir -p /opt/college-mgmt
sudo mkdir -p /var/log/college-mgmt
sudo mkdir -p /var/www/certbot

# Set directory permissions
sudo chown -R cms:cms /opt/college-mgmt
sudo chown -R cms:cms /var/log/college-mgmt
sudo chmod 755 /var/log/college-mgmt

# ------------------------------------------------------------------------------
# 4. Deploy Application Code
# ------------------------------------------------------------------------------
# Clone or copy repository into /opt/college-mgmt
sudo -u cms git clone https://github.com/your-org/college-mgmt-system.git /opt/college-mgmt
# Or if transferring locally:
# sudo chown -R cms:cms /opt/college-mgmt

cd /opt/college-mgmt

# ------------------------------------------------------------------------------
# 5. Create Virtual Environment and Install Dependencies
# ------------------------------------------------------------------------------
sudo -u cms python3.11 -m venv /opt/college-mgmt/venv
sudo -u cms /opt/college-mgmt/venv/bin/pip install --upgrade pip setuptools wheel
sudo -u cms /opt/college-mgmt/venv/bin/pip install -r /opt/college-mgmt/requirements.txt
sudo -u cms /opt/college-mgmt/venv/bin/pip install gunicorn eventlet

# ------------------------------------------------------------------------------
# 6. Configure Environment Variables File
# ------------------------------------------------------------------------------
sudo bash -c 'cat <<EOF > /etc/college-mgmt.env
# College Management System Production Configuration
FLASK_APP=wsgi.py
FLASK_ENV=production
DEBUG=False
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# AWS Configuration (Uses IAM Instance Profile - No Access Keys!)
AWS_REGION=us-east-1
S3_BUCKET_NAME=cms-college-data-YOUR_ACCOUNT_ID

# DynamoDB Table Names
DYNAMODB_TABLE_USERS=cms_users
DYNAMODB_TABLE_STUDENTS=cms_students
DYNAMODB_TABLE_ATTENDANCE=cms_attendance
DYNAMODB_TABLE_RESULTS=cms_results
DYNAMODB_TABLE_EXAMS=cms_exams
DYNAMODB_TABLE_QUESTIONS=cms_questions
DYNAMODB_TABLE_SUBMISSIONS=cms_submissions
DYNAMODB_TABLE_AUDIT_LOGS=cms_audit_logs

# Application Operational Parameters
CORS_ALLOWED_ORIGINS=*
SESSION_COOKIE_SECURE=True
REMEMBER_COOKIE_SECURE=True
EOF'

sudo chown root:cms /etc/college-mgmt.env
sudo chmod 640 /etc/college-mgmt.env

# ------------------------------------------------------------------------------
# 7. Initialize Database Tables and Default Admin Seed Data
# ------------------------------------------------------------------------------
# Replace YOUR_ACCOUNT_ID with actual AWS Account ID in /etc/college-mgmt.env first
sudo -u cms -E /opt/college-mgmt/venv/bin/python /opt/college-mgmt/scripts/create_tables.py
sudo -u cms -E /opt/college-mgmt/venv/bin/python /opt/college-mgmt/scripts/seed.py

# ------------------------------------------------------------------------------
# 8. Configure Systemd Service
# ------------------------------------------------------------------------------
sudo cp /opt/college-mgmt/systemd/college-mgmt.service /etc/systemd/system/college-mgmt.service
sudo systemctl daemon-reload
sudo systemctl enable college-mgmt.service
sudo systemctl start college-mgmt.service
sudo systemctl status college-mgmt.service --no-pager

# ------------------------------------------------------------------------------
# 9. Configure Nginx Reverse Proxy
# ------------------------------------------------------------------------------
sudo cp /opt/college-mgmt/nginx/college-mgmt.conf /etc/nginx/conf.d/college-mgmt.conf
# Note: Ensure /etc/nginx/nginx.conf includes conf.d/*.conf
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx
sudo systemctl status nginx --no-pager

# ------------------------------------------------------------------------------
# 10. Smoke Test Local Binding
# ------------------------------------------------------------------------------
curl -i http://localhost/health
```

---

## Step 10: Secure HTTPS with Let's Encrypt SSL

### 10.1 Install Certbot on Amazon Linux 2023
Amazon Linux 2023 installs Certbot via Python virtual environment:

```bash
# 1. Create a dedicated virtualenv for Certbot
sudo python3.11 -m venv /opt/certbot/
sudo /opt/certbot/bin/pip install --upgrade pip
sudo /opt/certbot/bin/pip install certbot certbot-nginx

# 2. Symlink certbot binary to system path
sudo ln -s /opt/certbot/bin/certbot /usr/bin/certbot

# 3. Obtain and automatically install certificate
# Replace your-domain.com with your registered DNS name pointing to the Elastic IP
sudo certbot --nginx -d college-mgmt.yourdomain.edu --non-interactive --agree-tos -m admin@yourdomain.edu

# 4. Automate Certificate Auto-Renewal via cron
echo "0 0,12 * * * root /usr/bin/certbot renew -q --post-hook 'systemctl reload nginx'" | sudo tee /etc/cron.d/certbot-renew
```

### 10.2 Production Alternative: AWS Certificate Manager (ACM) + ALB
For enterprise high-availability deployments:
1. Issue a free SSL/TLS certificate via **AWS Certificate Manager (ACM)**.
2. Provision an **Application Load Balancer (ALB)** in multiple public subnets.
3. Terminate SSL on the ALB (Port 443) with the ACM certificate.
4. Route unencrypted HTTP traffic from ALB to EC2 instances in private subnets on port 5000.
5. ALB handles seamless ACM certificate auto-renewal without server downtime or Certbot cron management.

---

## Step 11: CloudWatch Logs, Metrics & Alarms

### 11.1 Install and Configure the Unified CloudWatch Agent
```bash
# 1. Install Amazon CloudWatch Agent package
sudo dnf install -y amazon-cloudwatch-agent

# 2. Create CloudWatch Agent JSON configuration
sudo bash -c 'cat <<EOF > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/college-mgmt/gunicorn-error.log",
            "log_group_name": "/college-mgmt/application",
            "log_stream_name": "{instance_id}/gunicorn-error.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/college-mgmt/gunicorn-access.log",
            "log_group_name": "/college-mgmt/application",
            "log_stream_name": "{instance_id}/gunicorn-access.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/college-mgmt.access.log",
            "log_group_name": "/college-mgmt/nginx",
            "log_stream_name": "{instance_id}/nginx-access.log",
            "timezone": "UTC"
          },
          {
            "file_path": "/var/log/nginx/college-mgmt.error.log",
            "log_group_name": "/college-mgmt/nginx",
            "log_stream_name": "{instance_id}/nginx-error.log",
            "timezone": "UTC"
          }
        ]
      }
    }
  }
}
EOF'

# 3. Start and enable the CloudWatch Agent
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json
```

### 11.2 Create CloudWatch Alarms for High CPU and Instance Status Check

#### Console Navigation:
1. Navigate to **CloudWatch Console** > **Alarms** > **All alarms** > **Create alarm**.
2. **Select metric**: `EC2 > Per-Instance Metrics > CPUUtilization` for `cms-app-server`.
3. Threshold: Greater than `80%` for `5 minutes` (1 period of 300 seconds).
4. Notification: Send to SNS topic `cms-alerts` (Email subscription).
5. Repeat for `StatusCheckFailed`: metric `StatusCheckFailed` > `0` for 1 minute.

#### AWS CLI Commands:
```bash
# 1. Create SNS Topic for DevOps Alerts
SNS_TOPIC_ARN=$(aws sns create-topic \
  --name cms-devops-alerts \
  --query 'TopicArn' \
  --output text)

# Subscribe administrator email
aws sns subscribe \
  --topic-arn ${SNS_TOPIC_ARN} \
  --protocol email \
  --notification-endpoint devops-alerts@college.edu

# 2. Alarm 1: CPUUtilization > 80% for 5 Minutes
aws cloudwatch put-metric-alarm \
  --alarm-name "CMS-EC2-HighCPUUtilization" \
  --alarm-description "Triggers when EC2 CPU exceeds 80% for 5 continuous minutes" \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80.0 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=${INSTANCE_ID} \
  --evaluation-periods 1 \
  --alarm-actions ${SNS_TOPIC_ARN} \
  --unit Percent

# 3. Alarm 2: StatusCheckFailed > 0 (Hardware or VM failure)
aws cloudwatch put-metric-alarm \
  --alarm-name "CMS-EC2-StatusCheckFailed" \
  --alarm-description "Triggers immediately if EC2 underlying hardware or hypervisor fails" \
  --metric-name StatusCheckFailed \
  --namespace AWS/EC2 \
  --statistic Maximum \
  --period 60 \
  --threshold 0.0 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=InstanceId,Value=${INSTANCE_ID} \
  --evaluation-periods 1 \
  --alarm-actions ${SNS_TOPIC_ARN}
```

---

## Step 12: Infrastructure Verification & Teardown Procedures

### 12.1 Comprehensive Verification Commands
Run these commands from your local workstation or administrative bastion to confirm all components are active:

```bash
# 1. Verify VPC and Networking
aws ec2 describe-vpcs --vpc-ids ${VPC_ID} --query 'Vpcs[0].[VpcId,State,CidrBlock]' --output table
aws ec2 describe-subnets --subnet-ids ${SUBNET_ID} --query 'Subnets[0].[SubnetId,State,AvailableIpAddressCount]' --output table
aws ec2 describe-internet-gateways --internet-gateway-ids ${IGW_ID} --query 'InternetGateways[0].Attachments' --output table

# 2. Verify Security Groups
aws ec2 describe-security-groups --group-ids ${SG_ID} --query 'SecurityGroups[0].IpPermissions' --output json

# 3. Verify DynamoDB Tables & Continuous Backups
aws dynamodb list-tables --query 'TableNames[?starts_with(@, `cms_`)]' --output table
aws dynamodb describe-continuous-backups --table-name cms_users --query 'ContinuousBackupsDescription.PointInTimeRecoveryDescription'

# 4. Verify S3 Bucket & Versioning
aws s3 ls s3://cms-college-data-${ACCOUNT_ID}/
aws s3api get-bucket-versioning --bucket cms-college-data-${ACCOUNT_ID}

# 5. Verify IAM Instance Profile
aws iam get-instance-profile --instance-profile-name CMS-EC2-Profile --query 'InstanceProfile.[InstanceProfileName,Roles[0].RoleName]' --output table

# 6. Verify EC2 Server Public Access & Health
curl -i http://${ELASTIC_IP}/health
```

---

### 12.2 Clean-Up Order (Reverse Dependency Order)

To cleanly destroy all infrastructure without triggering AWS dependency errors, execute teardown in the exact sequence below:

```bash
# ------------------------------------------------------------------------------
# STEP 1: Terminate EC2 Instance
# ------------------------------------------------------------------------------
aws ec2 terminate-instances --instance-ids ${INSTANCE_ID}
aws ec2 wait instance-terminated --instance-ids ${INSTANCE_ID}

# ------------------------------------------------------------------------------
# STEP 2: Disassociate and Release Elastic IP
# ------------------------------------------------------------------------------
aws ec2 release-address --allocation-id ${ALLOC_ID}

# ------------------------------------------------------------------------------
# STEP 3: Detach and Delete Internet Gateway
# ------------------------------------------------------------------------------
aws ec2 detach-internet-gateway --internet-gateway-id ${IGW_ID} --vpc-id ${VPC_ID}
aws ec2 delete-internet-gateway --internet-gateway-id ${IGW_ID}

# ------------------------------------------------------------------------------
# STEP 4: Delete VPC Endpoints
# ------------------------------------------------------------------------------
ENDPOINT_IDS=$(aws ec2 describe-vpc-endpoints --filters "Name=vpc-id,Values=${VPC_ID}" --query 'VpcEndpoints[*].VpcEndpointId' --output text)
if [ -n "${ENDPOINT_IDS}" ]; then
  aws ec2 delete-vpc-endpoints --vpc-endpoint-ids ${ENDPOINT_IDS}
fi

# ------------------------------------------------------------------------------
# STEP 5: Delete Subnet and Route Table
# ------------------------------------------------------------------------------
aws ec2 delete-subnet --subnet-id ${SUBNET_ID}
aws ec2 delete-route-table --route-table-id ${RT_ID}

# ------------------------------------------------------------------------------
# STEP 6: Delete Security Group
# ------------------------------------------------------------------------------
aws ec2 delete-security-group --group-id ${SG_ID}

# ------------------------------------------------------------------------------
# STEP 7: Delete VPC
# ------------------------------------------------------------------------------
aws ec2 delete-vpc --vpc-id ${VPC_ID}

# ------------------------------------------------------------------------------
# STEP 8: Delete All 8 DynamoDB Tables
# ------------------------------------------------------------------------------
for tbl in cms_users cms_students cms_attendance cms_results cms_exams cms_questions cms_submissions cms_audit_logs; do
  aws dynamodb delete-table --table-name ${tbl}
  echo "Deleted table: ${tbl}"
done

# ------------------------------------------------------------------------------
# STEP 9: Empty and Delete S3 Bucket
# ------------------------------------------------------------------------------
aws s3 rm s3://cms-college-data-${ACCOUNT_ID} --recursive
# Delete all noncurrent object versions
aws s3api delete-objects --bucket cms-college-data-${ACCOUNT_ID} \
  --delete "$(aws s3api list-object-versions --bucket cms-college-data-${ACCOUNT_ID} --query='{Objects: Versions[].{Key:Key,VersionId:VersionId}}' --output json)" 2>/dev/null || true
aws s3api delete-bucket --bucket cms-college-data-${ACCOUNT_ID}

# ------------------------------------------------------------------------------
# STEP 10: Delete IAM Instance Profile, Role, and Policy
# ------------------------------------------------------------------------------
aws iam remove-role-from-instance-profile --instance-profile-name CMS-EC2-Profile --role-name CMS-EC2-Role
aws iam delete-instance-profile --instance-profile-name CMS-EC2-Profile
aws iam detach-role-policy --role-name CMS-EC2-Role --policy-arn ${POLICY_ARN}
aws iam detach-role-policy --role-name CMS-EC2-Role --policy-arn arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy
aws iam delete-role --role-name CMS-EC2-Role
aws iam delete-policy --policy-arn ${POLICY_ARN}

# ------------------------------------------------------------------------------
# STEP 11: Delete CloudWatch Alarms and Log Groups
# ------------------------------------------------------------------------------
aws cloudwatch delete-alarms --alarm-names "CMS-EC2-HighCPUUtilization" "CMS-EC2-StatusCheckFailed"
aws logs delete-log-group --log-group-name /college-mgmt/application 2>/dev/null || true
aws logs delete-log-group --log-group-name /college-mgmt/nginx 2>/dev/null || true
aws sns delete-topic --topic-arn ${SNS_TOPIC_ARN}

# ------------------------------------------------------------------------------
# STEP 12: Delete SSH Key Pair
# ------------------------------------------------------------------------------
aws ec2 delete-key-pair --key-name cms-keypair
rm -f cms-keypair.pem
```
