import os
from dataclasses import asdict
from pathlib import Path

from core.utils.dataclass_utils import from_dict_auto
from core.utils.files import get_absolute_path, file_exists, copyFile
from robot.control.bilbo_control_definitions import BILBO_ControlConfig
from core.utils.yaml_utils import write_yaml, load_yaml
from robot.paths import CONTROL_PATH, SOFTWARE_PATH


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into a copy of *base*. Nested dicts are
    merged rather than replaced; all other values are overwritten."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config_from_file(file: str, merge_with_default: bool = True):
    """Load a control config from a YAML file.

    Args:
        file: Path to the YAML file.
        merge_with_default: If True, treat the file as a partial override on top
            of the default config (same behaviour as named non-default configs).
    """
    file = str(Path(file).expanduser())
    yaml_data = load_yaml(file)
    if merge_with_default:
        return load_config_from_dict(yaml_data)
    return from_dict_auto(BILBO_ControlConfig, yaml_data)


def load_config_from_dict(data: dict):
    """Create a control config from a (possibly partial) dict, merged on top of default.yaml."""
    default_file = f"{CONTROL_PATH}default.yaml"
    if file_exists(default_file):
        base_data = load_yaml(str(Path(default_file).expanduser()))
        merged = _deep_merge(base_data, data)
        return from_dict_auto(BILBO_ControlConfig, merged)
    return from_dict_auto(BILBO_ControlConfig, data)


def load_config_by_name(name: str):
    if not name.endswith('.yaml'): name += '.yaml'

    file = f"{CONTROL_PATH}{name}"
    if not file_exists(file):
        raise FileNotFoundError(f"Config file '{name}' not found in '{CONTROL_PATH}'")

    # Non-default configs are treated as partial overrides on top of default.yaml
    if name != 'default.yaml':
        default_file = f"{CONTROL_PATH}default.yaml"
        if file_exists(default_file):
            base_data = load_yaml(str(Path(default_file).expanduser()))
            override_data = load_yaml(str(Path(file).expanduser()))
            merged = _deep_merge(base_data, override_data)
            return from_dict_auto(BILBO_ControlConfig, merged)

    return load_config_from_file(file)


def write_config_to_file(file: str, config: BILBO_ControlConfig):
    # Resolve file path and replace user directory
    file = str(Path(file).expanduser())
    config_dict = asdict(config)
    write_yaml(file, config_dict)


def generate_default_config(robot_id: str):
    config_dir = f"{SOFTWARE_PATH}/configs/control/{robot_id}"

    if not os.path.isdir(config_dir):
        raise FileNotFoundError(
            f"Control config folder for robot '{robot_id}' not found at '{config_dir}'"
        )

    files = [f for f in os.listdir(config_dir) if f.endswith('.yaml')]
    if not files:
        raise FileNotFoundError(f"No .yaml files found in '{config_dir}'")

    for filename in files:
        src = os.path.join(config_dir, filename)
        dst = os.path.join(CONTROL_PATH, filename)
        copyFile(src, dst)
        print(f"  Copied {filename} -> {dst}")

    print(f"Control configs for {robot_id}: copied {len(files)} file(s) to {CONTROL_PATH}")


if __name__ == '__main__':
    config = BILBO_ControlConfig()
    write_config_to_file('~/config.yaml', config)

    config2 = load_config_from_file('~/config.yaml')
    pass
