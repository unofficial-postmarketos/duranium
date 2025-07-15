# Design

The design is currently documented here: https://notes.postmarketos.org/docs/0610efde-84a0-4763-a1c5-9dc953db7bb2/

# How to use

Build image: `mkosi build --force --debug-workspace`

Boot image in qemu:
```
   # Add extra space to disk so repart can create partitions
   $ truncate -s +10G mkosi.output/postmarketOS_edge-2025.07.09-1_arm64.raw
   $ qemu-system-aarch64 -machine virt -cpu host -enable-kvm -m 8G -smp 4 -drive if=pflash,format=raw,readonly=on,file=/usr/share/AAVMF/AAVMF_CODE.fd -drive if=pflash,format=raw,file=AAVMF_VARS.fd -nographic -serial mon:stdio -drive format=raw,file=mkosi.output/postmarketOS_edge-2025.07.09-1_arm64.raw
```
TODO: There's probably a way to simplify this with `mkosi vm`

Notes:
   - EFI in qemu is required, adjust pflash params for host arch

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
