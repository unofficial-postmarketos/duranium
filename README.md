# Design

See `DESIGN.md`.

# How to use

Build image: `./build-image.py device-qemu-aarch64 ui-console --release=edge`

Boot image in qemu: `mkosi vm`

Build compressed image (e.g. for deployment on HTTP server): `./build-image.py device-qemu-aarch64 ui-console --release=edge --profile=compressed`

# Building images for different architectures

The `device-*` profiles should specify an `Architecture=`, and mkosi should be able to, with the help of binfmt+qemu, build images for different architectures. If there are exec failures, make sure that there's binfmt config registered for the target arch. If you ran `pmbootstrap` recently, make sure to `pmbootstrap shutdown` because it'll stomp on any binfmt config necessary for mkosi to work correctly.
