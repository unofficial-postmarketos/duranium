#!/usr/bin/env python3

import os
import sys
import subprocess
import argparse
import tempfile
from profiles import DEVICE_PROFILES, RELEASE_PROFILES, UI_PROFILES

def parse_remote(remote_arg):
    """Parse host:/path format"""
    if ':' not in remote_arg:
        print(f"ERROR: remote must be in format host:/path, got: {remote_arg}")
        sys.exit(1)
    host, remote_path = remote_arg.split(':', 1)
    return host, remote_path

def imageid_to_pretty(image_id):
    """Convert ImageId back to pretty profile names"""
    parts = image_id.split('_')
    if len(parts) < 4:
        print(f"ERROR: Image ID in invalid format: {image_id}")
        sys.exit(1)

    release_code = parts[-1]
    ui_code = parts[-2]
    mfg_code = parts[0]
    model_code = '_'.join(parts[1:-2])
    device_code = f"{mfg_code}_{model_code}"

    # Reverse lookup in profiles
    device = next((k for k, v in DEVICE_PROFILES.items() if v == device_code), device_code)
    ui = next((k for k, v in UI_PROFILES.items() if v == ui_code), ui_code)
    release = next((k for k, v in RELEASE_PROFILES.items() if v == release_code), release_code)

    # Clean up prefixes for display
    device_pretty = device.replace('device-', '')
    ui_pretty = ui.replace('ui-', '')
    release_pretty = release.replace('release-', '')

    return device_pretty, ui_pretty, release_pretty

def run_command(cmd, check=True, capture_output=False):
    """Run shell command"""
    if capture_output:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if check and result.returncode != 0:
            print(f"ERROR: Command failed: {cmd}")
            print(f"stderr: {result.stderr}")
            sys.exit(1)
        return result.stdout.strip()
    else:
        result = subprocess.run(cmd, shell=True)
        if check and result.returncode != 0:
            print(f"ERROR: Command failed: {cmd}")
            sys.exit(1)

def download_existing_sha256sums(host, remote_path, image_id, temp_dir):
    """Download existing SHA256SUMS if it exists"""
    remote_file = f"{host}:{remote_path}/{image_id}/SHA256SUMS"
    local_file = os.path.join(temp_dir, f"{image_id}_remote_SHA256SUMS")

    cmd = f"scp {remote_file} {local_file}"
    result = subprocess.run(cmd, shell=True, capture_output=True)

    if result.returncode == 0:
        return local_file
    return None

