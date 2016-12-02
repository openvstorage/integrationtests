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
import time

from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.dal.hybrids.storagerouter import StorageRouter
from ovs.extensions.generic.system import System
from ovs.log.log_handler import LogHandler


class StoragerouterHelper(object):

    """
    StoragerouterHelper class
    """
    LOGGER = LogHandler.get(source="helpers", name="ci_storagerouter_helper")

    cache_timeout = 60
    disk_map_cache = {}

    def __init__(self):
        pass

    @staticmethod
    def get_storagerouter_guid_by_ip(storagerouter_ip):
        """

        :param storagerouter_ip: ip of a storagerouter
        :type storagerouter_ip: str
        :return: storagerouter guid
        :rtype: str
        """
        return StoragerouterHelper.get_storagerouter_by_ip(storagerouter_ip).guid

    @staticmethod
    def get_storagerouter_by_ip(storagerouter_ip):
        """

        :param storagerouter_ip: ip of a storagerouter
        :type storagerouter_ip: str
        :return: storagerouter object
        :rtype: ovs.dal.hybrids.storagerouter.StorageRouter
        """
        return StorageRouterList.get_by_ip(storagerouter_ip)

    @staticmethod
    def get_disks_by_ip(storagerouter_ip):
        """

        :param storagerouter_ip:
        :type storagerouter_ip: str
        :return: disks found for the storagerouter ip
        :rtype: list of <class 'ovs.dal.hybrids.disk.Disk'>
        """
        storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(storagerouter_ip)
        return StorageRouter(storagerouter_guid).disks

    @staticmethod
    def get_disk_by_ip(ip, diskname):
        """
        Fetch a disk by its ip and name

        :param ip: ip address of a storagerouter
        :param diskname: shortname of a disk (e.g. sdb)
        :return: Disk Object
        :rtype: ovs.dal.hybrids.disk.disk
        """

        storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(ip)
        disks = StorageRouter(storagerouter_guid).disks
        for d in disks:
            if d.name == diskname:
                return d

    @staticmethod
    def get_local_storagerouter():
        """
        Fetch the local storagerouter settings

        :return: StorageRouter Object
        :rtype: ovs.dal.hybrids.storagerouter.StorageRouter
        """

        return System.get_my_storagerouter()

    @staticmethod
    def get_storagerouter_ips():
        """
        Fetch all the ip addresses in this cluster

        :return: list with storagerouter ips
        :rtype: list
        """
        return [storagerouter.ip for storagerouter in StorageRouterList.get_storagerouters()]

    @staticmethod
    def get_storagerouters():
        """
        Fetch the storagerouters

        :return: list with storagerouters
        :rtype: list
        """

        return StorageRouterList.get_storagerouters()

    @staticmethod
    def get_master_storagerouters():
        """
        Fetch the master storagerouters

        :return: list with master storagerouters
        :rtype: list
        """

        return StorageRouterList.get_masters()

    @staticmethod
    def get_master_storagerouter_ips():
        """
        Fetch the master storagerouters ips

        :return: list with master storagerouters ips
        :rtype: list
        """

        return [storagerouter.ip for storagerouter in StorageRouterList.get_masters()]

    @staticmethod
    def get_slave_storagerouters():
        """
        Fetch the slave storagerouters

        :return: list with slave storagerouters
        :rtype: list
        """

        return StorageRouterList.get_slaves()

    @staticmethod
    def get_slave_storagerouter_ips():
        """
        Fetch the slave storagerouters ips

        :return: list with slave storagerouters ips
        :rtype: list
        """

        return [storagerouter.ip for storagerouter in StorageRouterList.get_slaves()]

    @staticmethod
    def sync_disk_with_reality(api, guid=None, ip=None, timeout=None):
        """

        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param guid: guid of the storagerouter
        :type guid: str
        :param ip: ip of the storagerouter
        :type ip: str
        :return:
        """
        storagerouter_guid = guid
        if ip is not None:
            storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(ip)
        if storagerouter_guid is None:
            raise ValueError('No guid or ip found.')
        else:
            task_id = api.post(api='/storagerouters/{0}/rescan_disks/'.format(storagerouter_guid), data=None)
            return api.wait_for_task(task_id=task_id, timeout=timeout)