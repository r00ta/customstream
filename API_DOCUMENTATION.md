# API Documentation

## Base URL

```
http://localhost:8000
```

## Endpoints

### Frontend

#### `GET /`
Serves the main web UI.

**Response**: HTML page

---

### Upstream Mirror API

#### `POST /api/upstream/fetch`
Fetch available images from an upstream simplestream mirror.

**Request Body**:
```json
{
  "url": "https://images.maas.io/ephemeral-v3/stable/streams/v1/index.json"
}
```

**Response**:
```json
{
  "format": "products:1.0",
  "updated": "Mon, 18 Nov 2024 10:00:00 +0000",
  "products": [
    {
      "product_name": "com.ubuntu.maas:v3:amd64:ga-20.04:stable",
      "product_arch": "amd64",
      "product_os": "ubuntu",
      "product_release": "focal",
      "version_name": "20241118",
      "version_label": "release",
      "item_name": "boot-kernel",
      "item_ftype": "boot-kernel",
      "item_size": 12345678,
      "item_sha256": "abc123...",
      "item_path": "v3/stable/..."
    }
  ]
}
```

**Status Codes**:
- `200 OK`: Successfully fetched upstream data
- `400 Bad Request`: Invalid URL or blocked by SSRF protection
- `500 Internal Server Error`: Failed to fetch upstream

---

#### `POST /api/images/mirror`
Queue selected images for mirroring (placeholder endpoint).

**Request Body**:
```json
[
  {
    "product_name": "com.ubuntu.maas:v3:amd64:ga-20.04:stable",
    "version_name": "20241118",
    "item_name": "boot-kernel"
  }
]
```

**Response**:
```json
{
  "mirrored": [
    {
      "product_name": "com.ubuntu.maas:v3:amd64:ga-20.04:stable",
      "version_name": "20241118",
      "item_name": "boot-kernel",
      "status": "queued"
    }
  ],
  "message": "Images queued for mirroring"
}
```

---

### Image Upload API

#### `POST /api/images/upload`
Upload custom images with metadata.

**Request**: Multipart form data

**Form Fields**:
- `arch` (required): Architecture (e.g., amd64, arm64)
- `os` (required): Operating system (default: ubuntu)
- `release` (required): Release name (e.g., focal, jammy)
- `version` (required): Version string (e.g., 20241118)
- `label` (required): Label for the image (e.g., custom)
- `kernel` (optional): Kernel image file
- `initrd` (optional): Initial ramdisk file
- `rootfs` (optional): Root filesystem image file

**Note**: At least one file (kernel, initrd, or rootfs) is required.

**Response**:
```json
{
  "success": true,
  "upload_id": "abc123",
  "metadata": {
    "arch": "amd64",
    "release": "focal",
    "version": "20241118",
    "label": "custom",
    "os": "ubuntu",
    "upload_id": "abc123",
    "uploaded_at": "2024-11-18T10:00:00.000000",
    "files": {
      "kernel": {
        "filename": "vmlinuz",
        "path": "uploads/abc123/kernel-vmlinuz",
        "size": 12345678,
        "sha256": "abc123..."
      },
      "initrd": {
        "filename": "initrd.img",
        "path": "uploads/abc123/initrd-initrd.img",
        "size": 12345678,
        "sha256": "def456..."
      },
      "rootfs": {
        "filename": "rootfs.squashfs",
        "path": "uploads/abc123/rootfs-rootfs.squashfs",
        "size": 123456789,
        "sha256": "ghi789..."
      }
    }
  }
}
```

**Status Codes**:
- `200 OK`: Upload successful
- `400 Bad Request`: No files provided or validation error

---

#### `GET /api/images/list`
List all uploaded images.

**Response**:
```json
{
  "images": [
    {
      "arch": "amd64",
      "release": "focal",
      "version": "20241118",
      "label": "custom",
      "os": "ubuntu",
      "upload_id": "abc123",
      "uploaded_at": "2024-11-18T10:00:00.000000",
      "files": {
        "kernel": {
          "filename": "vmlinuz",
          "path": "uploads/abc123/kernel-vmlinuz",
          "size": 12345678,
          "sha256": "abc123..."
        }
      }
    }
  ]
}
```

---

### Simplestream API

