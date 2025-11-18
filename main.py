import os
import json
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, HttpUrl
import httpx
import aiofiles

app = FastAPI(title="MAAS Custom Simplestream Server")

# Configuration
UPLOAD_DIR = Path("uploads")  # Internal tracking directory
IMAGE_DIR = Path(".")  # Root directory for serving images (like ephemeral-v3/stable/)
DATA_DIR = Path("data")
STREAM_DIR = DATA_DIR / "streams" / "v1"
SYNC_DB = DATA_DIR / "synced_images.json"  # Database for tracking synced images

# Create necessary directories
UPLOAD_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
STREAM_DIR.mkdir(parents=True, exist_ok=True)


class UpstreamMirror(BaseModel):
    url: HttpUrl


class ImageMetadata(BaseModel):
    arch: str
    release: str
    version: str
    label: str
    os: str = "ubuntu"


class SelectedImage(BaseModel):
    product_name: str
    version_name: str
    item_name: str


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def calculate_size(file_path: Path) -> int:
    """Get file size in bytes."""
    return file_path.stat().st_size


@app.get("/")
async def root():
    """Serve the main UI."""
    return FileResponse("static/index.html")


@app.post("/api/upstream/fetch")
async def fetch_upstream(mirror: UpstreamMirror):
    """Fetch available images from an upstream simplestream mirror."""
    try:
        # Basic URL validation to prevent SSRF attacks
        url_str = str(mirror.url)
        
        # Only allow http and https schemes
        if not url_str.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="Only HTTP and HTTPS URLs are allowed")
        
        # Prevent access to localhost and private IP ranges
        from urllib.parse import urlparse
        parsed = urlparse(url_str)
        hostname = parsed.hostname
        
        if hostname:
            # Block localhost and private IPs
            if hostname.lower() in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
                raise HTTPException(status_code=400, detail="Access to localhost is not allowed")
            
            # Block private IP ranges (basic check)
            if hostname.startswith(('10.', '172.16.', '172.17.', '172.18.', '172.19.', 
                                   '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                                   '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                                   '172.30.', '172.31.', '192.168.', '169.254.')):
                raise HTTPException(status_code=400, detail="Access to private IP ranges is not allowed")
        
        # If URL doesn't end with index.json, append it
        if not url_str.endswith('index.json'):
            url_str = url_str.rstrip('/') + '/index.json'
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch the index.json
            # Note: This intentionally makes requests to user-provided URLs (upstream mirrors)
            # SSRF mitigation: localhost and private IP ranges are blocked above
            response = await client.get(url_str)
            response.raise_for_status()
            index_data = response.json()
            
            # Handle different index formats
            if "index" not in index_data:
                raise HTTPException(status_code=400, detail="Invalid simplestream index format")
            
            # Parse and return simplified product list from all streams
            simplified_products = []
            
            # Determine the base URL for constructing product paths
            # URL now always ends with index.json
            base_url = url_str.rsplit('/', 1)[0]
            
            # Iterate through all streams in the index
            for stream_name, stream_info in index_data["index"].items():
                # Skip if not a valid stream with a path
                if "path" not in stream_info:
                    continue
                
                # Process all image-related streams (image-downloads and image-ids)
                datatype = stream_info.get("datatype", "")
                if datatype not in ["image-downloads", "image-ids"]:
                    continue
                
                products_path = stream_info["path"]
                
                # Build the products URL - handle both relative and absolute paths
                if products_path.startswith('http://') or products_path.startswith('https://'):
                    products_url = products_path
                elif products_path.startswith('/'):
                    # Absolute path from root
                    parsed_base = urlparse(base_url)
                    products_url = f"{parsed_base.scheme}://{parsed_base.netloc}{products_path}"
                else:
                    # Relative path - need to go up to the proper base
                    # If path starts with "streams/v1/", we need the root of the mirror
                    if products_path.startswith('streams/'):
                        # Remove "streams/v1/" from base_url if present
                        mirror_root = base_url.split('/streams/')[0]
                        products_url = f"{mirror_root}/{products_path}"
                    else:
                        products_url = f"{base_url}/{products_path}"
                
                try:
                    # Fetch the products file for this stream
                    products_response = await client.get(products_url)
                    products_response.raise_for_status()
                    products_data = products_response.json()
                    
                    # Parse products from this stream
                    if "products" in products_data:
                        for product_name, product_info in products_data["products"].items():
                            if "versions" not in product_info:
                                continue
                            
                            # Extract product-level label (not version-level)
                            product_label = product_info.get("label", "")
                            
                            for version_name, version_info in product_info["versions"].items():
                                if "items" not in version_info:
                                    continue
                                
                                for item_name, item_info in version_info["items"].items():
                                    simplified_products.append({
                                        "product_name": product_name,
                                        "product_arch": product_info.get("arch", "unknown"),
                                        "product_os": product_info.get("os", "unknown"),
                                        "product_release": product_info.get("release", "unknown"),
                                        "version_name": version_name,
                                        "version_label": product_label,
                                        "item_name": item_name,
                                        "item_ftype": item_info.get("ftype", "unknown"),
                                        "item_size": item_info.get("size", 0),
                                        "item_sha256": item_info.get("sha256", ""),
                                        "item_path": item_info.get("path", ""),
                                    })
                except Exception as e:
                    # Log and continue if a specific stream fails
                    print(f"Failed to fetch stream {stream_name}: {e}")
                    continue
            
            return {
                "format": "products:1.0",
                "updated": index_data.get("updated", ""),
                "products": simplified_products
            }
            
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch upstream: {str(e)}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON response from upstream")


