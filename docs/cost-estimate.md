# AWS Monthly Cost Estimation & Architectural Roadmap

This document outlines the projected monthly AWS infrastructure operational expenses for the College Management System (CMS), based on current production requirements in the `us-east-1` (N. Virginia) region, followed by a roadmap of future architectural evolutions.

---

## 1. Baseline Cost Breakdown (100 Students, 5 Faculty)

### 1.1 Workload Assumptions
- **User Base**: 100 Students, 5 Faculty members, 2 Administrators.
- **Monthly Usage Profile**:
  - Daily active attendance checks (20 working days/month).
  - Weekly MCQ quizzes and semester final exams.
  - S3 document exports and report card PDF generations: ~5 GB active storage.
  - Application log volume: ~2 GB/month compressed in CloudWatch.

---

### 1.2 Itemized Monthly Infrastructure Cost Table

| Service / Resource | Specification / Configuration | Estimated Monthly Cost (USD) |
|---|---|---|
| **Amazon EC2** | 1x `t3.small` On-Demand instance (2 vCPU, 2 GiB RAM, 730 hrs/mo @ $0.0208/hr) | **$15.18** |
| **Amazon EBS** | 20 GB General Purpose SSD (`gp3`) @ $0.08/GB-month (3,000 IOPS, 125 MB/s included) | **$1.60** |
| **Amazon DynamoDB** | On-Demand (PAY_PER_REQUEST):<br>• Write Request Units: ~300,000 WRU ($0.375)<br>• Read Request Units: ~1,500,000 RRU ($0.375)<br>• Storage: < 1 GB (Within AWS Free Tier 25 GB)<br>• Point-In-Time Recovery (PITR): ~$0.20/GB-month | **$0.95** |
| **Amazon S3** | Standard Storage:<br>• 5 GB Storage @ $0.023/GB ($0.12)<br>• 5,000 PUT/POST requests @ $0.005/1000 ($0.03)<br>• 25,000 GET requests @ $0.0004/1000 ($0.01) | **$0.16** |
| **VPC Gateway Endpoints** | S3 & DynamoDB Gateway Endpoints | **$0.00** *(Always Free)* |
| **Elastic IP** | 1x IPv4 Elastic IP associated with active running EC2 instance | **$0.00** *(No charge while attached)* |
| **AWS Data Transfer** | Internal AWS VPC endpoints: $0.00<br>Public egress to students: ~15 GB/mo (First 100 GB/mo free under AWS Free Tier) | **$0.00** |
| **Amazon CloudWatch** | • 2 Alarms (CPU & StatusCheck) @ $0.10/alarm ($0.20)<br>• Log Ingestion: 2 GB @ $0.50/GB ($1.00)<br>• Log Storage: 2 GB @ $0.03/GB ($0.06) | **$1.26** |
| **AWS Certificate Manager** | Let's Encrypt / ACM SSL Certificates | **$0.00** *(Free)* |
| **TOTAL ESTIMATED MONTHLY COST** | **Baseline Continuous Operational Cost** | **~$19.15 / month** |

---

## 2. Usage Tiers Comparison (Low / Medium / High)

| Cost Component | Low Usage<br>*(Dev / Pilot: 50 Users)* | Medium Usage *(Baseline)*<br>*(100-500 Users)* | High Usage<br>*(University Scale: 2,500+ Users)* |
|---|---|---|---|
| **Compute (EC2)** | $15.18 (`t3.small`) | $15.18 (`t3.small`) | $60.74 (`t3.xlarge` or 2x `t3.medium`) |
| **Storage (EBS)** | $1.60 (20 GB `gp3`) | $1.60 (20 GB `gp3`) | $8.00 (100 GB `gp3`) |
| **DynamoDB (On-Demand)** | $0.40 | $0.95 | $12.50 |
| **S3 Storage & Requests** | $0.05 | $0.16 | $3.50 |
| **CloudWatch Observability** | $0.80 | $1.26 | $5.20 |
| **Data Egress (Public)** | $0.00 | $0.00 | $18.00 (~200 GB egress) |
| **Total Monthly Projection** | **~$18.03 / month** | **~$19.15 / month** | **~$107.94 / month** |