#### `GET /streams/v1/index.json`
Get the simplestream index file.

**Response**:
```json
{
  "format": "index:1.0",
  "index": {
    "images": {
      "datatype": "image-downloads",
      "path": "streams/v1/products.json",
      "updated": "Mon, 18 Nov 2024 10:00:00 ",
      "products": [
        "com.ubuntu.maas:ubuntu:focal:amd64:custom"
      ],
      "format": "products:1.0"
    }
  },
  "updated": "Mon, 18 Nov 2024 10:00:00 "
}
```

---

#### `GET /streams/v1/products.json`
Get the simplestream products file.

**Response**:
```json
{
  "content_id": "com.ubuntu.maas:custom",
  "format": "products:1.0",
  "updated": "Mon, 18 Nov 2024 10:00:00 ",
  "products": {
    "com.ubuntu.maas:ubuntu:focal:amd64:custom": {
      "arch": "amd64",
      "os": "ubuntu",
      "release": "focal",
      "release_title": "Focal",
      "support_eol": "2099-12-31",
      "version": "20241118",
      "versions": {
        "20241118": {
          "items": {
            "kernel": {
              "ftype": "kernel",
              "md5": "",
              "path": "uploads/abc123/kernel-vmlinuz",
              "sha256": "abc123...",
              "size": 12345678
            }
          },
          "label": "custom",
          "pubname": "ubuntu-focal-20241118-amd64"
        }
      }
    }
  }
}
```

---

#### `GET /uploads/{upload_id}/{filename}`
Download an uploaded file.

**Parameters**:
- `upload_id`: Upload ID from the upload response
- `filename`: Filename to download

**Response**: Binary file content

**Status Codes**:
- `200 OK`: File found and returned
- `404 Not Found`: File not found

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common error status codes:
- `400 Bad Request`: Invalid input or validation error
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

---

## SSRF Protection

The `/api/upstream/fetch` endpoint includes SSRF protection:

- Only HTTP and HTTPS schemes are allowed
- Localhost (127.0.0.1, ::1, localhost) is blocked
- Private IP ranges are blocked:
  - 10.0.0.0/8
  - 172.16.0.0/12
  - 192.168.0.0/16
  - 169.254.0.0/16

Attempts to access blocked URLs will return a 400 error.

---

## Rate Limiting

Currently, there is no rate limiting implemented. For production use, consider implementing rate limiting at the reverse proxy level or adding it to the application.

---

## Authentication

Currently, there is no authentication implemented. All endpoints are publicly accessible. For production use, consider implementing authentication using:

- API keys
- OAuth2
- Basic authentication
- JWT tokens

---

## Examples

### cURL Examples

**Fetch upstream images**:
```bash
curl -X POST http://localhost:8000/api/upstream/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://images.maas.io/ephemeral-v3/stable/streams/v1/index.json"}'
```

**Upload an image**:
```bash
curl -X POST http://localhost:8000/api/images/upload \
  -F "arch=amd64" \
  -F "os=ubuntu" \
  -F "release=focal" \
  -F "version=20241118" \
  -F "label=custom" \
  -F "kernel=@vmlinuz" \
  -F "initrd=@initrd.img" \
  -F "rootfs=@rootfs.squashfs"
```

**List uploaded images**:
```bash
curl http://localhost:8000/api/images/list
```

**Get simplestream index**:
```bash
curl http://localhost:8000/streams/v1/index.json
```

### Python Examples

```python
import requests

# Fetch upstream images
response = requests.post(
    "http://localhost:8000/api/upstream/fetch",
    json={"url": "https://images.maas.io/ephemeral-v3/stable/streams/v1/index.json"}
)
data = response.json()

# Upload an image
files = {
    "kernel": open("vmlinuz", "rb"),
    "initrd": open("initrd.img", "rb"),
    "rootfs": open("rootfs.squashfs", "rb")
}
data = {
    "arch": "amd64",
    "os": "ubuntu",
    "release": "focal",
    "version": "20241118",
    "label": "custom"
}
response = requests.post(
    "http://localhost:8000/api/images/upload",
    data=data,
    files=files
)
result = response.json()

# List images
response = requests.get("http://localhost:8000/api/images/list")
images = response.json()
```
