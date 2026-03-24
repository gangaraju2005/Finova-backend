# Finovo Deployment Guide

Complete guide for deploying Finovo Backend on AWS with Docker, self-hosted GitHub Actions runner, and automated CI/CD.

## 1. Architecture

```
  GitHub (push to main)
        │
        ▼
  ┌─────────────────────┐
  │ Self-Hosted Runner   │ ← runs ON the EC2 instance
  │ git pull → docker    │
  │ build → swap         │
  └──────────┬──────────┘
             │
    Internet  │
        │     │
   ┌────▼────┐│
   │   ALB   ││  (public subnets, HTTPS via ACM)
   └────┬────┘│
        │     │
  ┌─────▼─────▼────┐
  │  Target Group   │  health check: GET /api/health/
  └────────┬────────┘
           │ Port 8000
   ┌───────▼───────┐
   │  EC2 (private  │  Docker + GH Runner
   │   subnet)      │  Port 8000
   └──┬──────────┬──┘
      │          │
┌─────▼───┐  ┌──▼───────────┐
│ RDS PG   │  │ DynamoDB     │
│ (private)│  │ projections  │
│ 5432     │  └──────────────┘
└──────────┘
      │
┌─────▼─────┐
│  S3 Bucket │  avatars / media
└────────────┘
```

---

## 2. Environment Variables

See `.env.production` for a full template. Key variables:

```env
SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS
DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_REGION
DYNAMO_TABLE_NAME=finovo_projections
EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS
```

**Store credentials**: `.env` file on EC2 at `/home/ubuntu/.env` (referenced by Docker `--env-file`).

---

## 3. AWS Infrastructure Setup

### Step 1: VPC + Networking

1. **Create VPC**: `10.0.0.0/16`
2. **Subnets** (2 AZs):

   | Subnet | CIDR | Type | AZ |
   |--------|------|------|----|
   | `finovo-public-1` | `10.0.1.0/24` | Public | us-east-1a |
   | `finovo-public-2` | `10.0.2.0/24` | Public | us-east-1b |
   | `finovo-private-1` | `10.0.3.0/24` | Private | us-east-1a |
   | `finovo-private-2` | `10.0.4.0/24` | Private | us-east-1b |

3. **Internet Gateway** → attach to VPC
4. **NAT Gateway** → create in `finovo-public-1` with Elastic IP
5. **Route Tables**:
   - Public RT: `0.0.0.0/0 → IGW` → associate with public subnets
   - Private RT: `0.0.0.0/0 → NAT GW` → associate with private subnets

> **Note**: NAT Gateway is critical — EC2 needs outbound internet for: GitHub runner communication, Docker Hub pulls, SMTP email, pip installs.

### Step 2: Security Groups

| SG Name | Inbound Rules | Purpose |
|---------|---------------|---------|
| `finovo-alb-sg` | 80 from `0.0.0.0/0`, 443 from `0.0.0.0/0` | ALB |
| `finovo-ec2-sg` | 8000 from `finovo-alb-sg` only | EC2 |
| `finovo-rds-sg` | 5432 from `finovo-ec2-sg` only | RDS |

### Step 3: RDS PostgreSQL

1. **RDS → Create Database** → PostgreSQL 16
2. **Instance**: `db.t3.micro` (Free Tier eligible)
3. **DB Identifier**: `finovo-prod`
4. **Master Username**: `finovo_admin`
5. **VPC**: Your VPC, **Subnet Group**: both private subnets
6. **Security Group**: `finovo-rds-sg`
7. **Public Access**: **No**
8. **Initial DB Name**: `finovo_prod`

Copy the **Endpoint** → `DB_HOST` in `.env`.

### Step 4: S3 Bucket

1. **Name**: `finovo-media-prod` (globally unique)
2. **Region**: `us-east-1`
3. **Bucket Policy** (public read for avatars):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Principal": "*",
       "Action": "s3:GetObject",
       "Resource": "arn:aws:s3:::finovo-media-prod/*"
     }]
   }
   ```

### Step 5: DynamoDB Table

1. **Table Name**: `finovo_projections`
2. **Partition Key**: `userId` (String)
3. **Sort Key**: `monthLabel` (String)
4. **Capacity**: On-demand

### Step 6: IAM User for Backend

Create IAM user `finovo-backend-service` with this policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::finovo-media-prod", "arn:aws:s3:::finovo-media-prod/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"],
      "Resource": "arn:aws:dynamodb:us-east-1:ACCOUNT_ID:table/finovo_projections"
    }
  ]
}
```
Create **Access Keys** → `.env` as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.

