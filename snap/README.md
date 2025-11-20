# CustomStream Snap

This snap packages CustomStream, a MAAS simplestream mirroring and custom image manager.

## Installation

```bash
# Install from a local build
sudo snap install customstream_*.snap --dangerous

# Or from the Snap Store (once published)
sudo snap install customstream
```

## Usage

The service starts automatically after installation and runs on port 8000.

### Access the Web Interface

Open your browser to:
```
http://localhost:8000
```

### Access the Simplestream Endpoint

The simplestream index is available at:
```
http://localhost:8000/simplestreams/streams/v1/index.json
```

### Configure MAAS to Use CustomStream

Point MAAS to your CustomStream instance:

```bash
maas admin boot-sources create \
  url=http://<customstream-host>:8000/simplestreams/streams/v1/index.json \
  keyring_filename=''
```

## Data Storage

All data is stored in `$SNAP_COMMON`, which typically maps to:
```
/var/snap/customstream/common/
```

This includes:
- `customstream.db` - SQLite database
- `data/simplestreams/` - Mirrored images and custom uploads
- `uploads/` - Temporary upload staging area

## Logs

View service logs with:
```bash
sudo snap logs customstream -f
```

## Networking

The snap requires:
- `network` - to download upstream images
- `network-bind` - to serve the web UI and simplestream endpoint on port 8000

## Port Configuration

By default, CustomStream listens on port 8000. To change this, you'll need to:

1. Stop the service
2. Modify the snap's environment
3. Restart the service

```bash
sudo snap stop customstream
# Edit the launcher script if needed
sudo snap start customstream
```

## Building from Source

```bash
# Install snapcraft
sudo snap install snapcraft --classic

# Build the snap
cd /path/to/customstream
snapcraft

# Install your local build
sudo snap install customstream_*.snap --dangerous
```

## Troubleshooting

### Service won't start
Check logs:
```bash
sudo snap logs customstream -n 100
```

### Permission issues
Ensure the snap has the necessary plugs connected:
```bash
snap connections customstream
```

### Port already in use
Check if another service is using port 8000:
```bash
sudo lsof -i :8000
```

## Uninstall

```bash
sudo snap remove customstream
```

This will remove the application but preserve data in `/var/snap/customstream/common/`.
To completely remove all data, add the `--purge` flag:
```bash
sudo snap remove --purge customstream
```
