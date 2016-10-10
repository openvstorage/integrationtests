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
from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.helpers.storagerouter import StoragerouterHelper


class BackendRemover(object):

    LOGGER = LogHandler.get(source="remove", name="ci_backend_remover")
    REMOVE_ASD_TIMEOUT = 60
    REMOVE_DISK_TIMEOUT = 60

    def __init__(self):
        pass

    @staticmethod
    def remove_claimed_disk(api):
        pass

    @staticmethod
    def remove_asds(albabackend_name, target, disks, scaling, api):
        """
                Initialize and claim a new asd
                :param target: target to add asds too
                :type target: str
                :param disks: dict with diskname as key and amount of osds as value
                :type disks: dict
                :param scaling: type of scaling (local of global)
                :type scaling: str
                :param api: specify a valid api connection to the setup
                :type api: ci.helpers.api.OVSClient
                :param albabackend_name: Name of the AlbaBackend to configure
                :type albabackend_name: str
                :return: preset_name
                :rtype: str
                """
        albabackend_guid = BackendHelper.get_alba_backend_guid_by_name(albabackend_name)
        if scaling == 'LOCAL':
            # target is a node
            node_mapping = BackendHelper._map_alba_nodes(api)

            local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name, api=api)
            for disk, amount_of_osds in disks.iteritems():
                disk_object = StoragerouterHelper.get_disk_by_ip(ip=target, diskname=disk)
                # Get the name of the disk out of the path
                diskname = disk_object.path.rsplit('/', 1)[-1]
                for alba_node_id, alba_node_guid in node_mapping.iteritems():
                    # Check if the alba_node_id has the disk
                    if diskname in local_stack['local_stack'][alba_node_id]:
                        # Remove asds
                        if diskname in local_stack['local_stack'][alba_node_id]:
                            for asd_id, asd_info in local_stack['local_stack'][alba_node_id][diskname]['asds'].iteritems():
                                BackendRemover.LOGGER.info('Removing asd {0} for disk {1}'.format(asd_id, local_stack['local_stack'][alba_node_id][diskname]['guid']))
                                asd_safety = BackendHelper.get_asd_safety(albabackend_guid=albabackend_guid, asd_id=asd_id, api=api)
                                BackendRemover._remove_asd(
                                    alba_node_guid=alba_node_guid,
                                    asd_id=asd_id,
                                    asd_safety=asd_safety,
                                    api=api
                                )

            # Restarting iteration to avoid too many local stack calls:
            local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name,
                                                                api=api)
            for disk, amount_of_osds in disks.iteritems():
                disk_object = StoragerouterHelper.get_disk_by_ip(ip=target, diskname=disk)
                # Get the name of the disk out of the path
                diskname = disk_object.path.rsplit('/', 1)[-1]
                for alba_node_id, alba_node_guid in node_mapping.iteritems():
                    # Check if the alba_node_id has the disk
                    if diskname in local_stack['local_stack'][alba_node_id]:
                        # Initialize disk:
                        BackendRemover.LOGGER.info('Removing {0}.'.format(diskname))
                        BackendRemover._remove_disk(alba_node_guid=alba_node_guid,
                                                      diskname=diskname,
                                                      api=api
                                                    )

        elif scaling == 'GLOBAL':
            # target is a backend
            return
        else:
            raise KeyError('Scaling {0} is not implemented'.format(scaling))

    @staticmethod
    def _remove_asd(alba_node_guid, asd_id, asd_safety, api, timeout=REMOVE_ASD_TIMEOUT):
        """

        :param alba_node_guid:
        :param asd_id: id of the asd
        :type asd_id: str
        :param asd_safety:
        :type asd_safety: dict
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout:
        :return:
        """

        data = {
            'asd_id': asd_id,
            'safety': asd_safety
        }
        task_guid = api.post(
            api='/alba/nodes/{0}/reset_asd/'.format(alba_node_guid),
            data=data
        )
        return api.wait_for_task(task_id=task_guid, timeout=timeout)

    @staticmethod
    def _remove_disk(alba_node_guid, diskname, api, timeout=REMOVE_DISK_TIMEOUT):
        data = {
            'disk': diskname,
        }
        task_guid = api.post(
            api='/alba/nodes/{0}/remove_disk/'.format(alba_node_guid),
            data=data
        )
        return api.wait_for_task(task_id=task_guid, timeout=timeout)