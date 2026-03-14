"""
Cross-platform file picker utility that works from any thread.

Uses native OS dialogs via subprocess to avoid main-thread requirements
of GUI toolkits like tkinter.

Supported platforms:
- macOS: AppleScript via osascript
- Windows: PowerShell with Windows Forms
- Linux: zenity (GTK) or kdialog (KDE)
"""

import os
import platform
import subprocess
import shutil
from typing import Optional


def get_os() -> str:
    """Get the current operating system."""
    os_name = platform.system()
    if os_name == "Windows":
        return "Windows"
    elif os_name == "Darwin":
        return "Mac"
    elif os_name == "Linux":
        return "Linux"
    else:
        return "Unknown"


def _check_extension(path: str, allowed_extensions: list[str] | None) -> bool:
    """Check if a file path has one of the allowed extensions."""
    if not allowed_extensions:
        return True
    exts = {('.' + ext.lstrip('.')).lower() for ext in allowed_extensions}
    _, file_ext = os.path.splitext(path)
    return file_ext.lower() in exts


def _build_file_filter_windows(allowed_extensions: list[str] | None) -> str:
    """Build Windows Forms file filter string."""
    if not allowed_extensions:
        return "All Files (*.*)|*.*"

    exts = [ext.lstrip('.') for ext in allowed_extensions]
    ext_patterns = ';'.join(f'*.{ext}' for ext in exts)
    ext_display = ', '.join(f'*.{ext}' for ext in exts)
    return f"Allowed Files ({ext_display})|{ext_patterns}|All Files (*.*)|*.*"


def _build_file_filter_linux(allowed_extensions: list[str] | None) -> list[str]:
    """Build Linux zenity/kdialog file filter arguments."""
    if not allowed_extensions:
        return []

    exts = [ext.lstrip('.') for ext in allowed_extensions]
    patterns = ' '.join(f'*.{ext}' for ext in exts)
    return [f'--file-filter=Allowed files | {patterns}', '--file-filter=All files | *']


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# pick_file — single file selection
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def pick_file(
    title: str = "Select a file",
    initial_dir: str | None = None,
    allowed_extensions: list[str] | None = None
) -> Optional[str]:
    """
    Open a native file picker dialog and return the selected file path.

    This function can be called from any thread, not just the main thread.

    Args:
        title: Dialog window title.
        initial_dir: Starting directory for the file picker.
        allowed_extensions: List of allowed file extensions (e.g., ['txt', 'pdf'] or ['.txt', '.pdf']).
                           If None, all files are allowed.

    Returns:
        The absolute path of the selected file, or None if cancelled.
    """
    os_type = get_os()

    if os_type == "Mac":
        return _pick_file_macos(title, initial_dir, allowed_extensions)
    elif os_type == "Windows":
        return _pick_file_windows(title, initial_dir, allowed_extensions)
    elif os_type == "Linux":
        return _pick_file_linux(title, initial_dir, allowed_extensions)
    else:
        raise RuntimeError(f"Unsupported operating system: {os_type}")


