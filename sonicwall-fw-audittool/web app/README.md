# SonicWall Configuration Auditor - Web Application

A web-based interface for auditing SonicWall firewall configurations. Users upload their `.exp` configuration files through a browser, and receive instant security assessment reports.

## Features

- **Web-based**: No software installation required for end users
- **Secure**: Files processed server-side, automatically deleted after processing
- **Private**: Your audit logic stays on the server - source code not exposed
- **Professional Reports**: Download HTML and JSON reports
- **50+ Security Checks**: Comprehensive audit across 12 categories

## Quick Start

### Option 1: Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py

# Access at http://localhost:5000
```

### Option 2: Docker

```bash
# Build image
docker build -t sonicwall-auditor .

# Run container
docker run -p 8080:8080 sonicwall-auditor

# Access at http://localhost:8080
```

### Option 3: Docker Compose

```yaml
version: '3.8'
services:
  auditor:
    build: .
    ports:
      - "8080:8080"
    environment:
      - SECRET_KEY=your-production-secret-key
    restart: unless-stopped
```

## Cloud Deployment

### AWS Elastic Beanstalk

1. Install EB CLI: `pip install awsebcli`
2. Initialize: `eb init -p docker sonicwall-auditor`
3. Create environment: `eb create production`
4. Deploy: `eb deploy`

### Google Cloud Run

```bash
# Build and push to Google Container Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/sonicwall-auditor

# Deploy to Cloud Run
gcloud run deploy sonicwall-auditor \
  --image gcr.io/PROJECT_ID/sonicwall-auditor \
  --platform managed \
  --allow-unauthenticated
```

### Azure App Service

```bash
# Create resource group
az group create --name sonicwall-rg --location eastus

# Create App Service plan
az appservice plan create --name sonicwall-plan --resource-group sonicwall-rg --is-linux --sku B1

# Create web app with Docker
az webapp create --resource-group sonicwall-rg --plan sonicwall-plan \
  --name sonicwall-auditor --deployment-container-image-name sonicwall-auditor
```

### Heroku

```bash
# Login to Heroku
heroku login

# Create app
heroku create sonicwall-auditor

# Deploy
git push heroku main
```

## Production Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | Random (set in production!) |
| `MAX_CONTENT_LENGTH` | Max upload size | 16MB |
| `PORT` | Server port | 5000 |

### Security Recommendations

1. **Use HTTPS**: Always deploy behind a reverse proxy with TLS
2. **Set SECRET_KEY**: Use a strong random value in production
3. **Rate Limiting**: Add rate limiting for production deployments
4. **Authentication**: Consider adding authentication for internal tools

### Nginx Reverse Proxy Example

```nginx
server {
    listen 443 ssl;
    server_name auditor.example.com;

    ssl_certificate /etc/ssl/certs/auditor.crt;
    ssl_certificate_key /etc/ssl/private/auditor.key;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 16M;
    }
}
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Upload page |
| `/audit` | POST | Process uploaded file |
| `/results/<id>` | GET | View audit results |
| `/download/html/<id>` | GET | Download HTML report |
| `/download/json/<id>` | GET | Download JSON report |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Browser   │────▶│   Flask     │────▶│   Auditor   │
│  (Upload)   │◀────│   Server    │◀────│   Engine    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Temp File  │
                    │  Storage    │
                    └─────────────┘
```

## File Handling

- Uploaded files are saved to a temporary directory
- Files are automatically deleted after processing
- Old files (>1 hour) are cleaned up on each request
- Results stored temporarily for download

## License

Internal tool - SonicWall Pre-Sales Engineering

## Support

Contact your Pre-Sales Engineering team for support.