def merge_sha256sums(local_file, remote_file, output_file):
    """Merge local and remote SHA256SUMS files"""
    checksums = {}

    # Read remote file first
    if remote_file and os.path.exists(remote_file):
        with open(remote_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#'):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    checksums[parts[1]] = parts[0]

    # Read local file and override/add
    if os.path.exists(local_file):
        with open(local_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#'):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    checksums[parts[1]] = parts[0]

    # Write merged output
    with open(output_file, 'w') as f:
        for filename in sorted(checksums.keys()):
            f.write(f"{checksums[filename]}  {filename}\n")

def sign_file(filepath, gpg_key_id):
    """Sign file with GPG"""
    cmd = f"gpg --detach-sign --armor --local-user {gpg_key_id} {filepath}"
    run_command(cmd)

def get_latest_image_file(build_dir, image_id):
    """Find the latest .raw.xz file in ImageId directory"""
    image_dir = os.path.join(build_dir, image_id)
    if not os.path.exists(image_dir):
        return None

    raw_files = [f for f in os.listdir(image_dir) if f.endswith('.raw.xz') and 'usr-' not in f]
    if raw_files:
        raw_files.sort()
        return raw_files[0]
    return None

def generate_html_index(host, remote_path, build_dir):
    """Generate HTML index page"""
    image_ids = [d for d in os.listdir(build_dir)
                 if os.path.isdir(os.path.join(build_dir, d))]

    if not image_ids:
        return ""

    # Get remote file listings for each ImageId
    image_data = []
    for image_id in image_ids:
        device, ui, release = imageid_to_pretty(image_id)

        # Get latest image file
        latest_file = get_latest_image_file(build_dir, image_id)
        if latest_file:
            image_data.append({
                'device': device,
                'ui': ui,
                'release': release,
                'image_id': image_id,
                'filename': latest_file
            })

    # Sort by device, then UI
    image_data.sort(key=lambda x: (x['device'], x['ui']))

    html = """<!DOCTYPE html>
<html>
<head>
    <title>postmarketOS Immutable - Duranium</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        tr:nth-child(even) { background-color: #f9f9f9; }
        a { text-decoration: none; color: #0066cc; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>Images</h1>
    <table>
        <tr>
            <th>Device</th>
            <th>UI</th>
            <th>Release</th>
            <th>Download</th>
        </tr>
"""

    for img in image_data:
        download_url = f"{img['image_id']}/{img['filename']}"
        html += f"""        <tr>
            <td>{img['device']}</td>
            <td>{img['ui']}</td>
            <td>{img['release']}</td>
            <td><a href="{download_url}">{img['filename']}</a></td>
        </tr>
"""

    html += """    </table>
</body>
</html>
"""
    return html

def deploy_image_id(host, remote_path, build_dir, image_id, gpg_key_id, dry_run):
    """Deploy single ImageId directory"""
    local_dir = os.path.join(build_dir, image_id)
    if not os.path.exists(local_dir):
        print(f"Warning: {local_dir} not found, skipping")
        return

    print(f"Deploying {image_id}...")

    with tempfile.TemporaryDirectory() as temp_dir:
        # Download existing SHA256SUMS
        remote_sha256sums = download_existing_sha256sums(host, remote_path, image_id, temp_dir)

        # Merge SHA256SUMS files
        local_sha256sums = os.path.join(local_dir, "SHA256SUMS")
        merged_sha256sums = os.path.join(temp_dir, "SHA256SUMS")

        merge_sha256sums(local_sha256sums, remote_sha256sums, merged_sha256sums)

        # Sign if requested
        if gpg_key_id and not dry_run:
            sign_file(merged_sha256sums, gpg_key_id)

        if dry_run:
            print(f"  [DRY RUN] Would rsync {local_dir}/ to {host}:{remote_path}/{image_id}/")
            print("  [DRY RUN] Would upload merged SHA256SUMS")
            if gpg_key_id:
                print("  [DRY RUN] Would upload SHA256SUMS.asc")
        else:
            # Create remote directory
            run_command(f"ssh {host} 'mkdir -p {remote_path}/{image_id}'")

            # Rsync image files (exclude SHA256SUMS since we upload merged version)
            rsync_cmd = f"rsync -av --info=progress2 --exclude=SHA256SUMS {local_dir}/ {host}:{remote_path}/{image_id}/"
            run_command(rsync_cmd)

            # Upload merged SHA256SUMS
            run_command(f"scp {merged_sha256sums} {host}:{remote_path}/{image_id}/")

            # Upload signature if created
            if gpg_key_id:
                signature_file = f"{merged_sha256sums}.asc"
                if os.path.exists(signature_file):
                    run_command(f"scp {signature_file} {host}:{remote_path}/{image_id}/")

def main():
    parser = argparse.ArgumentParser(description='Deploy postmarketOS images to HTTP server')
    parser.add_argument('remote', help='Remote destination in format host:/path')
    parser.add_argument('--build-dir', default='mkosi.output', help='Local build directory')
    parser.add_argument('--gpg-key-id', help='GPG key ID for signing SHA256SUMS')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')

    args = parser.parse_args()

    host, remote_path = parse_remote(args.remote)

    if not os.path.exists(args.build_dir):
        print(f"ERROR: Build directory not found: {args.build_dir}")
        sys.exit(1)

    # Get list of ImageId directories
    image_ids = [d for d in os.listdir(args.build_dir)
                 if os.path.isdir(os.path.join(args.build_dir, d))]

    if not image_ids:
        print(f"No ImageId directories found in {args.build_dir}")
        sys.exit(1)

    print(f"Found {len(image_ids)} ImageId directories to deploy")

    # Deploy each ImageId
    for image_id in image_ids:
        deploy_image_id(host, remote_path, args.build_dir, image_id, args.gpg_key_id, args.dry_run)

    # Generate and upload HTML index
    html_content = generate_html_index(host, remote_path, args.build_dir)

    if args.dry_run:
        print("[DRY RUN] Would upload index.html")
        print("HTML content preview:")
        print(html_content[:500] + "..." if len(html_content) > 500 else html_content)
    else:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
            f.write(html_content)
            temp_html = f.name

        try:
            run_command(f"scp {temp_html} {host}:{remote_path}/index.html")
            print("Uploaded index.html")
        finally:
            os.unlink(temp_html)

    print("Deployment complete!")

if __name__ == '__main__':
    main()
