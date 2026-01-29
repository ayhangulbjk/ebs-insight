#!/usr/bin/env python
"""Simple git push script"""
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
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    sys.exit(result.returncode)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
