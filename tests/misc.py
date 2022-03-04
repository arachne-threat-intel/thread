import logging
import os


def delete_db_file(file_path):
    """Function to delete a local database test file."""
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)
    else:
        logging.warning('Test DB file %s could not be deleted; accumulated data in-between test runs expected.'
                        % file_path)
