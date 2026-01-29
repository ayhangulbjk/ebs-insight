#!/usr/bin/env python
"""Restore files from git"""
import subprocess

files = [
    "knowledge/controls/concurrent_mgr_health.json",
    "knowledge/controls/adop_status.json"
]

for f in files:
    result = subprocess.run(
        ["git", "checkout", f],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=10
    )
    print(f"Restored {f}: {result.returncode}")
    if result.returncode != 0:
        print(result.stderr)
