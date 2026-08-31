import logging
import os

SCHEMA_FILE = os.path.join("threadcomponents", "conf", "schema.sql")
logger = logging.getLogger(__name__)


def delete_db_file(file_path):
    """Function to delete a local database test file."""
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)
    else:
        logger.warning(
            f"Test DB file {file_path} could not be deleted; accumulated data in-between test runs expected."
        )
