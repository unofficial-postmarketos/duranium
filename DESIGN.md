# Overview

This document outlines an immutable, image-based design of postmarketOS following the concepts from systemd's "Fitting Everything Together" approach.

The design uses mkosi for image building with systemd tooling for A/B updates (systemd-sysupdate), partition management (systemd-repart ), and slot boot selection and automatic fallback on failure (systemd-boot). EFI is chosen as the boot interface because it provides a simple, easy way to configure the OS for booting and integrates seamlessly with the systemd tooling being used. UKI (Unified Kernel Images) enable future secure boot capabilities and simplify image-based updates by bundling kernel, initramfs, cmdline, and DTBs as versioned artifacts. For ARM devices lacking native EFI support (e.g. Android phones), u-boot with EFI capabilities is expected to bridge this gap. While the systemd tooling could (in theory) work standalone with OpenRC, this design currently requires that postmarketOS is built with systemd support enabled.

# Features

* **Hermetic /usr**: All OS resources contained in an immutable /usr partition

* **A/B Updates**: Atomic updates via partition switching

* **Factory Reset**: Easy restoration to known-good state

* **Image-based**: Move from package-based to image-based deployment

* **dm-verity**: Cryptographic integrity verification of /usr partition

* **Encrypted rootfs**: LUKS encryption for user data protection

* **UKI/Type 2 booting**: Unified kernel images with embedded initramfs and DTBs

* **Remote HTTP updates**: OTA updates via systemd-sysupdate from remote servers

* **First-boot provisioning**: Initial setup wizard assists user with creating account

# System Architecture

## Boot Overview

This design uses Type 2 booting with UKI, as defined in the UAPI Boot Loader Spec.

Type 1 Boot, where the kernel, initramfs, dtbs are separate files in the ESP, make image creation with mkosi and image-based updates with sysupdate very difficult. More specifically:

* **No ESP Update Mechanism**: mkosi uses kernel version paths (`/postmarketOS/6.15.8-0-stable/`) not IMAGE_VERSION. This means that boot artifacts (kernel) are not coupled with usr partition versions for sysupdate. In other words, it means that /usr/lib/modules may not match the booted kernel, and this is bad.

* **Verity Hash Timing**: `mkosi.finalize` runs before verity calculation, and `mkosi.postoutput` runs after the ESP partition is finalized/exported, so there's no scriptable point where the usrhash can be injected into the cmdline manually. Using mkosi's kernel-install mechanism isn't possible either since it writes to paths using kernel versions, and not IMAGE_VERSION. Given the previously mentioned issue, when sysupdate updates the usr partition, the loader config in the ESP will have a stale `usrhash=` value. Stale `usrhash=` values in the kernel cmdline break dm-verity.

* **Complex sysupdate.transfer config**: Trying to create an ESP layout with versioned Type 1 artifacts and a sysupdate config that can manage them all (so they can get updated) is difficult and fragile.

* **No SecureBoot Support**: While SecureBoot is not a requirement for an immutable pmOS, choosing a boot implementation that doesn't really support it will make supporting it more difficult in the future.

### Why UKI makes sense

UKI resolves/avoids all Type 1 limitations when using mkosi for image creation and sysupdate for image-based updates:

* **Automatic Verity**: mkosi injects `usrhash=` into UKI cmdline during build automatically, no need to patch mkosi to do this

* **Proper Versioning**: UKI files use versioning compatible with other sysupdated artifacts, with boot counting (e.g. `p64_pho_phosh_edge_24011501_arm64.efi+3-0.efi`), the same versioning is used to couple UKI with the correct usr partition for module loading.

* **Easy sysupdate.transfer config**: Single .efi file contains kernel + initramfs + cmdline + DTB(s), updated atomically by sysupdate, and the sysupdate.transfer configuration to handle this is very simple and straightforward.

* **SecureBoot support**: Entire UKI signed as single unit

### Supported Device Boot Scenarios

This uses boot-deploy's existing DTB resolution logic (by reading the sd-boot configuration boot-deploy generates) rather than reimplementing deviceinfo parsing, and doesn't seem to introduce any blockers to later SecureBoot compatibility.

* **u-boot + explicit DTB**: boot-deploy resolves DTB from deviceinfo, this dtb is embedded in UKI `.dtbauto` and copied to `/dtbs/` in the ESP for u-boot

* **u-boot + auto-detect**: u-boot provides DTB from internal logic, so embed all `/dtbs/` in UKI

