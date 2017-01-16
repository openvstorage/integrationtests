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
from ci.helpers.albanode import AlbaNodeHelper
from ci.validate.decorators import required_roles, required_backend, required_preset, check_backend, check_preset, \
    check_linked_backend, filter_osds


class BackendSetup(object):

    LOGGER = LogHandler.get(source="setup", name="ci_backend_setup")
    LOCAL_STACK_SYNC = 30
    BACKEND_TIMEOUT = 15
    INITIALIZE_DISK_TIMEOUT = 300
    ADD_PRESET_TIMEOUT = 60
    UPDATE_PRESET_TIMEOUT = 60
    CLAIM_ASD_TIMEOUT = 60
    LINK_BACKEND_TIMEOUT = 60
    MAX_BACKEND_TRIES = 20

    MAX_CLAIM_RETRIES = 5

    def __init__(self):
        pass

    @staticmethod
    @check_backend
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
        alba_backend = api.post(api='alba/backends', data={'backend_guid': backend['guid'], 'scaling': scaling})

        # CHECK_STATUS until done
        backend_running_status = "RUNNING"
        tries = 0
        while tries <= max_tries:
            try:
                if BackendHelper.get_backend_status_by_name(backend_name) == backend_running_status:
                    BackendSetup.LOGGER.info("Creation of Backend `{0}` and scaling `{1}` succeeded!"
                                             .format(backend_name, scaling))
                    return True
                else:
                    tries += 1
                    BackendSetup.LOGGER.warning("Creating backend `{0}`, try {1}. Sleeping for {2} seconds ..."
                                                .format(backend_name, tries, timeout))
                    time.sleep(timeout)
            except AttributeError as ex:
                tries += 1
                BackendSetup.LOGGER.warning("Creating backend `{0}`, try {1} with exception `{2}`. "
                                            "Sleeping for {3} seconds ...".format(backend_name, tries, ex, timeout))
                time.sleep(timeout)

        BackendSetup.LOGGER.error("Creation of Backend `{0}` and scaling `{1}` failed with status: {2}!"
                                  .format(backend_name, scaling,
                                          BackendHelper.get_backend_status_by_name(backend_name)))
        return False

    @staticmethod
    @check_preset
    @required_backend
    def add_preset(albabackend_name, preset_details, api, timeout=ADD_PRESET_TIMEOUT):
        """
        Add a new preset

        :param albabackend_name: albabackend name (e.g. 'mybackend')
        :type albabackend_name: str
        :param preset_details: dictionary with details of a preset e.g.
        {
            "name": "mypreset",
            "compression": "snappy",
            "encryption": "none",
            "policies": [
              [
                2,2,3,4
              ]
            ],
            "fragment_size": 2097152
        }
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
    @required_backend
    @filter_osds
    def add_asds(target, disks, albabackend_name, api, claim_retries=MAX_CLAIM_RETRIES):
        """
        Initialize and claim a new asds on given disks

        :param target: target to add asds too
        :type target: str
        :param disks: dict with diskname as key and amount of osds as value
        :type disks: dict
        :param claim_retries: Maximum amount of claim retries
        :type claim_retries: int
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param albabackend_name: Name of the AlbaBackend to configure
        :type albabackend_name: str
        :return: preset_name
        :rtype: str
        """
        # Make sure all backends are registered
        BackendSetup._discover_and_register_nodes(api)
        # target is a node
        node_mapping = AlbaNodeHelper._map_alba_nodes(api)

        local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name, api=api)
        disk_queue = {}
        for disk, amount_of_osds in disks.iteritems():
            disk_object = AlbaNodeHelper.get_disk_by_ip(ip=target, diskname=disk)
            # Get the name of the disk out of the path, only expecting one with ata-
            disk_path = BackendHelper.get_local_stack_alias(disk_object)
            for alba_node_id, alba_node_guid in node_mapping.iteritems():
                # Check if the alba_node_id has the disk
                if disk_path in local_stack['local_stack'][alba_node_id]:
                    if alba_node_guid not in disk_queue:
                        disk_queue[alba_node_guid] = {}
                    # Initialize disk:
                    BackendSetup.LOGGER.info(
                        'Adding {0} to disk queue for providing {1} asds.'.format(disk_path, amount_of_osds))
                    disk_queue[alba_node_guid][disk_path] = amount_of_osds
        for alba_node_guid, queue in disk_queue.iteritems():
            BackendSetup.LOGGER.info(
                'Posting disk queue {0} for alba_node_guid {1}'.format(disk_queue[alba_node_guid], alba_node_guid))
            result = BackendSetup._initialize_disk(
                alba_node_guid=alba_node_guid,
                queue=disk_queue[alba_node_guid],
                api=api)
            BackendSetup.LOGGER.info('Claiming disks was succesfull. Result = {0}'.format(result))

        # Local stack should sync with the new disks
        BackendSetup.LOGGER.info('Sleeping for {0} seconds to let local stack sync.'.format(BackendSetup.LOCAL_STACK_SYNC))
        time.sleep(BackendSetup.LOCAL_STACK_SYNC)

        # Restarting iteration to avoid too many local stack calls:
        local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name, api=api)
        asd_queue = {}
        for disk, amount_of_osds in disks.iteritems():
            disk_object = AlbaNodeHelper.get_disk_by_ip(ip=target, diskname=disk)
            # Get the name of the disk out of the path
            disk_path = BackendHelper.get_local_stack_alias(disk_object)
            for alba_node_id, alba_node_guid in node_mapping.iteritems():
                # Check if the alba_node_id has the disk
                if disk_path in local_stack['local_stack'][alba_node_id]:
                    # Claim asds
                    for asd_id, asd_info in local_stack['local_stack'][alba_node_id][disk_path]['asds'].iteritems():
                        # If the asd is not available, fetch local_stack again after 5s to wait for albamgr to claim it
                        current_retry = 0
                        while asd_info['status'] != 'available':
                            current_retry += 1
                            BackendSetup.LOGGER.info('ASD {0} for Alba node {1} was not available. Waiting 5 seconds'
                                                     ' to retry (currently {2} retries left).'.format(asd_id, alba_node_id, claim_retries - current_retry))
                            if current_retry >= claim_retries:
                                raise RuntimeError('ASD {0} for Alba node {1} did come available after {2} seconds'.format(asd_id, alba_node_id, current_retry * 5))
                            time.sleep(5)
                            local_stack = BackendHelper.get_backend_local_stack(albabackend_name=albabackend_name, api=api)
                            asd_info = local_stack['local_stack'][alba_node_id][disk_path]['asds'][asd_id]
                        BackendSetup.LOGGER.info('Adding asd {0} for disk {1} to claim queue'.format(asd_id,
                                                                                                     local_stack[
                                                                                                         'local_stack'][
                                                                                                         alba_node_id][
                                                                                                         disk_path][
                                                                                                         'guid']))
                        asd_queue[asd_id] = local_stack['local_stack'][alba_node_id][disk_path]['guid']
        if len(asd_queue.keys()) != 0:
            BackendSetup.LOGGER.info('Posting asd queue {0}'.format(asd_queue))
            BackendSetup._claim_asd(
                alba_backend_name=albabackend_name,
                api=api,
                queue=asd_queue
            )
        else:
            BackendSetup.LOGGER.info('No asds have to claimed for {0}'.format(albabackend_name))

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
            params=options
        )
        for node in response['data']:
            api.post(
                api='alba/nodes',
                data={'node_id': {'node_id': node['node_id']}}
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
    def _initialize_disk(alba_node_guid, api, timeout=INITIALIZE_DISK_TIMEOUT, diskname=None, amount_of_osds=None,
                         queue=None):
        """
        Initializes a disk to create osds
        :param alba_node_guid:
        :param diskname:
        :param amount_of_osds:
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param timeout: timeout counter in seconds
        :param queue: queue of disks
        :type queue: dict
        :type timeout: int
        :return:
        """
        if queue is None and (diskname and amount_of_osds is not None):
            queue = {'disks': {diskname: amount_of_osds}}

        data = {'disks': queue}
        task_guid = api.post(
            api='/alba/nodes/{0}/initialize_disks/'.format(alba_node_guid),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Initialize disk `{0}` for alba node `{1}` has failed".format(queue, alba_node_guid)
            BackendSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            BackendSetup.LOGGER.info("Succesfully initialized '{0}'".format(queue))
            return task_result[0]

    @staticmethod
    def _claim_asd(alba_backend_name, api, timeout=CLAIM_ASD_TIMEOUT, asd_id=None, disk_guid=None, queue=None):
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
        :param queue: queue of asds
        :type queue: dict
        :return:
        """
        if queue is None and (asd_id and disk_guid is not None):
            queue = {asd_id: disk_guid}
        data = {'osds': queue}
        task_guid = api.post(
            api='/alba/backends/{0}/add_units/'.format(BackendHelper.get_alba_backend_guid_by_name(alba_backend_name)),
            data=data
        )
        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Claim ASD `{0}` for alba backend `{1}` has failed with error '{2}'".format(queue, alba_backend_name, task_result[1])
            BackendSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            BackendSetup.LOGGER.info("Succesfully claimed '{0}'".format(queue))
            return task_result[0]

    @staticmethod
    @required_preset
    @required_backend
    @check_linked_backend
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

        task_result = api.wait_for_task(task_id=task_guid, timeout=timeout)

        if not task_result[0]:
            error_msg = "Linking backend `{0}` to global backend `{1}` has failed with error '{2}'".format(
                albabackend_name, globalbackend_name, task_result[1])
            BackendSetup.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            BackendSetup.LOGGER.info("Linking backend `{0}` to global backend `{1}` should have succeeded"
                                     .format(albabackend_name, globalbackend_name))
            return task_result[0]