@app.post("/api/images/mirror")
async def mirror_images(selected: List[SelectedImage]):
    """Download and mirror selected images from upstream."""
    # This is a placeholder - in a real implementation, you would download the actual files
    # For now, we'll just store the metadata
    mirrored = []
    for img in selected:
        mirrored.append({
            "product_name": img.product_name,
            "version_name": img.version_name,
            "item_name": img.item_name,
            "status": "queued"
        })
    
    return {"mirrored": mirrored, "message": "Images queued for mirroring"}


@app.post("/api/images/upload")
async def upload_image(
    arch: str = Form(...),
    release: str = Form(...),
    version: str = Form(...),
    label: str = Form(...),
    os: str = Form("ubuntu"),
    kernel: Optional[UploadFile] = File(None),
    initrd: Optional[UploadFile] = File(None),
    rootfs: Optional[UploadFile] = File(None)
):
    """Upload custom images with metadata."""
    
    if not kernel and not initrd and not rootfs:
        raise HTTPException(status_code=400, detail="At least one file (kernel, initrd, or rootfs) is required")
    
    # Create a unique directory for this upload (internal tracking)
    upload_id = hashlib.md5(f"{arch}{release}{version}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
    upload_path = UPLOAD_DIR / upload_id
    upload_path.mkdir(exist_ok=True)
    
    # Create directory structure like upstream: release/arch/version/subarch/
    image_dir = IMAGE_DIR / release / arch / version / "custom"
    image_dir.mkdir(parents=True, exist_ok=True)
    
    uploaded_files = {}
    
    # Save uploaded files in the proper directory structure
    for file, file_type in [(kernel, "kernel"), (initrd, "initrd"), (rootfs, "rootfs")]:
        if file:
            # Determine file name based on type (matching upstream naming)
            if file_type == "kernel":
                filename = "boot-kernel"
            elif file_type == "initrd":
                filename = "boot-initrd"
            elif file_type == "rootfs":
                filename = "squashfs"
            else:
                filename = file_type
            
            # Save to both locations:
            # 1. Internal tracking directory (uploads/)
            internal_path = upload_path / f"{file_type}-{file.filename}"
            # 2. Public directory structure (release/arch/version/custom/)
            public_path = image_dir / filename
            
            content = await file.read()
            
            async with aiofiles.open(internal_path, 'wb') as f:
                await f.write(content)
            
            async with aiofiles.open(public_path, 'wb') as f:
                await f.write(content)
            
            # Use the public path in metadata (matching upstream structure)
            uploaded_files[file_type] = {
                "filename": file.filename,
                "path": f"{release}/{arch}/{version}/custom/{filename}",
                "size": calculate_size(public_path),
                "sha256": calculate_sha256(public_path)
            }
    
    # Save metadata
    metadata = {
        "arch": arch,
        "release": release,
        "version": version,
        "label": label,
        "os": os,
        "upload_id": upload_id,
        "uploaded_at": datetime.now().isoformat(),
        "files": uploaded_files
    }
    
    metadata_path = upload_path / "metadata.json"
    async with aiofiles.open(metadata_path, 'w') as f:
        await f.write(json.dumps(metadata, indent=2))
    
    # Update the simplestream tree
    await update_simplestream_tree()
    
    return {
        "success": True,
        "upload_id": upload_id,
        "metadata": metadata
    }


@app.post("/api/upstream/download")
async def download_upstream_images(request: Dict[str, Any]):
    """Download and sync images from upstream mirror."""
    try:
        base_url = request.get("base_url", "")
        selected_images = request.get("images", [])
        
        if not base_url or not selected_images:
            raise HTTPException(status_code=400, detail="base_url and images are required")
        
        # Load existing synced images
        synced = await load_synced_images()
        synced_dict = {f"{s['release']}_{s['arch']}_{s['version']}_{s['label']}": s for s in synced}
        
        downloaded_count = 0
        async with httpx.AsyncClient(timeout=300.0) as client:
            for img_info in selected_images:
                try:
                    # Create unique key for this image
                    img_key = f"{img_info['product_release']}_{img_info['product_arch']}_{img_info['version_name']}_{img_info['version_label']}"
                    
                    # Skip if already synced
                    if img_key in synced_dict:
                        continue
                    
                    # Create directory structure
                    image_dir = IMAGE_DIR / img_info['product_release'] / img_info['product_arch'] / img_info['version_name'] / (img_info['version_label'] or "default")
                    image_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Download the file
                    file_url = base_url.rstrip('/') + '/' + img_info['item_path']
                    response = await client.get(file_url)
                    response.raise_for_status()
                    
                    # Determine filename from item_name
                    filename = img_info['item_name']
                    file_path = image_dir / filename
                    
                    # Save file
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(response.content)
                    
                    # Calculate hash
                    sha256 = calculate_sha256(file_path)
                    size = calculate_size(file_path)
                    
                    # Check if we need to create a metadata entry for this image group
                    if img_key not in synced_dict:
                        synced_dict[img_key] = {
                            "arch": img_info['product_arch'],
                            "release": img_info['product_release'],
                            "version": img_info['version_name'],
                            "label": img_info['version_label'] or "default",
                            "os": img_info['product_os'],
                            "synced_at": datetime.now().isoformat(),
                            "files": {}
                        }
                    
                    # Add file info
                    file_type = img_info['item_ftype'].replace('boot-', '') if img_info['item_ftype'].startswith('boot-') else img_info['item_ftype']
                    synced_dict[img_key]["files"][file_type] = {
                        "filename": filename,
                        "path": f"{img_info['product_release']}/{img_info['product_arch']}/{img_info['version_name']}/{img_info['version_label'] or 'default'}/{filename}",
                        "size": size,
                        "sha256": sha256
                    }
                    
                    downloaded_count += 1
                    
                except Exception as e:
                    print(f"Failed to download {img_info.get('item_name', 'unknown')}: {e}")
                    continue
        
        # Save updated synced database
        await save_synced_images(list(synced_dict.values()))
        
        # Update simplestream tree
        await update_simplestream_tree()
        
        return {
            "success": True,
            "downloaded": downloaded_count,
            "message": f"Downloaded {downloaded_count} files successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@app.get("/api/images/list")
async def list_images():
    """List all uploaded and synced images."""
    images = []
    
    # Load uploaded images
    if UPLOAD_DIR.exists():
        for upload_dir in UPLOAD_DIR.iterdir():
            if upload_dir.is_dir():
                metadata_path = upload_dir / "metadata.json"
                if metadata_path.exists():
                    async with aiofiles.open(metadata_path, 'r') as f:
                        content = await f.read()
                        metadata = json.loads(content)
                        metadata["source"] = "uploaded"
                        images.append(metadata)
    
    # Load synced images
    synced = await load_synced_images()
    for img in synced:
        img["source"] = "synced"
        images.append(img)
    
    return {"images": images}


@app.delete("/api/images/{upload_id}")
async def delete_image(upload_id: str):
    """Delete an uploaded image by upload_id."""
    upload_path = UPLOAD_DIR / upload_id
    
    if not upload_path.exists() or not upload_path.is_dir():
        raise HTTPException(status_code=404, detail="Image not found")
    
    # Read metadata to get the image directory path
    metadata_path = upload_path / "metadata.json"
    if metadata_path.exists():
        async with aiofiles.open(metadata_path, 'r') as f:
            content = await f.read()
            metadata = json.loads(content)
            
        # Delete from image directory structure
        image_dir = IMAGE_DIR / metadata['release'] / metadata['arch'] / metadata['version'] / "custom"
        if image_dir.exists():
            shutil.rmtree(image_dir, ignore_errors=True)
            
            # Clean up empty parent directories
            version_dir = image_dir.parent
            if version_dir.exists() and not any(version_dir.iterdir()):
                shutil.rmtree(version_dir, ignore_errors=True)
                
            arch_dir = version_dir.parent if version_dir.exists() else None
            if arch_dir and arch_dir.exists() and not any(arch_dir.iterdir()):
                shutil.rmtree(arch_dir, ignore_errors=True)
                
            release_dir = arch_dir.parent if arch_dir and arch_dir.exists() else None
            if release_dir and release_dir.exists() and not any(release_dir.iterdir()):
                shutil.rmtree(release_dir, ignore_errors=True)
    
    # Delete the upload directory and all its contents
    shutil.rmtree(upload_path)
    
    # Update the simplestream tree
    await update_simplestream_tree()
    
    return {
        "success": True,
        "message": f"Image {upload_id} deleted successfully"
    }


async def load_synced_images():
    """Load synced images from database."""
    if not SYNC_DB.exists():
        return []
    
    async with aiofiles.open(SYNC_DB, 'r') as f:
        content = await f.read()
        return json.loads(content)


async def save_synced_images(synced):
    """Save synced images to database."""
    async with aiofiles.open(SYNC_DB, 'w') as f:
        await f.write(json.dumps(synced, indent=2))


async def update_simplestream_tree():
    """Update the simplestream metadata tree based on uploaded AND synced images."""
    
    # Load all uploaded images
    uploaded_images = []
    if UPLOAD_DIR.exists():
        for upload_dir in UPLOAD_DIR.iterdir():
            if upload_dir.is_dir():
                metadata_path = upload_dir / "metadata.json"
                if metadata_path.exists():
                    async with aiofiles.open(metadata_path, 'r') as f:
                        content = await f.read()
                        uploaded_images.append(json.loads(content))
    
    # Load synced images
    synced_images = await load_synced_images()
    
    # Combine all images
    all_images = uploaded_images + synced_images
    
    # Build products structure following MAAS simplestream format (image-ids datatype)
    products = {}
    
    for img in all_images:
        # Product name format: com.ubuntu.maas.custom:v3:boot:release:arch:subarch
        product_name = f"com.ubuntu.maas.custom:v3:boot:{img['release']}:{img['arch']}:custom"
        
        if product_name not in products:
            products[product_name] = {
                "aliases": f"{img['release']}/custom",
                "arch": img['arch'],
                "ftype": "squashfs",
                "kflavor": "generic",
                "kpackage": "linux-generic",
                "label": img['label'],
                "os": img['os'],
                "release": img['release'],
                "release_codename": img['release'],
                "release_title": img['release'].title(),
                "subarch": "custom",
                "subarches": "generic,custom",
                "support_eol": "2099-12-31",
                "supported_platforms": [],
                "version": img['version'],
                "versions": {}
            }
        
        version_name = img['version']
        if version_name not in products[product_name]["versions"]:
            products[product_name]["versions"][version_name] = {
                "items": {},
                "label": img['label'],
                "pubname": f"{img['os']}-{img['release']}-{img['version']}-{img['arch']}-custom"
            }
        
        # Add each file as an item with proper ftype naming
        for file_type, file_info in img['files'].items():
            # Map file types to MAAS item names
            if file_type == "kernel":
                item_name = "boot-kernel"
            elif file_type == "initrd":
                item_name = "boot-initrd"
            elif file_type == "rootfs":
                item_name = "squashfs"
            else:
                item_name = file_type
            
            products[product_name]["versions"][version_name]["items"][item_name] = {
                "ftype": item_name,
                "kpackage": "linux-generic",
                "krel": "generic",
                "md5": "",
                "path": file_info['path'],
                "sha256": file_info['sha256'],
                "size": file_info['size']
            }
    
    # Create products.json with proper MAAS format (image-ids datatype)
    products_data = {
        "content_id": "com.ubuntu.maas:custom:v3:download",
        "datatype": "image-ids",
        "format": "products:1.0",
        "license": "http://www.canonical.com/intellectual-property-policy",
        "products": products,
        "updated": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    }
    
    products_path = STREAM_DIR / "com.ubuntu.maas:custom:v3:download.json"
    async with aiofiles.open(products_path, 'w') as f:
        await f.write(json.dumps(products_data, indent=2))
    
    # Create index.json with proper MAAS format (image-ids datatype)
    index_data = {
        "format": "index:1.0",
        "index": {
            "com.ubuntu.maas:custom:v3:download": {
                "datatype": "image-ids",
                "format": "products:1.0",
                "path": "streams/v1/com.ubuntu.maas:custom:v3:download.json",
                "products": list(products.keys()),
                "updated": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
            }
        },
        "updated": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")
    }
    
    index_path = DATA_DIR / "streams" / "v1" / "index.json"
    async with aiofiles.open(index_path, 'w') as f:
        await f.write(json.dumps(index_data, indent=2))


@app.get("/streams/v1/index.json")
async def get_index():
    """Serve the simplestream index."""
    index_path = DATA_DIR / "streams" / "v1" / "index.json"
    if not index_path.exists():
        # Create empty index if it doesn't exist
        await update_simplestream_tree()
    
    return FileResponse(index_path)


@app.get("/streams/v1/{filename}")
async def get_stream_file(filename: str):
    """Serve simplestream files (products, index, etc)."""
    file_path = STREAM_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Stream file not found")
    
    return FileResponse(file_path)


@app.get("/uploads/{upload_id}/{filename}")
async def get_uploaded_file(upload_id: str, filename: str):
    """Serve uploaded files (legacy endpoint for backward compatibility)."""
    file_path = UPLOAD_DIR / upload_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)


@app.get("/{release}/{arch}/{version}/{subarch}/{filename}")
async def get_image_file(release: str, arch: str, version: str, subarch: str, filename: str):
    """Serve image files from the release directory structure (matching upstream format)."""
    file_path = IMAGE_DIR / release / arch / version / subarch / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
