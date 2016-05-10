# Copyright 2016 iNuron NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A general class dedicated to ALBA backend logic
"""

import re
import json
import time
import random
import tempfile
from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_arakoon import GeneralArakoon
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_service import GeneralService
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.logHandler import LogHandler
from ovs.dal.exceptions import ObjectNotFoundException
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.lib.albacontroller import AlbaController
from ovs.lib.albanodecontroller import AlbaNodeController
from ovs.lib.helpers.toolbox import Toolbox


class GeneralAlba(object):
    """
    A general class dedicated to ALBA backend logic
    """
    ALBA_TIMER = 1800
    ALBA_TIMER_STEP = 5

    api = Connection()
    logger = LogHandler.get('backend', name='alba')
    logger.logger.propagate = False

    @staticmethod
    def get_alba_backend(guid):
        """
        :param guid: Guid of the ALBA backend
        :return: ALBA backend DAL object
        """
        return AlbaBackend(guid)

    @staticmethod
    def get_alba_nodes():
        """
        Retrieve all ALBA nodes
        :return: Data-object list of ALBA nodes
        """
        return AlbaNodeList.get_albanodes()

    @staticmethod
    def get_node_by_id(node_id):
        """
        Retrieve ASD node by ID
        :param node_id: ID of the ASD node
        :return: ASD node information
        """
        return AlbaNodeList.get_albanode_by_node_id(node_id=node_id)

    @staticmethod
    def get_abm_config(alba_backend):
        """
        Retrieve the configuration string to pass to the ALBA CLI
        :param alba_backend: ALBA backend
        :return: Configuration string
        """
        return '--config etcd://127.0.0.1:2379/ovs/arakoon/{0}/config'.format(alba_backend.abm_services[0].service.name)

    @staticmethod
    def prepare_alba_backend(name=None):
        """
        Create an ALBA backend and claim disks
        :param name: Name for the backend
        :return: None
        """
        # @TODO: Fix this, because backend_type should not be configurable if you always create an ALBA backend
        # @TODO 2: Get rid of these asserts, any test (or testsuite) should verify the required params first before starting execution
        autotest_config = General.get_config()
        if name is None:
            name = autotest_config.get('backend', 'name')
        nr_of_disks_to_claim = autotest_config.getint('backend', 'nr_of_disks_to_claim')
        type_of_disks_to_claim = autotest_config.get('backend', 'type_of_disks_to_claim')
        assert name, "Please fill out a valid backend name in autotest.cfg file"

        my_sr = GeneralStorageRouter.get_local_storagerouter()
        if GeneralStorageRouter.has_roles(storagerouter=my_sr, roles='DB') is False:
            GeneralDisk.add_db_role(my_sr)
        if GeneralStorageRouter.has_roles(storagerouter=my_sr, roles=['READ', 'SCRUB', 'WRITE']) is False:
            GeneralDisk.add_read_write_scrub_roles(my_sr)
        backend = GeneralBackend.get_by_name(name)
        if not backend:
            alba_backend = GeneralAlba.add_alba_backend(name)
        else:
            alba_backend = backend.alba_backend
        GeneralAlba.claim_asds(alba_backend, nr_of_disks_to_claim, type_of_disks_to_claim)

    @staticmethod
    def unclaim_disks_and_remove_alba_backend(alba_backend):
        """
        Removes an ALBA backend
        :param alba_backend: ALBA backend
        :return: None
        """
        GeneralAlba.unclaim_disks(alba_backend)
        GeneralAlba.remove_alba_backend(alba_backend)

    @staticmethod
    def execute_alba_cli_action(alba_backend, action, params=None, json_output=True):
        """
        Execute an ALBA CLI command
        :param alba_backend: ALBA backend
        :param action: Action to execute
        :param params: Parameters to pass to the action
        :param json_output: Return JSON output
        :return: Output of the action
        """
        config = GeneralAlba.get_abm_config(alba_backend)
        cmd = ['alba', action, config]
        if json_output:
            cmd.append('--to-json')
        if params is None:
            params = []
        cmd.extend(params)

        output = ''
        try:
            output, error, exit_code = General.execute_command(' '.join(cmd))
            if exit_code != 0:
                print 'Exit code: {0}'.format(exit_code)
                print 'Error thrown: {0}'.format(error)
                raise RuntimeError('ALBA command failed with exitcode {0} and error {1}'.format(exit_code, error))
            if json_output is True:
                return json.loads(output)['result']
            return output
        except (ValueError, RuntimeError):
            print "Command {0} failed:\nOutput: {1}".format(cmd, output)
            raise RuntimeError("Command {0} failed:\nOutput: {1}".format(cmd, output))

    @staticmethod
    def add_preset(alba_backend, name, policies=None, compression='none', encryption='none'):
        """
        Add a new preset
        :param alba_backend: ALBA backend
        :param name: Name of the preset to add
        :param policies: Policies to add in the preset
        :param compression: Compression to be used by the preset
        :param encryption: Encryption to be used by the preset
        :return: New preset
        """
        if policies is None:
            policies = [[1, 1, 1, 2]]
        data = {'name': name,
                'policies': policies,
                'compression': compression,
                'encryption': encryption}
        return GeneralAlba.api.execute_post_action('alba/backends', alba_backend.guid, 'add_preset', data, wait=True)

    @staticmethod
    def update_preset(alba_backend, name, policies):
        """
        Update an existing preset
        :param alba_backend: ALBA backend
        :param name: Name of the preset
        :param policies: Policies used by the preset
        :return: Updated preset
        """
        data = {'name': name, 'policies': policies}
        return GeneralAlba.api.execute_post_action('alba/backends', alba_backend.guid, 'update_preset', data, wait=True)

    @staticmethod
    def remove_preset(alba_backend, name):
        """
        Remove a preset
        :param alba_backend: ALBA backend
        :param name: Name of the preset
        :return: Outcome of delete action
        """
        data = {'alba_backend_guid': alba_backend.guid,
                'name': name}
        return GeneralAlba.api.execute_post_action('alba/backends', alba_backend.guid, 'delete_preset', data, wait=True)

    @staticmethod
    def wait_for_alba_backend_status(alba_backend, status='RUNNING', timeout=None):
        """
        Verify the ALBA backend status
        :param alba_backend: ALBA Backend
        :param status: Status to wait for
        :param timeout: Time to wait for status
        :return:
        """
        if timeout is None:
            timeout = GeneralAlba.ALBA_TIMER
        wait = GeneralAlba.ALBA_TIMER_STEP
        while timeout > 0:
            if alba_backend.backend.status == status:
                GeneralAlba.logger.info('Backend in status {0} after {1} seconds'.format(status, (GeneralAlba.ALBA_TIMER - timeout) * wait))
                return
            time.sleep(wait)
            timeout -= wait
            alba_backend = GeneralAlba.get_alba_backend(guid=alba_backend.guid)
        if timeout <= 0:
            raise ValueError('ALBA Backend {0} did not reach {1} status in {2} seconds'.format(alba_backend.backend.name, status, timeout))

    @staticmethod
    def add_alba_backend(name, wait=True):
        """
        Put an ALBA backend in the model
        :param name: Name of the backend
        :param wait: Wait for backend to enter RUNNING state
        :return: Newly created ALBA backend
        """
        backend = GeneralBackend.get_by_name(name)
        if backend is None:
            backend = GeneralBackend.add_backend(name, 'alba')
            alba_backend = AlbaBackend(GeneralAlba.api.add('alba/backends', {'backend_guid': backend.guid})['guid'])
            if wait is True:
                GeneralAlba.wait_for_alba_backend_status(alba_backend)

        out, err, _ = General.execute_command('etcdctl ls /ovs/alba/asdnodes')
        if err == '' and len(out):
            AlbaNodeController.model_local_albanode()

        return GeneralBackend.get_by_name(name).alba_backend

    @staticmethod
    def validate_alba_backend_sanity_without_claimed_disks(alba_backend):
        """
        Validate whether the ALBA backend is configured correctly
        :param alba_backend: ALBA backend
        :return: None
        """
        # Attribute validation
        assert alba_backend.available is True, 'ALBA backend {0} is not available'.format(alba_backend.backend.name)
        assert len(alba_backend.presets) >= 1, 'No preset found for ALBA backend {0}'.format(alba_backend.backend.name)
        assert len([default for default in alba_backend.presets if default['is_default'] is True]) == 1, 'Could not find default preset for backend {0}'.format(alba_backend.backend.name)
        assert alba_backend.backend.backend_type.code == 'alba', 'Backend type for ALBA backend is {0}'.format(alba_backend.backend.backend_type.code)
        assert alba_backend.backend.status == 'RUNNING', 'Status for ALBA backend is {0}'.format(alba_backend.backend.status)
        assert isinstance(alba_backend.metadata_information, dict) is True, 'ALBA backend {0} metadata information is not a dictionary'.format(alba_backend.backend.name)
        Toolbox.verify_required_params(actual_params=alba_backend.metadata_information,
                                       required_params={'nsm_partition_guids': (list, Toolbox.regex_guid)},
                                       exact_match=True)

        # Validate ABM and NSM services
        storagerouters = GeneralStorageRouter.get_storage_routers()
        storagerouters_with_db_role = [sr for sr in storagerouters if GeneralStorageRouter.has_roles(storagerouter=sr, roles='DB') is True and sr.node_type == 'MASTER']

        assert len(alba_backend.abm_services) == len(storagerouters_with_db_role), 'Not enough ABM services found'
        assert len(alba_backend.nsm_services) == len(storagerouters_with_db_role), 'Not enough NSM services found'

        # Validate ALBA backend ETCD structure
        alba_backend_key = '/ovs/alba/backends'
        assert EtcdConfiguration.exists(key=alba_backend_key, raw=True) is True, 'Etcd does not contain key {0}'.format(alba_backend_key)

        actual_etcd_keys = [key for key in EtcdConfiguration.list(alba_backend_key)]
        expected_etcd_keys = ['verification_schedule', 'global_gui_error_interval', alba_backend.guid]
        optional_etcd_keys = ['verification_factor']

        expected_keys_amount = 0
        for optional_key in optional_etcd_keys:
            if optional_key in actual_etcd_keys:
                expected_keys_amount += 1

        for expected_key in expected_etcd_keys:
            if not re.match(Toolbox.regex_guid, expected_key):
                expected_keys_amount += 1
            assert expected_key in actual_etcd_keys, 'Key {0} was not found in tree {1}'.format(expected_key, alba_backend_key)

        for actual_key in list(actual_etcd_keys):
            if re.match(Toolbox.regex_guid, actual_key):
                actual_etcd_keys.remove(actual_key)  # Remove all alba backend keys
        assert len(actual_etcd_keys) == expected_keys_amount, 'Another key was added to the {0} tree'.format(alba_backend_key)

        this_alba_backend_key = '{0}/{1}'.format(alba_backend_key, alba_backend.guid)
        actual_keys = [key for key in EtcdConfiguration.list(this_alba_backend_key)]
        expected_keys = ['maintenance']
        assert actual_keys == expected_keys, 'Actual keys: {0} - Expected keys: {1}'.format(actual_keys, expected_keys)

        maintenance_key = '{0}/maintenance'.format(this_alba_backend_key)
        actual_keys = [key for key in EtcdConfiguration.list(maintenance_key)]
        expected_keys = ['nr_of_agents', 'config']
        assert set(actual_keys) == set(expected_keys), 'Actual keys: {0} - Expected keys: {1}'.format(actual_keys, expected_keys)
        # @TODO: Add validation for config values

        # Validate ASD node ETCD structure
        alba_nodes = GeneralAlba.get_alba_nodes()
        assert len(alba_nodes) > 0, 'Could not find any ALBA nodes in the model'
        alba_node_key = '/ovs/alba/asdnodes'
        actual_keys = [key for key in EtcdConfiguration.list(alba_node_key)]
        assert len(alba_nodes) == len(actual_keys), 'Amount of ALBA nodes in model does not match amount of ALBA nodes in ETCD. In model: {0} - In Etcd: {1}'.format(len(alba_nodes), len(actual_keys))
        for alba_node in alba_nodes:
            assert alba_node.node_id in actual_keys, 'ALBA node with ID {0} not present in ETCD'.format(alba_node.node_id)

            actual_asdnode_keys = [key for key in EtcdConfiguration.list('{0}/{1}'.format(alba_node_key, alba_node.node_id))]
            expected_asdnode_keys = ['config']
            assert actual_asdnode_keys == expected_asdnode_keys, 'Actual keys: {0} - Expected keys: {1}'.format(actual_asdnode_keys, expected_asdnode_keys)

            actual_config_keys = [key for key in EtcdConfiguration.list('{0}/{1}/config'.format(alba_node_key, alba_node.node_id))]
            expected_config_keys = ['main', 'network']
            assert set(actual_config_keys) == set(expected_config_keys), 'Actual keys: {0} - Expected keys: {1}'.format(actual_config_keys, expected_config_keys)
            # @TODO: Add validation for main and network values

        # Validate Arakoon ETCD structure
        arakoon_abm_key = '/ovs/arakoon/{0}/config'.format(alba_backend.abm_services[0].service.name)
        arakoon_nsm_key = '/ovs/arakoon/{0}/config'.format(alba_backend.nsm_services[0].service.name)
        assert EtcdConfiguration.exists(key=arakoon_abm_key, raw=True) is True, 'Etcd key {0} does not exists'.format(arakoon_abm_key)
        assert EtcdConfiguration.exists(key=arakoon_nsm_key, raw=True) is True, 'Etcd key {0} does not exists'.format(arakoon_nsm_key)
        # @TODO: Add validation for config values

        # Validate maintenance agents
        actual_amount_agents = len([key for client in [alba_node.client.list_maintenance_services() for alba_node in alba_nodes] for key in client.iterkeys() if not key.startswith('_')])
        expected_amount_agents = EtcdConfiguration.get('/ovs/alba/backends/{0}/maintenance/nr_of_agents'.format(alba_backend.guid))
        assert actual_amount_agents == expected_amount_agents, 'Amount of maintenance agents is incorrect. Found {0} - Expected {1}'.format(actual_amount_agents, expected_amount_agents)

        # Validate arakoon services
        machine_ids = [sr.machine_id for sr in storagerouters_with_db_role]
        abm_service_name = alba_backend.abm_services[0].service.name
        nsm_service_name = alba_backend.nsm_services[0].service.name
        for storagerouter in storagerouters_with_db_role:
            root_client = SSHClient(endpoint=storagerouter,
                                    username='root')
            abm_arakoon_service_name = 'ovs-arakoon-{0}'.format(abm_service_name)
            nsm_arakoon_service_name = 'ovs-arakoon-{0}'.format(nsm_service_name)
            for service_name in [abm_arakoon_service_name, nsm_arakoon_service_name]:
                assert GeneralService.has_service(name=service_name,
                                                  client=root_client) is True, 'Service {0} not deployed on Storage Router {1}'.format(service_name, storagerouter.name)
                assert GeneralService.get_service_status(name=service_name,
                                                         client=root_client) is True, 'Service {0} not running on Storage Router {1}'.format(service_name, storagerouter.name)
                out, err, _ = General.execute_command('arakoon --who-master -config {0}'.format(GeneralArakoon.ETCD_CONFIG_PATH.format(abm_service_name)))
                assert out.strip() in machine_ids, 'Arakoon master is {0}, but should be 1 of "{1}"'.format(out.strip(), ', '.join(machine_ids))

    @staticmethod
    def validate_alba_backend_sanity_with_claimed_disks(alba_backend):
        """
        Validate an ALBA backend where disks have already been claimed
        :param alba_backend: ALBA backend
        :return: None
        """
        # Validate presets
        alba_backend.invalidate_dynamics('presets')
        preset_available = False
        for preset in alba_backend.presets:
            if 'policy_metadata' not in preset:
                raise ValueError('Preset information does not contain policy_metadata')
            for policy, policy_info in preset['policy_metadata'].iteritems():
                if 'is_available' not in policy_info:
                    raise ValueError('Policy information does not contain is_available')
                if policy_info['is_available'] is True:
                    preset_available = True
                    break
            if preset_available is True:
                break
        if preset_available is False:  # At least 1 preset must be available
            raise ValueError('No preset available for backend {0}'.format(alba_backend.backend.name))

        # Validate backend
        object_name = 'autotest-object'
        namespace_name = 'autotest-sanity-validation'
        GeneralAlba.execute_alba_cli_action(alba_backend, 'create-namespace', [namespace_name, 'default'], False)
        namespace_info = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend, name=namespace_name)
        assert len(namespace_info) == 1, 'Expected to find 1 namespace with name {0}'.format(namespace_name)

        GeneralAlba.upload_file(alba_backend=alba_backend, namespace_name=namespace_name, file_size=100, object_name=object_name)
        objects = GeneralAlba.list_objects_in_namespace(alba_backend=alba_backend, namespace_name=namespace_name)
        assert object_name in objects, 'Object with name {0} could not be found in namespace objects'.format(object_name)

        GeneralAlba.remove_alba_namespaces(alba_backend=alba_backend, namespaces=namespace_info)

    @staticmethod
    def validate_alba_backend_removal(alba_backend_info):
        """
        Validate whether the backend has been deleted properly
        alba_backend_info should be a dictionary containing:
            - guid
            - name
            - maintenance_service_names
        :param alba_backend_info: Information about the backend
        :return: None
        """
        Toolbox.verify_required_params(actual_params=alba_backend_info,
                                       required_params={'name': (str, None),
                                                        'guid': (str, Toolbox.regex_guid),
                                                        'maintenance_service_names': (list, None)},
                                       exact_match=True)

        alba_backend_guid = alba_backend_info['guid']
        alba_backend_name = alba_backend_info['name']
        backend = GeneralBackend.get_by_name(alba_backend_name)
        assert backend is None, 'Still found a backend in the model with name {0}'.format(alba_backend_name)

        # Validate services removed from model
        for service in GeneralService.get_services_by_name(ServiceType.SERVICE_TYPES.ALBA_MGR):
            assert service.name != '{0}-abm'.format(alba_backend_name), 'An AlbaManager service has been found with name {0}'.format(alba_backend_name)
        for service in GeneralService.get_services_by_name(ServiceType.SERVICE_TYPES.NS_MGR):
            assert service.name.startswith('{0}-nsm_'.format(alba_backend_name)) is False, 'An NamespaceManager service has been found with name {0}'.format(alba_backend_name)

        # Validate ALBA backend ETCD structure
        alba_backend_key = '/ovs/alba/backends'
        actual_etcd_keys = [key for key in EtcdConfiguration.list(alba_backend_key)]
        assert alba_backend_guid not in actual_etcd_keys, 'Etcd still contains an entry in {0} with guid {1}'.format(alba_backend_key, alba_backend_guid)

        # Validate Arakoon ETCD structure
        arakoon_keys = [key for key in EtcdConfiguration.list('/ovs/arakoon') if key.startswith(alba_backend_name)]
        assert len(arakoon_keys) == 0, 'Etcd still contains configurations for clusters: {0}'.format(', '.join(arakoon_keys))

        # Validate services
        for storagerouter in GeneralStorageRouter.get_storage_routers():
            root_client = SSHClient(endpoint=storagerouter,
                                    username='root')
            maintenance_services = alba_backend_info['maintenance_service_names']
            abm_arakoon_service_name = 'ovs-arakoon-{0}-abm'.format(alba_backend_name)
            nsm_arakoon_service_name = 'ovs-arakoon-{0}-nsm_0'.format(alba_backend_name)
            for service_name in [abm_arakoon_service_name, nsm_arakoon_service_name] + maintenance_services:
                assert GeneralService.has_service(name=service_name,
                                                  client=root_client) is False, 'Service {0} still deployed on Storage Router {1}'.format(service_name, storagerouter.name)

    @staticmethod
    def remove_alba_backend(alba_backend):
        """
        Remove an ALBA backend
        :param alba_backend: ALBA Backend
        :return: None
        """
        GeneralAlba.api.remove('alba/backends', alba_backend.guid)

        counter = GeneralAlba.ALBA_TIMER / GeneralAlba.ALBA_TIMER_STEP
        while counter > 0:
            try:
                GeneralAlba.get_alba_backend(alba_backend.guid)
            except ObjectNotFoundException:
                return
            counter -= 1
            time.sleep(GeneralAlba.ALBA_TIMER_STEP)

        if counter == 0:
            raise ValueError('Unable to remove backend {0}'.format(alba_backend.name))

    @staticmethod
    def upload_file(alba_backend, namespace_name, file_size, object_name=None):
        """
        Upload a file into ALBA
        :param alba_backend: ALBA backend
        :param namespace_name: Namespace to upload file into
        :param file_size: Size of file
        :param object_name: Name of the object in ALBA
        :return: None
        """
        if object_name is None:
            object_name = namespace_name
        contents = ''.join(random.choice(chr(random.randint(32, 126))) for _ in xrange(file_size))
        temp_file_name = tempfile.mktemp()
        with open(temp_file_name, 'wb') as temp_file:
            temp_file.write(contents)
            temp_file.flush()

        GeneralAlba.execute_alba_cli_action(alba_backend, 'upload-object', [namespace_name, temp_file_name, object_name], False)

    @staticmethod
    def list_alba_namespaces(alba_backend, **kwargs):
        """
        Retrieve all namespaces
        :param alba_backend: ALBA backend
        :return: Namespace information
        """
        nss = GeneralAlba.execute_alba_cli_action(alba_backend, 'list-namespaces')
        if len(nss) > 0:
            actual_keys = nss[0].keys()  # Only check 1st namespace for keys, assume rest is identical
            expected_keys = ['id', 'name', 'nsm_host_id', 'preset_name', 'state']
            assert set(actual_keys) == set(expected_keys), 'Expected keys did not match actual keys in namespace {0}'.format(nss[0])

        # Apply filter
        if kwargs.get('name') is not None:
            name = kwargs['name']
            if type(name) == Toolbox.compiled_regex_type:
                nss = [ns for ns in nss if re.match(name, ns['name'])]
            elif type(name) in (str, basestring, unicode):
                nss = [ns for ns in nss if ns['name'] == name]
            else:
                raise ValueError('Name should be a compiled regex or a string')
        return nss

    @staticmethod
    def list_objects_in_namespace(alba_backend, namespace_name):
        """
        List all objects from a namespace
        :param alba_backend: ALBA backend
        :param namespace_name: Name of the namespace
        :return: Objects in namespace
        """
        output = GeneralAlba.execute_alba_cli_action(alba_backend=alba_backend,
                                                     action='list-objects',
                                                     params=[namespace_name],
                                                     json_output=False)
        assert isinstance(output, str), 'List-objects output not as expected: {0}'.format(output)
        object_info = output.strip()
        # @TODO: Use --to-json option once implemented for list-objects (See http://jira.openvstorage.com/browse/OVS-4337)
        match = re.match('Found \d objects: (.*)', object_info)
        assert match is not None, 'List-objects returned different output then expected: {0}'.format(object_info)

        return json.loads(match.groups()[0].replace(';', ','))

    @staticmethod
    def remove_alba_namespaces(alba_backend, namespaces=None):
        """
        Remove ALBA namespaces
        :param alba_backend: ALBA backend
        :param namespaces: Name of namespaces to remove
        :return: None
        """
        ns_to_delete = namespaces
        if namespaces is None:
            ns_to_delete = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend)

        cmd_delete = "alba delete-namespace {0} ".format(GeneralAlba.get_abm_config(alba_backend))
        fd_namespaces = []
        for ns in ns_to_delete:
            namespace_name = str(ns['name'])
            if 'fd-' in namespace_name:
                fd_namespaces.append(ns)
                GeneralAlba.logger.info("Skipping vpool namespace: {0}".format(namespace_name))
                continue
            GeneralAlba.logger.info("WARNING: Deleting leftover namespace: {0}".format(str(ns)))
            print General.execute_command(cmd_delete + namespace_name)[0].replace('true', 'True')

        if namespaces is None:
            for ns in fd_namespaces:
                GeneralAlba.logger.info("WARNING: Deleting leftover vpool namespace: {0}".format(str(ns)))
                print General.execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')
            assert len(fd_namespaces) == 0, "Removing Alba namespaces should not be necessary!"

    @staticmethod
    def is_bucket_count_valid_with_policy(bucket_count, policies):
        """
        Verify bucket for policy
        :param bucket_count: Bucket information
        :param policies: Policies to verify
        :return: True if safe
        """
        # policy (k, m, c, x)
        # for both bucket_count and policy:
        # - k = nr of data fragments, should equal for both
        # - m = nr of parity fragments, should be equal for both

        # policy
        # - c = min nr of fragments to write
        # - x = max nr of fragments per storage node

        # bucket_count:
        # - c = nr of effectively written fragments, should be >= policy.c
        # - x = max nr of effectively written fragments on one specific node, should be<= policy.x

        # policies should all be present in bucket_count, removed policy via update could still be present during
        # maintenance rewrite cycle

        safe = False
        for policy in policies:
            policy = tuple(policy)
            for entry in bucket_count:
                bc_policy = entry[0]
                pol_k, pol_m, pol_c, pol_x = tuple(policy)
                bc_k, bc_m, bc_c, bc_x = tuple(bc_policy)
                safe = (pol_k == bc_k) and (pol_m == bc_m) and (bc_c >= pol_c) and (bc_x <= pol_c)
        return safe

    @staticmethod
    def filter_disks(disk_names, amount, disk_type):
        """
        Filter the available disks
        :param disk_names: Disks to filter
        :param amount: Amount to retrieve
        :param disk_type: Type of disk
        :return: Filtered disks
        """
        grid_ip = General.get_config().get('main', 'grid_ip')
        storagerouter = GeneralStorageRouter.get_storage_router_by_ip(ip=grid_ip)
        root_client = SSHClient(storagerouter, username='root')
        hdds, ssds = GeneralDisk.get_physical_disks(client=root_client)
        count = 0
        filtered_disks = list()

        if disk_type == 'SATA':
            list_to_check = hdds.values()
        elif disk_type == 'SSD':
            list_to_check = ssds.values()
        else:
            hdds.update(ssds)
            list_to_check = hdds.values()

        for disk_name in disk_names:
            for disk in list_to_check:
                if disk_name == disk['name']:
                    filtered_disks.append(disk['name'])
                    count += 1
            if count == amount:
                break

        return filtered_disks

    @staticmethod
    def initialise_disks(alba_backend, nr_of_disks, disk_type):
        """
        Initialize disks
        :param alba_backend: ALBA backend
        :param nr_of_disks: Amount of disks to initialize
        :param disk_type: Type of disks
        :return: None
        """
        # Assume no disks are claimed by a remote environment
        alba_backend.invalidate_dynamics(['storage_stack'])
        storage_stack = alba_backend.storage_stack

        initialised_disks = 0
        uninitialized_disk_names = []
        for disks in storage_stack.values():
            for disk_id, disk in disks.iteritems():
                if disk['status'] == 'initialized':
                    initialised_disks += 1
                elif disk['status'] == 'uninitialized':
                    uninitialized_disk_names.append(disk_id)
        nr_of_disks_to_init = nr_of_disks - initialised_disks
        if nr_of_disks_to_init <= 0:
            return True

        assert len(uninitialized_disk_names) >= nr_of_disks_to_init, "Not enough disks to initialize!"

        disks_to_init = GeneralAlba.filter_disks(uninitialized_disk_names, nr_of_disks_to_init, disk_type)
        assert len(disks_to_init) >= nr_of_disks_to_init, "Not enough disks to initialize!"

        grid_ip = General.get_config().get('main', 'grid_ip')
        alba_node = AlbaNodeList.get_albanode_by_ip(grid_ip)
        failures = AlbaNodeController.initialize_disks(alba_node.guid, dict((disk_id, 1) for disk_id in disks_to_init))
        assert not failures, 'Alba disk initialization failed for (some) disks: {0}'.format(failures)

    @staticmethod
    def claim_asds(alba_backend, nr_of_asds, disk_type=''):
        """
        Claim disks
        :param alba_backend: ALBA Backend
        :param nr_of_asds: Amount of disks to claim
        :param disk_type: Type of disks
        :return: None
        """
        def _wait_for_asd_count_with_status(_alba_backend, _nr_of_asds, status):
            grid_ip = General.get_config().get('main', 'grid_ip')
            alba_node = AlbaNodeList.get_albanode_by_ip(grid_ip)
            counter = GeneralAlba.ALBA_TIMER / GeneralAlba.ALBA_TIMER_STEP
            asds_with_status = {}
            while counter > 0:
                GeneralAlba.logger.info('counter: {0}'.format(counter))
                _alba_backend.invalidate_dynamics(['storage_stack'])
                if alba_node.node_id in _alba_backend.storage_stack:
                    for _disk in _alba_backend.storage_stack[alba_node.node_id].values():
                        for _asd_id, _asd in _disk['asds'].iteritems():
                            if _asd['status'] == status:
                                asds_with_status[_asd_id] = _disk.get('guid')
                GeneralAlba.logger.info('looking for {0} asds with status {1}: {2}'.format(_nr_of_asds, status, asds_with_status))
                if len(asds_with_status) >= _nr_of_asds:
                    break
                counter -= 1
                time.sleep(GeneralAlba.ALBA_TIMER_STEP)
            assert len(asds_with_status) >= _nr_of_asds,\
                "Unable to find {0} asds, only found {1} asds with status: {2}.\n".format(_nr_of_asds, len(asds_with_status), status)
            return asds_with_status

        claimed_asds = []
        alba_backend.invalidate_dynamics(['storage_stack'])
        storage_stack = alba_backend.storage_stack
        for disks in storage_stack.values():
            for disk in disks.values():
                for asd_id, asd in disk['asds'].iteritems():
                    if asd['status'] == 'claimed':
                        claimed_asds.append(asd_id)
        nr_asds_to_claim = nr_of_asds - len(claimed_asds)
        if nr_asds_to_claim <= 0:
            return True

        # @TODO: Initialize disks should be parameterized to be parallel or sequential with parallel being the default
        GeneralAlba.initialise_disks(alba_backend, nr_asds_to_claim, disk_type)

        claimable_asds = _wait_for_asd_count_with_status(alba_backend, nr_asds_to_claim, 'available')

        GeneralAlba.logger.info('osds: {0}'.format(claimable_asds))
        AlbaController.add_units(alba_backend.guid, claimable_asds)

        _wait_for_asd_count_with_status(alba_backend, nr_of_asds, 'claimed')

    @staticmethod
    def unclaim_disks(alba_backend):
        """
        Un-claim disks
        :param alba_backend: ALBA backend
        :return: None
        """
        # @TODO: Allow the unclaim of disks go sequentially or parallel (parallel should be default)
        alba_backend.invalidate_dynamics(['storage_stack'])
        for disks in alba_backend.storage_stack.values():
            for disk_id, disk in disks.iteritems():
                asd_node = GeneralAlba.get_node_by_id(disk['node_id'])
                for asd_id in disk['asds'].keys():
                    data = {'asd_id': asd_id,
                            'safety': {'good': 0, 'critical': 0, 'lost': 0}}
                    GeneralAlba.api.execute_post_action('alba/nodes', asd_node.guid, 'reset_asd', data, wait=True)
                data = {'disk': disk_id}
                GeneralAlba.api.execute_post_action('alba/nodes', asd_node.guid, 'remove_disk', data, wait=True)

    @staticmethod
    def checkup_maintenance_agents():
        """
        Perform a maintenance agent checkup
        :return: None
        """
        AlbaNodeController.checkup_maintenance_agents()

    @staticmethod
    def get_maintenance_services_for_alba_backend(alba_backend):
        """
        Retrieve all maintenance services for an ALBA backend
        IMPORTANT: Currently we deploy a maintenance service on ANY node where the SDM package has been installed,
                   regardless whether ASDs have been initialized or claimed by the backend
        :param alba_backend: ALBA backend
        :return: List of maintenance service names
        """
        service_names = []
        for asd_node in GeneralAlba.get_alba_nodes():
            for entry in asd_node.client.list_maintenance_services():
                if entry.startswith('alba-maintenance_{0}'.format(alba_backend.backend.name)):
                    service_names.append(entry)
        assert len(service_names) > 0, 'No maintenance services found for ALBA backend {0}'.format(alba_backend.backend.name)
        return service_names
