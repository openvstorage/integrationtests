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

from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.helpers.storagerouter import StoragerouterHelper
from ci.validate.decorators import required_roles, required_backend


class VPoolSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_vpool_setup")
    ADD_VPOOL_TIMEOUT = 500

    def __init__(self):
        pass

    @staticmethod
    @required_backend
    @required_roles(['DB', 'SCRUB', 'WRITE', 'READ'], "LOCAL")
    def add_vpool(vpool_name, vpool_details, api, storagerouter_ip, albabackend_name, timeout=ADD_VPOOL_TIMEOUT):
        """
        Adds a VPool to a storagerouter

        :param vpool_name: name of the new vpool
        :type vpool_name: str
        :param vpool_details: dictionary with storagedriver settings
        :type vpool_details: dict
        :param timeout: specify a timeout
        :type timeout: int
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param albabackend_name: name(s) of backend(s)
        :type albabackend_name: str or list
        :return: (storagerouter_ip, vpool_mountpoint)
        :rtype: tuple
        """

        # Build ADD_VPOOL parameters
        call_parameters = {
            "call_parameters": {
                "vpool_name": vpool_name,
                "type": "alba",
                "backend_connection_info": {
                    "host": "",
                    "port": 80,
                    "username": "",
                    "password": "",
                    "backend": {
                        "backend": BackendHelper.get_albabackend_by_name(vpool_details['backend_name']).guid,
                        "metadata": vpool_details['preset']
                    }
                },
                "storage_ip": vpool_details['storage_ip'],
                "storagerouter_ip": storagerouter_ip,
                "readcache_size": int(vpool_details['storagedriver']['global_read_buffer']),
                "writecache_size": int(vpool_details['storagedriver']['global_write_buffer']),
                "fragment_cache_on_read": vpool_details['fragment_cache']['strategy']['cache_on_read'],
                "fragment_cache_on_write": vpool_details['fragment_cache']['strategy']['cache_on_write'],
                "config_params": {
                    "dtl_mode": vpool_details['storagedriver']['dtl_mode'],
                    "sco_size": int(vpool_details['storagedriver']['sco_size']),
                    "dedupe_mode": vpool_details['storagedriver']['deduplication'],
                    "cluster_size": int(vpool_details['storagedriver']['cluster_size']),
                    "write_buffer": int(vpool_details['storagedriver']['volume_write_buffer']),
                    "dtl_transport": vpool_details['storagedriver']['dtl_transport'],
                    "cache_strategy": vpool_details['storagedriver']['strategy']
                }
            }
        }

        # Setting possible alba accelerated alba
        if vpool_details['fragment_cache']['location'] == "backend":
            aa = {
                    "host": "",
                    "port": 80,
                    "username": "",
                    "password": "",
                    "backend": {
                        "backend":
                            BackendHelper.get_albabackend_by_name(vpool_details['fragment_cache']['backend']['name'])
                                .guid,
                        "metadata": vpool_details['fragment_cache']['backend']['preset']
                    }
                 }
            call_parameters['call_parameters']['backend_connection_info_aa'] = aa
        elif vpool_details['fragment_cache']['location'] == "disk":
            pass
        else:
            error_msg = "Wrong `fragment_cache->location` in vPool configuration, it should be `disk` or `backend`"
            VPoolSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)

        task_guid = api.post(
            api='/storagerouters/{0}/add_vpool/'.format(
                    StoragerouterHelper.get_storagerouter_guid_by_ip(storagerouter_ip)),
            data=call_parameters
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)
        if not task_result[0]:
            error_msg = "vPool `{0}` has failed to create on storagerouter `{1}`".format(vpool_name, storagerouter_ip)
            VPoolSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            VPoolSetup.LOGGER.info("Creation of vPool `{0}` should have succeeded on storagerouter `{1}`"
                                   .format(vpool_name, storagerouter_ip))
            return storagerouter_ip, "/mnt/{0}".format(vpool_name)
