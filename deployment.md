# Finovo Deployment Guide

This document provides complete, step-by-step guidance for deploying the Finovo application. It covers both local development setup and a production-grade AWS deployment architecture using EC2, RDS, and Application Load Balancer (ALB).

## 1. Project Overview

Finovo is a full-stack personal finance application structured with the following architecture:
- **Frontend**: React Native (Expo) mobile application.
- **Backend**: Django REST Framework providing the API.
- **Relational Database**: Amazon RDS (PostgreSQL) for structured data (Users, Transactions, Budgets).
- **NoSQL Database**: Amazon DynamoDB for potentially scalable, flexible document storage.
- **Object Storage**: Amazon S3 for storing user avatars and file uploads.
- **Email Service**: SMTP server integration for sending verification OTPs and reports.

---

## 2. Environment Variables

Below is the list of all required environment variables for the application to run successfully. 

```env
# Core Django Config
SECRET_KEY=__________
DEBUG=__________
ALLOWED_HOSTS=__________

# Relational Database (RDS PostgreSQL)
DB_NAME=__________
DB_USER=__________
DB_PASSWORD=__________
DB_HOST=__________
DB_PORT=__________

# AWS Configuration (S3 / DynamoDB)
AWS_ACCESS_KEY_ID=__________
AWS_SECRET_ACCESS_KEY=__________
AWS_STORAGE_BUCKET_NAME=__________
DYNAMO_TABLE_NAME=__________
AWS_REGION=__________

# SMTP Email Service (OTP verification)
EMAIL_HOST=__________
EMAIL_PORT=__________
EMAIL_HOST_USER=__________
EMAIL_HOST_PASSWORD=__________
EMAIL_USE_TLS=__________
```

### Variable Explanations
- **Core Setup**: `SECRET_KEY` encrypts session data. `DEBUG` should remain `False` in production. `ALLOWED_HOSTS` contains the IP or domain name of your EC2/ALB.
- **Database**: Credentials pointing to your local database or remote AWS RDS PostgreSQL instance.
- **AWS Configuration**: IAM credentials and S3 bucket details for storing media attachments.
- **SMTP Service**: Email credentials required to securely send OTP verification codes to users.

---

## 3. Where to Store Credentials

To maintain security, adhere strictly to the following credential management practices:
- **Local Development**: Keep variables in a `.env` file at the root of your backend project directory.
- **Production (AWS)**: Inject variables directly into the server environment or utilize **AWS Secrets Manager** / **AWS Systems Manager Parameter Store** to feed variables securely into your instances.
- **SCM**: **Do NOT commit** your `.env` or secret keys to GitHub. Ensure `.env` is included in your `.gitignore`.

---

## 4. Local Development Setup

Follow these steps to quickly test the application backend locally:

1. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
2. **Install Requirements**
   ```bash
   pip install -r requirements.txt
   ```
3. **Setup `.env` File**
   Create a `.env` file inside the `backend/` directory using the template shown in Section 2.
4. **Run Migrations**
   ```bash
   python manage.py migrate
   ```
5. **Start Django Server**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## 5. Production Deployment (EC2)

Follow these steps for a complete production rollout on an AWS EC2 instance:

1. **Launch EC2 Instance**: Provision an Ubuntu Linux instance and connect via SSH.
2. **Install Dependencies**:
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv nginx libpq-dev postgresql-client
   ```
3. **Clone Repository**:
   ```bash
   git clone <your-repository-url>
   cd Finovo/backend
   ```
4. **Setup Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. **Add Environment Variables**:
   Create the `.env` file or export the required variables securely into the OS environment.
6. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```
7. **Collect Static Files**:
   ```bash
   python manage.py collectstatic --noinput
   ```

---

## 6. Gunicorn Setup

In production, avoid using `runserver`. Instead, use Gunicorn as the WSGI HTTP Server.

1. **Install Gunicorn**:
   ```bash
   pip install gunicorn
   ```
2. **Test Gunicorn Bind**:
   ```bash
   gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3
   ```
   *(Note: Adjust `core.wsgi` to match the exact name of your main Django project folder).*

For a permanent setup, configure Gunicorn to run as a `systemd` background service to execute autonomously.

