#!/usr/bin/env python
"""Push with SSH timeout and GIT_SSH_COMMAND"""
import subprocess
import sys
import os

try:
    env = os.environ.copy()
    # Set SSH timeout to 10 seconds
    env['GIT_SSH_COMMAND'] = 'ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new'
    env['GIT_TRACE'] = '1'
    
    print("=== ADD FILES ===")
    result = subprocess.run(
        ["git", "add", "-A"],
        cwd=r"d:\ebs-insight",
        timeout=5
    )
    
    print("=== COMMIT ===")
    result = subprocess.run(
        ["git", "commit", "-m", "fix: OllamaClient attribute references"],
        cwd=r"d:\ebs-insight",
        timeout=5
    )
    
    print("=== PUSH (with SSH timeout) ===")
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=r"d:\ebs-insight",
        timeout=30,
        env=env
    )
    print("Push completed with return code:", result.returncode)
    
except subprocess.TimeoutExpired as e:
    print(f"Timeout: {e}")
except Exception as e:
    print(f"Error: {e}")
