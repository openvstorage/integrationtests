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
A general class dedicated to Arakoon logic
"""

import os
from ConfigParser import RawConfigParser
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ovs.extensions.generic.configuration import Configuration
from ovs.lib.storagedriver import StorageDriverController
from StringIO import StringIO


class GeneralArakoon(object):
    """
    A general class dedicated to Arakoon logic
    """
    LOG_DIR = '/var/log/upstart'
    BASE_DIR = ArakoonInstaller.ARAKOON_BASE_DIR
    HOME_DIR = ArakoonInstaller.ARAKOON_HOME_DIR
    TLOG_DIR = ArakoonInstaller.ARAKOON_TLOG_DIR
    CONFIG_KEY = ArakoonInstaller.CONFIG_KEY
    CONFIG_ROOT = ArakoonInstaller.CONFIG_ROOT

    @staticmethod
    def get_config(cluster_name):
        """
        Retrieve the configuration for given cluster
        :param cluster_name: Name of the cluster
        :return: RawConfigParser object
        """
        config_key = GeneralArakoon.CONFIG_KEY.format(cluster_name)
        if not Configuration.exists(config_key, raw=True):
            raise ValueError('Unknown arakoon cluster_name {0} provided'.format(cluster_name))

        voldrv_config = Configuration.get(config_key, raw=True)
        parser = RawConfigParser()
        parser.readfp(StringIO(voldrv_config))
        return parser

    @staticmethod
    def delete_config(cluster_name):
        """
        Remove the etcd entry for arakoon cluster_name
        :param cluster_name: Name of the arakoon cluster
        :return: None
        """
        config_key = GeneralArakoon.CONFIG_KEY.format(cluster_name)
        if Configuration.exists(config_key, raw=True):
            Configuration.delete(os.path.dirname(config_key))

    @staticmethod
    def voldrv_arakoon_checkup():
        """
        Execute the scheduled task voldrv arakoon checkup
        :return: None
        """
        StorageDriverController.scheduled_voldrv_arakoon_checkup()  # No API available
