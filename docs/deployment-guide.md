# Deployment and Maintenance Guide: College Management System

This guide outlines standard operating procedures for initial deployment, zero-downtime updates, emergency rollbacks, and operational troubleshooting for the College Management System on AWS EC2.

---

## 1. Initial Production Deployment

### 1.1 Prerequisites
- Running EC2 instance configured with `CMS-EC2-Profile` IAM role.
- Security group allowing ports 22, 80, and 443.
- Elastic IP associated with the instance.
- SSH private key (`cms-keypair.pem`) on your local machine with `chmod 400`.

### 1.2 Step-by-Step Installation Runbook

```bash
# Connect to your EC2 instance
ssh -i cms-keypair.pem ec2-user@<ELASTIC_IP>

# ------------------------------------------------------------------------------
# Step 1: Base Operating System Preparation
# ------------------------------------------------------------------------------
sudo dnf update -y
sudo dnf install -y python3.11 python3.11-pip python3.11-devel git nginx gcc libffi-devel openssl-devel

# Create non-privileged system user for the application
sudo useradd -r -s /sbin/nologin -d /opt/college-mgmt cms

# Create application and logging directories
sudo mkdir -p /opt/college-mgmt
sudo mkdir -p /var/log/college-mgmt
sudo chown -R cms:cms /opt/college-mgmt /var/log/college-mgmt
sudo chmod 755 /var/log/college-mgmt

# ------------------------------------------------------------------------------
# Step 2: Clone Application Repository
# ------------------------------------------------------------------------------
sudo -u cms git clone https://github.com/your-org/college-mgmt-system.git /opt/college-mgmt
cd /opt/college-mgmt

# ------------------------------------------------------------------------------
# Step 3: Setup Python Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
sudo -u cms python3.11 -m venv /opt/college-mgmt/venv
sudo -u cms /opt/college-mgmt/venv/bin/pip install --upgrade pip setuptools wheel
sudo -u cms /opt/college-mgmt/venv/bin/pip install -r /opt/college-mgmt/requirements.txt
sudo -u cms /opt/college-mgmt/venv/bin/pip install gunicorn eventlet

# ------------------------------------------------------------------------------
# Step 4: Configure Production Environment Variables
# ------------------------------------------------------------------------------
sudo cp .env.example /etc/college-mgmt.env
# Edit the configuration file with production secrets
sudo nano /etc/college-mgmt.env
```

Ensure `/etc/college-mgmt.env` contains the required production values:
```ini
FLASK_APP=wsgi.py
FLASK_ENV=production
DEBUG=False
SECRET_KEY=generate_with_openssl_rand_hex_32
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32

AWS_REGION=us-east-1
S3_BUCKET_NAME=cms-college-data-YOUR_ACCOUNT_ID

DYNAMODB_TABLE_USERS=cms_users
DYNAMODB_TABLE_STUDENTS=cms_students
DYNAMODB_TABLE_ATTENDANCE=cms_attendance
DYNAMODB_TABLE_RESULTS=cms_results
DYNAMODB_TABLE_EXAMS=cms_exams
DYNAMODB_TABLE_QUESTIONS=cms_questions
DYNAMODB_TABLE_SUBMISSIONS=cms_submissions
DYNAMODB_TABLE_AUDIT_LOGS=cms_audit_logs

CORS_ALLOWED_ORIGINS=*
```

Secure the environment file:
```bash
sudo chown root:cms /etc/college-mgmt.env
sudo chmod 640 /etc/college-mgmt.env
```

```bash
# ------------------------------------------------------------------------------
# Step 5: Initialize DynamoDB Tables & Default Seed Records
# ------------------------------------------------------------------------------
sudo -u cms -E /opt/college-mgmt/venv/bin/python scripts/create_tables.py
sudo -u cms -E /opt/college-mgmt/venv/bin/python scripts/seed.py

# ------------------------------------------------------------------------------
# Step 6: Install and Start Systemd Service
# ------------------------------------------------------------------------------
sudo cp systemd/college-mgmt.service /etc/systemd/system/college-mgmt.service
sudo systemctl daemon-reload
sudo systemctl enable college-mgmt.service
sudo systemctl start college-mgmt.service
sudo systemctl status college-mgmt.service --no-pager

# ------------------------------------------------------------------------------
# Step 7: Install and Start Nginx
# ------------------------------------------------------------------------------
sudo cp nginx/college-mgmt.conf /etc/nginx/conf.d/college-mgmt.conf
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl start nginx

# ------------------------------------------------------------------------------
# Step 8: Verify Deployment Health
# ------------------------------------------------------------------------------
curl -i http://localhost/health
```

