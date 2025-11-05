#!/usr/bin/env python3

import sys
import subprocess
import os
import argparse
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

@dataclass
class BuildResult:
    device: str
    ui: str
    release: str
    success: bool
    error: Optional[str] = None
    duration: float = 0.0

@dataclass
class BuildCombination:
    device: str
    ui: str
    release: str

def validate_and_extract_profiles(profiles):
    """Validate exactly one profile of each type and extract names"""
    device_profiles = []
    ui_profiles = []

    for profile in profiles:
        if profile.startswith('device-'):
            device_profiles.append(profile)
        elif profile.startswith('ui-'):
            ui_profiles.append(profile)
        else:
            print(f"ERROR: Unknown profile type: {profile}")
            sys.exit(1)

    # Validate exactly one of each type
    if len(device_profiles) != 1:
        print(f"ERROR: Must specify exactly one device profile, got {len(device_profiles)}: {device_profiles}")
        sys.exit(1)

    if len(ui_profiles) != 1:
        print(f"ERROR: Must specify exactly one UI profile, got {len(ui_profiles)}: {ui_profiles}")
        sys.exit(1)

    device_profile = device_profiles[0]
    ui_profile = ui_profiles[0]

    # Extract names from profile strings (remove 'device-' and 'ui-' prefixes)
    device_name = device_profile.replace('device-', '', 1)
    ui_name = ui_profile.replace('ui-', '', 1)

    return device_name, ui_name

def load_config(config_path: str) -> Dict[str, Any]:
    """Load and validate YAML config file"""
    if yaml is None:
        print("ERROR: yaml support is missing")
        sys.exit(1)

    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Invalid YAML in config file: {e}")
        sys.exit(1)

    if 'devices' not in config:
        print("ERROR: Config must contain 'devices' section")
        sys.exit(1)

    return config

def generate_combinations(config: Dict[str, Any]) -> List[BuildCombination]:
    """Generate all build combinations from config"""
    combinations = []

    for device_name, device_config in config['devices'].items():
        if 'releases' not in device_config or 'ui' not in device_config:
            print(f"ERROR: Device {device_name} missing 'releases' or 'ui' section")
            sys.exit(1)

        releases = device_config['releases']
        ui_config = device_config['ui']

        for release in releases:
            # Determine which UI list to use
            if release in ui_config:
                ui_list = ui_config[release]
            elif 'all' in ui_config:
                ui_list = ui_config['all']
            else:
                print(f"ERROR: No UI config found for {device_name} + {release}")
                sys.exit(1)

            # Generate combinations for this device+release
            for ui in ui_list:
                combinations.append(BuildCombination(device_name, ui, release))

    return combinations

def build_image(profiles: List[str], extra_args: List[str]) -> BuildResult:
    """Core image building function used by both single and matrix modes"""
    start_time = time.time()

    # Extract profile types for BuildResult
    device_profile = next(p for p in profiles if p.startswith('device-'))
    ui_profile = next(p for p in profiles if p.startswith('ui-'))

    try:
        # Validate and extract profile names
        device_name, ui_name = validate_and_extract_profiles(profiles)

        # Extract release from extra_args
        release = "edge"
        for arg in extra_args:
            if arg.startswith('--release='):
                release = arg.split('=', 1)[1]
            break

        image_id = f"{device_name}_{ui_name}_{release}"

        # Join profiles for mkosi --profile argument
        profiles_str = ",".join(profiles)

        print(f"Device: {device_name}, UI: {ui_name}")
        print(f"ImageID: {image_id}")

        # Call mkosi
        mkosi_cmd = [
            os.environ.get('MKOSI', 'mkosi'),
            "build",
            "--force",
            f"--image-id={image_id}",
            f"--environment=PMOS_DEVICE={device_name}",
            f"--environment=PMOS_VARIANT={ui_name}",
            f"--profile={profiles_str}",
        ] + extra_args

        print(f"Executing: {' '.join(mkosi_cmd)}")

        subprocess.run(mkosi_cmd, check=True)

        duration = time.time() - start_time
        return BuildResult(device_profile, ui_profile, "release", True, duration=duration)

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        return BuildResult(device_profile, ui_profile, "release", False,
                         f"mkosi failed with exit code {e.returncode}", duration)
    except FileNotFoundError:
        duration = time.time() - start_time
        return BuildResult(device_profile, ui_profile, "release", False,
                         "mkosi command not found", duration)
    except Exception as e:
        duration = time.time() - start_time
        return BuildResult(device_profile, ui_profile, "release", False,
                         str(e), duration)

def print_summary(results: List[BuildResult]):
    """Print build summary"""
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful
    total_time = sum(r.duration for r in results)

    print("=== BUILD SUMMARY ===")
    print(f"Total combinations: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {total_time:.1f}s")

    if failed > 0:
        print("FAILED BUILDS:")
        for result in results:
            if not result.success:
                print(f"  {result.device} + {result.ui} + {result.release}: {result.error}")

def build_matrix(config_path: str, extra_args: List[str]):
    """Build all combinations from config file"""
    config = load_config(config_path)
    combinations = generate_combinations(config)

    print(f"Building {len(combinations)} image combinations...")

    results = []
    for i, combination in enumerate(combinations, 1):
        print(f"\n[{i}/{len(combinations)}]")

        build_args = [f"--release={combination.release}"] + extra_args
        result = build_image([combination.device, combination.ui], build_args)
        results.append(result)

        if result.success:
            print(f"✓ Success ({result.duration:.1f}s)")
        else:
            print(f"✗ Failed: {result.error}")

    print_summary(results)

    # Exit with error code if any builds failed
    if any(not r.success for r in results):
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Build postmarketOS images using mkosi profiles')
    parser.add_argument('--config', help='YAML config file for building multiple image combinations')
    parser.add_argument('profiles', nargs='*', help='Device and UI profiles (when not using --config)')

    # Parse known args so we can pass through extra mkosi args
    args, extra_args = parser.parse_known_args()

    if args.config:
        # Matrix build mode
        build_matrix(args.config, extra_args)
    else:
        # Single build mode
        if len(args.profiles) < 2:
            print("Usage: build-image.py <device-profile> <ui-profile> [mkosi-args...]")
            print("   or: build-image.py --config <config.yaml> [mkosi-args...]")
            print("Example: build-image.py device-pine64-pinephone ui-plasma-mobile --release=edge --profile=compressed")
            print("Example: build-image.py --config build-images.yaml --profile=compressed")
            sys.exit(1)

        result = build_image(args.profiles, extra_args)
        if not result.success:
            print(f"ERROR: {result.error}")
            sys.exit(1)

if __name__ == '__main__':
    main()
