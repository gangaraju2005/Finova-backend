# Finovo Backend Setup Guide

This guide covers the setup for the Django REST API in both local development and production environments.

## 1. Prerequisites
- **Python 3.10+**
- **PostgreSQL** (installed and running)
- **pip** (Python package manager)

---

## 2. Local Development Environment

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   - Copy the template: `cp .env.template .env`
   - Open `.env` and configure your local database credentials (e.g., `DB_NAME`, `DB_USER`, `DB_PASSWORD`).
   - Leave `AWS_ACCESS_KEY_ID` and `DYNAMO_TABLE_NAME` empty. The application will automatically detect this and fallback to standard RDS calculations for analytics.
   - Ensure `DEBUG=True` is set for development features.

5. **Run Migrations:**
   ```bash
   python manage.py migrate
   ```

6. **Start the Server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```
   The API will be available at `http://localhost:8000/api`.

---

## 3. Production Environment

When deploying to a server (e.g., AWS EC2), follow these critical configuration steps:

1. **Environment Variables:**
   - Set `DEBUG=False` in your production environment/`.env` file.
   - Specify your domain names in `ALLOWED_HOSTS` (comma-separated), e.g., `ALLOWED_HOSTS=api.finovo.app`.
   - Use a strong, unique `SECRET_KEY`.

2. **Database:**
   - Update `DB_HOST` to point to your **RDS PostgreSQL** endpoint.

3. **AWS Services (Production Optimization):**
   - **S3**: Provide `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_STORAGE_BUCKET_NAME`. The app will route all images here.
   - **DynamoDB**: Provide `DYNAMO_TABLE_NAME`. The application will store pre-calculated "Projections" here for high-speed analytics serving. When present, the app skips RDS calculation and reads directly from DynamoDB.

4. **Static Files:**
   - Run `python manage.py collectstatic` to gather all static assets for Nginx to serve.

5. **WSGI Server:**
   - Do **NOT** use `runserver` in production. Use **Gunicorn**:
     ```bash
     gunicorn core.wsgi:application --bind 0.0.0.0:8000
     ```

---

## 4. Common Troubleshooting
- **Database Connection Error**: Ensure PostgreSQL is running and your `.env` credentials match.
- **Email not sending**: Check your `EMAIL_HOST_USER` and ensure you are using an **App Password** for Gmail.
