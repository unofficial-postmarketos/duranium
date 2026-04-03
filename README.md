# Design

See `DESIGN.md`.

# How to use

Build image: `./build-image.py device-qemu-aarch64 ui-console --release=edge`

Boot image in qemu: `mkosi vm`

Build compressed image (e.g. for deployment on HTTP server): `./build-image.py device-qemu-aarch64 ui-console --release=edge --profile=compressed`

# Building images for different architectures

The `device-*` profiles should specify an `Architecture=`, and mkosi should be able to, with the help of binfmt+qemu, build images for different architectures. If there are exec failures, make sure that there's binfmt config registered for the target arch. If you ran `pmbootstrap` recently, make sure to `pmbootstrap shutdown` because it'll stomp on any binfmt config necessary for mkosi to work correctly.

# CI Pipelines

There are two Gitlab CI pipelines:

- **Weekly build** (`main` branch): Builds all device/UI/release combinations and deploys to the remote server (duranium.postmarketos.org). Packages come from the postmarketOS binary repo.

- **Staging build** (`staging` branch): Builds a reduced set of device/UI combinations for testing. It is triggered manually, and not scheduled. It builds packages from the `duranium/staging` pmaports branch. Artifacts are deployed under a `staging/` prefix on the remote server, and they are isolated from production images.

The staging pipeline is used to validate changes (new sysexts, transfer file updates, package changes, etc.) before they land on main.

## Switching a device to staging

    duranium-set-channel staging

This rewrites the sysupdate transfer files in /etc/sysupdate.d/ to pull from the staging server path. To switch back:

    duranium-set-channel main

Note: the /etc/ overrides are full copies of the transfer files. If the base transfer files change after an OS update, run `duranium-set-channel staging` again to pick up the changes.
