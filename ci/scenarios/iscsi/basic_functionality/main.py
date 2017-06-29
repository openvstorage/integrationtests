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
import random
import time
from ci.api_lib.helpers.api import NotFoundException
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.scenario_helpers.ci_constants import CIConstants
# @todo replace with api
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.dal.lists.iscsinodelist import IscsiNodeList
from ovs.lib.iscsinode import IscsiNodeController
from ovs.log.log_handler import LogHandler
from ci.scenario_helpers.data_writing import DataWriter


class BasicIscsi(CIConstants):
    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_iscsi_basic2"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)

    @classmethod
    def main(cls, blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        cls.LOGGER.info('Starting')
        _ = blocked
        return cls.start_test()

    @classmethod
    def start_test(cls):
        """
        Runs the multiple steps within the test
        :return: 
        """
        api = cls.get_api_instance()
        cluster_info = cls.setup()
        return cls.execute_test(cluster_info, api)

    @classmethod
    def setup(cls):
        """
        Fetches all necessary starting info 
        :raises AssertionError: * when no iscsi nodes are registered
                                * when no vpool with two storagedrivers can be found
        """
        iscsi_nodes = IscsiNodeList.get_iscsi_nodes()
        assert len(iscsi_nodes) > 0, 'No iscsi nodes have been registered.'
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 1:
                vpool = vp
                break
        assert vpool is not None, 'Found no vpool'
        if len(vpool.storagedrivers) == 1:
            chosen_storagedrivers = random.sample(vpool.storagedrivers, 1)
        else:
            chosen_storagedrivers = random.sample(vpool.storagedrivers, 2)
        chosen_storagedrivers = random.sample(vpool.storagedrivers, 1)
        cluster_info = {'storagedrivers': {'destination': chosen_storagedrivers[1] if len(chosen_storagedrivers) > 1 else None,
                                           'source': chosen_storagedrivers[0]},
                        'iscsi_nodes': iscsi_nodes}

        return cluster_info

    @classmethod
    def execute_test(cls, cluster_info, api):
        """
        Execute the test.
        - Create vdisks
        - Add targets to vdisks
        - Validate written data
        - Validate poweroff
        :param cluster_info: information about to cluster to use
        :param api: api instance
        :raises AssertionError: * When errors occurred during the tests
        :return: 
        """
        logger = cls.LOGGER
        logger.info('Executing')
        source_storagedriver = cluster_info['storagedrivers']['source']
        vpool = source_storagedriver.vpool
        amount_of_targets = 1
        iscsi_node = random.choice(cluster_info['iscsi_nodes'])
        # tests = [cls.test_expose_unexpose_remove, cls.test_expose_remove, cls.test_expose_twice, cls.test_data_acceptance, cls.test_exposed_move, cls.test_expose_two_nodes]
        tests = [cls.test_move_of_subdir]
        for _function in tests:
            vdisk_info = cls.deployment(amount_of_targets, vpool, source_storagedriver.storage_ip, api)
            try:
                _function(vdisk_info, iscsi_node, api)
            finally:
                errors = []
                try:
                    cls.tear_down(vdisk_info, api)
                except Exception as ex:
                    errors.append(ex)
                assert len(errors) == 0, 'Got the following errors during cleanup: {0}.'.format(', '.join((str(ex) for ex in errors)))

    @classmethod
    def deployment(cls, amount, vpool, storagerouter_ip, api, base_name=TEST_NAME):
        """
        Sets up vdisks
        :param amount: amount of vdisks to make 
        :param storagerouter_ip: ip of the storagerouter to make them on
        :param api: api instance
        :param base_name: name to use as a base for all vdisks that will be made
        :return: vdisk_info
        """
        vdisk_info = {}
        for target_number in xrange(0, amount):
            vdisk_name = '{0}_{1}'.format(base_name, target_number)
            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name, vpool_name=vpool.name, size=1 * 1024 ** 3,
                                                 storagerouter_ip=storagerouter_ip, api=api)
            vdisk_info[vdisk_name] = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
        return vdisk_info

    @classmethod
    def tear_down(cls, vdisk_info, api):
        logger = cls.LOGGER
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Removing vdisk {0}.'.format(vdisk_name))
            try:
                VDiskRemover.remove_vdisk(vdisk_object.guid, api)
            except NotFoundException:
                pass

    @classmethod
    def test_expose_unexpose_remove(cls, vdisk_info, iscsi_node, api):
        logger = cls.LOGGER
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter')
        cls._validate_iscsi(iscsi_node)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Unexposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            IscsiNodeController.unexpose_vdisk(vdisk_object.guid)
        # cls._validate_iscsi(iscsi_node)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Removing unexposed vdisk {0}.'.format(vdisk_name))
            VDiskRemover.remove_vdisk(vdisk_object.guid, api)

    @classmethod
    def test_expose_remove(cls, vdisk_info, iscsi_node, api):
        logger = cls.LOGGER
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter')
        cls._validate_iscsi(iscsi_node)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Removing exposed vdisk {0}.'.format(vdisk_name))
            VDiskRemover.remove_vdisk(vdisk_object.guid, api)
        # cls._validate_iscsi(iscsi_node)

    @classmethod
    def test_expose_twice(cls, vdisk_info, iscsi_node, api):
        """
        Vdisk should'nt be able to be exposed twice
        """
        logger = cls.LOGGER
        _ = api
        for iteration in xrange(2):
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                try:
                    IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter')
                except Exception as ex:
                    if iteration == 0:
                        raise
                    if '{0} has already been exposed on iSCSI Node'.format(vdisk_name).lower() in str(ex).lower():
                        logger.info('Failed as expected. Message: {}.'.format(str(ex)))
                    else:
                        raise

    @classmethod
    def test_expose_two_nodes(cls, vdisk_info, iscsi_node, api):
        logger = cls.LOGGER
        _ = api
        _ = iscsi_node
        iqns = []
        iscsi_nodes = IscsiNodeList.get_iscsi_nodes()
        if len(iscsi_nodes) <= 1:
            raise ValueError('Not enough iscsi_nodes to test this.')
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            for iscsi_node in iscsi_nodes:
                try:
                    logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
                    iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
                except Exception as ex:
                    logger.warning('Issue when xposing {0} on {1}. {2}'.format(vdisk_name, iscsi_node.api_ip, str(ex)))
                    raise

    @classmethod
    def test_data_acceptance(cls, vdisk_info, iscsi_node, api):
        """
        Verify that the target can accept data
        """
        _ = api
        logger = cls.LOGGER
        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
        cls._validate_iscsi(iscsi_node)
        cls._write_data_to_target(iqns)

    @classmethod
    def test_restart_target(cls, vdisk_info, iscsi_node, api):
        """
        """
        logger = cls.LOGGER
        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            IscsiNodeController.restart_targets_for_vdisk(vdisk_object.guid)

    @classmethod
    def test_move_of_subdir(cls, vdisk_info, iscsi_node, api):
        logger = cls.LOGGER
        iqns = []
        a_vdisk = vdisk_info.values()[0]
        a_vdisk_storagerouter = StoragerouterHelper.get_storagerouter_by_guid(a_vdisk.storagerouter_guid)
        base_dir = 'a_testing_subdir'
        base_name = '{0}/{1}'.format(base_dir, cls.TEST_NAME)
        vdisk_info = cls.deployment(amount=1, vpool=a_vdisk.vpool, storagerouter_ip=a_vdisk_storagerouter.ip, api=api, base_name=base_name)
        client = SSHClient(a_vdisk_storagerouter, username='root')
        try:  # Isolate own creation
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
                iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
            cls._write_data_to_target(iqns, a_vdisk.size / 10)
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                current_path = '/mnt/{0}/{1}'.format(vdisk_object.vpool.name, vdisk_object.devicename.split('/', 1)[-1].rsplit('/', 1)[0])
                destination_path = current_path.replace(base_dir, 'a_second_testing_subdir')
                cmd = ['mv', current_path, destination_path]
                client.run(cmd)
            cls._validate_iscsi(iscsi_node)
            # Validate data acceptance
            cls._write_data_to_target(iqns, a_vdisk.size / 10)
        except:
            cls.tear_down(vdisk_info, api)
            raise

    @classmethod
    def test_extend(cls, vdisk_info, iscsi_node, api):
        iqns = []
        logger = cls.LOGGER
        a_vdisk = vdisk_info.values()[0]
        a_vdisk_storagerouter = StoragerouterHelper.get_storagerouter_by_guid(a_vdisk.storagerouter_guid)
        client = SSHClient(a_vdisk_storagerouter, username='root')
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            cmd = ['truncate', '--size', vdisk_object.size * 2, '/mnt/{0}/{1}'.format(vdisk_object.vpool.name, vdisk_object.devicename)]
            client.run(cmd)
        cls._validate_iscsi(iscsi_node)
        cls._write_data_to_target(iqns, a_vdisk.size / 10)

    @classmethod
    def test_exposed_move(cls, vdisk_info, iscsi_node, api):
        """
        Move a vdisk while it is exposed and ensure that the data channel isn't interrupted
        """
        logger = cls.LOGGER
        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            iqns.append(IscsiNodeController.expose_vdisk(iscsi_node.guid, vdisk_object.guid, 'root', 'rooter'))
        cls._validate_iscsi(iscsi_node)
        # @todo offload to screen to make this test valid
        cls._write_data_to_target(iqns, screen=False)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            logger.debug('Moving Vdisk {0}'.format(vdisk_name))
            # Ensured we had 2 std at the start
            target_storagerouter_guid = [std.storagerouter_guid for std in vdisk_object.vpool.storagedrivers
                                         if std.storagerouter_guid != vdisk_object.storagerouter_guid][0]
            VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=target_storagerouter_guid, api=api)

    @classmethod
    def _write_data_to_target(cls, iqns, size=1 * 1024 ** 3, screen=False):
        """
        Write data to iqn target
        :param iqns: targets to write to
        :param size: size. If the size > volume size, the volume size will be written
        :param screen: offload to screen
        :return:
        """
        logger = cls.LOGGER
        try:
            for iqn in iqns:
                cls._login_target(iqn)
            mapping = cls._associate_target_to_disk()
            associated_disks = [disk for iqn, disk in mapping.iteritems() if iqn in iqns]
            logger.debug('Working with the following mapping: {0}'.format(mapping))
            local_client = SSHClient(System.get_my_storagerouter(), 'root')
            screen_names = []
            try:
                fio_config = {'io_size': size, 'configuration': (50, 50), 'bs': '1k'}
                screen_names, output_files = DataWriter.write_data_fio(local_client, fio_config, file_locations=associated_disks, screen=screen)
            finally:
                for screen_name in screen_names:
                    local_client.run(['screen', '-S', screen_name, '-X', 'quit'])
        except Exception as ex:
            logger.exception('Exception during write data. {0}'.format(str(ex)))
        finally:
            for iqn in iqns:
                try:
                    cls._disconnect_target(iqn)
                except Exception as ex:
                    logger.warning('Exception during disconnect: {0}.'.format(str(ex)))

    @classmethod
    def _validate_iscsi(cls, iscsi_node):
        """
        Validate the iscsi targets / portals
        """
        local_client = SSHClient(System.get_my_storagerouter(), 'root')
        try:
            portal_target_entries = local_client.run(['iscsiadm', '-m', 'discovery', '-t', 'st', '-p', iscsi_node.api_ip]).splitlines()
        except Exception:
            if len(iscsi_node.targets) == 0:
                return
            raise
        found_portals = []
        found_targets = []
        for portal_target_entry in portal_target_entries:
            split_entry = portal_target_entry.split(',')
            found_portals.append(split_entry[0])  # Eg: 10.100.69.122:3260
            found_targets.append(split_entry[1].split(' ')[-1])  # Eg iqn.2013-03.com.openvstorage:myvpool-mahdisk
        cls._validate_iscsi_target(iscsi_node, found_targets)
        cls._validate_iscsi_portal(iscsi_node, found_portals)

    @classmethod
    def _validate_iscsi_target(cls, iscsi_node, found_targets):
        """
        Validates if the iscsi target is registered in the DAL
        :param iscsi_node: iscsi node object
        :param found_targets: iqns of discovered targets
        :raises AssertionError: when DAL stored iqns that could not be discovered
        :raises AssertionError: when discovery found iqns that are not stored in the DAL
        """
        iscsi_node.invalidate_dynamics('targets')
        targets = iscsi_node.targets
        targets_by_iqn = {}
        for target_guid, target_info in targets.iteritems():
            new_target = dict(target_info)
            new_target['guid'] = target_guid
            targets_by_iqn[target_info['iqn']] = new_target
        difference_dal = set(targets_by_iqn.keys()).difference(set(found_targets))
        difference_reality = set(found_targets).difference(set(targets_by_iqn.keys()))
        assert len(difference_dal) == 0, 'The following IQNs are found in DAL but not by discovery: {0}'.format(', '.join(difference_dal))
        assert len(difference_reality) == 0, 'The following IQNs are found in reality but not in the DAL: {0}'.format(', '.join(difference_reality))

    @classmethod
    def _validate_iscsi_portal(cls, iscsi_node, found_portals):
        """
        Match found portals to DAL
        :param iscsi_node: iscsi node object 
        :param found_portals: list of ip:port portals
        :raises AssertionError: when no portals are matched
        :return: 
        """
        logger = cls.LOGGER
        wildcard_range = '0.0.0.0'
        iscsi_node.invalidate_dynamics('portals')
        defined_portal_dict = {}
        found_portals_dict = {}
        for defined_portal in iscsi_node.portals:  # Map ip to port
            split_portal = defined_portal.split(':')
            defined_portal_dict[split_portal[0]] = {'ip': split_portal[0], 'port': split_portal[1], 'in_use': False}
        for found_portal in found_portals:
            split_portal = found_portal.split(':')
            found_portals_dict[split_portal[0]] = {'ip': split_portal[0], 'port': split_portal[1], 'in_use': False}
        matching = {}  # Logging purposes
        for ip, connection_info in defined_portal_dict.iteritems():
            matched_values = []
            matching['{0}:{1}'.format(connection_info['ip'], connection_info['port'])] = matched_values
            for conn_info in found_portals_dict.values():
                if conn_info['port'] == connection_info['port']:
                    if ip == wildcard_range or conn_info['ip'] == connection_info['ip']:
                        conn_info['in_use'] = True
                        matched_values.append('{0}:{1}'.format(conn_info['ip'], conn_info['port']))
            if len(matched_values) > 0 and connection_info['in_use'] is False:
                connection_info['in_use'] = True
        logger.info('Was able to match: {0}'.format(matching))
        leftover_found = ['{0}:{1}'.format(found['ip'], found['port']) for found in found_portals_dict.values() if found['in_use'] is False]
        leftover_dal = ['{0}:{1}'.format(found['ip'], found['port']) for found in defined_portal_dict.values() if found['in_use'] is False]
        assert len(leftover_found) == 0, 'The following portals could not be matched to the DAL ones: {0}'.format(', '.join(leftover_found))
        assert len(leftover_dal) == 0, 'The following DAL portals could not be matched to the real ones: {0}'.format(', '.join(leftover_dal))

    @classmethod
    def _login_target(cls, target_iqn):
        """
        Logs into a specific target
        :param target_iqn: iqn of the target
        :return: 
        """
        cmd = ['iscsiadm', '-m', 'node', '--login', '-T', target_iqn]
        local_client = SSHClient(System.get_my_storagerouter(), 'root')
        local_client.run(cmd, timeout=10)

    @classmethod
    def _associate_target_to_disk(cls):
        """
        Maps IQN to disks
        :return: mapping object with iqn as key and disk as value (eg {'iqn.mydisk': '/dev/sdg'})
        :rtype: dict
        """
        cmd = """lsscsi --transport | awk 'BEGin{FS=OFS=" "} $4!="-" && match($3, "^iqn.*") && split($3, arr, ",") {print arr[1]" "$4}'"""
        local_client = SSHClient(System.get_my_storagerouter(), 'root')
        output = local_client.run(cmd, allow_insecure=True)
        mapping = {}  # maps IQN to disk
        for line in output.splitlines():
            split_line = line.split(' ')
            mapping[split_line[0]] = split_line[1]
        return mapping

    @classmethod
    def _disconnect_target(cls, target_iqn):
        """
        Logout of a specific target
        :param target_iqn: iqn of the target
        :return: 
        """
        cmd = ['iscsiadm', '-m', 'node', '--logout', '-T', target_iqn]
        local_client = SSHClient(System.get_my_storagerouter(), 'root')
        local_client.run(cmd)

        
def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return BasicIscsi().main(blocked)

if __name__ == "__main__":
    run()