---

## 7. NGINX Configuration

NGINX sits in front of Gunicorn, acting as a reverse proxy mapping port 80 traffic to port 8000.

1. Create a configuration file: `/etc/nginx/sites-available/finovo`
   ```nginx
   server {
       listen 80;
       server_name your_domain_or_IP;

       location = /favicon.ico { access_log off; log_not_found off; }
       
       location /static/ {
           root /home/ubuntu/Finovo/backend;
       }

       location /media/ {
           root /home/ubuntu/Finovo/backend;
       }

       location / {
           proxy_set_header Host $http_host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_pass http://127.0.0.1:8000;
       }
   }
   ```
2. **Enable and Restart**:
   ```bash
   sudo ln -s /etc/nginx/sites-available/finovo /etc/nginx/sites-enabled
   sudo systemctl restart nginx
   ```

---

## 8. Database Connection

To connect Django reliably to **AWS RDS (PostgreSQL)**:
- Navigate to AWS RDS and assure your PostgreSQL instance is publicly accessible OR correctly peered internally via a VPC.
- Set the `DB_HOST` in your environment variables to the **Endpoint URL** provided under RDS Connectivity & Security.
- **Security Groups**: You *must* authorize the RDS Security Group to allow inbound PostgreSQL traffic (port 5432) originating from the Security Group associated with your EC2 instance. 

---

## 9. S3 and DynamoDB Configuration

AWS Services are used for offloading heavy storage and high-speed read operations.

1. **Amazon S3**: Utilized for serving media files (user avatars, generic uploads).
   - Update Django settings to utilize `boto3` and `django-storages`.
   - **IAM Permissions**: The IAM User requires `s3:PutObject`, `s3:GetObject`, and `s3:ListBucket`.
2. **Amazon DynamoDB**: Utilized for serving pre-calculated "Analytics Projections".
   - The application automatically pushes calculated summaries to DynamoDB when `DYNAMO_TABLE_NAME` is present.
   - **IAM Permissions**: The IAM User requires `dynamodb:PutItem`, `dynamodb:GetItem`, and `dynamodb:UpdateItem` for the specified table.
   - **Schema**: Create a table with Partition Key `userId` (String) and Sort Key `monthLabel` (String).

---

## 10. SMTP Configuration

The application uses SMTP specifically to shoot OTP verifications upon sign-up alongside systemic reporting emails.
- If using Gmail: Enter `smtp.gmail.com` under `EMAIL_HOST` and `587` for `EMAIL_PORT`.
- Generate an "App Password" inside your Google Workspace / Gmail account to use as `EMAIL_HOST_PASSWORD`, keeping your master password safe.
- Enable `EMAIL_USE_TLS=True` unconditionally in your environment config.

---

## 11. Optional Improvements

For an enhanced and scalable production configuration, consider the following upgrades:
- **Redis Integration**: Drop the relational database for temporary OTP limits and embrace Redis cache logic. Storing OTP states directly into an in-memory datastore radically bolsters API performance.
- **Implement HTTPS via ALB**: Attach an AWS Application Load Balancer (ALB) to your EC2 instance, generate a free SSL certificate utilizing **AWS Certificate Manager (ACM)**, and force all HTTP port 80 traffic to explicitly redirect to secure port 443 ensuring all backend traffic is encrypted.

---

## 12. Common Errors & Fixes

- **SMTP not sending emails**:
  Make sure your `EMAIL_HOST_PASSWORD` isn't your login password but an explicitly generated App Password. Also, ensure your EC2 host isn't actively blocking outbound traffic on port 587 inherently via strict Outbound Security Group rules.
- **DB connection issues (`OperationalError`)**:
  Check your RDS precise inbound Security Groups. The target EC2 IP/Security Group must be explicitly whitelisted for port 5432. Double-check your `DB_HOST` guarantees it omits trailing spaces or database slashes.
- **Static files not loading (404s)**:
  Make universally sure you ran `python manage.py collectstatic`. Confirm your NGINX location `/static/` strictly maps to the absolute directory path on Linux, and that the `ubuntu` system user or `www-data` has `rx` (read and execute) permissions to access the path.