---

## 3. Future Architectural Evolutions & Roadmap

As the user base expands across academic departments, the infrastructure should evolve from a single-node server to an enterprise cloud architecture.

### 1. Application Load Balancer (ALB) + Auto Scaling Group (ASG)
- **Design**: Replace the single EC2 instance with an Auto Scaling Group spanning multiple Availability Zones (`us-east-1a`, `us-east-1b`), fronted by an Application Load Balancer.
- **Benefit**: Eliminates single point of failure (SPOF), handles sudden traffic spikes during exam submission windows, and enables zero-downtime rolling deployments.

### 2. Multi-Tier VPC with Private Subnets and NAT Gateway
- **Design**: Relocate EC2 application servers into private subnets with no public IP addresses. Route outbound internet traffic through an AWS NAT Gateway.
- **Benefit**: Hardens security by completely removing backend compute resources from the public internet, satisfying FERPA and institutional compliance standards.

### 3. Amazon Cognito for Identity & Access Management
- **Design**: Migrate authentication and user sessions from custom bcrypt/JWT routines to Amazon Cognito User Pools and Identity Pools.
- **Benefit**: Provides built-in Multi-Factor Authentication (MFA), password rotation policies, brute-force protection, and OAuth2/SAML integration with institutional Single Sign-On (SSO) systems (e.g., Google Workspace, Microsoft Entra ID).

### 4. Amazon ElastiCache for Redis (Socket.IO Cluster Bus)
- **Design**: Deploy a Redis cluster using Amazon ElastiCache to serve as the message broker (`redis-adapter`) for Socket.IO.
- **Benefit**: Enables WebSocket broadcasting and real-time state synchronization across multiple horizontally scaled EC2 instances.

### 5. Amazon CloudFront Content Delivery Network (CDN)
- **Design**: Place CloudFront CDN in front of Nginx and S3.
- **Benefit**: Caches static assets (CSS, JavaScript, logos, PDF templates) at edge locations worldwide, offloading up to 80% of HTTP traffic from EC2 and reducing page load times to under 100ms.

### 6. Amazon Aurora Serverless v2 Alternative
- **Design**: For complex relational queries (cross-semester GPA calculations, multi-table joins), evaluate Amazon Aurora PostgreSQL Serverless v2.
- **Benefit**: Automatically scales database compute in granular 0.5 ACU increments, providing ACID relational transactional safety with automated failover.

### 7. AWS WAF (Web Application Firewall)
- **Design**: Attach AWS WAF to the CloudFront CDN or ALB with AWS Managed Rules (Common Rule Set, SQL Injection Protection, Rate-based limits).
- **Benefit**: Blocks automated scrapers, brute-force credential stuffing, and application-layer DDoS attacks before they reach backend compute.

### 8. Microservices Decoupling for Exam Engine
- **Design**: Decouple the real-time exam taking and auto-grading engine into an isolated microservice running on AWS Fargate (Serverless Containers).
- **Benefit**: Guarantees that general student portal traffic does not starve CPU or memory resources during simultaneous examination submissions.

### 9. Event-Driven Asynchronous Processing with AWS Lambda & SQS
- **Design**: Offload heavy computational tasks (generating 500 individual student grade sheet PDFs, bulk CSV parsing, automated attendance anomaly detection) to AWS Lambda functions triggered by SQS queues.
- **Benefit**: Keeps Gunicorn worker event loops free and responsive, preventing long-running HTTP timeouts.

### 10. Multi-Region Disaster Recovery with DynamoDB Global Tables
- **Design**: Replicate DynamoDB tables across `us-east-1` and `us-west-2` using DynamoDB Global Tables with automated Route 53 health check DNS failover.
- **Benefit**: Achieves enterprise Recovery Point Objective (RPO) < 1 second and Recovery Time Objective (RTO) < 1 minute in the event of an AWS regional outage.
