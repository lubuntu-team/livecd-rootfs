#!/usr/bin/python3
import apt
import os
import platform
import datetime
from datetime import datetime, timezone

# Get the current date and time in UTC timezone aware
utc_now = datetime.now(timezone.utc)

def get_system_architecture():
    arch = platform.machine()
    if arch == 'x86_64':
        return 'amd64'
    elif arch == 'aarch64':
        return 'arm64'
    else:
        return f"Unknown architecture: {arch}"

print("Format: 1.0")
print("Build-Origin: Ubuntu")
print(f"Build-Architecture: {get_system_architecture()}")
print(f"Build-Date: {utc_now}")
# Using python-apt to gather installed packages
try:
    package_cache = apt.Cache()

    print("List of installed packages:")
    for package in package_cache:
        if package.is_installed:
            print(f" {package.name} (= {package.installed.version}),")

except Exception as e:
    print(f"An error occurred while fetching installed packages: {e}")

# Using os module to list all environment variables
try:
    print("\nEnvironment variables:")
    for param, value in os.environ.items():
        print(f" {param}={value}")

except Exception as e:
    print(f"An error occurred while fetching environment variables: {e}")
