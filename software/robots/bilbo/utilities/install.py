import subprocess
import platform
import urllib.request
import os
import sys


def check_nodejs():
    """Check if Node.js and npm are installed on the system."""
    try:
        result = os.popen("npm --version").read()
        if result == '':
            return False
        else:
            return True
    except Exception:
        return False


def download_nodejs():
    """Download and install the Node.js prebuilt installer."""
    # Determine the OS and download URL
    system = platform.system().lower()
    node_version = "18.17.1"  # Specify the desired version here

    if system == "windows":
        nodejs_url = f"https://nodejs.org/dist/v{node_version}/node-v{node_version}-x64.msi"
        installer_file = "nodejs_installer.msi"
    elif system == "darwin":
        nodejs_url = f"https://nodejs.org/dist/v{node_version}/node-v{node_version}.pkg"
        installer_file = "nodejs_installer.pkg"
    elif system == "linux":
        # For Linux, downloading a binary tarball or using a package manager is typically preferred.
        # Here, we'll download the tarball version as an example.
        nodejs_url = f"https://nodejs.org/dist/v{node_version}/node-v{node_version}-linux-x64.tar.xz"
        installer_file = "nodejs_installer.tar.xz"
    else:
        print("Unsupported operating system.")
        return

    # Download the Node.js installer
    print(f"Downloading Node.js from {nodejs_url}...")
    urllib.request.urlretrieve(nodejs_url, installer_file)
    print("Download complete.")

    # Install Node.js based on OS
    try:
        if system == "windows":
            # Run the .msi installer for Windows
            subprocess.check_call(["msiexec", "/i", installer_file, "/quiet", "/norestart"])
            print("Node.js installed successfully on Windows.")
        elif system == "darwin":
            # Run the .pkg installer for macOS
            subprocess.check_call(["sudo", "installer", "-pkg", installer_file, "-target", "/"])
            print("Node.js installed successfully on macOS.")
        elif system == "linux":
            # For Linux, extract the tarball and set up Node.js
            subprocess.check_call(["tar", "-xf", installer_file])
            # Move the extracted folder to a directory in PATH, like /usr/local (requires sudo)
            node_dir = f"node-v{node_version}-linux-x64"
            subprocess.check_call(["sudo", "mv", node_dir, "/usr/local/"])
            # Link node and npm binaries to /usr/local/bin for easier access
            subprocess.check_call(["sudo", "ln", "-sf", f"/usr/local/{node_dir}/bin/node", "/usr/local/bin/node"])
            subprocess.check_call(["sudo", "ln", "-sf", f"/usr/local/{node_dir}/bin/npm", "/usr/local/bin/npm"])
            print("Node.js installed successfully on Linux.")
    except subprocess.CalledProcessError as e:
        print("An error occurred during installation.")
        print(e)

    # Clean up the installer file
    if os.path.exists(installer_file):
        os.remove(installer_file)
        print("Installer file removed.")


def main():
    if (3, 10) <= sys.version_info < (3, 12):
        print("Python version is compatible.")
    else:
        print("Incompatible Python version detected. Please use Python 3.10 or 3.11.")
    # Install all required packages
    try:
        # Run pip install with requirements.txt
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("All required packages have been installed.")
    except subprocess.CalledProcessError as e:
        print("An error occurred while installing packages.")
        print(e)

    # Install the GUI

    import extensions.gui._archive.nodejs_gui.nodejs_gui as gui
    # Check for Node.js
    nodejs_installed = check_nodejs()
    if not nodejs_installed:
        print("Node.Js is not installed")
        print("Node.Js Prebuilt Installer can be found here: https://nodejs.org/en/download/prebuilt-installer")
        return
    gui.install()

    print("Successfully installed the Robot Manager")


if __name__ == '__main__':
    main()
