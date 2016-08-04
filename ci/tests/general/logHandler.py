# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Contains the loghandler module
"""

import os
import inspect
import logging
from ci.tests.general.general import General


def _ignore_formatting_errors():
    """
    Decorator to ignore formatting errors during logging
    """
    def wrap(outer_function):
        """
        Wrapper function
        :param outer_function: Function to wrap
        """
        def new_function(self, msg, *args, **kwargs):
            """
            Wrapped function
            :param self: Logger instance
            :param msg: Message
            """
            try:
                msg = str(msg)
                return outer_function(self, msg, *args, **kwargs)
            except TypeError as exception:
                too_many = 'not all arguments converted during string formatting' in str(exception)
                not_enough = 'not enough arguments for format string' in str(exception)
                if too_many or not_enough:
                    msg = msg.replace('%', '%%')
                    msg = msg % args
                    msg = msg.replace('%%', '%')
                    return outer_function(self, msg, *[], **kwargs)
                raise

        new_function.__name__ = outer_function.__name__
        new_function.__module__ = outer_function.__module__
        return new_function
    return wrap


class LogHandler(object):
    """
    Log handler
    """
    cache = {}
    targets = {'api': 'api',
               'api-connection': 'api-connection',
               'arakoon': 'arakoon',
               'backend': 'backend',
               'disklayout': 'disklayout',
               'general': 'general',
               'gui': 'gui',
               'license': 'license',
               'mgmtcenter': 'mgmtcenter',
               'sanity': 'sanity',
               'system': 'system',
               'validation': 'validation',
               'vdisks': 'vdisk',
               'vmachines': 'vmachine',
               'vpool': 'vpool'}

    def __init__(self, source, name=None, propagate=False):
        """
        Initializes the logger
        """
        parent_invoker = inspect.stack()[1]
        if not __file__.startswith(parent_invoker[1]) or parent_invoker[3] != 'get':
            raise RuntimeError('Cannot invoke instance from outside this class. Please use LogHandler.get(source, name=None) instead')

        if name is None:
            name = General.get_config().get('logger', 'default_name')

        log_filename = LogHandler.load_path(source)

        formatter = logging.Formatter('%(asctime)s - [%(process)s] - [%(levelname)s] - [{0}] - [%(name)s] - %(message)s'.format(source))
        handler = logging.FileHandler(log_filename)
        handler.setFormatter(formatter)

        self.logger = logging.getLogger(name)
        self.logger.propagate = propagate
        self.logger.setLevel(getattr(logging, General.get_config().get('logger', 'level')))
        self.logger.addHandler(handler)

    @staticmethod
    def load_path(source):
        """
        Retrieve the absolute path for the logfile
        :param source: Source for the logfile
        :return: Absolute path to logfile
        """
        log_path = General.get_config().get('logger', 'path')
        if not os.path.exists(log_path):
            os.mkdir(log_path)
        file_name = LogHandler.targets[source] if source in LogHandler.targets else General.get_config().get('logger', 'default_file')
        log_filename = '{0}/{1}.log'.format(log_path, file_name)
        if not os.path.exists(log_filename):
            open(log_filename, 'a').close()
            os.chmod(log_filename, 0o666)
        return log_filename

    @staticmethod
    def get(source, name=None):
        """
        Retrieve a LogHandler object
        :param source: Source of LogHandler
        :param name: Name used in logging
        :return: LogHandler object
        """
        key = '{0}_{1}'.format(source, name)
        if key not in LogHandler.cache:
            logger = LogHandler(source, name)
            LogHandler.cache[key] = logger
        return LogHandler.cache[key]

    @_ignore_formatting_errors()
    def info(self, msg, *args, **kwargs):
        """
        Info
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.info(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def error(self, msg, *args, **kwargs):
        """
        Error
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.error(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def debug(self, msg, *args, **kwargs):
        """
        Debug
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.debug(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def warning(self, msg, *args, **kwargs):
        """
        Warning
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.warning(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def log(self, msg, *args, **kwargs):
        """
        Log
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.log(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def critical(self, msg, *args, **kwargs):
        """
        Critical
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.critical(msg, *args, **kwargs)

    @_ignore_formatting_errors()
    def exception(self, msg, *args, **kwargs):
        """
        Exception
        :param msg: Message to log
        """
        if 'print_msg' in kwargs:
            del kwargs['print_msg']
            print msg
        return self.logger.exception(msg, *args, **kwargs)