* **WoA + explicit DTB**: boot-deploy resolves DTB from deviceinfo, this dtb is embedded in the UKI + copied to `/dtbs/` in the ESP for dtbloader

* **WoA + auto-detect**: dtbloader detects from `/dtbs` OR `/dtbs` is missing, embed all `/dtbs/` in UKI

* **ACPI devices**: No DTB sections in UKI, normal ACPI boot

**Note about embedding many devicetrees in a UKI**: Embedding all ~1.6K dtbs shipped in the postmarketos-linux-next kernel and booting it on a Thinkpad X13s resulted in no perceived delay in booting while the stub detected/loaded the correct dtb for this device from the large selection of embedded dtbs.

## Versioning

A lot consideration was taken to choose a versioning scheme for images, because there are several components that need to agree on a versioning scheme and some of these components have constraints that need to be accounted for. These components use an `ImageId` (aka `IMAGE_ID` in os-release) and `ImageVersion` (aka `IMAGE_VERSION` in os-release).

* **mkosi**: Uses the id+version to generate image artifacts that are ultimately enumerated/fetched by sysupdate.

* **sysupdate**: Uses the id+version to identify when updates are available. Sysupdate uses the id+version info that is stored in the GPT partition name to determine which partition to preserve and which one to install an image update to. Sysupdate also requires that newer image updates have an version that's higher than the currently active image.

* **repart**: mkosi calls repart when creating a full disk image for provisioning a system, and embeds the id+version in the active slot partition name.

* **GPT Partition Name**: This field is limited to a maximum of 34 characters, so any id+version needs to fit within this size.

* **postmarketOS**: There are many device ports, dozens of UIs, and multiple releases (edge, stable releases), and the id needs to be able to differentiate between all different combinations so that we do not accidentally cause sysupdate to flash an incompatible image update on a device.

Given all of these requirements, the following format is used:

`{mfg_3}_{model_6}_{ui_5}_{release_4}_{date_6}{rev_2}`

In this format:

* `ImageId / IMAGE_ID` = `{mfg_3}_{model_6}_{ui_5}`

* `ImageVersion / IMAGE_VERSION` = `{date_6}{rev_2}`

**Component Definitions:**

* **mfg (3 chars):** Manufacturer code (`p64`=Pine64, `smg`=Samsung, `mft`=Microsoft, `len`=Lenovo, `ggl`=Google, etc.)

* **model (6 chars):** Device model within manufacturer (`pineph`=PinePhone, `ppp`=PinePhone Pro, `gaxy4m`=Galaxy S4 Mini, `21bx`=Thinkpad x13s/21bx)

* **ui (5 chars):** Interface (`phosh`, `gnomo`=GNOME Mobile, `plamo`=Plasma Mobile)

* **release (4 chars):** `edge` for edge builds, `YYMM` for stable (e.g., `2506` for v25.06)

* **date (6 chars):** `YYMMDD` format (e.g., `240115` for 2024-01-15)

* **rev (2 chars):** Daily revision counter (`01`, `02`, etc.)

For **partition names**, this translates to: `Version` + `_{suffix_3}` where suffix = `usr`, `vty`, `vts` for the usr, usr-verity, and user-verity-signing partitions respectively.

**Examples:**

* Edge: `p64_pineph_phosh_edge_24011501`

* Stable: `p64_pineph_phosh_2506_24011501`

* Partition labels: `p64_pineph_phosh_edge_24011501_usr`, `p64_pineph_phosh_edge_24011501_vty`

## Partition Layout

**Initial shipped image:**

1. ESP (EFI System Partition) with systemd-boot, UKI, DTBs (for dtbloader/u-boot compatibility, separate from UKI-embedded DTBs)

2. /usr partition (version A) - immutable, labeled with image version

3. Verity partition for /usr (version A)

4. Verity signature partition for /usr (version A)

**Created on first boot by systemd-repart:**

1. /usr partition (version B) - initially empty, labeled `_empty`

2. Verity partition for /usr (version B)

3. Verity signature partition for /usr (version B)

4. Root filesystem - encrypted with LUKS (optional)

### ESP Layout for UKI

