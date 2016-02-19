# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A general class dedicated to ALBA backend logic
"""

import json
import time
import random
import tempfile
from ci.tests.general.connection import Connection
from ci.tests.general.general import General
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_disk import GeneralDisk
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.logHandler import LogHandler
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.extensions.generic.sshclient import SSHClient
from ovs.lib.albacontroller import AlbaController
from ovs.lib.albanodecontroller import AlbaNodeController


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
    def get_abm_config(backend_name):
        """
        Retrieve the configuration string to pass to the ALBA CLI
        :param backend_name: Name of the backend
        :return: Configuration string
        """
        return '--config etcd://127.0.0.1:2379/ovs/arakoon/{0}-abm/config'.format(backend_name)

    @staticmethod
    def add_alba_backend(name=None):
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
        backend_type = autotest_config.get('backend', 'type')
        nr_of_disks_to_claim = autotest_config.getint('backend', 'nr_of_disks_to_claim')
        type_of_disks_to_claim = autotest_config.get('backend', 'type_of_disks_to_claim')
        assert name, "Please fill out a valid backend name in autotest.cfg file"
        assert backend_type in GeneralBackend.get_valid_backendtypes(), "Please fill out a valid backend type in autotest.cfg file"

        my_sr = GeneralStorageRouter.get_local_storagerouter()
        GeneralDisk.add_db_role(my_sr)
        GeneralDisk.add_read_write_scrub_roles(my_sr)
        backend = GeneralBackend.get_backend_by_name_and_type(name, backend_type)
        if not backend:
            backend_guid = GeneralAlba.model_alba_backend(name)
            backend = GeneralBackend.get_backend(backend_guid)
        GeneralAlba.claim_disks(backend['alba_backend_guid'], nr_of_disks_to_claim, type_of_disks_to_claim)

    @staticmethod
    def unclaim_disks_and_remove_alba_backend():
        """
        Removes an ALBA backend
        :return: None
        """
        autotest_config = General.get_config()
        backend_name = autotest_config.get('backend', 'name')
        backend_type = autotest_config.get('backend', 'type')
        assert backend_name, "Please fill out a valid backend name in autotest.cfg file"
        assert backend_type in GeneralBackend.get_valid_backendtypes(), "Please fill out a valid backend type in autotest.cfg file"

        be = GeneralBackend.get_backend_by_name_and_type(backend_name, backend_type)
        if be:
            alba_backend = GeneralAlba.get_alba_backend(be['alba_backend_guid'])
            GeneralAlba.unclaim_disks(alba_backend)
            GeneralAlba.remove_alba_backend(be['alba_backend_guid'])

    @staticmethod
    def execute_alba_cli_action(backend_name, action, params=None, json_output=True):
        """
        Execute an ALBA CLI command
        :param backend_name: Name of the ALBA backend
        :param action: Action to execute
        :param params: Parameters to pass to the action
        :param json_output: Return JSON output
        :return: Output of the action
        """
        config = GeneralAlba.get_abm_config(backend_name)
        cmd = ['alba', action, config]
        if json_output:
            cmd.append('--to-json')
        if params is None:
            params = []
        cmd.extend(params)

        output = ''
        try:
            output = General.execute_command(' '.join(cmd))
            if json_output is True:
                return json.loads(output[0])['result']
            return output
        except (ValueError, RuntimeError):
            print "Command {0} failed:\nOutput: {1}".format(cmd, output)
            raise

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
    def is_alba_backend_running(backend_guid, trigger=False):
        """
        Verify the ALBA backend status
        :param backend_guid: ALBA backend guid
        :param trigger:
        :return:
        """
        timeout = GeneralAlba.ALBA_TIMER
        wait = GeneralAlba.ALBA_TIMER_STEP
        is_running = False
        while timeout > 0 and not is_running:
            backend = GeneralBackend.get_backend(backend_guid)
            if backend:
                if backend['status'] in ['RUNNING']:
                    is_running = True
                    GeneralAlba.logger.info('Backend in status running after {0} seconds'.format((GeneralAlba.ALBA_TIMER - timeout) * wait))
                    break
                elif trigger:
                    GeneralAlba.logger.info('Trigger backend installation')
                    trigger = False
                    GeneralAlba.api.add('alba/backends', {'backend_guid': backend_guid})
            time.sleep(wait)
            timeout -= wait
        return is_running

    @staticmethod
    def model_alba_backend(name):
        """
        Put an ALBA backend in the model
        :param name: Name of the backend
        :return: Guid of the backend
        """
        if not GeneralBackend.is_backend_present(name, 'alba'):
            backend_guid = GeneralBackend.add_backend(name, 'alba')
            assert (GeneralAlba.is_alba_backend_running(backend_guid, trigger=True)), 'Backend {0} not in status RUNNING'.format(name)
        else:
            backend = GeneralBackend.get_backend_by_name_and_type(name, 'alba')
            backend_guid = backend['guid']

        out, err = General.execute_command('etcdctl ls /ovs/alba/asdnodes')
        if err == '' and len(out):
            AlbaNodeController.model_local_albanode()

        return backend_guid

    @staticmethod
    def remove_alba_backend(guid):
        """
        Remove an ALBA backend
        :param guid: Guid of the backend to remove
        :return: None
        """
        name = GeneralAlba.api.fetch('alba/backends', guid)['name']
        GeneralAlba.api.remove('alba/backends', guid)

        counter = GeneralAlba.ALBA_TIMER / GeneralAlba.ALBA_TIMER_STEP
        while counter >= 0:
            if not GeneralAlba.api.get_component_by_name('backends', name):
                break
            counter -= 1
            time.sleep(GeneralAlba.ALBA_TIMER_STEP)

        assert (GeneralAlba.api.get_component_by_name('backends', name) is None), "Unable to remove backend {0}".format(name)

    @staticmethod
    def get_node_by_id(node_id):
        """
        Retrieve ASD node by ID
        :param node_id: ID of the ASD node
        :return: ASD node information
        """
        nodes = GeneralAlba.api.list('alba/nodes')
        for node_guid in nodes:
            node = GeneralAlba.api.fetch('alba/nodes', node_guid)
            if node['node_id'] == node_id:
                return node_guid

    @staticmethod
    def upload_file(backend_name, namespace, file_size):
        """
        Upload a file into ALBA
        :param backend_name: Name of the ALBA backend
        :param namespace: Namespace to upload file into
        :param file_size: Size of file
        :return: None
        """
        contents = ''.join(random.choice(chr(random.randint(32, 126))) for _ in xrange(file_size))
        temp_file_name = tempfile.mktemp()
        with open(temp_file_name, 'wb') as temp_file:
            temp_file.write(contents)
            temp_file.flush()

        GeneralAlba.execute_alba_cli_action(backend_name, 'upload', [namespace, temp_file_name, temp_file_name], False)

    @staticmethod
    def remove_alba_namespaces(name=""):
        """
        Remove ALBA namespaces
        :param name: Name of the ALBA backend
        :return: None
        """
        if not GeneralBackend.is_backend_present(name, 'alba'):
            return

        cmd_delete = "alba delete-namespace {0} ".format(GeneralAlba.get_abm_config(name))
        nss = GeneralAlba.execute_alba_cli_action(name, 'list-namespaces')
        GeneralAlba.logger.info("Namespaces present: {0}".format(str(nss)))
        fd_namespaces = list()
        for ns in nss:
            if 'fd-' in ns['name']:
                fd_namespaces.append(ns)
                GeneralAlba.logger.info("Skipping vpool namespace: {0}".format(ns['name']))
                continue
            GeneralAlba.logger.info("WARNING: Deleting leftover namespace: {0}".format(str(ns)))
            print General.execute_command(cmd_delete + str(ns['name']))[0].replace('true', 'True')

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
    def filter_disks(available_disks, amount, disk_type):
        """
        Filter the available disks
        :param available_disks: Disks to filter
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

        for disk_name in available_disks:
            for disk in list_to_check:
                if disk_name == disk['name']:
                    filtered_disks.append(disk['name'])
                    count += 1
            if count == amount:
                break

        return filtered_disks

    @staticmethod
    def initialise_disks(alba_backend_guid, nr_of_disks, disk_type):
        """
        Initialize disks
        :param alba_backend_guid: Guid of the ALBA backend
        :param nr_of_disks: Amount of disks to initialize
        :param disk_type: Type of disks
        :return: None
        """
        # Assume no disks are claimed by a remote environment
        alba_backend = GeneralAlba.get_alba_backend(alba_backend_guid)
        all_disks = alba_backend.all_disks

        initialised_disks = [disk['name'] for disk in all_disks if disk['status'] == 'available']
        nr_of_disks_to_init = nr_of_disks - len(initialised_disks)
        if nr_of_disks_to_init <= 0:
            return True

        uninitialized_disks = [disk['name'] for disk in all_disks if disk['status'] == 'uninitialized']
        assert len(uninitialized_disks) >= nr_of_disks_to_init, "Not enough disks to initialize!"

        disks_to_init = GeneralAlba.filter_disks(uninitialized_disks, nr_of_disks_to_init, disk_type)
        assert len(disks_to_init) >= nr_of_disks_to_init, "Not enough disks to initialize!"

        grid_ip = General.get_config().get('main', 'grid_ip')
        alba_node = AlbaNodeList.get_albanode_by_ip(grid_ip)
        failures = AlbaNodeController.initialize_disks(alba_node.guid, disks_to_init)
        assert not failures, 'Alba disk initialization failed for (some) disks: {0}'.format(failures)

    @staticmethod
    def claim_disks(alba_backend_guid, nr_of_disks, disk_type=''):
        """
        Claim disks
        :param alba_backend_guid: Guid of the ALBA backend
        :param nr_of_disks: Amount of disks to claim
        :param disk_type: Type of disks
        :return: None
        """
        def _wait_for_disk_count_with_status(_alba_backend, _nr_of_disks, status):
            counter = GeneralAlba.ALBA_TIMER / GeneralAlba.ALBA_TIMER_STEP
            disks_with_status = []
            while counter > 0:
                GeneralAlba.logger.info('counter: {0}'.format(counter))
                _alba_backend.invalidate_dynamics(['all_disks'])
                disks_with_status = [d['name'] for d in _alba_backend.all_disks if 'status' in d and d['status'] == status and 'asd_id' in d]
                GeneralAlba.logger.info('looking for {0} disks with status {1}: {2}'.format(_nr_of_disks, status, disks_with_status))
                if len(disks_with_status) >= _nr_of_disks:
                    break
                counter -= 1
                time.sleep(GeneralAlba.ALBA_TIMER_STEP)
            assert len(disks_with_status) >= _nr_of_disks,\
                "Unable to find {0} disks, only found {1} disks with status: {2}.\n".format(_nr_of_disks, len(disks_with_status), status)
            return disks_with_status

        alba_backend = GeneralAlba.get_alba_backend(alba_backend_guid)
        all_disks = alba_backend.all_disks

        claimed_disks = [disk['name'] for disk in all_disks if 'status' in disk and disk['status'] == 'claimed' and 'name' in disk]
        nr_disks_to_claim = nr_of_disks - len(claimed_disks)
        if nr_disks_to_claim <= 0:
            return True

        GeneralAlba.initialise_disks(alba_backend_guid, nr_disks_to_claim, disk_type)

        claimable_disks = _wait_for_disk_count_with_status(alba_backend, nr_disks_to_claim, 'available')

        disks_to_claim = GeneralAlba.filter_disks(claimable_disks, nr_disks_to_claim, disk_type)
        assert len(disks_to_claim) >= nr_disks_to_claim,\
            "Unable to claim {0} disks, only found {1} disks.\n".format(nr_of_disks, len(disks_to_claim))

        alba_backend.invalidate_dynamics(['all_disks'])
        all_disks = alba_backend.all_disks
        osds = dict()

        grid_ip = General.get_config().get('main', 'grid_ip')
        alba_node = AlbaNodeList.get_albanode_by_ip(grid_ip)
        for name in disks_to_claim:
            for disk in all_disks:
                if name in disk['name'] and 'asd_id' in disk:
                    osds[disk['asd_id']] = alba_node.guid

        GeneralAlba.logger.info('osds: {0}'.format(osds))
        AlbaController.add_units(alba_backend_guid, osds)

        _wait_for_disk_count_with_status(alba_backend, nr_of_disks, 'claimed')

    @staticmethod
    def unclaim_disks(alba_backend):
        """
        Un-claim disks
        :param alba_backend: ALBA backend
        :return: None
        """
        alba_backend.invalidate_dynamics(['all_disks'])
        for disk in alba_backend.all_disks:
            if disk['status'] in ['available', 'claimed']:
                node_guid = GeneralAlba.get_node_by_id(disk['node_id'])
                data = {'alba_backend_guid': alba_backend.guid,
                        'disk': disk['name'],
                        'safety': {'good': 0, 'critical': 0, 'lost': 0}}
                GeneralAlba.api.execute_post_action('alba/nodes', node_guid, 'remove_disk', data, wait=True)
