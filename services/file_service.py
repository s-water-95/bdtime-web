import os
import shutil
import logging
from datetime import datetime
from typing import Optional, Tuple, List
import config
from utils.config_parser import parse_network_file

logger = logging.getLogger(__name__)


def ensure_directory_exists(directory: str) -> None:
    """
    Ensure that the given directory exists, create it if it doesn't.

    Args:
        directory: Directory path
    """
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def backup_config_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Create a backup of a configuration file.

    Args:
        file_path: Path to the file to back up

    Returns:
        Tuple containing:
        - bool: Success status
        - Optional[str]: Backup file path if successful, error message otherwise
    """
    if not os.path.exists(file_path):
        return False, f"File does not exist: {file_path}"

    ensure_directory_exists(config.NETWORK_CONFIG_BACKUP_DIR)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(file_path)
    backup_path = f"{config.NETWORK_CONFIG_BACKUP_DIR}{filename}.{timestamp}"

    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup of {file_path} at {backup_path}")
        return True, backup_path
    except Exception as e:
        logger.exception(f"Failed to create backup of {file_path}")
        return False, str(e)


def write_config_file(filename: str, content: str) -> Tuple[bool, Optional[str]]:
    """
    Write content to a configuration file.

    Args:
        filename: Filename (without path)
        content: File content to write

    Returns:
        Tuple containing:
        - bool: Success status
        - Optional[str]: Error message if failed, None otherwise
    """
    file_path = os.path.join(config.NETWORK_CONFIG_DIR, filename)

    # Backup existing file if it exists
    if os.path.exists(file_path):
        success, result = backup_config_file(file_path)
        if not success:
            return False, f"Failed to create backup: {result}"

    try:
        ensure_directory_exists(config.NETWORK_CONFIG_DIR)
        with open(file_path, 'w') as f:
            f.write(content)
        logger.info(f"Successfully wrote configuration to {file_path}")
        return True, None
    except Exception as e:
        logger.exception(f"Failed to write configuration to {file_path}")
        return False, str(e)


def find_network_files() -> List[str]:
    """
    Find all .network files in the configuration directory.

    Returns:
        List[str]: List of file paths
    """
    network_files = []

    try:
        if os.path.exists(config.NETWORK_CONFIG_DIR):
            for filename in os.listdir(config.NETWORK_CONFIG_DIR):
                if filename.endswith(".network"):
                    network_files.append(os.path.join(config.NETWORK_CONFIG_DIR, filename))
    except Exception as e:
        logger.exception("Error finding network files")

    return network_files


def get_interface_config_file(interface_name: str) -> Optional[str]:
    """
    Get the configuration file path for a specific interface.

    Args:
        interface_name: Name of the interface

    Returns:
        Optional[str]: Configuration file path if found, None otherwise
    """
    expected_filename = f"{interface_name}.network"
    expected_path = os.path.join(config.NETWORK_CONFIG_DIR, expected_filename)

    if os.path.exists(expected_path):
        return expected_path

    # If the expected filename doesn't exist, search for files that might contain this interface
    network_files = find_network_files()
    for file_path in network_files:
        interface, _ = parse_network_file(file_path)
        if interface == interface_name:
            return file_path

    return None