import os
import shutil
import subprocess

from core.utils.files import copyFile, dirExists, makeDir, copyFolder


def download_folder_from_github(repo_url, folder_path, destination):
    """
    Downloads a specific folder from a GitHub repository using sparse-checkout,
    manually editing .git/info/sparse-checkout so that only the specified folder
    (and its contents) are included.

    :param repo_url: The URL of the GitHub repository.
    :param folder_path: The path to the folder within the repo to download
                       (e.g., "software/robot/software/BILBO-Software").
    :param destination: The destination directory where the folder will be saved.
    """
    # Create a temporary directory for the repository
    temp_dir = os.path.join(os.path.expanduser("~"), "temp_repo")

    # Ensure the temp directory doesn't already exist
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    try:
        # 1. Clone the repo with minimal checkout (no-checkout)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", repo_url, temp_dir],
            check=True
        )

        # 2. Change to the repo directory
        os.chdir(temp_dir)

        # 3. Enable sparse-checkout in non-cone mode
        subprocess.run(["git", "sparse-checkout", "init", "--no-cone"], check=True)

        # 4. Manually write the desired path to .git/info/sparse-checkout
        #    This ensures only folder_path (and its subdirectories) are checked out.
        folder_path_stripped = folder_path.strip("/")
        sparse_checkout_file = os.path.join(".git", "info", "sparse-checkout")
        with open(sparse_checkout_file, "w", encoding="utf-8") as f:
            # Trailing slash ensures we include subfolders inside folder_path_stripped.
            f.write(folder_path_stripped + "/\n")

        # 5. Finally, checkout the contents
        subprocess.run(["git", "checkout"], check=True)

        # 6. Move or copy the desired folder to the destination
        if not os.path.exists(destination):
            os.makedirs(destination, exist_ok=True)

        source_folder = os.path.join(temp_dir, folder_path_stripped)
        copyFolder(source_folder, destination)

    finally:
        # Clean up temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


def download_file_from_github(repo_url, file_path, destination):
    """
    Downloads a single file from a GitHub repository using sparse-checkout.

    :param repo_url: The URL of the GitHub repository.
    :param file_path: The path (in-repo) to the file to download (e.g., "path/to/file.txt").
    :param destination: The destination directory where the file will be saved.
    """

    # Create a temporary directory for the repository
    temp_dir = os.path.join(os.path.expanduser("~"), "temp_repo_file")

    # Ensure the temp directory doesn't already exist
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    try:
        # 1. Clone the repo with minimal checkout (no-checkout)
        subprocess.run(
            ["git", "clone", "--filter=blob:none", "--no-checkout", repo_url, temp_dir],
            check=True,
        )

        # 2. Change to the repo directory
        os.chdir(temp_dir)

        # 3. Initialize sparse-checkout in non-cone mode
        subprocess.run(["git", "sparse-checkout", "init", "--no-cone"], check=True)

        # 4. Manually write the file path to .git/info/sparse-checkout
        file_path_stripped = file_path.lstrip("/")
        sparse_checkout_file = os.path.join(".git", "info", "sparse-checkout")
        with open(sparse_checkout_file, "w", encoding="utf-8") as f:
            f.write(file_path_stripped + "\n")

        # 5. Checkout the contents (just that single file)
        subprocess.run(["git", "checkout"], check=True)

        # 6. Copy the desired file to the destination
        # if not os.path.exists(destination):
        #     os.makedirs(destination, exist_ok=True)
        #
        source_file = os.path.join(temp_dir, file_path_stripped)
        destination_path = os.path.join(destination, os.path.basename(file_path_stripped))
        if not dirExists(destination):
            makeDir(destination)

        copyFile(source_file, destination_path)

    finally:
        ...
        # Clean up temporary directory
        # Move out of temp_dir so we can remove it on Windows
        os.chdir(os.path.expanduser("~"))
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
