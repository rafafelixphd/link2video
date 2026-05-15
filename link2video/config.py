import yaml
import os
from pathlib import Path
from typing import Dict


def load_config() -> Dict:
    """
    Load configuration from config.yaml file.

    Returns:
        Dict: Configuration dictionary with all settings

    Raises:
        FileNotFoundError: If config.yaml is not found
        yaml.YAMLError: If config.yaml has malformed YAML syntax
        PermissionError: If config.yaml cannot be read due to permissions
    """
    config_path = Path(__file__).parent / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
    except PermissionError as e:
        raise PermissionError(f"Permission denied reading config file: {config_path}") from e
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Malformed YAML in config file: {config_path}") from e

    return config or {}


def get_default_download_path() -> str:
    """
    Get the default download path from configuration.
    Expands ~ to the user's home directory.

    Returns:
        str: Expanded path to the default download directory

    Raises:
        ValueError: If the configured path does not exist or is not a directory
    """
    config = load_config()
    default_path = config.get('download_path', '~/Movies')

    # Expand ~ to home directory
    expanded_path = os.path.expanduser(default_path)

    # Validate the path
    if not os.path.exists(expanded_path):
        raise ValueError(f"Download path does not exist: {expanded_path}")

    if not os.path.isdir(expanded_path):
        raise ValueError(f"Download path is not a directory: {expanded_path}")

    return expanded_path


def set_download_path(path: str) -> None:
    """
    Set the default download path in the configuration file.

    Args:
        path (str): The new download path (can include ~)

    Raises:
        ValueError: If the path does not exist, is not a directory, or is not writable
        PermissionError: If the config file cannot be written due to permissions
    """
    # Expand the path for validation
    expanded_path = os.path.expanduser(path)

    # Validate the path exists
    if not os.path.exists(expanded_path):
        raise ValueError(f"Path does not exist: {expanded_path}")

    # Validate it's a directory
    if not os.path.isdir(expanded_path):
        raise ValueError(f"Path is not a directory: {expanded_path}")

    # Validate it's writable
    if not os.access(expanded_path, os.W_OK):
        raise ValueError(f"Path is not writable: {expanded_path}")

    config_path = Path(__file__).parent / "config.yaml"

    # Load current config
    config = load_config()

    # Update the download path
    config['download_path'] = path

    # Write back to file
    try:
        with open(config_path, 'w') as file:
            yaml.safe_dump(config, file, default_flow_style=False)
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing config file: {config_path}") from e
