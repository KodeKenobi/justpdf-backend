# Trevnoctilla API Documentation

A comprehensive file conversion API with authentication, rate limiting, and async processing.

## Features

- **File Conversion**: Video, audio, image, and PDF processing
- **API Authentication**: Secure API key-based authentication
- **Rate Limiting**: Per-key rate limiting with Redis
- **Async Processing**: Background job processing with Celery
- **Webhooks**: Real-time notifications for job completion
- **Admin Dashboard**: User and API key management
- **Client Dashboard**: Self-service API key management
- **Monitoring**: System health and performance metrics
- **Documentation**: Interactive API documentation

## Quick Start

### Prerequisites

- Python 3.8+
- Redis (for rate limiting and async processing)
- FFmpeg (for video/audio conversion)
- ImageMagick (for image conversion)
- Ghostscript (for PDF processing)

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd trevnoctilla-backend
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Start Redis**

   ```bash
   redis-server
   ```

5. **Run the startup script**
   ```bash
   python start_api.py
   ```

The API will be available at `http://localhost:5000`

## API Endpoints

### Authentication

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user
- `POST /auth/reset-password` - Request password reset
- `POST /auth/change-password` - Change password (requires auth)
- `GET /auth/profile` - Get user profile (requires auth)
- `PUT /auth/profile` - Update user profile (requires auth)

### File Conversion

- `POST /api/v1/convert/video` - Convert video files
- `POST /api/v1/convert/audio` - Convert audio files
- `POST /api/v1/convert/image` - Convert image files
- `POST /api/v1/pdf/extract-text` - Extract text from PDF
- `POST /api/v1/pdf/extract-images` - Extract images from PDF
- `POST /api/v1/pdf/merge` - Merge PDF files
- `POST /api/v1/pdf/split` - Split PDF files
- `POST /api/v1/pdf/compress` - Compress PDF files
- `POST /api/v1/qr/generate` - Generate QR codes

### Job Management

- `GET /api/v1/jobs/{job_id}/status` - Get job status
- `GET /api/v1/jobs/{job_id}/download` - Download job result

### Client API

- `GET /api/client/keys` - Get user's API keys
- `POST /api/client/keys` - Create new API key
- `PUT /api/client/keys/{id}` - Update API key
- `DELETE /api/client/keys/{id}` - Delete API key
- `GET /api/client/usage` - Get usage statistics
- `GET /api/client/jobs` - Get user's jobs

### Admin API

- `GET /api/admin/users` - List all users
- `GET /api/admin/users/{id}` - Get user details
- `POST /api/admin/users/{id}/api-keys` - Create API key for user
- `DELETE /api/admin/api-keys/{id}` - Revoke API key
- `GET /api/admin/usage/stats` - Get system statistics
- `GET /api/admin/jobs` - List all jobs
- `GET /api/admin/system/health` - Get system health

## Authentication

All API endpoints (except auth endpoints) require authentication using an API key:

```bash
curl -H "X-API-Key: your-api-key-here" \
     https://api.trevnoctilla.com/api/v1/convert/video
```

## Rate Limiting

API requests are rate limited per API key:

- Default: 1,000 requests per hour
- Rate limit headers included in responses
- Higher limits available for paid plans

## Async Processing

Large files are processed asynchronously:

1. Submit conversion request
2. Receive job ID
3. Poll job status endpoint
4. Download result when completed

Example:

```bash
# Start conversion
curl -X POST "https://api.trevnoctilla.com/api/v1/convert/video" \
  -H "X-API-Key: your-key" \
  -F "file=@video.mp4" \
  -F "async=true"

# Response: {"job_id": "123...", "status": "processing"}

# Check status
curl "https://api.trevnoctilla.com/api/v1/jobs/123.../status" \
  -H "X-API-Key: your-key"

# Download result
curl "https://api.trevnoctilla.com/api/v1/jobs/123.../download" \
  -H "X-API-Key: your-key" -o result.mp4
```

## Webhooks

Configure webhooks to receive notifications when jobs complete:

```bash
curl -X POST "https://api.trevnoctilla.com/api/client/webhooks" \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhook",
    "events": ["job.completed", "job.failed"]
  }'
```

## Error Handling

The API uses standard HTTP status codes:

- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error

Error responses include details:

```json
{
  "error": "API key required",
  "code": "MISSING_API_KEY"
}
```

## Monitoring

### Health Check

```bash
curl https://api.trevnoctilla.com/health
```

### System Metrics

```bash
curl -H "X-API-Key: admin-key" \
     https://api.trevnoctilla.com/api/admin/system/health
```

## Configuration

### Environment Variables

| Variable             | Description                | Default                         |
| -------------------- | -------------------------- | ------------------------------- |
| `DATABASE_URL`       | Database connection string | `sqlite:///trevnoctilla_api.db` |
| `REDIS_URL`          | Redis connection string    | `redis://localhost:6379/0`      |
| `SECRET_KEY`         | Flask secret key           | Required                        |
| `JWT_SECRET_KEY`     | JWT signing key            | Required                        |
| `API_BASE_URL`       | Base URL for API           | `https://api.trevnoctilla.com`  |
| `FRONTEND_URL`       | Frontend URL               | `https://trevnoctilla.com`      |
| `MAX_FILE_SIZE`      | Maximum file size          | `100MB`                         |
| `DEFAULT_RATE_LIMIT` | Default rate limit         | `1000`                          |

### Database Setup

The API uses SQLAlchemy with support for SQLite (development) and PostgreSQL (production).

For PostgreSQL:

```bash
export DATABASE_URL="postgresql://user:password@localhost/trevnoctilla_api"
```

### Redis Setup

Redis is required for:

- Rate limiting
- Async job processing
- Caching

```bash
# Install Redis
brew install redis  # macOS
sudo apt-get install redis-server  # Ubuntu

# Start Redis
redis-server
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Code Style

```bash
black .
flake8 .
```

### Database Migrations

```bash
# Create migration
flask db migrate -m "Description"

# Apply migration
flask db upgrade
```

## Deployment

### Docker

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "start_api.py"]
```

### Production Checklist

- [ ] Set strong secret keys
- [ ] Use PostgreSQL database
- [ ] Configure Redis
- [ ] Set up monitoring
- [ ] Configure webhooks
- [ ] Set up SSL/TLS
- [ ] Configure rate limiting
- [ ] Set up logging
- [ ] Configure backups

## Support

- **Documentation**: https://trevnoctilla.com/api/docs
- **Dashboard**: https://trevnoctilla.com/dashboard
- **Admin Panel**: https://trevnoctilla.com/admin
- **Email**: support@trevnoctilla.com

## License

This project is licensed under the MIT License.