---

## 2. Zero-Downtime Application Update Procedure

When pushing updates or bug fixes to production, execute the following staged deployment to maintain uninterrupted WebSocket and HTTP availability:

```bash
cd /opt/college-mgmt

# 1. Fetch latest changes from the release branch
sudo -u cms git fetch origin main
sudo -u cms git pull origin main

# 2. Update Python dependencies if requirements changed
sudo -u cms /opt/college-mgmt/venv/bin/pip install -r requirements.txt

# 3. Execute any new database index migrations or data backfills
sudo -u cms -E /opt/college-mgmt/venv/bin/python scripts/migrate_tables.py

# 4. Gracefully restart Gunicorn eventlet worker
# Gunicorn will finish active requests before replacing the worker
sudo systemctl restart college-mgmt

# 5. Reload Nginx to flush any proxy cache or apply updated server rules
sudo nginx -t && sudo systemctl reload nginx

# 6. Verify health endpoint
curl -f http://localhost/health || echo "HEALTH CHECK FAILED!"

# 7. Confirm WebSocket handshake and live service
sudo systemctl status college-mgmt --no-pager
```

---

## 3. Instant Rollback Runbook

If a newly deployed commit introduces critical bugs or service degradation, immediately roll back to the previously known stable release:

```bash
cd /opt/college-mgmt

# 1. Review recent git commit history
git log --oneline -10

# 2. Revert code to stable commit or tag (e.g., v1.4.2 or commit hash a1b2c3d)
sudo -u cms git checkout <STABLE_COMMIT_HASH>

# 3. Re-install virtual environment dependencies to match previous state
sudo -u cms /opt/college-mgmt/venv/bin/pip install -r requirements.txt

# 4. Restart the systemd service
sudo systemctl restart college-mgmt

# 5. Check health status immediately
curl -i http://localhost/health

# 6. Verify error logs
sudo tail -n 50 /var/log/college-mgmt/gunicorn-error.log
```

---

## 4. Operational Monitoring & Diagnostics

### 4.1 Real-Time Log Streams
```bash
# Real-time Gunicorn application errors
sudo tail -f /var/log/college-mgmt/gunicorn-error.log

# Real-time Gunicorn access logs
sudo tail -f /var/log/college-mgmt/gunicorn-access.log

# Real-time Nginx web server access logs
sudo tail -f /var/log/nginx/college-mgmt.access.log

# Real-time Nginx web server error logs
sudo tail -f /var/log/nginx/college-mgmt.error.log

# Systemd service unit logs (journald)
sudo journalctl -u college-mgmt -f -n 100
```

### 4.2 Health & Status Checks
```bash
# Check if Gunicorn is listening on port 5000
sudo ss -tulpn | grep 5000

# Check if Nginx is listening on ports 80 and 443
sudo ss -tulpn | grep -E ':80|:443'

# Test local HTTP health check
curl -s http://127.0.0.1:5000/health | jq .

# Test public endpoint through Nginx reverse proxy
curl -s http://localhost/health | jq .
```

### 4.3 Common Troubleshooting Scenarios

| Issue | Root Cause | Resolution |
|---|---|---|
| **HTTP 502 Bad Gateway** | Gunicorn process is stopped or crashed on startup. | Run `sudo systemctl status college-mgmt` and inspect `/var/log/college-mgmt/gunicorn-error.log`. Verify Python syntax and environment variables. |
| **HTTP 403 Forbidden on DynamoDB** | IAM role missing or insufficient permissions. | Verify IAM Instance Profile: `curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/iam/info`. Ensure policy allows action on the specific table ARN. |
| **WebSocket connection fails** | Missing `Upgrade` header or proxy buffering enabled. | Verify `proxy_set_header Upgrade $http_upgrade;` and `proxy_buffering off;` exist in `/etc/nginx/conf.d/college-mgmt.conf`. |
| **CSV upload fails (HTTP 413)** | Request body exceeds Nginx default 1MB limit. | Confirm `client_max_body_size 10M;` is present in Nginx server block. Run `sudo nginx -t && sudo systemctl reload nginx`. |
| **Gunicorn eventlet monkey patch warning** | `eventlet.monkey_patch()` called late. | Ensure `import eventlet; eventlet.monkey_patch()` is at the very top of `wsgi.py` before importing Flask or Boto3. |
