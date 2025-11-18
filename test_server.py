#!/usr/bin/env python3
"""
Simple test script to validate the MAAS custom simplestream server functionality.
"""

import requests
import json
import os
from pathlib import Path

BASE_URL = "http://localhost:8000"

def test_simplestream_index():
    """Test that the simplestream index endpoint works."""
    print("Testing simplestream index endpoint...")
    response = requests.get(f"{BASE_URL}/streams/v1/index.json")
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "index:1.0"
    assert "index" in data
    assert "images" in data["index"]
    print("✓ Simplestream index endpoint works")

def test_simplestream_products():
    """Test that the simplestream products endpoint works."""
    print("Testing simplestream products endpoint...")
    response = requests.get(f"{BASE_URL}/streams/v1/products.json")
    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "products:1.0"
    assert "products" in data
    print("✓ Simplestream products endpoint works")

def test_upload_image():
    """Test image upload functionality."""
    print("Testing image upload...")
    
    # Create test files
    test_files_dir = Path("/tmp/test_images")
    test_files_dir.mkdir(exist_ok=True)
    
    kernel_file = test_files_dir / "test_kernel.img"
    kernel_file.write_text("Test kernel content")
    
    initrd_file = test_files_dir / "test_initrd.img"
    initrd_file.write_text("Test initrd content")
    
    rootfs_file = test_files_dir / "test_rootfs.img"
    rootfs_file.write_text("Test rootfs content")
    
    # Upload files
    files = {
        "kernel": open(kernel_file, "rb"),
        "initrd": open(initrd_file, "rb"),
        "rootfs": open(rootfs_file, "rb"),
    }
    
    data = {
        "arch": "amd64",
        "os": "ubuntu",
        "release": "jammy",
        "version": "20241118-test",
        "label": "automated-test"
    }
    
    response = requests.post(f"{BASE_URL}/api/images/upload", data=data, files=files)
    
    # Close files
    for f in files.values():
        f.close()
    
    assert response.status_code == 200
    result = response.json()
    assert result["success"] == True
    assert "upload_id" in result
    assert "metadata" in result
    
    upload_id = result["upload_id"]
    print(f"✓ Image upload successful (upload_id: {upload_id})")
    
    return upload_id

def test_list_images():
    """Test listing uploaded images."""
    print("Testing list images endpoint...")
    response = requests.get(f"{BASE_URL}/api/images/list")
    assert response.status_code == 200
    data = response.json()
    assert "images" in data
    assert len(data["images"]) > 0
    print(f"✓ Found {len(data['images'])} uploaded image(s)")

def test_file_download(upload_id):
    """Test downloading an uploaded file."""
    print("Testing file download...")
    response = requests.get(f"{BASE_URL}/uploads/{upload_id}/kernel-test_kernel.img")
    assert response.status_code == 200
    assert response.text == "Test kernel content"
    print("✓ File download works")

def test_products_updated():
    """Test that products.json was updated with the uploaded image."""
    print("Testing products.json update...")
    response = requests.get(f"{BASE_URL}/streams/v1/products.json")
    assert response.status_code == 200
    data = response.json()
    
    # Check for jammy product
    found_product = False
    for product_name, product in data["products"].items():
        if "jammy" in product_name:
            found_product = True
            assert product["release"] == "jammy"
            assert product["arch"] == "amd64"
            assert "versions" in product
            print(f"✓ Product found in metadata: {product_name}")
            break
    
    assert found_product, "Uploaded product not found in products.json"

def main():
    """Run all tests."""
    print("=" * 60)
    print("MAAS Custom Simplestream Server - Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_simplestream_index()
        test_simplestream_products()
        upload_id = test_upload_image()
        test_list_images()
        test_file_download(upload_id)
        test_products_updated()
        
        print()
        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        return 0
        
    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"✗ Test failed: {e}")
        print("=" * 60)
        return 1
    except Exception as e:
        print()
        print("=" * 60)
        print(f"✗ Unexpected error: {e}")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    exit(main())
