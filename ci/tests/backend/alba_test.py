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
ALBA testsuite
"""

import time
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.logHandler import LogHandler
from ovs.dal.hybrids.albaosd import AlbaOSD
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.hybrids.albanode import AlbaNode
from ovs.dal.hybrids.albadisk import AlbaDisk
from ovs.dal.hybrids.backend import Backend
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient
from ovs.lib.albascheduledtask import AlbaScheduledTaskController



class TestALBA(object):
    """
    ALBA testsuite
    """

    backend_name = General.get_config().get('backend', 'name')
    logger = LogHandler.get('backend', name='alba')

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
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        valid = False
        for preset in alba_backend.presets:
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
                        TestALBA.logger.info('Matching: {0} with {1}'.format(tuple(policy), alba_policy))
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
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        for preset in alba_backend.presets:
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
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        status, message = GeneralAlba.add_preset(alba_backend, name, policies, compression, encryption)
        assert status, "Add preset failed with: {0}".format(message)
        assert TestALBA.is_preset_present(name), "Preset with name {0} is not present".format(name)
        TestALBA.verify_policies_for_preset(name, policies, compression, encryption)
        if remove_when_finished:
            status, message = GeneralAlba.remove_preset(alba_backend, name)
            assert status, "Remove preset failed with: {0}".format(message)
            assert not TestALBA.is_preset_present(name), "Preset with name {0} is not present".format(name)

    #########
    # TESTS #
    #########

    @staticmethod
    def be_0001_add_and_remove_backend_test():
        """
        Create an ALBA backend and verify its status
        Validate services, configuration, arakoon without claiming disks
        Claim some disks and validate whether backend can be used for storing objects in namespaces
        """
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)

        GeneralAlba.validate_alba_backend_sanity_without_claimed_disks(alba_backend=alba_backend)

        GeneralAlba.claim_asds(alba_backend, 3, 'SATA')
        GeneralAlba.validate_alba_backend_sanity_with_claimed_disks(alba_backend=alba_backend)

        guid = alba_backend.guid
        service_names = GeneralAlba.get_maintenance_services_for_alba_backend(alba_backend=alba_backend)

        GeneralAlba.unclaim_disks(alba_backend)
        GeneralAlba.remove_alba_backend(alba_backend)
        GeneralAlba.validate_alba_backend_removal(alba_backend_info={'name': TestALBA.backend_name,
                                                                     'guid': guid,
                                                                     'maintenance_service_names': service_names})
        GeneralAlba.add_alba_backend(TestALBA.backend_name)

    @staticmethod
    def be_0002_add_remove_preset_no_compression_no_encryption_test():
        """
        Add and remove a preset without compression and encryption
        """

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
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        GeneralAlba.claim_asds(alba_backend=alba_backend, nr_of_asds=3, disk_type='SATA')

        timeout = 300
        preset_name = 'be_preset_0007'
        namespace_name = 'be_0007_ns'
        compression = 'none'
        encryption = 'aes-cbc-256'
        org_policy = [[1, 1, 1, 2]]
        new_policy = [[2, 2, 3, 3]]

        TestALBA.add_validate_remove_preset(preset_name, compression, encryption, org_policy,
                                            remove_when_finished=False)
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
            result = GeneralAlba.execute_alba_cli_action(alba_backend, 'show-namespace',
                                                         [namespace_name])['bucket_count']

        assert object_has_new_policy is True, "Object was not rewritten within {0} seconds: {1}".format(timeout, result)

        # cleanup
        GeneralAlba.execute_alba_cli_action(alba_backend, 'delete-namespace', [namespace_name], False)
        GeneralAlba.remove_preset(alba_backend, preset_name)

    @staticmethod
    def ovs_3490_add_remove_preset_test():
        """
        Adds and removes a preset with encryption to an existing alba backend
        """
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)

        name = 'ovs-3490'
        policies = [[1, 1, 1, 2]]
        compression = 'none'
        encryption = 'aes-cbc-256'
        status, message = GeneralAlba.add_preset(alba_backend, name, policies, compression, encryption)
        assert status, "Add preset failed with: {0}".format(message)
        TestALBA.verify_policies_for_preset(name, policies, compression, encryption)
        status, message = GeneralAlba.remove_preset(alba_backend, name)
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
        abe.scaling = 'LOCAL'
        abe.save()

        ad = AlbaDisk()
        ad.alba_node = an
        ad.aliases = ['/mnt/disk1']
        ad.save()

        asd = AlbaOSD()
        asd.alba_backend = abe
        asd.osd_id = 'ovs3769asd'
        asd.osd_type = 'ASD'
        asd.alba_disk = ad
        asd.save()

        try:
            abe.statistics
        except KeyError, ex:
            TestALBA.logger.error('Regression OVS-3769 - asd statistics raises a KeyError: {0}'.format(str(ex)))

        assert asd.statistics == dict(), "asd statistics should return an empty dict, go {0}".format(asd.statistics)
        asd.delete()
        ad.delete()
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

        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        GeneralAlba.claim_asds(alba_backend=alba_backend, nr_of_asds=3, disk_type='SATA')
        GeneralAlba.add_preset(alba_backend, preset_name, policies, compression, encryption)

        for x in range(nr_of_disks_to_create):
            namespace_name = namespace_prefix + str(x)
            GeneralAlba.execute_alba_cli_action(alba_backend, 'create-namespace', [namespace_name, preset_name], False)
            GeneralAlba.upload_file(alba_backend, namespace_name, 1024 * 1024 * 1)

        AlbaScheduledTaskController.verify_namespaces()

        GeneralAlba.remove_alba_namespaces(alba_backend)
        GeneralAlba.remove_preset(alba_backend, preset_name)

    @staticmethod
    def ovs_3977_maintenance_agent_test():
        """
        Test maintenance agent processes distribution:
        Logic:
        - local backend:
        -- only on nodes who have an asd claimed for a backend
        -- up to nr in config key
        -- at least one if not a single asd node has an asd claimed
        - global backend: nr gets deployed as requested as claimed asds does not matter in this case,
          if sufficient asdnodes are available
        """
        alba_backend = GeneralAlba.get_by_name(TestALBA.backend_name)
        alba_node_ips = [node.ip for node in GeneralAlba.get_alba_nodes()]

        def _get_agent_distribution():
            result = {}
            total = 0
            for sr in GeneralStorageRouter.get_storage_routers():
                count = 0
                client = SSHClient(endpoint=sr)
                all_processes = client.run(['ps', '-ef'])
                for process in all_processes.splitlines():
                    if '/usr/bin/alba maintenance' in process and '{0}/maintenance/config'.format(alba_backend.guid) in process:
                        count += 1
                result[sr.ip] = count
                total += count
            result['total'] = total

            TestALBA.logger.info('Maintenance agent distribution: {0}'.format(result))
            for ip in alba_node_ips:
                assert (result[ip] == total / len(alba_node_ips) or result[ip] == (total / len(alba_node_ips)) + 1),\
                    "Agents not equally distributed!"

            return result

        def _validate_actual_and_requested(requested, final):
            Configuration.set(config_key, requested)
            GeneralAlba.checkup_maintenance_agents()
            actual_nr_of_agents = int(_get_agent_distribution()['total'])

            assert actual_nr_of_agents == final, \
                'Actual {0} and final {1} nr of agents does not match'.format(actual_nr_of_agents, final)

        config_key = '/ovs/alba/backends/{0}/maintenance/nr_of_agents'.format(alba_backend.guid)
        current_nr_of_agents = Configuration.get(config_key)

        _validate_actual_and_requested(0, 1)
        _validate_actual_and_requested(12, 3)
        _validate_actual_and_requested(5, 3)

        Configuration.set(config_key, current_nr_of_agents)
        GeneralAlba.checkup_maintenance_agents()
