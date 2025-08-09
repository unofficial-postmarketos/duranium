# Design

The design is currently documented here: https://notes.postmarketos.org/docs/0610efde-84a0-4763-a1c5-9dc953db7bb2/

# How to use

Build image: `mkosi build --auto-bump --force --debug-workspace`

Boot image in qemu: `mkosi vm`

# mkosi Configuration

Immutable postmarketOS system with A/B slots

## Layout

```
mkosi.conf                  # Main configuration
mkosi.conf.d/               # Additional config fragments
mkosi.configure             # Dynamic config script
mkosi.finalize              # Finalize script
mkosi.postroot              # Post-root build script
mkosi.postinst              # Post-installation script

mkosi.repart/               # Build-time partition definitions
├── 00-esp.conf             # EFI system partition
├── 10-usr-verity-sig.conf  # USR A slot verity signature
├── 11-usr-verity.conf      # USR A slot verity hash
└── 12-usr.conf             # USR A slot data partition

mkosi.extra/                # Files copied into image, included in initramfs
└── usr/lib/repart.d/       # Runtime partition definitions
    ├── 00-esp.conf         # ESP (runtime copy)
    ├── 10-12-*.conf        # A slot configs
    ├── 20-22-*.conf        # B slot configs (empty placeholders)
    └── 30-root.conf        # Root partition
└── usr/lib/sysupdate.d/    # Runtime sysupdate definitions
    ├── 10-usr-verity-sig.transfer
    ├── 11-usr-verity.transfer
    ├── 12-usr.transfer
    └── 20-esp.transfer
```

## Concepts

- **mkosi.repart/**: Creates initial disk image (A slot only)
- **mkosi.extra/.../repart.d/**: Runtime partition management (both slots + root)
- **A/B slots**: Handled by systemd's `%A` template in partition labels
- **Verity**: All USR partitions include verity hash and signature partitions
