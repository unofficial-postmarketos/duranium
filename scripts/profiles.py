# IMPORTANT: must not exceed: 3 char for mfg and 6 char for model
DEVICE_PROFILES = {
    'device-generic-x86_64': 'gen_x86_64',
    'device-google-x64cros': 'ggl_x64cros',
    'device-lenovo-21bx': 'len_21bx',
    'device-nvidia-tegra-armv7': 'nvd_tgrav7',
    'device-pine64-pinephone': 'p64_pphone',
    'device-pine64-pinephone-pro': 'p64_ppp',
    'device-qemu-aarch64': 'qmu_arm64',
    'device-qemu-amd64': 'qmu_amd64',
    # Add more device mappings here
}

# IMPORTANT: must not exceed 5 char!
UI_PROFILES = {
    'ui-console': 'consl',
    'ui-cosmic': 'cosmc',
    'ui-gnome-mobile': 'gnomo',
    'ui-phosh': 'phosh',
    'ui-plasma-mobile': 'plamo',
    'ui-gnome': 'gnome',
    'ui-plasma-desktop': 'plade',
    'ui-plasma-bigscreen': 'plabs',
    'ui-sxmo': 'sxmo',
    # Add more UI mappings here
}

RELEASE_PROFILES = {
    'release-edge': 'edge',
    'release-v25.06': '2506',
    # Add more release mappings here
}