```
/boot/efi/
├── efi/                                               # installed once, not managed by A/B updates
│   ├── boot/
│   │   └── bootaa64.efi                               # systemd-boot
│   └── systemd/
│       └── drivers/
│           └── dtbloaderaa64.efi                      # Optional, for WoA devices
├── dtbs/                                              # Device detection DTBs (unversioned)
│   ├── qcom/
│   │   ├── sc8280xp-lenovo-thinkpad-x13s.dtb
│   │   └── ...
│   └── ...
└── EFI/Linux/
    ├── len_21b_phosh_edge_25071501_arm64.efi          # UKI (dtb(s) in dtbauto sections)
    └── len_21b_phosh_edge_25071801_arm64.efi+3-0.efi  # Next version with boot counting
```

## Image Building

This build system uses mkosi profiles to generate images for postmarketOS's many device, UI, and release combinations. Rather than maintaining separate configurations for every possible combination or relying on pmbootstrap/pmaports, three orthogonal profile types (device, UI, release) are composed at build time with mkosi to generate images targeting specific configurations. The 3 profiles are used to generate a unique `ImageId` that describes the device, UI and release combination (see the Version section for more information).

The profiles themselves are quite simple, often just including a single package, but mkosi is quite flexible and they would be expanded to do more stuff later if necessary for building images for a specific device.

### Build Process

1. **Device profile** installs device-specific package

2. **UI profile** installs UI-specific package

3. **Release profile** configures repository sources for specific pmOS release

4. Images are built using `build-image.py` wrapper script with these 3 profiles

5. Wrapper validates exactly one profile of each type is provided

6. Wrapper generates `ImageId` from profile names (see Versioning section)

7. Wrapper invokes mkosi with computed `ImageId` and profiles

8. mkosi calculates `ImageVersion` and builds the image for the specified device, UI, and release

### Profile Structure

```
mkosi.profiles/
├── device-pine64-pinephone/
│   └── mkosi.conf
├── device-samsung-galaxy-s4-mini/
│   └── mkosi.conf
├── ui-plasma-mobile/
│   └── mkosi.conf
├── ui-gnome-mobile/
│   └── mkosi.conf
├── ui-phosh/
│   └── mkosi.conf
├── release-edge/
│   └── mkosi.conf
└── release-v25.06/
    └── mkosi.conf
```

### Deploying on HTTP server

sysupdate is configured to query/fetch image updates from a remote HTTP server. Images should be laid out on the server under directories named after the image's `ImageId`, and each `ImageId` directory should contain a file `SHA256SUMS` that serves as a manifest of available images for sysupdate along with a checksum of the image files. This manifest should be signed (`SHA256SUMS.gpg`), and the public key included in images created by mkosi so that they can be verified at runtime.

Image files (except the UKI) will be compressed to save space on the server and reduce download size.

An example layout might look something like this:

```
qmu_a64_consol_edge/
├── qmu_a64_consol_edge_25081111_arm64.efi
├── qmu_a64_consol_edge_25081111_arm64.usr-arm64-verity-sig.e57b459d4a3f4260805fb3481f99b1de.raw.xz
├── qmu_a64_consol_edge_25081111_arm64.usr-arm64-verity.4c62010a14dda6d767e3108092367651.raw.xz
├── qmu_a64_consol_edge_25081111_arm64.usr-arm64.77415c80aa85f09c68ab25fba2481fa2.raw.xz
├── qmu_a64_consol_edge_25081111_arm64.efi
├── qmu_a64_consol_edge_25082001_arm64.usr-arm64-verity-sig.1ed99882ef219b02a5a5dcd0e8127161.raw.xz
├── qmu_a64_consol_edge_25082001_arm64.usr-arm64-verity.5d8faa5c7560e499080bd6993ed67359.raw.xz
├── qmu_a64_consol_edge_25082001_arm64.usr-arm64.60c62c8db2a1c111ad9d53fe69a74074.raw.xz
├── SHA256SUMS
├── SHA256SUMS.gpg
p64_ppp_phosh_edge/
├── p64_ppp_phosh_edge_25081111_arm64.efi
├── p64_ppp_phosh_edge_25081111_arm64.usr-arm64-verity-sig.6cc10fdd3e5ac8377defe389c21c47d6.raw.xz
├── p64_ppp_phosh_edge_25081111_arm64.usr-arm64-verity.e07910a06a086c83ba41827aa00b26ed.raw.xz
├── p64_ppp_phosh_edge_25081111_arm64.usr-arm64.34c5f9b2cd3e1504604d186a190cbaaf.raw.xz
├── SHA256SUMS
├── SHA256SUMS.gpg
```

A mkosi profile, `compressed`, will automatically compress the usr+verity partitions and generate a SHA256SUMs file with these artifacts listed in it that can be appended to an existing manifest on the HTTP server when the new artifacts are deployed to it.

