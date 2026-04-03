#!/usr/bin/env python3
import sys
import os
from pathlib import Path
from jinja2 import Template

sys.path.insert(0, str(Path(__file__).parent))
from config import IMAGE_COMBOS, STAGING_IMAGE_COMBOS

if len(sys.argv) != 3:
    print("usage: generate_image_jobs.py TEMPLATE OUTPUT")
    sys.exit(1)

branch = os.environ.get("CI_COMMIT_BRANCH")
if branch is None:
    print("error: CI_COMMIT_BRANCH is not set", file=sys.stderr)
    sys.exit(1)

if branch == "main":
    image_combos = IMAGE_COMBOS
    remote_base = "/var/www/duranium.postmarketos.org/images"
elif branch == "staging":
    image_combos = STAGING_IMAGE_COMBOS
    remote_base = "/var/www/duranium.postmarketos.org/images/staging"
else:
    print("error: unsupported branch '%s'" % branch, file=sys.stderr)
    sys.exit(1)

template = Template(Path(sys.argv[1]).read_text())
output = template.render(image_combos=image_combos, remote_base=remote_base)
Path(sys.argv[2]).write_text(output)
