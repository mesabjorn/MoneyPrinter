
import logging

def init_logger(level: int=logging.DEBUG):
    logger = logging.getLogger(__name__)

    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if not logger.hasHandlers():
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

LOGGER = init_logger()
