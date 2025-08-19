#!/usr/bin/env python3

import sys
import subprocess
import os

from profiles import DEVICE_PROFILES, RELEASE_PROFILES, UI_PROFILES

def validate_and_extract_profiles(profiles):
    """Validate exactly one profile of each type and extract mappings"""
    device_profiles = []
    ui_profiles = []
    release_profiles = []
    
    for profile in profiles:
        if profile.startswith('device-'):
            device_profiles.append(profile)
        elif profile.startswith('ui-'):
            ui_profiles.append(profile)
        elif profile.startswith('release-'):
            release_profiles.append(profile)
        else:
            print(f"ERROR: Unknown profile type: {profile}", file=sys.stderr)
            sys.exit(1)
    
    # Validate exactly one of each type
    if len(device_profiles) != 1:
        print(f"ERROR: Must specify exactly one device profile, got {len(device_profiles)}: {device_profiles}", file=sys.stderr)
        sys.exit(1)
    
    if len(ui_profiles) != 1:
        print(f"ERROR: Must specify exactly one UI profile, got {len(ui_profiles)}: {ui_profiles}", file=sys.stderr)
        sys.exit(1)
    
    if len(release_profiles) != 1:
        print(f"ERROR: Must specify exactly one release profile, got {len(release_profiles)}: {release_profiles}", file=sys.stderr)
        sys.exit(1)
    
    device_profile = device_profiles[0]
    ui_profile = ui_profiles[0]
    release_profile = release_profiles[0]
    
    # Map to short codes
    if device_profile not in DEVICE_PROFILES:
        print(f"ERROR: Unknown device profile: {device_profile}", file=sys.stderr)
        sys.exit(1)
    
    if ui_profile not in UI_PROFILES:
        print(f"ERROR: Unknown UI profile: {ui_profile}", file=sys.stderr)
        sys.exit(1)
    
    if release_profile not in RELEASE_PROFILES:
        print(f"ERROR: Unknown release profile: {release_profile}", file=sys.stderr)
        sys.exit(1)
    
    return (
        DEVICE_PROFILES[device_profile],
        UI_PROFILES[ui_profile], 
        RELEASE_PROFILES[release_profile]
    )

def main():
    if len(sys.argv) < 4:
        print("Usage: build-image.py <device-profile> <ui-profile> <release-profile> [mkosi-args...]", file=sys.stderr)
        print("Example: build-image.py device-pine64-pinephone ui-plasma-mobile release-edge --force", file=sys.stderr)
        sys.exit(1)
    
    profiles = sys.argv[1:4]
    
    # Validate and extract profile mappings
    device_code, ui_code, release_code = validate_and_extract_profiles(profiles)
    
    # Generate ImageId with profile codes
    image_id = f"{device_code}_{ui_code}_{release_code}"
    
    # Join profiles for mkosi --profiles argument
    profiles = ",".join(profiles)
    
    print(f"Generated ImageID: {image_id}", file=sys.stderr)
    print(f"Using profiles: {profiles}", file=sys.stderr)
    
    # Call mkosi with generated ImageId and profiles
    mkosi_cmd = [
        os.environ.get('MKOSI', 'mkosi'),
        "build",
        "--force",
        f"--image-id={image_id}",
        f"--profile={profiles}",
        "-B",
    ] + sys.argv[4:]

    print(f"Executing: {' '.join(mkosi_cmd)}", file=sys.stderr)
    
    try:
        subprocess.run(mkosi_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: mkosi failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("ERROR: mkosi command not found", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
