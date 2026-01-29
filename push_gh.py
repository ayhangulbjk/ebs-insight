#!/usr/bin/env python
"""Using gh CLI for push"""
import subprocess
import sys

try:
    print("=== Testing GH CLI ===")
    result = subprocess.run(
        ["gh", "auth", "status"],
        cwd=r"d:\ebs-insight",
        capture_output=True,
        text=True,
        timeout=10
    )
    print(result.stdout)
    print(result.stderr)
    
    if result.returncode == 0:
        print("\n=== GH PUSH ===")
        result = subprocess.run(
            ["gh", "repo", "push"],
            cwd=r"d:\ebs-insight",
            capture_output=True,
            text=True,
            timeout=30
        )
        print(result.stdout)
        print(result.stderr)
    else:
        print("GH CLI not authenticated, trying git push with GIT_TRACE")
        import os
        env = os.environ.copy()
        env['GIT_TRACE'] = '1'
        result = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=r"d:\ebs-insight",
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        print("Return:", result.returncode)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