def _pick_file_macos(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> Optional[str]:
    """Open file picker on macOS using AppleScript with Python-side extension validation."""
    script_parts = ['set theFile to choose file']
    if title:
        script_parts.append(f'with prompt "{title}"')
    if initial_dir:
        script_parts.append(f'default location POSIX file "{initial_dir}"')

    script = ' '.join(script_parts)
    script += '\nreturn POSIX path of theFile'

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode == 0:
            path = result.stdout.strip()
            if not path:
                return None
            # macOS AppleScript 'of type' doesn't work for extensions without a UTI (like .yaml),
            # so we validate the extension in Python after selection.
            if not _check_extension(path, allowed_extensions):
                return None
            return path
        else:
            return None

    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


def _pick_file_windows(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> Optional[str]:
    """Open file picker on Windows using PowerShell and Windows Forms."""
    file_filter = _build_file_filter_windows(allowed_extensions)

    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "{title}"
$dialog.Filter = "{filter}"
{initial_dir}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.FileName
}}
'''.format(
        title=title.replace('"', '`"'),
        filter=file_filter.replace('"', '`"'),
        initial_dir=f'$dialog.InitialDirectory = "{initial_dir}"' if initial_dir else ''
    )

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        else:
            return None

    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


def _pick_file_linux(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> Optional[str]:
    """Open file picker on Linux using zenity or kdialog."""

    if shutil.which('zenity'):
        return _pick_file_zenity(title, initial_dir, allowed_extensions)

    if shutil.which('kdialog'):
        return _pick_file_kdialog(title, initial_dir, allowed_extensions)

    raise RuntimeError(
        "No file picker available. Please install 'zenity' (GTK) or 'kdialog' (KDE).\n"
        "  Ubuntu/Debian: sudo apt install zenity\n"
        "  Fedora: sudo dnf install zenity\n"
        "  Arch: sudo pacman -S zenity"
    )


def _pick_file_zenity(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> Optional[str]:
    """Open file picker using zenity (GTK)."""
    cmd = ['zenity', '--file-selection', f'--title={title}']

    if initial_dir:
        cmd.append(f'--filename={initial_dir}/')

    filter_args = _build_file_filter_linux(allowed_extensions)
    cmd.extend(filter_args)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        else:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


def _pick_file_kdialog(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> Optional[str]:
    """Open file picker using kdialog (KDE)."""
    cmd = ['kdialog', '--getopenfilename']

    if initial_dir:
        cmd.append(initial_dir)
    else:
        cmd.append('.')

    if allowed_extensions:
        exts = [ext.lstrip('.') for ext in allowed_extensions]
        patterns = ' '.join(f'*.{ext}' for ext in exts)
        cmd.append(f'{patterns}|Allowed files')

    cmd.extend(['--title', title])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        else:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# pick_files — multiple file selection
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def pick_files(
    title: str = "Select files",
    initial_dir: str | None = None,
    allowed_extensions: list[str] | None = None
) -> list[str]:
    """
    Open a native file picker dialog for multiple file selection.

    This function can be called from any thread.

    Args:
        title: Dialog window title.
        initial_dir: Starting directory for the file picker.
        allowed_extensions: List of allowed file extensions.

    Returns:
        List of selected file paths, or empty list if cancelled.
    """
    os_type = get_os()

    if os_type == "Mac":
        return _pick_files_macos(title, initial_dir, allowed_extensions)
    elif os_type == "Windows":
        return _pick_files_windows(title, initial_dir, allowed_extensions)
    elif os_type == "Linux":
        return _pick_files_linux(title, initial_dir, allowed_extensions)
    else:
        raise RuntimeError(f"Unsupported operating system: {os_type}")


def _pick_files_macos(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> list[str]:
    """Open multi-file picker on macOS using AppleScript."""
    script_parts = ['set theFiles to choose file with multiple selections allowed']
    if title:
        script_parts.append(f'with prompt "{title}"')
    if initial_dir:
        script_parts.append(f'default location POSIX file "{initial_dir}"')

    script = ' '.join(script_parts)
    script += '''
set pathList to ""
repeat with aFile in theFiles
    set pathList to pathList & (POSIX path of aFile) & linefeed
end repeat
return pathList
'''

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            paths = [p for p in result.stdout.strip().split('\n') if p]
            if allowed_extensions:
                paths = [p for p in paths if _check_extension(p, allowed_extensions)]
            return paths
        return []
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


def _pick_files_windows(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> list[str]:
    """Open multi-file picker on Windows."""
    file_filter = _build_file_filter_windows(allowed_extensions)

    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = "{title}"
$dialog.Filter = "{filter}"
$dialog.Multiselect = $true
{initial_dir}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    $dialog.FileNames | ForEach-Object {{ Write-Output $_ }}
}}
'''.format(
        title=title.replace('"', '`"'),
        filter=file_filter.replace('"', '`"'),
        initial_dir=f'$dialog.InitialDirectory = "{initial_dir}"' if initial_dir else ''
    )

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            paths = result.stdout.strip().split('\n')
            return [p for p in paths if p]
        else:
            return []
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


