#!/usr/bin/env python
"""Git commit and push with longer timeout"""
import subprocess
import sys

try:
    # First, check git status
    print("=== GIT STATUS ===")
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout)
    
    # Add all changes
    print("\n=== GIT ADD ===")
    result = subprocess.run(
        ["git", "add", "-A"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=10
    )
    print("Added files")
    
    # Commit
    print("\n=== GIT COMMIT ===")
    result = subprocess.run(
        ["git", "commit", "-m", "fix: OllamaClient attribute references (model_name, summary_bullets)"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
    
    # Push with 60 second timeout
    print("\n=== GIT PUSH (60s timeout) ===")
    result = subprocess.run(
        ["git", "push", "origin", "main", "-v"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=60
    )
    print(result.stdout)
    print(result.stderr)
    print(f"Return code: {result.returncode}")
    
except subprocess.TimeoutExpired:
    print("TIMEOUT - but push may have started in background")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
