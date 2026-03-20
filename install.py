"""
Installer for WYSIWYG HTML Editor dependencies.
Run this before launching main.py for the first time.
"""

import subprocess
import sys

REQUIREMENTS = [
    "PyQt6>=6.6.0",
    "PyQt6-WebEngine>=6.6.0",
    "pygments>=2.17.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.1.0",
]


def main():
    print("=" * 50)
    print("  WYSIWYG HTML Editor — Dependency Installer")
    print("=" * 50)
    print()

    failed = []
    for pkg in REQUIREMENTS:
        print(f"Installing {pkg} ...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"  OK")
        else:
            print(f"  FAILED: {result.stderr.strip().splitlines()[-1]}")
            failed.append(pkg)
        print()

    print("=" * 50)
    if failed:
        print(f"Some packages failed to install: {', '.join(failed)}")
        print("Try running:  pip install " + " ".join(failed))
    else:
        print("All dependencies installed successfully!")
        print("You can now run:  python main.py")
    print("=" * 50)

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