def _pick_files_linux(
    title: str,
    initial_dir: str | None,
    allowed_extensions: list[str] | None
) -> list[str]:
    """Open multi-file picker on Linux."""

    if shutil.which('zenity'):
        cmd = ['zenity', '--file-selection', '--multiple', '--separator=\n', f'--title={title}']

        if initial_dir:
            cmd.append(f'--filename={initial_dir}/')

        filter_args = _build_file_filter_linux(allowed_extensions)
        cmd.extend(filter_args)

    elif shutil.which('kdialog'):
        cmd = ['kdialog', '--getopenfilename', '--multiple']

        if initial_dir:
            cmd.append(initial_dir)
        else:
            cmd.append('.')

        if allowed_extensions:
            exts = [ext.lstrip('.') for ext in allowed_extensions]
            patterns = ' '.join(f'*.{ext}' for ext in exts)
            cmd.append(f'{patterns}|Allowed files')

        cmd.extend(['--title', title])
    else:
        raise RuntimeError(
            "No file picker available. Please install 'zenity' or 'kdialog'."
        )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            output = result.stdout.strip()
            if '\n' in output:
                paths = output.split('\n')
            else:
                paths = output.split(' ')
            return [p for p in paths if p]
        else:
            return []
    except subprocess.TimeoutExpired:
        return []
    except Exception as e:
        raise RuntimeError(f"Failed to open file picker: {e}")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# save_file — save dialog
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def save_file(
    title: str = "Save file",
    initial_dir: str | None = None,
    suggested_name: str | None = None,
    allowed_extensions: list[str] | None = None
) -> Optional[str]:
    """
    Open a native save-file dialog and return the selected path.

    This function can be called from any thread.

    Args:
        title: Dialog window title.
        initial_dir: Starting directory for the dialog.
        suggested_name: Default filename to suggest.
        allowed_extensions: List of allowed file extensions.

    Returns:
        The absolute path chosen by the user, or None if cancelled.
    """
    os_type = get_os()

    if os_type == "Mac":
        return _save_file_macos(title, initial_dir, suggested_name)
    elif os_type == "Windows":
        return _save_file_windows(title, initial_dir, suggested_name, allowed_extensions)
    elif os_type == "Linux":
        return _save_file_linux(title, initial_dir, suggested_name, allowed_extensions)
    else:
        raise RuntimeError(f"Unsupported operating system: {os_type}")


def _save_file_macos(title: str, initial_dir: str | None, suggested_name: str | None) -> Optional[str]:
    """Open save dialog on macOS using AppleScript."""
    script_parts = ['set theFile to choose file name']
    if title:
        script_parts.append(f'with prompt "{title}"')
    if initial_dir:
        script_parts.append(f'default location POSIX file "{initial_dir}"')
    if suggested_name:
        script_parts.append(f'default name "{suggested_name}"')
    script = ' '.join(script_parts)
    script += '\nreturn POSIX path of theFile'

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open save dialog: {e}")


