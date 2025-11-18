# Deployment Guide

## Prerequisites

- Python 3.12 or higher
- pip package manager

## Installation

1. Clone the repository:
```bash
git clone https://github.com/r00ta/customstream.git
cd customstream
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

## Running the Server

### Development Mode

Start the server on port 8000:
```bash
python main.py
```

The server will be available at http://localhost:8000

### Production Mode

For production deployment, use a production-grade ASGI server:

```bash
pip install uvicorn[standard]
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

Or with Gunicorn:

```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Configuration

### Environment Variables

You can set the following environment variables:

- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)

### Storage

- Uploaded images are stored in the `uploads/` directory
- Simplestream metadata is stored in the `data/streams/v1/` directory

Make sure these directories have appropriate write permissions.

## Reverse Proxy Setup

### Nginx

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Increase upload size limit for image files
    client_max_body_size 10G;
}
```

### Apache

```apache
<VirtualHost *:80>
    ServerName your-domain.com

    ProxyPreserveHost On
    ProxyPass / http://localhost:8000/
    ProxyPassReverse / http://localhost:8000/

    # Increase upload size limit
    LimitRequestBody 10737418240
</VirtualHost>
```

## MAAS Integration

Once the server is running, configure MAAS to use it as a boot source:

```bash
maas admin boot-sources create \
    url=http://your-server:8000/streams/v1/index.json \
    keyring_filename="" \
    keyring_data=""
```

Then sync the images:

```bash
maas admin boot-resources import
```

## Security Considerations

1. **SSRF Protection**: The server includes basic SSRF protection that blocks requests to localhost and private IP ranges when fetching from upstream mirrors.

2. **File Upload**: Consider implementing additional validation for uploaded files (e.g., file type checking, virus scanning).

3. **Authentication**: This basic implementation does not include authentication. For production use, consider adding authentication/authorization (e.g., using OAuth2, API keys, or basic auth).

4. **HTTPS**: Always use HTTPS in production. Configure your reverse proxy to handle SSL/TLS.

5. **File Size Limits**: Configure appropriate file size limits based on your use case.

## Monitoring

### Health Check

The server provides a root endpoint that can be used for health checks:

```bash
curl http://localhost:8000/
```

### Logs

In production mode with uvicorn, logs are written to stdout/stderr. Configure your deployment to capture these logs.

## Backup

Regularly backup the following directories:

- `uploads/` - Contains all uploaded image files
- `data/` - Contains simplestream metadata

## Troubleshooting

### Port Already in Use

If port 8000 is already in use, either stop the conflicting service or change the port:

```bash
python main.py  # Edit main.py to change the port in uvicorn.run()
```

### Permission Errors

Ensure the application has write permissions to create the `uploads/` and `data/` directories.

### File Upload Fails

Check that:
1. The file size is within limits
2. The disk has sufficient space
3. The `uploads/` directory is writable

### Upstream Fetch Fails

The upstream fetch may fail due to:
1. Network connectivity issues
2. Invalid upstream URL
3. Upstream server is down
4. URL is blocked by SSRF protection (localhost, private IPs)
