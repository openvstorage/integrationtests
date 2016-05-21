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
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
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
    ETCD_CONFIG_KEY = ArakoonInstaller.ETCD_CONFIG_KEY
    ETCD_CONFIG_PATH = ArakoonInstaller.ETCD_CONFIG_PATH
    ETCD_CONFIG_ROOT = ArakoonInstaller.ETCD_CONFIG_ROOT

    @staticmethod
    def get_config(cluster_name):
        """
        Retrieve the configuration for given cluster
        :param cluster_name: Name of the cluster
        :return: RawConfigParser object
        """
        etcd_key = GeneralArakoon.ETCD_CONFIG_KEY.format(cluster_name)
        if not EtcdConfiguration.exists(etcd_key, raw=True):
            raise ValueError('Unknown arakoon cluster_name {0} provided'.format(cluster_name))

        voldrv_config = EtcdConfiguration.get(etcd_key, raw=True)
        parser = RawConfigParser()
        parser.readfp(StringIO(voldrv_config))
        return parser

    @staticmethod
    def delete_etcd_config(cluster_name):
        """
        Remove the etcd entry for arakoon cluster_name
        :param cluster_name: Name of the arakoon cluster
        :return: None
        """
        etcd_key = GeneralArakoon.ETCD_CONFIG_KEY.format(cluster_name)
        if EtcdConfiguration.exists(etcd_key, raw=True):
            EtcdConfiguration.delete(os.path.dirname(etcd_key))

    @staticmethod
    def voldrv_arakoon_checkup():
        """
        Execute the scheduled task voldrv arakoon checkup
        :return: None
        """
        StorageDriverController.scheduled_voldrv_arakoon_checkup()  # No API available