def _save_file_windows(title: str, initial_dir: str | None, suggested_name: str | None,
                       allowed_extensions: list[str] | None) -> Optional[str]:
    """Open save dialog on Windows using PowerShell."""
    file_filter = _build_file_filter_windows(allowed_extensions)
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.SaveFileDialog
$dialog.Title = "{title}"
$dialog.Filter = "{filter}"
{initial_dir}
{filename}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.FileName
}}
'''.format(
        title=title.replace('"', '`"'),
        filter=file_filter.replace('"', '`"'),
        initial_dir=f'$dialog.InitialDirectory = "{initial_dir}"' if initial_dir else '',
        filename=f'$dialog.FileName = "{suggested_name}"' if suggested_name else ''
    )

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open save dialog: {e}")


def _save_file_linux(title: str, initial_dir: str | None, suggested_name: str | None,
                     allowed_extensions: list[str] | None) -> Optional[str]:
    """Open save dialog on Linux using zenity or kdialog."""
    if shutil.which('zenity'):
        cmd = ['zenity', '--file-selection', '--save', '--confirm-overwrite', f'--title={title}']
        if initial_dir and suggested_name:
            cmd.append(f'--filename={initial_dir}/{suggested_name}')
        elif initial_dir:
            cmd.append(f'--filename={initial_dir}/')
        elif suggested_name:
            cmd.append(f'--filename={suggested_name}')
        filter_args = _build_file_filter_linux(allowed_extensions)
        cmd.extend(filter_args)
    elif shutil.which('kdialog'):
        cmd = ['kdialog', '--getsavefilename']
        if initial_dir:
            cmd.append(initial_dir + ('/' + suggested_name if suggested_name else ''))
        else:
            cmd.append(suggested_name or '.')
        if allowed_extensions:
            exts = [ext.lstrip('.') for ext in allowed_extensions]
            patterns = ' '.join(f'*.{ext}' for ext in exts)
            cmd.append(f'{patterns}|Allowed files')
        cmd.extend(['--title', title])
    else:
        raise RuntimeError("No file picker available. Please install 'zenity' or 'kdialog'.")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open save dialog: {e}")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# pick_directory — directory selection
# ══════════════════════════════════════════════════════════════════════════════════════════════════

def pick_directory(
    title: str = "Select a directory",
    initial_dir: str | None = None
) -> Optional[str]:
    """
    Open a native directory picker dialog.

    This function can be called from any thread.

    Args:
        title: Dialog window title.
        initial_dir: Starting directory for the picker.

    Returns:
        The absolute path of the selected directory, or None if cancelled.
    """
    os_type = get_os()

    if os_type == "Mac":
        return _pick_directory_macos(title, initial_dir)
    elif os_type == "Windows":
        return _pick_directory_windows(title, initial_dir)
    elif os_type == "Linux":
        return _pick_directory_linux(title, initial_dir)
    else:
        raise RuntimeError(f"Unsupported operating system: {os_type}")


def _pick_directory_macos(title: str, initial_dir: str | None) -> Optional[str]:
    """Open directory picker on macOS using AppleScript."""
    script_parts = ['set theFolder to choose folder']
    if title:
        script_parts.append(f'with prompt "{title}"')
    if initial_dir:
        script_parts.append(f'default location POSIX file "{initial_dir}"')

    script = ' '.join(script_parts)
    script += '\nreturn POSIX path of theFolder'

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            return path.rstrip('/') if path else None
        return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open directory picker: {e}")


def _pick_directory_windows(title: str, initial_dir: str | None) -> Optional[str]:
    """Open directory picker on Windows."""
    ps_script = '''
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = "{title}"
{initial_dir}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.SelectedPath
}}
'''.format(
        title=title.replace('"', '`"'),
        initial_dir=f'$dialog.SelectedPath = "{initial_dir}"' if initial_dir else ''
    )

    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        else:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open directory picker: {e}")


def _pick_directory_linux(title: str, initial_dir: str | None) -> Optional[str]:
    """Open directory picker on Linux."""

    if shutil.which('zenity'):
        cmd = ['zenity', '--file-selection', '--directory', f'--title={title}']

        if initial_dir:
            cmd.append(f'--filename={initial_dir}/')

    elif shutil.which('kdialog'):
        cmd = ['kdialog', '--getexistingdirectory']

        if initial_dir:
            cmd.append(initial_dir)
        else:
            cmd.append('.')

        cmd.extend(['--title', title])
    else:
        raise RuntimeError(
            "No directory picker available. Please install 'zenity' or 'kdialog'."
        )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            path = result.stdout.strip()
            return path if path else None
        else:
            return None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        raise RuntimeError(f"Failed to open directory picker: {e}")


# Example usage
if __name__ == "__main__":
    import threading

    def test_from_thread():
        print("Testing file picker from non-main thread...")

        # Test single file picker
        path = pick_file(
            title="Select a YAML file",
            allowed_extensions=['yaml', 'yml']
        )
        print(f"Selected file: {path}")

        # Test directory picker
        dir_path = pick_directory(title="Select a directory")
        print(f"Selected directory: {dir_path}")

    # Run from a thread to demonstrate thread-safety
    thread = threading.Thread(target=test_from_thread)
    thread.start()
    thread.join()
