#!/usr/bin/env python3
import sys
from pathlib import Path
from jinja2 import Template

sys.path.insert(0, str(Path(__file__).parent))
from combos import IMAGE_COMBOS

if len(sys.argv) != 3:
    print("usage: generate_image_jobs.py TEMPLATE OUTPUT")
    sys.exit(1)

template = Template(Path(sys.argv[1]).read_text())
output = template.render(image_combos=IMAGE_COMBOS)
Path(sys.argv[2]).write_text(output)
