# Design

See `DESIGN.md`.

# How to use

Build image: `./build-image.py device-qemu-aarch64 ui-console release-edge`

Boot image in qemu: `mkosi vm`

Build compressed image (e.g. for deployment on HTTP server): `./build-image.py device-qemu-aarch64 ui-console release-edge --profile=compressed`