## Booting

As mentioned previously, EFI is required for booting in this design. Devicetree handling, where u-boot or dtbloader are used, and "generic" kernels (i.e. support multiple devices) were considered.

* **DTB devices**: UKI contains multiple `.dtbauto` sections with all required DTBs embedded. U-boot and dtbloader look for dtbs in well known paths in the ESP (e.g. `/dtbs`) so in addition to embedding dtbs, dtb files will be maintained in this path too.

* **ACPI devices**: Standard UKI without DTB sections, relies on firmware-provided ACPI

### Pre-kernel Boot Flow

1. **Device Detection**: dtbloader (WoA) or u-boot reads DTBs from `/dtbs/` to identify device and set `compatible` string via EFI configuration table. These are unversioned, and not updated by sysupdate, and this is fine since they only serve to assist u-boot or dtbloader with selecting the correct dtb embedded in a (versioned) UKI. This is not applicable for devices that support ACPI.

2. **systemd-boot**: selects boot entries by sorting UKI files by version and boot count status. Entries without counters (successful boots) are preferred, followed by entries with tries remaining (+N suffix), then entries with zero tries left (marked bad).

3. **DTB Matching**: systemd-stub reads `compatible` from EFI table, finds matching `.dtbauto` section in UKI, replaces temporary DTB with version-matched one. This is not applicable for devices that support ACPI.

4. **Kernel Launch**: Boot proceeds with kernel boot

### Initramfs Boot Flows

For first boot configuration, a new wizard application that runs from the initramfs will be created, named f0rmz. It's based on the buffybox/unl0kr codebase. In the flows below, rootfs encryption is optional and if it's not enabled then any steps explicitly listing encryption or decryption would be skipped.

Brief overview: initramfs starts → detect if first boot and handle it → parse usrhash= and verify /usr with dm-verity → mount, create or decrypt rootfs → switchroot

**First boot flow:**

1. Detect root missing

2. Run f0rmz to prompt user for username, passwords, encryption choice

3. Create repart config with encryption passphrase from user

4. Run systemd-repart with passphrase to create rootfs

5. Mount root

6. Create new user account, configure password

7. Run `systemd-firstboot --root=/sysroot`

8. switchroot

**Factory reset flow:**

1. Detect factory reset flag

2. Run systemd-repart to delete partitions marked `FactoryReset=yes` (e.g. rootfs)

3. First boot logic is triggered since no rootfs exists. f0rmz has a shutdown option

4. If user chooses to continue, proceed with first boot flow above, otherwise device shuts down with user data wiped

**Normal boot flow:**

1. Detect existing root partition

2. Unlock and mount root

3. switchroot

## Initramfs Changes Required

* **Immutable Install Detection**: The presence of `usrhash=` in kernel cmdline is used to detect when initramfs is running for an immutable install or not. This commandline option is only used for dm-verity, so it shouldn't appear in the cli unless dm-verity is being used (i.e. an immutable install boot). The changes in this section **MUST** preserve existing initramfs logic for mutable installs and non-EFI devices, immutable logic is only used when `usrhash=` is present.

* **Boot Device and Root Discovery**: The EFI variable `LoaderDevicePartUUID` is used to get the block device containing the booted ESP. This device is then searched for a rootfs matching the partition type for the system architecture, following the UAPI Discoverable Partition Spec (DPS). Other existing logic in the initramfs for rootfs discovery, e.g. for handling subpartitions/Android logic is not used.

* **Early Boot Decision Making**: For immutable installs, attempt to mount root partition early and check for `/etc/os-release` existence to distinguish:

  * **First Boot**: No root partition or empty partition (missing `/etc/os-release`)

  * **Factory Reset**: Existing partition but empty after systemd-repart factory reset

  * **Normal Boot**: Populated partition with `/etc/os-release` present, implies this is after first rootfs boot of install (since /etc is populated)

* **Parse usrhash= from cmdline and set up dm-verity verified /usr**

  * usrhash contains the partition UUID in the first 128-bits, this will be used to locate the correct usr partition (A or B)

  * Extract UUIDs for both /usr and verity partitions from usrhash value

  * Set up dm-verity mapping then mount /usr

