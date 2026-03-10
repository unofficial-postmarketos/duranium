# Overview

This document outlines the design of Duranium, an immutable, image-based variant of postmarketOS following the concepts from systemd's "Fitting Everything Together" approach. Duranium requires systemd.

Duranium uses mkosi for image building with systemd tooling for A/B updates (systemd-sysupdate), partition management (systemd-repart), and slot boot selection and automatic fallback on failure (systemd-boot). EFI is chosen as the boot interface because it provides a simple, easy way to configure the OS for booting and integrates seamlessly with the systemd tooling being used. UKI (Unified Kernel Images) enable future secure boot capabilities and simplify image-based updates by bundling kernel, initramfs, cmdline, and DTBs as versioned artifacts. For ARM devices lacking native EFI support (e.g. Android phones), u-boot's implemetation of EFI is expected to bridge this gap.

# Features

* **Immutable, verified /usr**: All OS resources live in a read-only /usr partition, verified at boot with dm-verity. Updates replace the entire partition image atomically.

* **A/B updates with automatic rollback**: Two /usr slots allow atomic updates via systemd-sysupdate. If a new image fails to boot, systemd-boot automatically falls back to the previous slot.

* **Factory reset**: Wipe the rootfs and re-enter first boot setup. Triggered from an authenticated session via an EFI variable.

* **Encrypted by default**: Rootfs is always created on a LUKS volume. Users can set a custom passphrase during first boot or later.

* **First-boot provisioning**: On first boot, a setup wizard handles user account creation and optional FDE passphrase configuration.

# System Architecture

## Boot Overview

This design uses Type 2 booting with UKI, as defined in the UAPI Boot Loader Spec.

Type 1 Boot, where the kernel, initramfs, dtbs are separate files in the ESP, make image creation with mkosi and image-based updates with sysupdate very difficult. More specifically:

* **No ESP Update Mechanism**: mkosi uses kernel version paths (`/postmarketOS/6.15.8-0-stable/`) not IMAGE_VERSION. This means that boot artifacts (kernel) are not coupled with usr partition versions for sysupdate. In other words, it means that /usr/lib/modules may not match the booted kernel, and this is bad.

* **Verity Hash Timing**: `usrhash=` must be passed on the kernel cmdline, the value of this is only available **after** the usr partition is created and finished. For type 2, mkosi automatically creates and injects this into the kernel cmdline in the UKI, but for type 1 there is no point where this can be done. `mkosi.finalize` runs before verity calculation, and `mkosi.postoutput` runs after the ESP partition is finalized/exported, so there's no scriptable point where the usrhash can be injected into the cmdline manually. Using mkosi's kernel-install mechanism isn't possible either since it writes to paths using kernel versions, and not IMAGE_VERSION. Given the previously mentioned issue, when sysupdate updates the usr partition, the loader config in the ESP will have a stale `usrhash=` value. Stale `usrhash=` values in the kernel cmdline break dm-verity.

* **Complex sysupdate.transfer config**: Trying to create an ESP layout with versioned Type 1 artifacts and a sysupdate config that can manage them all (so they can get updated) is difficult and fragile.

* **No SecureBoot Support**: While SecureBoot is not a requirement for an immutable pmOS, choosing a boot implementation that doesn't really support it will make supporting it more difficult in the future.

### Why UKI

UKI resolves/avoids all Type 1 limitations when using mkosi for image creation and sysupdate for image-based updates:

* **Automatic Verity**: mkosi injects `usrhash=` into UKI cmdline during build automatically, no need to patch mkosi to do this

* **Proper Versioning**: UKI files use versioning compatible with other sysupdated artifacts, with boot counting (e.g. `oneplus-enchilada_gnome-mobile_edge_26012901+3-0.efi`), the same versioning is used to couple UKI with the correct usr partition for module loading.

* **Easy sysupdate.transfer config**: Single .efi file contains kernel + initramfs + cmdline + DTB(s), updated atomically by sysupdate, and the sysupdate.transfer configuration to handle this is very simple and straightforward.

* **SecureBoot support**: Entire UKI signed as single unit

### Supported Device Boot Scenarios

