# 🚂 Railway Deployment Guide

## Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Repository**: Your code should be in a GitHub repository
3. **Environment Variables**: Already configured in Railway

## 🚀 Quick Deployment

### Step 1: Connect to Railway

1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository

### Step 2: Configure Environment Variables

Railway will automatically detect your environment variables. Make sure these are set in your Railway project:

```bash
# Required Variables (Already configured)
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_VERIFY_SERVICE_SID=your_twilio_verify_service_sid
JWT_SECRET_KEY=your_jwt_secret_key
GEMINI_API_KEY=your_gemini_api_key

# Optional Variables (Set these for production)
BASE_URL=https://your-railway-app.railway.app
ALLOWED_ORIGINS=https://your-frontend-domain.com
DEBUG=false

# Image storage (Railway Bucket) - reference the bucket's variables
# (replace "Bucket" with your bucket service name)
S3_ENDPOINT_URL=${{Bucket.ENDPOINT}}
S3_REGION=${{Bucket.REGION}}
S3_BUCKET_NAME=${{Bucket.BUCKET}}
AWS_ACCESS_KEY_ID=${{Bucket.ACCESS_KEY_ID}}
AWS_SECRET_ACCESS_KEY=${{Bucket.SECRET_ACCESS_KEY}}
# S3_ADDRESSING_STYLE=virtual   # optional, "path" for other S3 providers
```

When all S3 variables are set, profile, analysis and thumbnail images are stored in the bucket
(keys `profiles/...`, `thumbnails/...`) instead of the container's ephemeral disk. URLs are
unchanged (`/api/auth/images/...`) and the API proxies the bytes since Railway buckets are private.
If the variables are missing, local disk (`UPLOAD_DIR`) is used as before.

### Step 3: Deploy

1. Railway will automatically build and deploy your application
2. The build process uses the `Dockerfile`
3. Railway will assign a URL like: `https://your-app-name.railway.app`

### Step 4: Verify Deployment

1. Check the deployment logs in Railway dashboard
2. Test the health endpoint: `https://your-app-name.railway.app/health`
3. Test your API endpoints

## 🔧 Railway-Specific Configuration

### Environment Variables

Railway automatically provides:
- `PORT`: The port your app should listen on
- `DATABASE_URL`: If you add a PostgreSQL database
- `RAILWAY_ENVIRONMENT`: Set to "true" in Railway

### Database Options

#### Option 1: SQLite (Default)
- Uses local SQLite database
- Data persists in the container
- Good for development/testing

#### Option 2: PostgreSQL (Recommended for Production)
1. Add PostgreSQL plugin in Railway
2. Railway will automatically set `DATABASE_URL`
3. Update your models to use PostgreSQL

### File Storage

**Important**: Railway containers are ephemeral. For production:

1. **Use External Storage**: Consider using AWS S3, Google Cloud Storage, or similar
2. **Database Storage**: Store file paths in database, not actual files
3. **Temporary Storage**: Current setup works for development

## 📊 Monitoring

### Railway Dashboard
- View logs in real-time
- Monitor resource usage
- Check deployment status

### Health Checks
- Railway automatically checks `/health` endpoint
- Configured in `railway.json`

### Logs
```bash
# View logs in Railway dashboard
# Or use Railway CLI
railway logs
```

## 🔒 Security Considerations

### CORS Configuration
Update `ALLOWED_ORIGINS` in Railway environment variables:
```bash
ALLOWED_ORIGINS=https://your-frontend-domain.com,https://www.your-frontend-domain.com
```

### Base URL
Set `BASE_URL` to your Railway app URL:
```bash
BASE_URL=https://your-app-name.railway.app
```

## 🚀 Production Checklist

- ✅ **Environment Variables**: All required variables set
- ✅ **CORS**: Frontend domain added to allowed origins
- ✅ **Base URL**: Set to Railway app URL
- ✅ **Database**: Consider PostgreSQL for production
- ✅ **File Storage**: Plan for external storage
- ✅ **Monitoring**: Health checks enabled
- ✅ **Security**: JWT secret key is secure

## 🔧 Troubleshooting

### Common Issues

1. **Build Fails**
   - Check Railway build logs
   - Ensure all dependencies are in `requirements.txt`
   - Verify Dockerfile is correct

2. **App Won't Start**
   - Check Railway logs
   - Verify PORT environment variable
   - Ensure health check endpoint works

3. **Database Issues**
   - Check DATABASE_URL format
   - Verify database connection
   - Check migration logs

4. **Environment Variables**
   - Verify all required variables are set
   - Check variable names (case-sensitive)
   - Restart deployment after adding variables

### Useful Commands

```bash
# Railway CLI (if installed)
railway login
railway link
railway up
railway logs
railway status
```

## 📞 Support

- **Railway Documentation**: [docs.railway.app](https://docs.railway.app)
- **Railway Discord**: [discord.gg/railway](https://discord.gg/railway)
- **GitHub Issues**: Create an issue in your repository

## 🎉 Success!

Once deployed, your API will be available at:
```
https://your-app-name.railway.app
```

Test endpoints:
- Health: `https://your-app-name.railway.app/health`
- API Docs: `https://your-app-name.railway.app/docs`
