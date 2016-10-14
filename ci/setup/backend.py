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
from ci.validate.decorators import required_roles, required_backend, required_preset


class BackendSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_backend_setup")
    BACKEND_TIMEOUT = 15
    INITIALIZE_DISK_TIMEOUT = 300
    ADD_PRESET_TIMEOUT = 60
    UPDATE_PRESET_TIMEOUT = 60
    CLAIM_ASD_TIMEOUT = 60
    LINK_BACKEND_TIMEOUT = 60
    MAX_BACKEND_TRIES = 20

    def __init__(self):
        pass

    @staticmethod
    @required_roles(['DB'])
    def add_backend(backend_name, api, scaling='LOCAL', timeout=BACKEND_TIMEOUT, max_tries=MAX_BACKEND_TRIES):
        """
        Add a new backend

        :param backend_name: Name of the Backend to add
        :type backend_name: str
        :param scaling: LOCAL or GLOBAL
        :type scaling: str
        :return: backend_name
        :rtype: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: timeout between tries
        :type timeout: int
        :param max_tries: amount of max. tries to check if a backend has been successfully created
        :type max_tries: int
        :returns: creation is successfully succeeded?
        :rtype: bool
        """

        # ADD_BACKEND
        backend = api.post(
            api='backends',
            data={
                'name': backend_name,
                'backend_type_guid': BackendHelper.get_backendtype_guid_by_code('alba'),
                'scaling': scaling
            }
        )

        # ADD_ALBABACKEND
        alba_backend_guid = BackendHelper.get_albabackend_by_guid(
                api.post(
                    api='alba/backends',
                    data={
                        'backend_guid': backend['guid'],
                        'scaling': scaling
                    }
                )['guid'])

        # CHECK_STATUS until done
        backend_running_status = "RUNNING"
        tries = 0
        while tries <= max_tries:
            if BackendHelper.get_backend_status_by_name(backend_name) == backend_running_status:
                BackendSetup.LOGGER.info("Creation of Backend `{0}` and scaling `{1}` succeeded!"
                                         .format(backend_name, scaling))
                return True
            else:
                tries += 1
                BackendSetup.LOGGER.warning("Creating backend `{0}`, try {1}. Sleeping for {2} seconds ..."
                                            .format(backend_name, tries, timeout))
                time.sleep(timeout)

        BackendSetup.LOGGER.error("Creation of Backend `{0}` and scaling `{1}` failed with status: {2}!"
                                  .format(backend_name, scaling,
                                          BackendHelper.get_backend_status_by_name(backend_name)))
        return False

    @staticmethod
    @required_backend
    def add_preset(albabackend_name, preset_details, api, timeout=ADD_PRESET_TIMEOUT):
        """
        Add a new preset

        :param albabackend_name: albabackend name
        :type albabackend_name: str
        :param preset_details: dictionary with details of a preset
        :type preset_details: dict
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: amount of max time that preset may take to be added
        :type timeout: int
        :return: success or not
        :rtype: bool
        """

        # BUILD_PRESET
        preset = {'name': preset_details['name'],
                  'policies': preset_details['policies'],
                  'compression': preset_details['compression'],
                  'encryption': preset_details['encryption'],
                  'fragment_size': preset_details['fragment_size']}

        # ADD_PRESET
        task_guid = api.post(
            api='/alba/backends/{0}/add_preset'.format(BackendHelper.get_alba_backend_guid_by_name(albabackend_name)),
            data=preset
        )

        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Preset `{0}` has failed to create on backend `{1}`"\
                .format(preset_details['name'], albabackend_name)
            BackendSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            BackendSetup.LOGGER.info("Creation of preset `{0}` should have succeeded on backend `{1}`"
                                     .format(preset_details['name'], albabackend_name))
            return True

    @staticmethod
    @required_preset
    @required_backend
    def update_preset(albabackend_name, preset_name, policies, api, timeout=UPDATE_PRESET_TIMEOUT):
        """
        Update a existing preset

        :param albabackend_name: albabackend name
        :type albabackend_name: str
        :param preset_name: name of a existing preset
        :type preset_name: str
        :param policies: policies to be updated (e.g. [[1,1,2,2], [1,1,1,2]])
        :type policies: list > list
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: amount of max time that preset may take to be added
        :type timeout: int
        :return: success or not
        :rtype: bool
        """

        task_guid = api.post(
            api='/alba/backends/{0}/update_preset'
                .format(BackendHelper.get_alba_backend_guid_by_name(albabackend_name)),
            data={"name": preset_name, "policies": policies}
        )

        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Preset `{0}` has failed to update with policies `{1}` on backend `{2}`"\
                .format(preset_name, policies, albabackend_name)
            BackendSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            BackendSetup.LOGGER.info("Update of preset `{0}` should have succeeded on backend `{1}`"
                                     .format(preset_name, albabackend_name))
            return True

    @staticmethod
    def add_asds(target, disks, scaling, albabackend_name, api):
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
        # Make sure all backends are registered
        BackendSetup._discover_and_register_nodes(api)
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
                        # Initialize disk:
                        BackendSetup.LOGGER.info('Initializing {0} and providing {1} asds.'.format(diskname, amount_of_osds))
                        BackendSetup._initialize_disk(alba_node_guid=alba_node_guid, diskname=diskname, amount_of_osds=amount_of_osds, api=api)

            # Restarting iteration to avoid too many local stack calls:
            local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name, api=api)
            for disk, amount_of_osds in disks.iteritems():
                disk_object = StoragerouterHelper.get_disk_by_ip(ip=target, diskname=disk)
                # Get the name of the disk out of the path
                diskname = disk_object.path.rsplit('/', 1)[-1]
                for alba_node_id, alba_node_guid in node_mapping.iteritems():
                    # Check if the alba_node_id has the disk
                    if diskname in local_stack['local_stack'][alba_node_id]:
                        # Claim asds
                        if diskname in local_stack['local_stack'][alba_node_id]:
                            for asd_id, asd_info in local_stack['local_stack'][alba_node_id][diskname]['asds'].iteritems():
                                BackendSetup.LOGGER.info('Claiming asd {0} for disk {1}'.format(asd_id, local_stack['local_stack'][alba_node_id][diskname]['guid']))
                                BackendSetup._claim_asd(
                                    alba_backend_name=albabackend_name,
                                    asd_id=asd_id,
                                    disk_guid=local_stack['local_stack'][alba_node_id][diskname]['guid'],
                                    api=api
                                )

        elif scaling == 'GLOBAL':
            # target is a backend
            return
        else:
            raise KeyError('Scaling {0} is not implemented'.format(scaling))

    @staticmethod
    def _discover_and_register_nodes(api):
        """
        Will discover and register potential nodes to the DAL/Alba
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """

        options = {
            'sort': 'ip',
            'contents': 'node_id,_relations',
            'discover': True
        }
        response = api.get(
            api='alba/nodes',
            params={'queryparams': options}
        )
        for node_id in response['data']:
            api.post(
                api='alba/nodes',
                data={'node_id': node_id}
            )

    @staticmethod
    def _map_alba_nodes(api):
        """
        Will map the alba_node_id with its guid counterpart and return the map dict
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """
        mapping = {}

        options = {
            'contents': 'node_id,_relations',
        }
        response = api.get(
            api='alba/nodes',
            params=options
        )
        for node in response['data']:
            print node
            mapping[node['node_id']] = node['guid']

        return mapping

    @staticmethod
    def get_backend_local_stack(alba_backend_name, api):
        """
        Fetches the local stack property of a backend
        :param alba_backend_name: backend name
        :type alba_backend_name: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """
        options = {
            'contents': 'local_stack',
        }
        return api.get(api='/alba/backends/{0}/'.format(BackendHelper.get_alba_backend_guid_by_name(alba_backend_name)),
                       params={'queryparams': options}
                       )

    @staticmethod
    def _initialize_disk(alba_node_guid, diskname, amount_of_osds, api, timeout=INITIALIZE_DISK_TIMEOUT):
        """
        Initializes a disk to create osds
        :param alba_node_guid:
        :param diskname:
        :param amount_of_osds:
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: timeout counter in seconds
        :type timeout: int
        :return:
        """
        data = {'disks': {diskname: amount_of_osds}}
        task_guid = api.post(
            api='/alba/nodes/{0}/initialize_disks/'.format(alba_node_guid),
            data=data
        )
        return api.wait_for_task(task_id=task_guid, timeout=timeout)

    @staticmethod
    def _claim_asd(alba_backend_name, asd_id, disk_guid, api, timeout=CLAIM_ASD_TIMEOUT):
        """
        Claims a asd
        :param alba_backend_name: backend name
        :type alba_backend_name: str
        :param asd_id: id of the asd
        :type asd_id: str
        :param disk_guid: guid of the disk
        :type disk_guid: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: timeout counter in seconds
        :type timeout: int
        :return:
        """
        data = {'osds':{asd_id: disk_guid}}
        task_guid = api.post(
            api='/alba/backends/{0}/add_units/'.format(BackendHelper.get_alba_backend_guid_by_name(alba_backend_name)),
            data=data
        )
        return api.wait_for_task(task_id=task_guid, timeout=timeout)

    @staticmethod
    @required_backend
    def link_backend(albabackend_name, globalbackend_name, preset_name, api, timeout=LINK_BACKEND_TIMEOUT):
        """
        Link a LOCAL backend to a GLOBAL backend

        :param albabackend_name: name of a LOCAL alba backend
        :type albabackend_name: str
        :param globalbackend_name: name of a GLOBAL alba backend
        :type globalbackend_name: str
        :param preset_name: name of the preset available in the LOCAL alba backend
        :type preset_name: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: timeout counter in seconds
        :type timeout: int
        :return:
        """
        local_albabackend = BackendHelper.get_albabackend_by_name(albabackend_name)

        data = {
           "metadata": {
              "backend_connection_info": {
                 "host": "",
                 "port": 80,
                 "username": "",
                 "password": ""
              },
              "backend_info": {
                 "linked_guid": local_albabackend.guid,
                 "linked_name": local_albabackend.name,
                 "linked_preset": preset_name,
                 "linked_alba_id": local_albabackend.alba_id
              }
           }
        }
        task_guid = api.post(
            api='/alba/backends/{0}/link_alba_backends'
                .format(BackendHelper.get_alba_backend_guid_by_name(globalbackend_name)),
            data=data
        )
        return api.wait_for_task(task_id=task_guid, timeout=timeout)