### Step 7: EC2 Instance

1. **AMI**: Ubuntu 24.04 LTS
2. **Instance Type**: `t3.small`
3. **Subnet**: `finovo-private-1`
4. **Security Group**: `finovo-ec2-sg`
5. **IAM Role**: Attach `AmazonSSMManagedInstanceCore` for SSM access
6. **No public IP**

**Connect via SSM:**
```bash
aws ssm start-session --target i-xxxxxxxxxxxx
```

### Step 8: EC2 Setup — Docker + GitHub Runner

SSH into EC2 via SSM, then run the setup script:

```bash
# Clone repo (first time only)
git clone https://github.com/KarthikHT-DEV/Finovo_backend.git
cd Finovo_backend

# Create .env file
nano /home/ubuntu/.env
# (paste values from .env.production, fill in real values)

# Run the runner setup script
chmod +x scripts/setup-runner.sh
./scripts/setup-runner.sh
```

The script will:
1. Install Docker
2. Download GitHub Actions runner
3. Ask you for a runner token (get it from your repo → Settings → Actions → Runners → New)
4. Register and start the runner as a systemd service

### Step 9: ALB + Target Group

1. **Create Target Group** (`finovo-tg`):
   - Protocol: HTTP, Port: 8000
   - Health check: `/api/health/` (interval: 30s, threshold: 2)
   - Register: your EC2 instance

2. **Create ALB** (`finovo-alb`):
   - Internet-facing, both public subnets
   - Security Group: `finovo-alb-sg`
   - Listener: HTTP:80 → forward to `finovo-tg`

3. **Test**: `curl http://<alb-dns>/api/health/`

### Step 10: HTTPS (Recommended)

1. **ACM → Request Certificate** for `api.yourdomain.com`
2. Validate via DNS
3. **ALB → Add HTTPS:443 listener** → forward to `finovo-tg`, select ACM cert
4. **Edit HTTP:80** → redirect to HTTPS:443
5. Point domain DNS to ALB

---

## 4. CI/CD Pipeline

The pipeline at `.github/workflows/deploy.yml` runs automatically on push to `main`:

```
Push to main
  → Self-hosted runner (on EC2) picks up job
  → git checkout latest code
  → docker stop old container
  → docker build new image
  → docker run new container (--env-file /home/ubuntu/.env)
  → python manage.py migrate
  → Health check (curl /api/health/)
  → Prune old images
```

**No ECR, no SSH, no external access needed.** The runner sits on the EC2 and does everything locally.

### First Manual Deploy

Before the pipeline takes over, do the first deploy manually:
```bash
cd ~/Finovo_backend
docker build -t finovo-backend:latest .
docker run -d --name finovo-backend --restart=always --env-file /home/ubuntu/.env -p 8000:8000 finovo-backend:latest
docker exec finovo-backend python manage.py migrate --noinput
```

---

## 5. SMTP Configuration

- `EMAIL_HOST=smtp.gmail.com`, `EMAIL_PORT=587`, `EMAIL_USE_TLS=True`
- Use a Gmail **App Password** (not your login password) for `EMAIL_HOST_PASSWORD`
- EC2 outbound SG must allow port 587 (default allows all outbound)

---

## 6. Common Errors & Fixes

| Error | Fix |
|-------|-----|
| **Runner offline** | Check NAT Gateway is working. Runner needs outbound to `github.com` |
| **Docker build fails** | Check NAT Gateway. Docker needs to pull base images from Docker Hub |
| **SMTP not sending** | Use App Password. Check outbound port 587 |
| **DB connection refused** | RDS SG must allow 5432 from EC2 SG |
| **502 from ALB** | EC2 SG must allow 8000 from ALB SG. Check `docker ps` |
| **Target unhealthy** | `curl localhost:8000/api/health/` on EC2. Check container is running |

---

## 7. Useful Commands

```bash
# Docker
docker ps                              # Running containers
docker logs finovo-backend -f          # Live logs
docker restart finovo-backend          # Restart
docker exec -it finovo-backend bash    # Shell into container

# GitHub Runner
sudo systemctl status actions.runner.* # Runner status
sudo systemctl restart actions.runner.* # Restart runner

# Database (inside container)
docker exec finovo-backend python manage.py migrate
docker exec finovo-backend python manage.py createsuperuser
docker exec finovo-backend python manage.py check --deploy
```
