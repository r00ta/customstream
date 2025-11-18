# MAAS Custom Simplestream Server

A web application for managing and serving MAAS images via the simplestream protocol. This application allows you to:

- Fetch and browse images from upstream simplestream mirrors (like images.maas.io)
- Select specific images to mirror locally
- Upload custom images (kernel, initrd, rootfs) with metadata
- Serve images via a simplestream-compatible API that MAAS can consume

## Features

### Upstream Mirror Management
- Specify any upstream simplestream mirror URL
- Browse available images with filtering and search
- Select specific images to mirror (placeholder for actual download functionality)

### Custom Image Upload
- Upload kernel, initrd, and rootfs files
- Specify metadata (architecture, OS, release, version, label)
- Automatic SHA256 hash calculation
- File size tracking

### Simplestream Server
- Exposes simplestream-compatible index.json and products.json
- Automatically generates metadata based on uploaded images
- Serves uploaded files for MAAS consumption

## Installation

1. Clone the repository:
```bash
git clone https://github.com/r00ta/customstream.git
cd customstream
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Start the server:
```bash
python main.py
```

The server will start on http://localhost:8000

2. Open your browser and navigate to http://localhost:8000

3. Use the web interface to:
   - **Upstream Mirror Tab**: Enter an upstream mirror URL and browse available images
   - **Upload Images Tab**: Upload your custom images with metadata
   - **Uploaded Images Tab**: View all uploaded images
   - **Simplestream URLs Tab**: Get the URLs to configure MAAS

## MAAS Configuration

Once you have uploaded images, configure MAAS to use this server:

```bash
maas admin boot-sources create \
    url=http://your-server:8000/streams/v1/index.json \
    keyring_filename="" \
    keyring_data=""
```

## API Endpoints

### Frontend
- `GET /` - Web UI

### API
- `POST /api/upstream/fetch` - Fetch images from upstream mirror
- `POST /api/images/mirror` - Queue images for mirroring (placeholder)
- `POST /api/images/upload` - Upload custom images
- `GET /api/images/list` - List all uploaded images

### Simplestream
- `GET /streams/v1/index.json` - Simplestream index
- `GET /streams/v1/products.json` - Simplestream products
- `GET /uploads/{path}` - Serve uploaded files

## Development

The application uses:
- **Backend**: FastAPI (Python)
- **Frontend**: HTML, Bootstrap 5, Vanilla JavaScript
- **Storage**: Local filesystem

## License

See LICENSE file for details.
