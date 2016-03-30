# Copyright 2016 iNuron NV
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ALBA testsuite
"""

import time
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.logHandler import LogHandler
from ovs.dal.hybrids.albanode import AlbaNode
from ovs.dal.hybrids.albaasd import AlbaASD
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.hybrids.backend import Backend
from ovs.dal.hybrids.albaasd import AlbaASD
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.hybrids.albanode import AlbaNode
from ovs.dal.hybrids.backend import Backend
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.lib.albascheduledtask import AlbaScheduledTaskController


class TestALBA(object):
    """
    ALBA testsuite
    """
    logger = LogHandler.get('backend', name='alba')
    logger.logger.propagate = False

    autotest_config = General.get_config()
    backend_name = autotest_config.get('backend', 'name')

    ####################
    # HELPER FUNCTIONS #
    ####################

    @staticmethod
    def verify_policies_for_preset(preset_name, policies, compression, encryption):
        """
        Verify the policies of a preset
        :param preset_name: Name of preset
        :param policies: Policies to verify
        :param compression: Compression for preset
        :param encryption: Encryption for preset
        :return: True is valid
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        valid = False
        for preset in backend.alba_backend.presets:
            if preset['name'] == preset_name:
                assert preset['compression'] == compression,\
                    "Alba compression {0} does not match configured {1} type".format(preset['compression'],
                                                                                     compression)
                assert preset['fragment_encryption'][0] == encryption, \
                    "Alba encryption {0} does not match configured {1} type".format(preset['fragment_encryption'],
                                                                                    encryption)
                for policy in policies:
                    valid = False
                    for alba_policy in preset['policies']:
                        print 'Matching: {0} with {1}'.format(tuple(policy), alba_policy)
                        if tuple(policy) == alba_policy:
                            valid = True
                            continue
        return valid

    @staticmethod
    def is_preset_present(name):
        """
        Verify if a preset is present
        :param name: Name of the preset
        :return: True if present
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        for preset in backend.alba_backend.presets:
            if name == preset['name']:
                return True
        return False

    @staticmethod
    def add_validate_remove_preset(name, compression, encryption, policies, remove_when_finished=True):
        """
        Add a preset, validate the preset and remove it
        :param name: Name of the preset
        :param compression: Compression used by the preset
        :param encryption: Encryption used by the preset
        :param policies: Policies used by the preset
        :param remove_when_finished: Remove after validation
        :return: None
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        status, message = GeneralAlba.add_preset(backend.alba_backend, name, policies, compression, encryption)
        assert status, "Add preset failed with: {0}".format(message)
        assert TestALBA.is_preset_present(name), "Preset with name {0} is not present".format(name)
        TestALBA.verify_policies_for_preset(name, policies, compression, encryption)
        if remove_when_finished:
            status, message = GeneralAlba.remove_preset(backend.alba_backend, name, )
            assert status, "Remove preset failed with: {0}".format(message)
            assert not TestALBA.is_preset_present(name), "Preset with name {0} is not present".format(name)

    #########
    # TESTS #
    #########

    @staticmethod
    def be_0001_add_and_remove_backend_test():
        """
        Create an ALBA backend and verify its status
        Validate services, etcd, arakoon without claiming disks
        Claim some disks and validate whether backend can be used for storing objects in namespaces
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is not None:
            raise ValueError('A backend has already been deployed, cannot execute test')

        alba_backend = GeneralAlba.add_alba_backend(TestALBA.backend_name)
        GeneralAlba.validate_alba_backend_sanity_without_claimed_disks(alba_backend=alba_backend)

        GeneralAlba.claim_disks(alba_backend, 3, 'SATA')
        GeneralAlba.validate_alba_backend_sanity_with_claimed_disks(alba_backend=alba_backend)

        guid = alba_backend.guid
        name = TestALBA.backend_name
        service_names = GeneralAlba.get_maintenance_services_for_alba_backend(alba_backend=alba_backend)

        GeneralAlba.unclaim_disks(alba_backend)
        GeneralAlba.remove_alba_backend(alba_backend)
        GeneralAlba.validate_alba_backend_removal(alba_backend_info={'name': name,
                                                                     'guid': guid,
                                                                     'maintenance_service_names': service_names})

    @staticmethod
    def be_0002_add_remove_preset_no_compression_no_encryption_test():
        """
        Add and remove a preset without compression and encryption
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            GeneralAlba.add_alba_backend(TestALBA.backend_name)

        compression = 'none'
        encryption = 'none'
        name = 'be_preset_02'
        policies = [[1, 1, 1, 2]]
        TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

    @staticmethod
    def be_0003_add_remove_preset_compression_no_encryption_test():
        """
        Add and remove a preset with compression and without encryption
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            GeneralAlba.add_alba_backend(TestALBA.backend_name)

        name = 'be_preset_03'
        compression = 'bz2'
        encryption = 'none'
        policies = [[1, 1, 1, 2]]
        TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

    @staticmethod
    def be_0004_validate_preset_with_replication_copies_test():
        """
        Validate a preset
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            GeneralAlba.add_alba_backend(TestALBA.backend_name)

        compression = 'none'
        encryption = 'none'
        name_prefix = 'be_preset_04'
        for nr in xrange(6):
            name = name_prefix + str(nr)
            policies = [[1, nr, 1, 1 + nr]]
            TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

    @staticmethod
    def be_0005_add_remove_preset_no_compression_encryption_test():
        """
        Add and remove a preset without compression and with encryption
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            GeneralAlba.add_alba_backend(TestALBA.backend_name)

        name = 'be_preset_05'
        compression = 'none'
        encryption = 'aes-cbc-256'
        policies = [[1, 1, 1, 2]]
        TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

    @staticmethod
    def be_0006_add_remove_preset_compression_encryption_test():
        """
        Add and remove a preset with compression and encryption
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            GeneralAlba.add_alba_backend(TestALBA.backend_name)

        name = 'be_preset_06a'
        compression = 'bz2'
        encryption = 'aes-cbc-256'
        policies = [[1, 1, 1, 2]]
        TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

        name = 'be_preset_06b'
        compression = 'snappy'
        TestALBA.add_validate_remove_preset(name, compression, encryption, policies)

    @staticmethod
    def be_0007_add_update_remove_preset_test():
        """
        Add, update and remove a preset
        Validation for OVS-3187 - edit policy of preset
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            alba_backend = GeneralAlba.add_alba_backend(TestALBA.backend_name)
        else:
            alba_backend = backend.alba_backend

        GeneralAlba.claim_disks(alba_backend=alba_backend, nr_of_disks=3, disk_type='SATA')

        timeout = 300
        preset_name = 'be_preset_0007'
        namespace_name = 'be_0007_ns'
        compression = 'none'
        encryption = 'aes-cbc-256'
        org_policy = [[1, 1, 1, 2]]
        new_policy = [[2, 2, 3, 3]]

        TestALBA.add_validate_remove_preset(preset_name, compression, encryption, org_policy, remove_when_finished=False)
        result = GeneralAlba.list_alba_namespaces(alba_backend=alba_backend,
                                                  name=namespace_name)

        for namespace in result:
            GeneralAlba.execute_alba_cli_action(alba_backend, 'delete-namespace', [namespace['name']], False)
        GeneralAlba.execute_alba_cli_action(alba_backend, 'create-namespace', [namespace_name, preset_name], False)

        GeneralAlba.upload_file(alba_backend=alba_backend, namespace_name=namespace_name, file_size=1024 * 1024)

        result = GeneralAlba.execute_alba_cli_action(alba_backend, 'show-namespace', [namespace_name])['bucket_count']
        assert len(result) == 1, "Only one policy should be present, found: {0}".format(result)

        # update and verify policies for preset
        GeneralAlba.update_preset(alba_backend, preset_name, new_policy)

        result = GeneralAlba.execute_alba_cli_action(alba_backend, 'show-namespace', [namespace_name])['bucket_count']
        assert len(result) == 1, "Expected 1 policy, but got: {0}".format(result)

        object_has_new_policy = False
        for _ in xrange(timeout):
            if GeneralAlba.is_bucket_count_valid_with_policy(result, new_policy):
                object_has_new_policy = True
                break
            time.sleep(1)
            result = GeneralAlba.execute_alba_cli_action(alba_backend, 'show-namespace', [namespace_name])['bucket_count']

        assert object_has_new_policy is True, "Object was not rewritten within {0} seconds: {1}".format(timeout, result)

        # cleanup
        GeneralAlba.execute_alba_cli_action(alba_backend, 'delete-namespace', [namespace_name], False)
        GeneralAlba.remove_preset(alba_backend, preset_name)

    @staticmethod
    def ovs_3490_add_remove_preset_test():
        """
        Adds and removes a preset with encryption to an existing alba backend
        """
        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            backend = GeneralAlba.add_alba_backend(TestALBA.backend_name).backend

        name = 'ovs-3490'
        policies = [[1, 1, 1, 2]]
        compression = 'none'
        encryption = 'aes-cbc-256'
        status, message = GeneralAlba.add_preset(backend.alba_backend, name, policies, compression, encryption)
        assert status, "Add preset failed with: {0}".format(message)
        TestALBA.verify_policies_for_preset(name, policies, compression, encryption)
        status, message = GeneralAlba.remove_preset(backend.alba_backend, name)
        assert status, "Remove preset failed with: {0}".format(message)
        assert not TestALBA.is_preset_present(name), "Preset with name {0} is not present".format(name)

    @staticmethod
    def ovs_3769_validation_test():
        """
        Create an albanode with an asd statistics part set to empty dictionary
        Assert code does not raise
        """
        an = AlbaNode()
        an.password = 'rooter'
        an.node_id = 'ovs3769an'
        an.port = 1234
        an.ip = '127.0.0.1'
        an.username = 'root'
        an.save()

        bet = GeneralBackend.get_backendtype_by_code('alba')

        be = Backend()
        be.backend_type = bet
        be.name = 'ovs3769be'
        be.save()

        abe = AlbaBackend()
        abe.backend = be
        abe.save()

        asd = AlbaASD()
        asd.alba_backend = abe
        asd.asd_id = 'ovs3769asd'
        asd.alba_node = an
        asd.save()

        try:
            abe.statistics
        except KeyError, ex:
            TestALBA.logger.error('Regression OVS-3769 - asd statistics raises a KeyError: {0}'.format(str(ex)))

        assert asd.statistics == dict(), "asd statistics should return an empty dict, go {0}".format(asd.statistics)
        asd.delete()
        an.delete()
        abe.delete()
        be.delete()

    @staticmethod
    def ovs_3188_verify_namespace_test():
        """
        Verify namespaces
        """
        nr_of_disks_to_create = 5
        namespace_prefix = 'ovs_3188-'
        compression = 'none'
        encryption = 'none'
        preset_name = 'be_preset_02'
        policies = [[1, 1, 1, 2]]

        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            backend = GeneralAlba.add_alba_backend(TestALBA.backend_name).backend
        GeneralAlba.add_preset(backend.alba_backend, preset_name, policies, compression, encryption)

        for x in range(nr_of_disks_to_create):
            namespace_name = namespace_prefix + str(x)
            GeneralAlba.execute_alba_cli_action(backend.alba_backend, 'create-namespace', [namespace_name, preset_name], False)
            GeneralAlba.upload_file(backend.alba_backend, namespace_name, 1024 * 1024 * 1)

        AlbaScheduledTaskController.verify_namespaces()

        GeneralAlba.remove_alba_namespaces(backend.alba_backend)
        GeneralAlba.remove_preset(backend.alba_backend, preset_name)

    @staticmethod
    def ovs_3977_maintenance_agent_test():
        """
        Test maintenance agent processes
        """
        def _get_agent_distribution(agent_name):
            result = {}
            total = 0
            for ip in alba_node_ips:
                count = General.execute_command_on_node(ip, 'ls /etc/init/ovs-alba-maintenance_{0}-* | wc -l'.format(agent_name))
                if count:
                    count = int(count)
                else:
                    count = 0
                total += count
                result[ip] = count
            result['total'] = total

            print 'Maintenance agent distribution: {0}'.format(result)
            for ip in alba_node_ips:
                assert (result[ip] == total / len(alba_node_ips) or result[ip] == (total / len(alba_node_ips)) + 1),\
                    "Agents not equally distributed!"

            return result

        backend = GeneralBackend.get_by_name(TestALBA.backend_name)
        if backend is None:
            backend = GeneralAlba.add_alba_backend(TestALBA.backend_name).backend
        name = backend.alba_backend.name

        alba_node_ips = [node.ip for node in GeneralAlba.get_alba_nodes()]

        etcd_key = '/ovs/alba/backends/{0}/maintenance/nr_of_agents'.format(backend.alba_backend.guid)
        nr_of_agents = EtcdConfiguration.get(etcd_key)
        print '1. - nr of agents: {0}'.format(nr_of_agents)

        actual_nr_of_agents = _get_agent_distribution(name)['total']
        assert nr_of_agents == actual_nr_of_agents, \
            'Actual {0} and requested {1} nr of agents does not match'.format(nr_of_agents, actual_nr_of_agents)

        # set nr to zero
        EtcdConfiguration.set(etcd_key, 0)
        GeneralAlba.checkup_maintenance_agents()
        assert _get_agent_distribution(name)['total'] == 0, \
            'Actual {0} and requested {1} nr of agents does not match'.format(nr_of_agents, actual_nr_of_agents)
        print '2. - nr of agents: {0}'.format(nr_of_agents)

        # set nr to 10
        EtcdConfiguration.set(etcd_key, 10)
        GeneralAlba.checkup_maintenance_agents()
        assert _get_agent_distribution(name)['total'] == 10, \
            'Actual {0} and requested {1} nr of agents does not match'.format(nr_of_agents, actual_nr_of_agents)
        print '3. - nr of agents: {0}'.format(nr_of_agents)