DTB loading is handled by embedding devicetrees as `.dtbauto` sections in the UKI, where systemd-stub selects the correct one at boot by matching the `compatible` string from the EFI configuration table. mkosi handles the DTB embedding during image build.

* **u-boot + explicit DTB**: DTB from deviceinfo is embedded in UKI `.dtbauto` and copied to `/dtbs/` in the ESP for u-boot

* **u-boot + auto-detect**: u-boot provides DTB from internal logic, so embed all `/dtbs/` in UKI

* **WoA + explicit DTB**: DTB from deviceinfo is embedded in the UKI

* **WoA + auto-detect**: embed all `/dtbs/` in UKI

* **ACPI devices**: No DTB sections in UKI, normal ACPI boot

**Note about embedding many devicetrees in a UKI**: Embedding all ~1.6K dtbs shipped in the postmarketos-linux-next kernel and booting it on a Thinkpad X13s resulted in no perceived delay in booting while the stub detected/loaded the correct dtb for this device from the large selection of embedded dtbs.

## Versioning

A lot consideration was taken to choose a versioning scheme for images, because we do not want to accidentally configure sysupdate to flash incompatible or unexpected images to devices during update, and there are limitations to how long partitions labels can be.

os-release is used to set a variety of parameters for images:

* `IMAGE_ID`: Contains the device name, e.g. `qemu-aarch64`, `apple-mac-aarch64`, `generic-x86_64`, `lenovo-21bx`

* `VARIANT_ID`: Contains the UI, e.g. `gnome`, `plasma-mobile`, `console`, `cosmic`

* `VERSION_ID`: Contains the release, e.g. `edge`, `v25.06`

* `IMAGE_VERSION`: Contains a build date code and increment, e.g. `25110402`

* **mkosi**: Uses ImageId (from build-image.py) for output filenames, but `IMAGE_ID` in `os-release` and `initrd-release`, used by repart for partition labels, sysupdate for matching, and factory reset, are overwritten in `mkosi.finalize` to only specify the device name.

* **sysupdate**: Uses these to identify when updates are available. Sysupdate uses the `IMAGE_ID`+`IMAGE_VERSION` stored in the GPT partition name to determine which partition to preserve and which one to install an image update to. Sysupdate also requires that newer image updates have an version that's higher than the currently active image. Sysupdate uses all of these variables from os-release to search for updates. Modifying `VARIANT_ID` and/or `VERSION_ID` in `/etc/os-release` after image installation and running sysupdate allows one to switch to a different UI or release, respectively.

* **repart**: mkosi calls repart when creating a full disk image for provisioning a system, and embeds the `IMAGE_ID` and `IMAGE_VERSION` in the active slot partition name.

* **GPT Partition Name**: This field is limited to a maximum of 34 characters, so `IMAGE_ID` + `IMAGE_VERSION` needs to fit. In order to fix within this size, the device name should be limited to a maximum of 21 characters in order to leave enough space for including the `IMAGE_VERION`. Some space should also be reserved for indicating the partition type as suffix. Sysupdate uses the suffix to select the correct partition image during updates.

* **postmarketOS**: There are many device ports, dozens of UIs, and multiple releases (edge, stable releases), and the id needs to be able to differentiate between all different combinations so that we do not accidentally cause sysupdate to flash an incompatible image update on a device.

Given all of these requirements, the following format is used for partition labels:

`{IMAGE_ID}_{IMAGE_VERSION}_{partition type suffix}` = device(21) + _(1) + version(8) + _(1) + suffix(3) = 34 chars max

A real world example of a partition label in this format might look like: `pine64-pinephone_25110402_vty` for the /usr verity partition on a pine64 pinephone.


## Partition Layout

**Initial shipped image:**

1. ESP (EFI System Partition) with systemd-boot, UKI, DTBs (for u-boot compatibility, separate from UKI-embedded DTBs)

2. /usr partition (version A) - immutable, labeled with image version

3. Verity partition for /usr (version A)

4. Verity signature partition for /usr (version A)

**Created on first boot by systemd-repart:**

1. /usr partition (version B) - initially empty, labeled `_empty`

2. Verity partition for /usr (version B)

3. Verity signature partition for /usr (version B)

4. Root filesystem - encrypted with LUKS (blank passphrase by default)

### ESP Layout for UKI

