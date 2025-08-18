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

from profiles import DEVICE_PROFILES, RELEASE_PROFILES, UI_PROFILES

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
            print(f"ERROR: Unknown profile type: {profile}")
            sys.exit(1)

    # Validate exactly one of each type
    if len(device_profiles) != 1:
        print(f"ERROR: Must specify exactly one device profile, got {len(device_profiles)}: {device_profiles}")
        sys.exit(1)

    if len(ui_profiles) != 1:
        print(f"ERROR: Must specify exactly one UI profile, got {len(ui_profiles)}: {ui_profiles}")
        sys.exit(1)

    if len(release_profiles) != 1:
        print(f"ERROR: Must specify exactly one release profile, got {len(release_profiles)}: {release_profiles}")
        sys.exit(1)

    device_profile = device_profiles[0]
    ui_profile = ui_profiles[0]
    release_profile = release_profiles[0]

    # Map to short codes
    if device_profile not in DEVICE_PROFILES:
        print(f"ERROR: Unknown device profile: {device_profile}")
        sys.exit(1)

    if ui_profile not in UI_PROFILES:
        print(f"ERROR: Unknown UI profile: {ui_profile}")
        sys.exit(1)

    if release_profile not in RELEASE_PROFILES:
        print(f"ERROR: Unknown release profile: {release_profile}")
        sys.exit(1)

    return (
        DEVICE_PROFILES[device_profile],
        UI_PROFILES[ui_profile],
        RELEASE_PROFILES[release_profile]
    )

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

def build_single_image(combination: BuildCombination, extra_args: List[str]) -> BuildResult:
    """Build a single image and return result"""
    start_time = time.time()

    profiles = [combination.device, combination.ui, combination.release]

    try:
        # Validate and extract profile mappings
        device_code, ui_code, release_code = validate_and_extract_profiles(profiles)

        # Generate ImageId with profile codes
        image_id = f"{device_code}_{ui_code}_{release_code}"

        # Join profiles for mkosi --profiles argument
        profiles_str = ",".join(profiles)

        print(f"Building: {combination.device} + {combination.ui} + {combination.release}")
        print(f"ImageID: {image_id}")

        # Call mkosi with generated ImageId and profiles
        mkosi_cmd = [
            os.environ.get('MKOSI', 'mkosi'),
            "build",
            "--force",
            f"--image-id={image_id}",
            f"--profile={profiles_str}",
        ] + extra_args

        subprocess.run(mkosi_cmd, check=True)

        duration = time.time() - start_time
        return BuildResult(combination.device, combination.ui, combination.release, True, duration=duration)

    except subprocess.CalledProcessError as e:
        duration = time.time() - start_time
        return BuildResult(combination.device, combination.ui, combination.release, False,
                         f"mkosi failed with exit code {e.returncode}", duration)
    except FileNotFoundError:
        duration = time.time() - start_time
        return BuildResult(combination.device, combination.ui, combination.release, False,
                         "mkosi command not found", duration)
    except Exception as e:
        duration = time.time() - start_time
        return BuildResult(combination.device, combination.ui, combination.release, False,
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
        result = build_single_image(combination, extra_args)
        results.append(result)

        if result.success:
            print(f"✓ Success ({result.duration:.1f}s)")
        else:
            print(f"✗ Failed: {result.error}")

    print_summary(results)

    # Exit with error code if any builds failed
    if any(not r.success for r in results):
        sys.exit(1)

def build_single_legacy(profiles: List[str], extra_args: List[str]):
    """Original single-image build logic"""
    device_code, ui_code, release_code = validate_and_extract_profiles(profiles)

    # Generate ImageId with profile codes
    image_id = f"{device_code}_{ui_code}_{release_code}"

    # Join profiles for mkosi --profiles argument
    profiles_str = ",".join(profiles)

    print(f"Generated ImageID: {image_id}")
    print(f"Using profiles: {profiles_str}")

    # Call mkosi with generated ImageId and profiles
    mkosi_cmd = [
        os.environ.get('MKOSI', 'mkosi'),
        "build",
        "--force",
        f"--image-id={image_id}",
        f"--profile={profiles_str}",
    ] + extra_args

    print(f"Executing: {' '.join(mkosi_cmd)}")

    try:
        subprocess.run(mkosi_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: mkosi failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("ERROR: mkosi command not found")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Build postmarketOS images using mkosi profiles')
    parser.add_argument('--config', help='YAML config file for building multiple image combinations')
    parser.add_argument('profiles', nargs='*', help='Device, UI, and release profiles (when not using --config)')

    # Parse known args so we can pass through extra mkosi args
    args, extra_args = parser.parse_known_args()

    if args.config:
        # Matrix build mode
        build_matrix(args.config, extra_args)
    else:
        # Legacy single build mode
        if len(args.profiles) < 3:
            print("Usage: build-image.py <device-profile> <ui-profile> <release-profile> [mkosi-args...]")
            print("   or: build-image.py --config <config.yaml> [mkosi-args...]")
            print("Example: build-image.py device-pine64-pinephone ui-plasma-mobile release-edge --profile=compressed --force")
            print("Example: build-image.py --config build-images.yaml --profile=compressed")
            sys.exit(1)

        profiles = args.profiles[:3]
        remaining_args = args.profiles[3:] + extra_args
        build_single_legacy(profiles, remaining_args)

if __name__ == '__main__':
    main()
