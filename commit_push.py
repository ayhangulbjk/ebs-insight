#!/usr/bin/env python
"""Commit and push changes"""
import subprocess
import sys
import os

os.chdir(r"d:\ebs-insight")

try:
    # Stage files
    print("=== Staging files ===")
    result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True, timeout=10)
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    
    # Commit
    print("\n=== Committing ===")
    result = subprocess.run(
        ["git", "commit", "-m", "fix: Fix ORA-01036 execute timeout and add error collection"],
        capture_output=True, text=True, timeout=10
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    
    # Push
    print("\n=== Pushing ===")
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True, timeout=30
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    
    print("\n=== Done ===")
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
