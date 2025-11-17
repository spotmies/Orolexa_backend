# 🦷 Dental AI API

A production-ready FastAPI backend for dental image analysis using Google's Gemini AI.

## 🚀 Features

- **AI-Powered Analysis**: Dental health assessment using Gemini 1.5 Flash
- **Authentication**: OTP-based login/registration with Twilio
- **Image Processing**: Multi-image upload with automatic thumbnail generation
- **Security**: JWT tokens, rate limiting, CORS protection
- **Production Ready**: Docker containerization, health checks, logging
- **Database**: SQLite/PostgreSQL with Alembic migrations

## 📋 Prerequisites

- Python 3.11+
- Docker & Docker Compose (for production)
- Twilio Account (for SMS OTP)
- Google Gemini API Key

## 🛠️ Installation

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Orolexa_backend
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp env.railway.example .env
   # Edit .env with your actual values
   ```

5. **Run database migrations (Alembic)**
```bash
alembic upgrade head
```

6. **Run the application**
   ```bash
   python -m app.main
   ```

### Production Deployment

1. **Using Docker Compose (Recommended)**
   ```bash
   # Copy environment template
   cp env.railway.example .env
   
   # Edit .env with production values
   nano .env
   
   # Deploy
   ./deploy.sh production
   ```

2. **Manual Docker deployment**
   ```bash
   docker build -t dental-ai-api .
   docker run -p 8000:8000 --env-file .env dental-ai-api
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode | `false` |
| `JWT_SECRET_KEY` | JWT secret key | Required |
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Required |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Required |
| `TWILIO_VERIFY_SERVICE_SID` | Twilio verify service SID | Required |
| `BASE_URL` | Base URL for image serving | `http://localhost:8000` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `*` |
| `DATABASE_URL` | Database connection string | `sqlite:///./app/orolexa.db` |

### Database Migrations

You can run Alembic on startup by setting an environment flag:

```bash
RUN_ALEMBIC_ON_STARTUP=true python -m app.main
```

Or manage migrations explicitly in CI/CD:

```bash
alembic upgrade head
```

### Production Settings

For production deployment, update these settings in `.env`:

```bash
DEBUG=false
JWT_SECRET_KEY=your-super-secret-key
ALLOWED_ORIGINS=https://yourdomain.com
BASE_URL=https://yourdomain.com
```

### Railway Deployment (Production)

Railway uses the provided `Dockerfile` and `railway.json` to build and run the API.

1. **Prepare secrets locally**
   ```bash
   cp env.railway.example .env
   # Fill in JWT, Twilio, Firebase, Gemini, etc.
   ```
2. **Connect the repo to Railway** (New Project → Deploy from GitHub).
3. **Add environment variables** under Project Settings → Variables (Railway already injects `PORT` and, if you add a Postgres service, `DATABASE_URL`).
4. **Deploy**. Railway runs `alembic upgrade head` before booting Gunicorn (see `railway.json`). Verify the deployment via:
   - `https://<your-app>.up.railway.app/health`
   - `https://<your-app>.up.railway.app/docs`

## 📚 API Documentation

### Base URL
```
http://localhost:8000
```

### Authentication Endpoints

#### Send OTP for Login
```http
POST /auth/login/send-otp
Content-Type: application/json

{
  "mobile_number": "+1234567890"
}
```

#### Verify OTP for Login
```http
POST /auth/login/verify-otp
Content-Type: application/json

{
  "mobile_number": "+1234567890",
  "otp_code": "123456"
}
```

### Analysis Endpoints

#### Analyze Dental Images
```http
POST /analysis/analyze-images
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data

file1: [required image file]
file2: [optional image file]
file3: [optional image file]
```

#### Get Analysis History
```http
GET /analysis/history
Authorization: Bearer <jwt_token>
```

### Profile Endpoints

#### Get User Profile
```http
GET /profile
Authorization: Bearer <jwt_token>
```

#### Update User Profile
```http
PUT /profile
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data

full_name: John Doe
profile_photo: [optional image file]
```

### Utility Endpoints

#### Health Check
```http
GET /health
```

## 🐳 Docker Commands

### Build Image
```bash
docker build -t dental-ai-api .
```

### Run Container
```bash
docker run -p 8000:8000 --env-file .env dental-ai-api
```

### Using Docker Compose
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

## 🔒 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Rate Limiting**: 60 requests per minute per IP
- **CORS Protection**: Configurable cross-origin resource sharing
- **Security Headers**: XSS protection, content type options
- **File Validation**: Type and size validation for uploads
- **Input Sanitization**: Protection against injection attacks

## 📊 Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

### Logs
```bash
# Docker logs
docker-compose logs -f

# Application logs
tail -f logs/app.log
```

## 🚀 Deployment Options

### 1. Docker Compose (Recommended)
```bash
./deploy.sh production
```

### 2. Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dental-ai-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: dental-ai-api
  template:
    metadata:
      labels:
        app: dental-ai-api
    spec:
      containers:
      - name: dental-ai-api
        image: dental-ai-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: dental-ai-secrets
              key: secret-key
```

### 3. Cloud Platforms

#### AWS ECS
```bash
aws ecs create-service \
  --cluster your-cluster \
  --service-name dental-ai-api \
  --task-definition dental-ai-api:1 \
  --desired-count 3
```

#### Google Cloud Run
```bash
gcloud run deploy dental-ai-api \
  --image gcr.io/your-project/dental-ai-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## 🔧 Development

### Running Tests
```bash
pytest tests/
```

### Code Formatting
```bash
black app/
isort app/
```

### Linting
```bash
flake8 app/
mypy app/
```

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📞 Support

For support, email support@yourdomain.com or create an issue in the repository.
