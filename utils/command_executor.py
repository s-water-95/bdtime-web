import subprocess
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def execute_command(command: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Execute a system command and return the result.

    Args:
        command: The command to execute

    Returns:
        Tuple containing:
        - bool: Success status
        - Optional[str]: stdout if successful, None otherwise
        - Optional[str]: stderr if failed, None otherwise
    """
    try:
        logger.debug(f"Executing command: {command}")
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            return True, stdout.strip(), None
        else:
            logger.error(f"Command failed: {command}, Error: {stderr.strip()}")
            return False, None, stderr.strip()
    except Exception as e:
        logger.exception(f"Exception executing command: {command}")
        return False, None, str(e)