```
/boot/
├── efi/                                               # installed once, not managed by A/B updates
│   ├── boot/
│   │   └── bootaa64.efi                               # systemd-boot
│   └── systemd/
├── dtbs/                                              # Device detection DTBs (optional, unversioned)
│   ├── qcom/
│   │   ├── sc8280xp-lenovo-thinkpad-x13s.dtb
│   │   └── ...
│   └── ...
└── EFI/Linux/
    ├── lenovo-21bx_phosh_edge_25071501.efi            # UKI (dtb(s) in dtbauto sections)
    └── lenovo-21bx_phosh_edge_25071801.efi+3-0.efi    # Next version with boot counting
```

## Image Building

This build system uses mkosi profiles to generate images for postmarketOS's many device, UI, and release combinations. Rather than maintaining separate configurations for every possible combination or relying on pmbootstrap/pmaports, two orthogonal profile types (device, UI) are composed at build time with mkosi to generate images targeting specific configurations. Release is configured via mkosi's `Release=` setting (defaulting to `edge`, overridable with `--release=`). The profiles and release are used to generate a unique `ImageId` that describes the device, UI and release combination (see the Version section for more information).

The profiles themselves are quite simple, often just including a single package, but mkosi is quite flexible and they would be expanded to do more stuff later if necessary for building images for a specific device.

### Build Process

1. **Device profile** installs device-specific package, build-image.py uses device name to construct the composite `ImageId=` setting for mkosi

2. **UI profile** installs UI-specific package, build-image.py uses UI name to construct the composite `ImageId=` setting for mkosi, and mkosi.finalize sets `VARIANT_ID` in os-release

3. Images are built using `build-image.py` wrapper script with these 2 profiles

4. Wrapper validates exactly one profile of each type is provided

5. Wrapper generates composite `ImageId` from device and UI profile names, and release (from `--release=` flag, defaulting to `edge`). The format for this is: `{device}_{ui}_{release}`

6. Wrapper invokes mkosi with `ImageId` and profiles, and passes (for `mkosi.finalize` ) `--environment=PMOS_VARIANT` and `--environment=PMOS_DEVICE`.

7. `mkosi.finalize` modifies os-release to: set `VARIANT_ID=$PMOS_VARIANT` and `IMAGE_ID=$PMOS_DEVICE`

8. mkosi uses composite `ImageId`, for output filenames via `Output=` in `mkosi.conf`, but repart uses device name-only `IMAGE_ID` from os-release for partition labels

9. mkosi sets `VERSION_ID` in os-release from `Release=` (configured with a default in mkosi.conf or passed via `--release=` flag)

### Profile Structure

```
mkosi.profiles/
├── compressed/
│   └── mkosi.conf
├── device-oneplus-enchilada/
│   └── mkosi.conf
├── device-qemu-aarch64/
│   └── mkosi.conf
├── device-generic-x86_64/
│   └── mkosi.conf
├── ui-console/
│   └── mkosi.conf
├── ui-phosh/
│   └── mkosi.conf
├── ui-plasma-mobile/
│   └── mkosi.conf
```

### Deploying on HTTP server

The postmarketOS infra is currently hosting images at https://duranium.postmarketos.org. The information below is included in case this needs to change in the future. For now, images are being built and pushed there automatically by gitlab CI. See here for more info: https://gitlab.postmarketos.org/postmarketOS/duranium/-/issues/6

sysupdate is configured to query/fetch image updates from a remote HTTP server. Images should be laid out on the server under directories named after the image's `ImageId`, and each `ImageId` directory should contain a file `SHA256SUMS` that serves as a manifest of available images for sysupdate along with a checksum of the image files. This manifest should be signed (`SHA256SUMS.gpg`), and the public key included in images created by mkosi so that they can be verified at runtime.

Image files (except the UKI) will be compressed to save space on the server and reduce download size.

An example layout might look something like this:

