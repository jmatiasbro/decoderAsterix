# -*- coding: utf-8 -*-
import logging
import logging.handlers
import os.path
from . constants import LOGGING_LEVEL


def setup_logger(config):
    # general
    logger = logging.getLogger(config['logger']['name'])
    logger.setLevel(LOGGING_LEVEL[config['logger']['level']])
    _setup_logger_file(config, logger)
    _setup_logger_stream(config, logger)
    return logger


def _setup_logger_file(config, logger):
    os.makedirs(os.path.dirname(config['logger']['file_name']), exist_ok=True)
    _logger_fh = logging.handlers.TimedRotatingFileHandler(
        config['logger']['file_name'],
        when=config['logger']['file_when'],
        interval=config['logger']['file_interval'],
        backupCount=config['logger']['file_backup_count'],
        encoding='utf-8',
        delay=config['logger']['file_delay'])
    _logger_fh.setLevel(LOGGING_LEVEL[config['logger']['file_level']])
    date_fmt = config['logger']['file_date_format']
    if date_fmt == '':
        date_fmt = None
    _logger_ffmt = logging.Formatter(
        fmt=config['logger']['file_formatter'],
        datefmt=date_fmt)
    _logger_fh.setFormatter(_logger_ffmt)
    logger.addHandler(_logger_fh)


def _setup_logger_stream(config, logger):
    # stream handler
    _logger_sh = logging.StreamHandler()
    _logger_sh.setLevel(LOGGING_LEVEL[config['logger']['stream_level']])
    date_fmt = config['logger']['stream_date_format']
    if date_fmt == '':
        date_fmt = None
    _logger_sfmt = logging.Formatter(
        fmt=config['logger']['stream_formatter'],
        datefmt=date_fmt)
    _logger_sh.setFormatter(_logger_sfmt)
    logger.addHandler(_logger_sh)
