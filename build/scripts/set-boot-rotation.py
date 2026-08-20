#!/usr/bin/env python3
"""Sets the fbcon=rotate:N kernel boot parameter in /boot/firmware/cmdline.txt
so the text console (and anything drawing straight to the framebuffer, like
the boot splash) rotates along with the X/touch orientation the wizard set.
Takes effect on next boot. Usage: set-boot-rotation.py <0|1|2|3>
"""
import re
import sys

CMDLINE_PATH = "/boot/firmware/cmdline.txt"

VALID = {"0", "1", "2", "3"}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in VALID:
        sys.exit(f"Usage: {sys.argv[0]} <0|1|2|3>")
    value = sys.argv[1]

    with open(CMDLINE_PATH) as f:
        content = f.read()

    if re.search(r"\bfbcon=rotate:\d+\b", content):
        content = re.sub(r"\bfbcon=rotate:\d+\b", f"fbcon=rotate:{value}", content)
    else:
        content = content.rstrip("\n") + f" fbcon=rotate:{value}\n"

    with open(CMDLINE_PATH, "w") as f:
        f.write(content)


if __name__ == "__main__":
    main()
