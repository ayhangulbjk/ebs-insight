#!/usr/bin/env python
"""Git push script"""
import subprocess
import sys

try:
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=30
    )
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    print("Return code:", result.returncode)
    sys.exit(result.returncode)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