```
qemu-aarch64_console_edge/
├── qemu-aarch64_console_edge_25081111.efi
├── qemu-aarch64_console_edge_25081111.usr-arm64-verity-sig.e57b459d4a3f4260805fb3481f99b1de.raw.xz
├── qemu-aarch64_console_edge_25081111.usr-arm64-verity.4c62010a14dda6d767e3108092367651.raw.xz
├── qemu-aarch64_console_edge_25081111.usr-arm64.77415c80aa85f09c68ab25fba2481fa2.raw.xz
├── qemu-aarch64_console_edge_25082001.efi
├── qemu-aarch64_console_edge_25082001.usr-arm64-verity-sig.1ed99882ef219b02a5a5dcd0e8127161.raw.xz
├── qemu-aarch64_console_edge_25082001.usr-arm64-verity.5d8faa5c7560e499080bd6993ed67359.raw.xz
├── qemu-aarch64_console_edge_25082001.usr-arm64.60c62c8db2a1c111ad9d53fe69a74074.raw.xz
├── SHA256SUMS
├── SHA256SUMS.gpg
pine64-pinephonepro_phosh_edge/
├── pine64-pinephonepro_phosh_edge_25081111.efi
├── pine64-pinephonepro_phosh_edge_25081111.usr-arm64-verity-sig.6cc10fdd3e5ac8377defe389c21c47d6.raw.xz
├── pine64-pinephonepro_phosh_edge_25081111.usr-arm64-verity.e07910a06a086c83ba41827aa00b26ed.raw.xz
├── pine64-pinephonepro_phosh_edge_25081111.usr-arm64.34c5f9b2cd3e1504604d186a190cbaaf.raw.xz
├── SHA256SUMS
├── SHA256SUMS.gpg
```

A mkosi profile, `compressed`, will automatically compress the usr+verity partitions and generate a SHA256SUMs file with these artifacts listed in it that can be appended to an existing manifest on the HTTP server when the new artifacts are deployed to it.

## Booting

As mentioned previously, EFI is required for booting Duranium.

* **DTB devices**: UKI contains multiple `.dtbauto` sections with all required DTBs embedded. U-boot looks for dtbs in well known paths in the ESP (e.g. `/dtbs`) so in addition to embedding dtbs, dtb files will be maintained in this path too.

* **ACPI devices**: Standard UKI without DTB sections, relies on firmware-provided ACPI

### Pre-kernel Boot Flow

1. **systemd-boot**: selects boot entries by sorting UKI files by version and boot count status. Entries without counters (successful boots) are preferred, followed by entries with tries remaining (+N suffix), then entries with zero tries left (marked bad).

2. **DTB Matching**: systemd-stub reads `compatible` from EFI table, finds matching `.dtbauto` section in UKI, replaces temporary DTB with version-matched one. This is not applicable for devices that support ACPI.

3. **Kernel Launch**: Boot proceeds with kernel boot

### Initramfs

The initramfs is built by mkosi and runs systemd as init. This replaced an earlier POC approach that modified the pmOS mkinitfs-generated initramfs, which was complicated and buggy. Switching to the mkosi initramfs solved several outstanding issues, particularly around disk detection (systemd in the initramfs sets up disks/partitions and the state persists seamlessly into the rootfs after switch-root).

All boot logic (first boot, normal boot, factory reset) is implemented as systemd units in the initramfs. systemd handles /usr partition + dm-verity setup automatically via `usrhash=` in the kernel cmdline. For Android devices with nested subpartitions, a systemd unit runs early in boot to scan and initialize them (using the same logic from the pmOS initramfs).

`mkosi.finalize` patches `initrd-release` in the initramfs with the correct `IMAGE_ID` and related variables, which is necessary for factory reset to work, since systemd-repart compares the IMAGE_ID in the EFI variable with the value in `/etc/initrd-release` to make sure it's resetting the correct OS.

**Normal boot flow:**

1. Subpartitions scanned/initialized (if applicable)

2. systemd detects LUKS partition for root. unl0kr is configured as a password agent for systemd to unlock it.

3. systemd automatically handles /usr partition + dm-verity setup

4. switchroot

**First boot flow:**

1. systemd-repart in the initramfs creates missing partitions (B-slot usr + verity, and rootfs). Rootfs is always created on a LUKS volume with a default blank passphrase.

2. Subpartitions scanned/initialized (if applicable), then systemd switches root

