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
    def _clear_disk_cache(ip=None):
        if ip is None:
            StoragerouterHelper.disk_map_cache = {}
        else:
            StoragerouterHelper.disk_map_cache[ip] = {}

    @staticmethod
    def _append_to_disk_cache(ip, cache_start=None, diskname=None, mapping=None):
        if ip not in StoragerouterHelper.disk_map_cache:
            StoragerouterHelper.disk_map_cache[ip] = {}
            if cache_start is not None:
                StoragerouterHelper.disk_map_cache[ip]['cache_start'] = cache_start
        else:
            if cache_start is not None:
                StoragerouterHelper.disk_map_cache[ip]['cache_start'] = cache_start
        if diskname is not None and mapping is not None:
            StoragerouterHelper.disk_map_cache[ip][diskname] = mapping

    @staticmethod
    def _get_from_disk_cache(diskname, ip):
        if ip in StoragerouterHelper.disk_map_cache:
            # Get check cache for IP:
            if StoragerouterHelper.disk_map_cache[ip]['cache_start'] is None or (StoragerouterHelper.disk_map_cache[ip]['cache_start'] + StoragerouterHelper.cache_timeout) - time.time() < 0:
                # Cache expired
                StoragerouterHelper._clear_disk_cache(ip)
                StoragerouterHelper._build_disk_cache(ip)
        else:
            # Found no entries, cache must be built
            StoragerouterHelper._build_disk_cache(ip)
        if ip in StoragerouterHelper.disk_map_cache and diskname in StoragerouterHelper.disk_map_cache[ip]:
            return StoragerouterHelper.disk_map_cache[ip][diskname]
        raise ValueError('Found no entry for {0} in the cache. Rebuilding might have failed. Cache: {1}'.format(diskname, StoragerouterHelper.disk_map_cache))

    @staticmethod
    def _build_disk_cache(ip):
        """

        :param ip: ip address
        :type ip: str
        :return:
        """
        StoragerouterHelper.LOGGER.info('Building cache for {0}'.format(ip))
        from ovs.extensions.generic.remote import remote
        import os
        # Slow because of the remote - caching for future reuse
        with remote(ip, [os]) as rem:
            path_mapping = {}
            for path_type in rem.os.listdir('/dev/disk'):
                directory = '/dev/disk/{0}'.format(path_type)
                for symlink in rem.os.listdir(directory):
                    link = rem.os.path.realpath('{0}/{1}'.format(directory, symlink))
                    if link not in path_mapping:
                        path_mapping[link] = {}
                    # Only want wwn and model
                    if path_type == 'by-id':
                        if symlink.startswith('wwn-'):
                            path_mapping[link]['wwn'] = '{0}/{1}'.format(directory, symlink)
                        else:
                            path_mapping[link]['model'] = '{0}/{1}'.format(directory, symlink)
                        StoragerouterHelper._append_to_disk_cache(ip=ip, cache_start=time.time())
                        StoragerouterHelper._append_to_disk_cache(ip=ip, diskname=link.rsplit('/', 1)[-1], mapping=path_mapping[link])

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
                # Pathname could a wwn name (world wide name) - in that case we want to map it to a model name:
                disk_path_name = d.path.rsplit('/', 1)[-1]
                if str(disk_path_name).startswith('wwn-'):
                    # Fetch mapping for the disk
                    d.path = StoragerouterHelper._get_from_disk_cache(diskname, ip)['model']

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

        return map(lambda storagerouter: storagerouter.ip, StorageRouterList.get_storagerouters())

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

        return map(lambda storagerouter: storagerouter.ip, StorageRouterList.get_masters())
