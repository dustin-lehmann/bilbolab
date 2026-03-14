#!/usr/bin/env python3
"""
Content Server Ingestion Tool

Interactive CLI for adding content to experiments.json without manual JSON editing.

Usage:
    python ingest.py              # Interactive mode
    python ingest.py --list       # List all folders and experiments
    python ingest.py --validate   # Validate all file references
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

# Directory where this script lives (content_server root)
SCRIPT_DIR = Path(__file__).parent.absolute()
EXPERIMENTS_FILE = SCRIPT_DIR / "experiments.json"

# Content directories
CONTENT_DIRS = {
    "videos": SCRIPT_DIR / "videos",
    "figures": SCRIPT_DIR / "figures",
    "pdfs": SCRIPT_DIR / "pdfs",
    "code": SCRIPT_DIR / "code",
    "models": SCRIPT_DIR / "models",
}

# Supported content types
CONTENT_TYPES = {
    "synchronized": "Multi-video synchronized playback",
    "collection": "Independent video clips",
    "figures": "Image gallery",
    "pdf": "PDF document",
    "code": "Source code with syntax highlighting",
    "interactive": "3D model viewer",
}

# Language options for code type
CODE_LANGUAGES = [
    "python", "javascript", "typescript", "cpp", "c", "java",
    "rust", "go", "bash", "sql", "json", "yaml", "markdown"
]


class BackException(Exception):
    """Raised when user wants to go back to previous menu."""
    pass


class CancelException(Exception):
    """Raised when user wants to cancel the entire operation."""
    pass


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print("  (Type 'b' to go back, 'q' to cancel)")
    print()


def print_menu(options: list[str], title: str = "Options"):
    print(f"\n{title}:")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    print(f"  [b] Back")
    print()


def check_back_cancel(value: str):
    """Check if input is a back/cancel command and raise appropriate exception."""
    v = value.strip().lower()
    if v in ('b', 'back'):
        raise BackException()
    if v in ('q', 'quit', 'cancel'):
        raise CancelException()


def get_choice(max_val: int, prompt: str = "Choice", allow_zero: bool = False) -> int:
    """Get a numeric choice. Returns -1 for back."""
    while True:
        try:
            choice = input(f"{prompt}: ").strip()
            if choice.lower() in ('b', 'back'):
                return -1
            if choice.lower() in ('q', 'quit', 'cancel'):
                raise CancelException()
            if choice == "":
                return -1  # Empty = back
            val = int(choice)
            if allow_zero and val == 0:
                return 0
            if 1 <= val <= max_val:
                return val
            print(f"Please enter a number between 1 and {max_val} (or 'b' to go back)")
        except ValueError:
            print("Please enter a valid number (or 'b' to go back)")


def get_input(prompt: str, default: str = "", required: bool = True, allow_back: bool = True) -> str:
    """Get text input. Raises BackException if user types 'b'."""
    suffix = f" [{default}]" if default else ""
    suffix += " (required)" if required and not default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()

        # Check for back/cancel
        if allow_back and value.lower() in ('b', 'back'):
            raise BackException()
        if value.lower() in ('q', 'quit', 'cancel'):
            raise CancelException()

        if value == "" and default:
            return default
        if value == "" and required:
            print("This field is required (or type 'b' to go back)")
            continue
        return value


def get_multiline_input(prompt: str) -> str:
    print(f"{prompt} (empty line to finish, 'b' alone to go back):")
    lines = []
    while True:
        line = input()
        if line.lower() in ('b', 'back') and not lines:
            raise BackException()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def confirm(prompt: str, default: bool = True) -> bool:
    """Get yes/no confirmation. 'b' raises BackException."""
    suffix = " [Y/n/b]" if default else " [y/N/b]"
    while True:
        response = input(f"{prompt}{suffix}: ").strip().lower()
        if response in ('b', 'back'):
            raise BackException()
        if response in ('q', 'quit', 'cancel'):
            raise CancelException()
        if response == "":
            return default
        if response in ('y', 'yes'):
            return True
        if response in ('n', 'no'):
            return False
        print("Please enter y/n or 'b' to go back")


class ContentIngestor:
    def __init__(self):
        self.data = self.load_data()

    def load_data(self) -> dict:
        if EXPERIMENTS_FILE.exists():
            with open(EXPERIMENTS_FILE, 'r') as f:
                return json.load(f)
        return {"folders": [], "experiments": []}

    def save_data(self):
        # Create backup
        if EXPERIMENTS_FILE.exists():
            backup_path = EXPERIMENTS_FILE.with_suffix('.json.backup')
            shutil.copy(EXPERIMENTS_FILE, backup_path)
            print(f"Backup saved to: {backup_path.name}")

        with open(EXPERIMENTS_FILE, 'w') as f:
            json.dump(self.data, f, indent=2)
        print(f"Saved to: {EXPERIMENTS_FILE.name}")

    def get_all_folders(self, folders: list = None, path: list = None) -> list[tuple[list, dict]]:
        """Get all folders with their paths. Returns list of (path, folder) tuples."""
        if folders is None:
            folders = self.data.get("folders", [])
        if path is None:
            path = []

        result = []
        for folder in folders:
            current_path = path + [folder["name"]]
            result.append((current_path, folder))
            if "folders" in folder:
                result.extend(self.get_all_folders(folder["folders"], current_path))
        return result

    def get_all_experiments(self, folders: list = None, path: list = None) -> list[tuple[list, dict]]:
        """Get all experiments with their paths."""
        if folders is None:
            # Start with root-level experiments
            result = [(["(root)"], exp) for exp in self.data.get("experiments", [])]
            folders = self.data.get("folders", [])
            path = []
        else:
            result = []

        for folder in folders:
            current_path = path + [folder["name"]]
            for exp in folder.get("experiments", []):
                result.append((current_path, exp))
            if "folders" in folder:
                result.extend(self.get_all_experiments(folder["folders"], current_path))
        return result

    def id_exists(self, id_: str) -> bool:
        """Check if an ID already exists in folders or experiments."""
        for _, folder in self.get_all_folders():
            if folder.get("id") == id_:
                return True
        for _, exp in self.get_all_experiments():
            if exp.get("id") == id_:
                return True
        return False

    def generate_id(self, title: str) -> str:
        """Generate a unique ID from title."""
        base_id = title.lower().replace(" ", "_").replace("-", "_")
        base_id = "".join(c for c in base_id if c.isalnum() or c == "_")

        if not self.id_exists(base_id):
            return base_id

        counter = 2
        while self.id_exists(f"{base_id}_{counter}"):
            counter += 1
        return f"{base_id}_{counter}"

    def list_available_files(self, content_type: str) -> list[str]:
        """List files available for a content type."""
        if content_type in ("synchronized", "collection"):
            directory = CONTENT_DIRS["videos"]
            extensions = (".mp4", ".webm", ".mov")
        elif content_type == "figures":
            directory = CONTENT_DIRS["figures"]
            extensions = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
        elif content_type == "pdf":
            directory = CONTENT_DIRS["pdfs"]
            extensions = (".pdf",)
        elif content_type == "code":
            directory = CONTENT_DIRS["code"]
            extensions = (".py", ".js", ".ts", ".cpp", ".c", ".h", ".java", ".rs", ".go", ".sh", ".sql")
        elif content_type == "interactive":
            directory = CONTENT_DIRS["models"]
            extensions = (".glb", ".gltf")
        else:
            return []

        if not directory.exists():
            return []

        files = []
        for f in sorted(directory.iterdir()):
            if f.is_file() and f.suffix.lower() in extensions:
                files.append(f.name)
        return files

    def validate_file(self, filename: str, content_type: str) -> bool:
        """Check if a file exists in the appropriate directory."""
        if content_type in ("synchronized", "collection"):
            return (CONTENT_DIRS["videos"] / filename).exists()
        elif content_type == "figures":
            return (CONTENT_DIRS["figures"] / filename).exists()
        elif content_type == "pdf":
            return (CONTENT_DIRS["pdfs"] / filename).exists()
        elif content_type == "code":
            return (CONTENT_DIRS["code"] / filename).exists()
        elif content_type == "interactive":
            return (CONTENT_DIRS["models"] / filename).exists()
        return False

    def select_folder(self) -> Optional[dict]:
        """Interactive folder selection. Returns folder dict, None for root, or raises BackException."""
        all_folders = self.get_all_folders()

        if not all_folders:
            print("No folders exist yet. Content will be added to root.")
            return None

        print_header("Select Target Folder")
        print("  [0] (root level)")
        for i, (path, folder) in enumerate(all_folders, 1):
            indent = "    " * (len(path) - 1)
            print(f"  [{i}] {indent}{folder['name']}")
        print(f"  [b] Back")
        print()

        choice = get_choice(len(all_folders), "Select folder", allow_zero=True)
        if choice == -1:  # Back
            raise BackException()
        if choice == 0:  # Root
            return None
        return all_folders[choice - 1][1]

    def select_files(self, content_type: str, multi: bool = True) -> list[str]:
        """Interactive file selection. Raises BackException if user goes back."""
        available = self.list_available_files(content_type)

        if not available:
            dir_name = {
                "synchronized": "videos/",
                "collection": "videos/",
                "figures": "figures/",
                "pdf": "pdfs/",
                "code": "code/",
                "interactive": "models/",
            }.get(content_type, "")
            print(f"\nNo files found in {dir_name}")
            print("You can manually enter filenames, or add files to the directory first.")
            print("(Type 'b' to go back)")

            if multi:
                files = []
                while True:
                    try:
                        filename = get_input("Enter filename (empty to finish)", required=False)
                        if not filename:
                            break
                        files.append(filename)
                    except BackException:
                        if not files:
                            raise  # Re-raise if no files added yet
                        break  # Otherwise just stop adding files
                return files
            else:
                return [get_input("Enter filename")]

        print(f"\nAvailable files in {content_type} directory:")
        for i, f in enumerate(available, 1):
            print(f"  [{i}] {f}")
        print(f"  [m] Manual entry")
        print(f"  [b] Back")
        print()

        if multi:
            print("Enter file numbers separated by commas, 'all' for all files, or 'b' to go back:")
            selection = input("Selection: ").strip()

            if selection.lower() in ('b', 'back'):
                raise BackException()
            if selection.lower() in ('q', 'quit', 'cancel'):
                raise CancelException()
            if selection.lower() == "all":
                return available
            elif selection.lower() == "m":
                files = []
                print("(Type 'b' alone to go back, empty line to finish)")
                while True:
                    try:
                        filename = get_input("Enter filename (empty to finish)", required=False)
                        if not filename:
                            break
                        files.append(filename)
                    except BackException:
                        if not files:
                            raise
                        break
                return files
            else:
                try:
                    indices = [int(x.strip()) for x in selection.split(",")]
                    result = [available[i-1] for i in indices if 1 <= i <= len(available)]
                    if not result:
                        print("No valid files selected")
                        raise BackException()
                    return result
                except (ValueError, IndexError):
                    print("Invalid selection")
                    raise BackException()
        else:
            choice = input("Selection (or 'm' for manual, 'b' to go back): ").strip()
            if choice.lower() in ('b', 'back'):
                raise BackException()
            if choice.lower() in ('q', 'quit', 'cancel'):
                raise CancelException()
            if choice.lower() == "m":
                return [get_input("Enter filename")]
            try:
                idx = int(choice)
                if 1 <= idx <= len(available):
                    return [available[idx - 1]]
            except ValueError:
                pass
            print("Invalid selection")
            raise BackException()

    # =========================================================================
    # Content Type Creation Methods
    # =========================================================================

    def create_synchronized(self) -> Optional[dict]:
        """Create a synchronized video experiment. Raises BackException to go back."""
        print_header("Create Synchronized Video Content")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect video files:")
        files = self.select_files("synchronized", multi=True)
        if not files:
            print("No files selected")
            raise BackException()

        videos = []
        for f in files:
            name = get_input(f"Display name for '{f}'", default=Path(f).stem)
            videos.append({"name": name, "file": f})

        markers = []
        try:
            if confirm("Add timeline markers?", default=False):
                print("Enter markers (empty time to finish, 'b' to stop adding):")
                while True:
                    try:
                        time_str = get_input("Time (seconds)", required=False)
                        if not time_str:
                            break
                        try:
                            time = float(time_str)
                            label = get_input("Label")
                            markers.append({"time": time, "label": label})
                        except ValueError:
                            print("Invalid time format")
                    except BackException:
                        break  # Stop adding markers
        except BackException:
            pass  # Skip markers

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "synchronized",
            "videos": videos,
        }
        if description:
            experiment["description"] = description
        if markers:
            experiment["markers"] = markers

        return experiment

    def create_collection(self) -> Optional[dict]:
        """Create a video collection (independent videos). Raises BackException to go back."""
        print_header("Create Video Collection")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect video files:")
        files = self.select_files("collection", multi=True)
        if not files:
            print("No files selected")
            raise BackException()

        videos = []
        for f in files:
            name = get_input(f"Display name for '{f}'", default=Path(f).stem)
            videos.append({"name": name, "file": f})

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "collection",
            "videos": videos,
        }
        if description:
            experiment["description"] = description

        return experiment

    def create_figures(self) -> Optional[dict]:
        """Create a figures gallery. Raises BackException to go back."""
        print_header("Create Figure Gallery")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect figure files:")
        files = self.select_files("figures", multi=True)
        if not files:
            print("No files selected")
            raise BackException()

        figures = []
        for f in files:
            name = get_input(f"Caption for '{f}'", default=Path(f).stem.replace("_", " ").title())
            figures.append({"name": name, "file": f})

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "figures",
            "figures": figures,
        }
        if description:
            experiment["description"] = description

        return experiment

    def create_pdf(self) -> Optional[dict]:
        """Create a PDF document entry. Raises BackException to go back."""
        print_header("Create PDF Document")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect PDF file:")
        files = self.select_files("pdf", multi=False)
        if not files:
            print("No file selected")
            raise BackException()

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "pdf",
            "file": files[0],
        }
        if description:
            experiment["description"] = description

        return experiment

    def create_code(self) -> Optional[dict]:
        """Create a code viewer entry. Raises BackException to go back."""
        print_header("Create Code Viewer")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect code file:")
        files = self.select_files("code", multi=False)
        if not files:
            print("No file selected")
            raise BackException()

        # Try to auto-detect language from extension
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".cpp": "cpp", ".c": "c", ".h": "cpp", ".java": "java",
            ".rs": "rust", ".go": "go", ".sh": "bash", ".sql": "sql",
        }
        ext = Path(files[0]).suffix.lower()
        default_lang = ext_map.get(ext, "python")

        print(f"\nAvailable languages: {', '.join(CODE_LANGUAGES)}")
        language = get_input("Language", default=default_lang)

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "code",
            "file": files[0],
            "language": language,
        }
        if description:
            experiment["description"] = description

        return experiment

    def create_interactive(self) -> Optional[dict]:
        """Create an interactive 3D model entry. Raises BackException to go back."""
        print_header("Create 3D Model Viewer")

        title = get_input("Title")
        description = get_input("Description", required=False)

        print("\nSelect model file (GLB/GLTF):")
        files = self.select_files("interactive", multi=False)
        if not files:
            print("No file selected")
            raise BackException()

        experiment = {
            "id": self.generate_id(title),
            "title": title,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": "interactive",
            "model": files[0],
        }
        if description:
            experiment["description"] = description

        return experiment

    # =========================================================================
    # Folder Management
    # =========================================================================

    def create_folder(self) -> Optional[dict]:
        """Create a new folder. Raises BackException to go back."""
        print_header("Create New Folder")

        name = get_input("Folder name (e.g., '5.1 Balancing Control')")
        description = get_input("Description", required=False)

        folder = {
            "id": self.generate_id(name),
            "name": name,
            "experiments": [],
        }
        if description:
            folder["description"] = description

        return folder

    def add_folder(self):
        """Add a new folder to the hierarchy."""
        try:
            while True:
                try:
                    parent = self.select_folder()
                except BackException:
                    return  # Back to main menu

                try:
                    folder = self.create_folder()
                except BackException:
                    continue  # Back to parent selection

                if folder is None:
                    continue

                if parent is None:
                    self.data.setdefault("folders", []).append(folder)
                else:
                    parent.setdefault("folders", []).append(folder)

                print(f"\nCreated folder: {folder['name']}")
                try:
                    if confirm("Save changes?"):
                        self.save_data()
                except BackException:
                    pass
                return

        except CancelException:
            print("\nCancelled.")
            return

    # =========================================================================
    # Main Menu Actions
    # =========================================================================

    def add_content(self):
        """Main flow for adding content with back navigation support."""
        try:
            while True:  # Loop to allow going back
                # Step 1: Select target folder
                try:
                    folder = self.select_folder()
                except BackException:
                    return  # Back from folder selection goes to main menu

                # Step 2: Select content type
                try:
                    print_header("Select Content Type")
                    type_names = list(CONTENT_TYPES.keys())
                    for i, (type_id, desc) in enumerate(CONTENT_TYPES.items(), 1):
                        print(f"  [{i}] {type_id:<15} - {desc}")
                    print(f"  [b] Back")
                    print()

                    choice = get_choice(len(type_names))
                    if choice == -1:  # Back
                        continue  # Go back to folder selection
                except BackException:
                    continue  # Go back to folder selection

                content_type = type_names[choice - 1]

                # Step 3: Create content based on type
                creators = {
                    "synchronized": self.create_synchronized,
                    "collection": self.create_collection,
                    "figures": self.create_figures,
                    "pdf": self.create_pdf,
                    "code": self.create_code,
                    "interactive": self.create_interactive,
                }

                try:
                    experiment = creators[content_type]()
                except BackException:
                    continue  # Go back to content type selection

                if experiment is None:
                    continue  # Go back to content type selection

                # Step 4: Preview and confirm
                print("\n" + "-" * 40)
                print("Preview:")
                print(json.dumps(experiment, indent=2))
                print("-" * 40)

                try:
                    if not confirm("Add this content?"):
                        continue  # Go back to start
                except BackException:
                    continue

                # Step 5: Add to data structure
                if folder is None:
                    self.data.setdefault("experiments", []).append(experiment)
                else:
                    folder.setdefault("experiments", []).append(experiment)

                print(f"\nAdded: {experiment['title']}")
                try:
                    if confirm("Save changes?"):
                        self.save_data()
                except BackException:
                    pass  # Don't save, but don't undo the add either

                return  # Done, go back to main menu

        except CancelException:
            print("\nCancelled.")
            return

    def list_content(self):
        """List all folders and experiments."""
        print_header("Content Overview")

        def print_folder(folder: dict, indent: int = 0):
            prefix = "  " * indent
            exp_count = len(folder.get("experiments", []))
            sub_count = len(folder.get("folders", []))
            print(f"{prefix}[Folder] {folder['name']} ({exp_count} items, {sub_count} subfolders)")

            for exp in folder.get("experiments", []):
                print(f"{prefix}  - [{exp['type']}] {exp['title']}")

            for subfolder in folder.get("folders", []):
                print_folder(subfolder, indent + 1)

        # Root-level experiments
        root_exps = self.data.get("experiments", [])
        if root_exps:
            print("[Root Level]")
            for exp in root_exps:
                print(f"  - [{exp['type']}] {exp['title']}")
            print()

        # Folders
        for folder in self.data.get("folders", []):
            print_folder(folder)
            print()

    def validate_content(self):
        """Validate all file references."""
        print_header("Validating File References")

        errors = []
        warnings = []

        for path, exp in self.get_all_experiments():
            path_str = " > ".join(path)
            exp_type = exp.get("type", "unknown")

            if exp_type in ("synchronized", "collection"):
                for video in exp.get("videos", []):
                    if not self.validate_file(video["file"], exp_type):
                        errors.append(f"{path_str} > {exp['title']}: Missing video '{video['file']}'")

            elif exp_type == "figures":
                for fig in exp.get("figures", []):
                    if not self.validate_file(fig["file"], exp_type):
                        errors.append(f"{path_str} > {exp['title']}: Missing figure '{fig['file']}'")

            elif exp_type == "pdf":
                if not self.validate_file(exp.get("file", ""), exp_type):
                    errors.append(f"{path_str} > {exp['title']}: Missing PDF '{exp.get('file')}'")

            elif exp_type == "code":
                if not self.validate_file(exp.get("file", ""), exp_type):
                    errors.append(f"{path_str} > {exp['title']}: Missing code file '{exp.get('file')}'")

            elif exp_type == "interactive":
                if not self.validate_file(exp.get("model", ""), exp_type):
                    errors.append(f"{path_str} > {exp['title']}: Missing model '{exp.get('model')}'")

        if errors:
            print("ERRORS (missing files):")
            for err in errors:
                print(f"  [!] {err}")
        else:
            print("All file references are valid!")

        if warnings:
            print("\nWARNINGS:")
            for warn in warnings:
                print(f"  [?] {warn}")

        print(f"\nTotal: {len(self.get_all_experiments())} experiments checked")

    def quick_add_from_directory(self):
        """Quickly add all files from a directory as a content entry."""
        try:
            print_header("Quick Add from Directory")

            print("This will scan a directory and create content from all matching files.")
            print("Supported patterns:")
            print("  - Multiple videos -> synchronized or collection")
            print("  - Multiple images -> figures gallery")
            print()

            # Get directory path
            dir_path = get_input("Directory path (relative to content_server or absolute)")

            # Resolve path
            path = Path(dir_path)
            if not path.is_absolute():
                path = SCRIPT_DIR / dir_path

            if not path.exists() or not path.is_dir():
                print(f"Directory not found: {path}")
                return

            # Detect file types
            video_exts = {".mp4", ".webm", ".mov"}
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}

            videos = sorted([f.name for f in path.iterdir() if f.suffix.lower() in video_exts])
            images = sorted([f.name for f in path.iterdir() if f.suffix.lower() in image_exts])

            print(f"\nFound: {len(videos)} videos, {len(images)} images")

            if videos and images:
                print("\nBoth videos and images found. Choose content type:")
                print("  [1] Create synchronized video content")
                print("  [2] Create video collection")
                print("  [3] Create figure gallery")
                print("  [b] Back")
                choice = get_choice(3)
                if choice == -1:
                    return
            elif videos:
                print("\nVideos found. Choose content type:")
                print("  [1] Create synchronized video content")
                print("  [2] Create video collection")
                print("  [b] Back")
                choice = get_choice(2)
                if choice == -1:
                    return
            elif images:
                print("\nImages found. Creating figure gallery.")
                choice = 3
            else:
                print("No supported files found in directory")
                return

            # Get metadata
            title = get_input("Title", default=path.name.replace("_", " ").title())
            description = get_input("Description", required=False)

            # Select target folder
            folder = self.select_folder()

            # Create experiment based on choice
            if choice == 1:  # synchronized
                experiment = {
                    "id": self.generate_id(title),
                    "title": title,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "synchronized",
                    "videos": [{"name": Path(v).stem.replace("_", " ").title(), "file": v} for v in videos],
                }
                print(f"\nNote: Ensure video files are in {CONTENT_DIRS['videos']}")

            elif choice == 2:  # collection
                experiment = {
                    "id": self.generate_id(title),
                    "title": title,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "collection",
                    "videos": [{"name": Path(v).stem.replace("_", " ").title(), "file": v} for v in videos],
                }
                print(f"\nNote: Ensure video files are in {CONTENT_DIRS['videos']}")

            elif choice == 3:  # figures
                experiment = {
                    "id": self.generate_id(title),
                    "title": title,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "type": "figures",
                    "figures": [{"name": Path(f).stem.replace("_", " ").title(), "file": f} for f in images],
                }
                print(f"\nNote: Ensure figure files are in {CONTENT_DIRS['figures']}")
            else:
                return

            if description:
                experiment["description"] = description

            # Preview
            print("\n" + "-" * 40)
            print("Preview:")
            print(json.dumps(experiment, indent=2))
            print("-" * 40)

            if not confirm("Add this content?"):
                return

            # Add to structure
            if folder is None:
                self.data.setdefault("experiments", []).append(experiment)
            else:
                folder.setdefault("experiments", []).append(experiment)

            print(f"\nAdded: {experiment['title']}")
            if confirm("Save changes?"):
                self.save_data()

        except (BackException, CancelException):
            print("\nCancelled.")
            return

    def edit_content(self):
        """Edit an existing experiment."""
        try:
            print_header("Edit Content")

            all_experiments = self.get_all_experiments()
            if not all_experiments:
                print("No experiments found")
                return

            # List all experiments
            for i, (path, exp) in enumerate(all_experiments, 1):
                path_str = " > ".join(path)
                print(f"  [{i}] [{exp['type']}] {exp['title']}")
                print(f"      Path: {path_str}")
            print(f"  [b] Back")
            print()

            choice = get_choice(len(all_experiments), "Select experiment to edit")
            if choice == -1:
                return

            _, experiment = all_experiments[choice - 1]

            print(f"\nEditing: {experiment['title']}")
            print("\nCurrent values:")
            print(json.dumps(experiment, indent=2))
            print()

            # Edit fields
            new_title = get_input("Title", default=experiment.get("title", ""))
            new_desc = get_input("Description", default=experiment.get("description", ""), required=False)

            experiment["title"] = new_title
            if new_desc:
                experiment["description"] = new_desc
            elif "description" in experiment and not new_desc:
                if confirm("Remove description?", default=False):
                    del experiment["description"]

            print("\nUpdated:")
            print(json.dumps(experiment, indent=2))

            if confirm("Save changes?"):
                self.save_data()

        except (BackException, CancelException):
            print("\nCancelled.")
            return

    def delete_content(self):
        """Delete an experiment."""
        try:
            print_header("Delete Content")

            all_experiments = self.get_all_experiments()
            if not all_experiments:
                print("No experiments found")
                return

            for i, (path, exp) in enumerate(all_experiments, 1):
                path_str = " > ".join(path)
                print(f"  [{i}] [{exp['type']}] {exp['title']}")
                print(f"      Path: {path_str}")
            print(f"  [b] Back")
            print()

            choice = get_choice(len(all_experiments), "Select experiment to delete")
            if choice == -1:
                return

            path, experiment = all_experiments[choice - 1]

            print(f"\nAbout to delete: {experiment['title']}")
            if not confirm("Are you sure?", default=False):
                return

            # Find and remove from data structure
            def remove_from_folder(folders, target_id):
                for folder in folders:
                    exps = folder.get("experiments", [])
                    for i, exp in enumerate(exps):
                        if exp.get("id") == target_id:
                            del exps[i]
                            return True
                    if remove_from_folder(folder.get("folders", []), target_id):
                        return True
                return False

            # Try root experiments first
            root_exps = self.data.get("experiments", [])
            removed = False
            for i, exp in enumerate(root_exps):
                if exp.get("id") == experiment.get("id"):
                    del root_exps[i]
                    removed = True
                    break

            if not removed:
                removed = remove_from_folder(self.data.get("folders", []), experiment.get("id"))

            if removed:
                print(f"Deleted: {experiment['title']}")
                if confirm("Save changes?"):
                    self.save_data()
            else:
                print("Error: Could not find experiment to delete")

        except (BackException, CancelException):
            print("\nCancelled.")
            return

    def run(self):
        """Main menu loop."""
        while True:
            try:
                clear_screen()
                print("\n" + "=" * 60)
                print("  Content Server Ingestion Tool")
                print("=" * 60)
                print("  (Type 'q' to quit)")
                print()

                print("\nMain Menu:")
                print("  [1] Add content (experiment/material)")
                print("  [2] Add folder")
                print("  [3] Quick add from directory")
                print("  [4] Edit content")
                print("  [5] Delete content")
                print("  [6] List all content")
                print("  [7] Validate file references")
                print("  [8] Exit")
                print()

                choice = get_choice(8, allow_zero=False)

                if choice == -1 or choice == 8:
                    print("Goodbye!")
                    break
                elif choice == 1:
                    self.add_content()
                elif choice == 2:
                    self.add_folder()
                elif choice == 3:
                    self.quick_add_from_directory()
                elif choice == 4:
                    self.edit_content()
                elif choice == 5:
                    self.delete_content()
                elif choice == 6:
                    self.list_content()
                elif choice == 7:
                    self.validate_content()

                if choice not in (-1, 8):
                    input("\nPress Enter to continue...")

            except CancelException:
                print("Goodbye!")
                break
            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break


def main():
    import sys

    if "--list" in sys.argv:
        ingestor = ContentIngestor()
        ingestor.list_content()
    elif "--validate" in sys.argv:
        ingestor = ContentIngestor()
        ingestor.validate_content()
    else:
        ingestor = ContentIngestor()
        ingestor.run()


if __name__ == "__main__":
    main()