3. f0rmz runs in the rootfs, triggered by a sentinel file under `/etc`. It creates the user account and optionally sets a custom LUKS passphrase (replacing the blank passphrase set by repart). f0rmz was chosen over UI-specific first boot tools (gnome-initial-setup, Plasma setup) because it allows prompting for and setting a FDE passphrase, and is UI-agnostic. f0rmz is based on the buffybox/unl0kr codebase and is still incomplete.

**Factory reset flow:**

1. Triggered from the rootfs, e.g. `systemctl start systemd-factory-reset-request && reboot`. This sets the `FactoryResetRequest` EFI variable with OS data from `/etc/os-release`.

2. On next boot, systemd-repart in the initramfs detects the EFI variable, deletes the rootfs, and recreates it

3. Boot proceeds as first boot

## Populating /etc

Since many packages in Alpine Linux do not support a hermetic /usr install, we must handle this at image build time in a way that does not break existing applications while also giving power users / system admins a way to override defaults and make changes to system software in an immutable installation. Using systemd-tmpfiles helps accomplish this. On first boot when /etc is effectively empty, systemd-tmpfiles will read generated configuration in the immutable /usr partition to populate /etc.

While building an image, tmpfiles.d configuration is generated to create a hybrid /etc structure of symlinks and real directories:

* **Directories**: Create real directories in /etc matching /usr/share/factory/etc structure with preserved permissions

* **Files**: Create symlinks in /etc pointing to factory files

**Benefits:**

* Updates to factory files automatically propagate to /etc through symlinks

* Admins can override individual files by breaking symlinks without affecting other configs in the same directory

* Simpler customization workflow compared to bulk directory copying, which would also break auto-propagation of updates for files unrelated to those that were modified by the user/sysadmin.

**Example**: `/etc/ssh/` becomes a real directory with `/etc/ssh/sshd_config` as a symlink to `/usr/share/factory/etc/ssh/sshd_config`. Admin override: `cp /usr/share/factory/etc/ssh/sshd_config /etc/ssh/` breaks the symlink while other configs in this directory remain current with factory.

**Exceptions:**

* **User/group databases**: These files are not copied or symlinked from the factory since doing so would overwrite any changes from first boot configuration.

* **Backup files / machine-specific config**: These are also skipped entirely: backup files (`passwd-`, `group-`, `shadow-`), lock files (`.pwd.lock`), machine-specific files (`machine-id`, `hostname`)

* **Create empty**: `fstab` using tmpfiles.d "f" directive

* **Skeleton directory**: `/etc/skel` is moved to `/usr/share/skel` at build time so that `useradd` copies real files into `~/` rather than symlinks back into the immutable /usr tree. `/etc/default/useradd` is configured with `SKEL=/usr/share/skel` to point at the new location.

## Factory Reset

Some other immutable OS designs using systemd tooling (e.g. ParticleOS) use a kernel command line parameter to trigger a factory reset condition. This is accomplished by building a UKI with a profile to add this parameter and named something like "Factory Reset", and the bootloader (systemd-boot) exposes this option in the boot menu. Having this as a boot menu option could lead to an accidental (or malicious) factory reset of the device, since it doesn't require any authentication to select this boot option and could be done unintentionally with a misplaced click/button press. There's also some risk that this option might be auto-selected by the bootloader! In the best case this is inconvenient if the user has good backups, but a more likely worst case is unrecoverable loss of data.

To help avoid this situation, this design relies on systemd's factory reset infrastructure to set an EFI variable that systemd-repart detects on the next boot. The variable is set from within an authenticated OS session (e.g. via `systemd-factory-reset-request.service`), and could be wrapped behind a GUI application in userspace to make it user-friendly. SecureBoot further limits the scope where this variable could be set.

This uses systemd's factory reset infrastructure (requires systemd >=258) <https://www.freedesktop.org/software/systemd/man/devel/systemd-factory-reset.html>

**Flow:**

1. User triggers factory reset from authenticated OS session (e.g. `systemctl start systemd-factory-reset-request`, or a GUI that calls into it)

2. The `FactoryResetRequest` EFI variable is set, which the initramfs/repart will detect on the next boot to trigger the reset process.

3. System is rebooted

4. See Initramfs section above for the factory reset boot flow

## References

* [Fitting Everything Together](https://0pointer.net/blog/fitting-everything-together.html)

* [ParticleOS](https://github.com/particle-iot/particle-os)