* **Two-Stage Repart Flow for First Boot/Factory Reset:**

  1. Check for `FactoryReset` EFI variable at `/sys/firmware/efi/efivars/FactoryReset-8cf2644b-4b0b-428f-9387-6d876050dc67`

  * NOTE: systemd-258 deprecates this var in favor of `FactoryResetRequest`

  1. systemd-repart handles factory reset (deletes partitions marked `FactoryReset=yes`) if EFI variable present

  2. rootfs created by repart is deleted. If this isn't done, then running repart again to enable encryption does not work as intended because repart will not modify an existing partition, and at this point in the flow we do not know if the user wants to enable encryption.

  3. Run f0rmz for gathering user configuration (username, passwords, encryption choice)

  4. systemd-repart creates/configures partitions based on user input

  5. Create user account, run `systemd-firstboot --root=/sysroot`

  6. Continue normal initramfs boot with root partition

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

## Factory Reset

Some other immutable OS designs using systemd tooling (e.g. ParticleOS) use a kernel command line parameter to trigger a factory reset condition. This is accomplished by building a UKI with a profile to add this parameter and named something like "Factory Reset", and the bootloader (systemd-boot) exposes this option in the boot menu. Having this as a boot menu option could lead to an accidental (or malicious) factory reset of the device, since it doesn't require any authentication to select this boot option and could be done unintentionally with a misplaced click/button press. There's also some risk that this option might be auto-selected by the bootloader! In the best case this is inconvenient if the user has good backups, but a more likely worst case is unrecoverable loss of data.

To help avoid this situation, this design will instead rely on setting an EFI variable that systemd-repart supports for triggering a factory reset. This variable is typically set from within an authenticated OS session, and could be wrapped behind a GUI application in userspace to make it user-friendly. SecureBoot further limits the scope where this variable could be set.

This uses systemd's factory reset infrastructure, which required systemd >=258) <https://www.freedesktop.org/software/systemd/man/devel/systemd-factory-reset.html>

**Flow:**

1. User triggers factory reset from authenticated OS session (using systemd-factory-reset, or a GUI that calls into it)

2. systemd-factory-reset sets the `FactoryResetRequest` EFI variable which the initramfs/repart will detect on the next boot to trigger the reset process.

3. System is rebooted

4. See info above about Initramfs Changes Required for exact flow of factory reset in the initramfs

# Open Questions / Future Work

* Migration tool for existing installations? (TBD)

* systemd-homed integration for user home encryption?

* Subpartitions for devices without GPT support

* SecureBoot / trusted booting with signed verity

* TPM2 support where available

* U-Boot with EFI support for ARM devices

* Get rid of /esp/dtbs:

  * ensure u-boot always provides it's dtb if none is found on esp

  * update dtbloader to generate stub dtb for supported devices

* Or support dtbloader for auto-loading device-trees

  * Doesn't work with versioned artifacts in ESP

  * Casey working on proposal to BLS to make this possible

* Investigate using mkosi's kernel-install implementation for generating/installing boot artifacts

  * This installs artifacts in the esp using kernel version, not image version so not really possible to sysupdate and couple with usr partition updates

  * This may not be desired/necessary after all if we stick with UKI

* Update mechanism for ESP/efi (systemd-boot, dtbloader, etc)

  * E.g. bootupctl from silverblue?

* What do to about pmb_recommends and pmb_select?

  * mkosi building images doesn't include packages listed here

  * abuild doesn't include them either, for obvious reasons

  * These packages are no longer 'optional dependencies' in the context of an immutable image, so maybe we should build an "immutable" subpackage for packages that have these where `depends=$_pmb_recommend` and have that get pulled in automatically?

* Generate basic repart config from deviceinfo (filesystem only)

  * No one seems to be using deviceinfo_root_filesystem in pmaports...

* Create a UX-friendly GUI app for triggering a factory reset from within the OS on next boot

  * should allow canceling the request

  * should give an option to reboot now/immediately to process the request

* Could this project help simplify managing BLS-compliant ESP? <https://github.com/AerynOS/blsforme>

* Partition sizing - updates vs wasted space:

  * Conservative sizing wastes space but prevents update failures.

  * Aggressive sizing risks future updates being too large for target partitions.

  * Particularly problematic on storage-constrained devices.

* Image building, on bpo or ??

  * Manifest (and images?) should be signed so they can be verified by sysupdate, keys will need to be baked into the image

## Dependencies

* Extended unl0kr for first boot UI (pmaports#2776)

* mkosi support for pmOS (mkosi#3781)

## References

* [Fitting Everything Together](https://0pointer.net/blog/fitting-everything-together.html)

* [ParticleOS](https://github.com/particle-iot/particle-os)

