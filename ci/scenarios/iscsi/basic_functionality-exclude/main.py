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
import random
import threading
from subprocess import CalledProcessError
from ci.api_lib.helpers.api import NotFoundException
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.helpers.iscsi import ISCSIHelper
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System


class BasicIscsi(CIConstants):
    """
    Basic iSCSI testing class
    """
    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_iscsi_basic2"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))

    ISCSI_SYNC_TIME = 4  # A small sync time for syncing with reality

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
        cluster_info = cls.setup()
        return cls.execute_test(cluster_info)

    @classmethod
    def setup(cls):
        """
        Fetches all necessary starting info
        :raises AssertionError: * when no iscsi nodes are registered
                                * when no vpool with two storagedrivers can be found
        """
        iscsi_nodes = ISCSIHelper.get_iscsi_nodes()
        assert len(iscsi_nodes) > 0, 'No iscsi nodes have been registered.'
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 1:
                vpool = vp
                break
        assert vpool is not None, 'Found no vpool'
        chosen_storagedrivers = random.sample(vpool.storagedrivers, 1)
        cluster_info = {'storagedrivers': {'destination': chosen_storagedrivers[1] if len(chosen_storagedrivers) > 1 else None,
                                           'source': chosen_storagedrivers[0]},
                        'iscsi_nodes': iscsi_nodes}

        return cluster_info

    @classmethod
    def execute_test(cls, cluster_info):
        """
        Execute the test.
        - Create vdisks
        - Add targets to vdisks
        - Validate written data
        - Validate poweroff
        :param cluster_info: information about to cluster to use
        :raises AssertionError: * When errors occurred during the tests
        :return:
        """
        cls.LOGGER.info('Executing')
        source_storagedriver = cluster_info['storagedrivers']['source']
        vpool = source_storagedriver.vpool
        amount_of_targets = 3
        iscsi_node = random.choice(cluster_info['iscsi_nodes'])
        tests = [cls.test_expose_unexpose_remove,  cls.test_expose_remove, cls.test_expose_twice, cls.test_data_acceptance,
                 cls.test_exposed_move, cls.test_expose_two_nodes, cls.test_expose_ha, cls.test_expose_concurrently]
        run_errors = []
        for _function in tests:
            vdisk_basename = cls.TEST_NAME + '_' + _function.__name__
            vdisk_info = cls.deployment(amount_of_targets, vpool, source_storagedriver.storage_ip, base_name=vdisk_basename)
            cls.LOGGER.info("Environment set up for test: {0}".format(_function.__name__))
            try:
                removed = _function(vdisk_info, iscsi_node)
                cls.LOGGER.info("Succesfully passed test: {0}".format(_function.__name__))
            except Exception as ex:
                cls.LOGGER.exception(str(ex))
                run_errors.append(ex)
            finally:
                cleanup_errors = []
                try:
                    if removed:  # Some tests already remove the vdisks, resulting in errors cause they cannot be removed
                        for name in removed:
                            if name in vdisk_info:
                                vdisk_info.pop(name)
                    cls.tear_down(vdisk_info)
                except Exception as ex:
                    cleanup_errors.append(ex)
                assert len(cleanup_errors) == 0, 'Got the following errors during cleanup: {0}.'.format(', '.join((str(ex) for ex in cleanup_errors)))
        assert len(run_errors) == 0, 'Got the following errors during testing: {0}.'.format(', '.join((str(ex) for ex in run_errors)))

    @classmethod
    def deployment(cls, amount, vpool, storagerouter_ip, base_name=TEST_NAME):
        """
        Sets up vdisks
        :param amount: amount of vdisks to make
        :param storagerouter_ip: ip of the storagerouter to make them on
        :param vpool: vpool on which to deploy vdisks on
        :param base_name: name to use as a base for all vdisks that will be made
        :return: vdisk_info
            {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        """
        vdisk_info = {}
        for target_number in xrange(0, amount):
            vdisk_name = '{0}_{1}'.format(base_name, target_number)
            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name, vpool_name=vpool.name, size=1 * 1024 ** 3,
                                                 storagerouter_ip=storagerouter_ip)
            vdisk_info[vdisk_name] = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
        return vdisk_info

    @classmethod
    def tear_down(cls, vdisk_info):
        """
        Will tear down given vDisks
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :return:
        """
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            try:
                VDiskRemover.remove_vdisk(vdisk_object.guid)
            except NotFoundException:
                pass
            except Exception:
                cls.LOGGER.exception('Failed to remove vDisk {0}'.format(vdisk_name))

    @classmethod
    def test_expose_unexpose_remove(cls, vdisk_info, iscsi_node):
        """
        Will test behavior of iSCSI nodes upon exposure and unexposure
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        removed = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter')
        cls._validate_iscsi(iscsi_node)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            ISCSIHelper.unexpose_vdisk(vdisk_object.guid)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            VDiskRemover.remove_vdisk(vdisk_object.guid)
            removed.append(vdisk_name)
        return removed

    @classmethod
    def test_expose_remove(cls, vdisk_info, iscsi_node):
        """
        Will test behavior of iSCSI nodes upon exposure and removal of the vDisks
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        removed = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter')
        cls._validate_iscsi(iscsi_node)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            VDiskRemover.remove_vdisk(vdisk_object.guid)
            removed.append(vdisk_name)
        return removed

    @classmethod
    def test_expose_concurrently(cls, vdisk_info, iscsi_node):
        """
        Test concurrent expose of all vdisks present in the iscsi environment
        :param vdisk_info: include the vdisk_name and their corresponding vdisk object
        :type vdisk_info: dict
        :param iscsi_node: iscsiNode to test the logic on
        :type iscsi_node: IscsiNode
        :return:
        """
        if len(vdisk_info.items()) < 2:
            raise ValueError('Not enough vDisks to test this scenario')
        errorlist = []

        def _worker(vdisk_guid):
            try:
                ISCSIHelper.expose_vdisk(iscsi_node_guid=iscsi_node.guid, vdisk_guid=vdisk_guid, username='root', password='rooter')
            except Exception as ex:
                errorlist.append(str(ex))

        threads = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            cls.LOGGER.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            t = threading.Thread(target=_worker(vdisk_object.guid,))
            threads.append(t)
            t.start()
        for thread in threads:
            thread.join()
        if len(errorlist) > 0:
            raise RuntimeError('Concurrent exposing failed : \n - {0}'.format('\n - '.join(errorlist)))

    @classmethod
    def test_expose_ha(cls, vdisk_info, iscsi_node):
        """
        Test concurrent expose of all vdisks present in the iscsi environment
        :param vdisk_info: include the vdisk_name and their corresponding vdisk object
        :type vdisk_info: dict
        :param iscsi_node: iscsiNode to test the logic on
        :type iscsi_node: IscsiNode
        :return:
        """
        _ = iscsi_node
        iscsi_nodes = ISCSIHelper.get_iscsi_nodes()
        if len(iscsi_nodes) <= 1:
            raise ValueError('Not enough iscsi_nodes to test this.')
        vdisk = vdisk_info.pop(random.choice(vdisk_info.keys()))
        primary_node = random.choice(iscsi_nodes)
        iscsi_nodes.remove(primary_node)
        failover_node_guids = [iscsi_node.guid for iscsi_node in iscsi_nodes]

        cls.LOGGER.info('Exposing {0} on {1} and failover nodes: {2}.'.format(vdisk.name, primary_node.api_ip, failover_node_guids))
        ISCSIHelper.expose_vdisk(primary_node.guid, vdisk.guid, failover_node_guids=failover_node_guids, username='rooter', password='rooter')

    @classmethod
    def test_expose_twice(cls, vdisk_info, iscsi_node):
        """
        Will test behavior of iSCSI nodes upon double exposure: vDisks shouldn't be able to be exposed twice
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        for iteration in xrange(2):
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                try:
                    ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter')
                except Exception as ex:
                    if iteration == 0:
                        raise
                    if '{0} has already been exposed on iSCSI Node'.format(vdisk_name).lower() in str(ex).lower():
                        cls.LOGGER.info('Failed as expected. Message: {}.'.format(str(ex)))
                    else:
                        raise

    @classmethod
    def test_expose_two_nodes(cls, vdisk_info, iscsi_node):
        """
        Will test behavior of 2 iSCSI nodes upon exposure
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        _ = iscsi_node
        iqns = []
        iscsi_nodes = ISCSIHelper.get_iscsi_nodes()
        if len(iscsi_nodes) <= 1:
            raise ValueError('Not enough iscsi_nodes to test this.')
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            for iscsi_node in iscsi_nodes:
                try:
                    cls.LOGGER.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
                    iqns.append(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
                except Exception as ex:
                    cls.LOGGER.warning('Issue when xposing {0} on {1}. {2}'.format(vdisk_name, iscsi_node.api_ip, str(ex)))
                    raise

    @classmethod
    def test_data_acceptance(cls, vdisk_info, iscsi_node):
        """
        Verify that the target can accept data
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            iqns += cls._fetch_iqns(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
        cls._validate_iscsi(iscsi_node)
        cls._write_data_to_target(iqns)

    @classmethod
    def test_restart_target(cls, vdisk_info, iscsi_node):
        """
        Test that will restart iSCSI nodes
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            iqns += cls._fetch_iqns(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            ISCSIHelper.restart_targets_for_vdisk(vdisk_object.guid)

    @classmethod
    def test_move_of_subdir(cls, vdisk_info, iscsi_node):
        """
        Test that will move subdirectories and test for data acceptance
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        iqns = []
        a_vdisk = vdisk_info.values()[0]
        a_vdisk_storagerouter = StoragerouterHelper.get_storagerouter_by_guid(a_vdisk.storagerouter_guid)
        base_dir = 'a_testing_subdir'
        base_name = '{0}/{1}'.format(base_dir, cls.TEST_NAME)
        vdisk_info = cls.deployment(amount=1, vpool=a_vdisk.vpool, storagerouter_ip=a_vdisk_storagerouter.ip, base_name=base_name)
        client = SSHClient(a_vdisk_storagerouter, username='root')
        try:  # Isolate own creation
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                cls.LOGGER.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
                iqns += cls._fetch_iqns(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
            cls._validate_iscsi(iscsi_node)
            time.sleep(cls.ISCSI_SYNC_TIME)  # Small sync
            cls._write_data_to_target(iqns, a_vdisk.size / 10)
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                current_path = '/mnt/{0}/{1}'.format(vdisk_object.vpool.name, vdisk_object.devicename.split('/', 1)[-1].rsplit('/', 1)[0])
                destination_path = current_path.replace(base_dir, 'a_second_testing_subdir')
                cmd = ['mv', current_path, destination_path]
                client.run(cmd)
            cls._validate_iscsi(iscsi_node)
            time.sleep(cls.ISCSI_SYNC_TIME)  # Small sync
            # Validate data acceptance
            cls._write_data_to_target(iqns, a_vdisk.size / 10)
        except Exception as ex:
            cls.LOGGER.warning('Exception during move of subdir. {0}'.format(str(ex)))
        finally:
            cls.tear_down(vdisk_info)

    @classmethod
    def test_extend(cls, vdisk_info, iscsi_node):
        """
        Test that will extend and validate nodes
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        iqns = []
        a_vdisk = vdisk_info.values()[0]
        a_vdisk_storagerouter = StoragerouterHelper.get_storagerouter_by_guid(a_vdisk.storagerouter_guid)
        client = SSHClient(a_vdisk_storagerouter, username='root')
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            cls.LOGGER.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            iqns += cls._fetch_iqns(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
        # Login to targets
        cls._validate_iscsi(iscsi_node)
        try:
            for iqn in iqns:
                cls._login_target(iqn)
            for vdisk_name, vdisk_object in vdisk_info.iteritems():
                cmd = ['truncate', '--size', vdisk_object.size * 2, '/mnt/{0}/{1}'.format(vdisk_object.vpool.name, vdisk_object.devicename)]
                client.run(cmd)
            cls._validate_iscsi(iscsi_node)
            # Check if size changed on the initiator side - shouldnt be the case without relogging
        finally:
            for iqn in iqns:
                try:
                    cls._disconnect_target(iqn)
                except Exception as ex:
                    cls.LOGGER.warning('Exception during disconnect: {0}.'.format(str(ex)))

    @classmethod
    def test_exposed_move(cls, vdisk_info, iscsi_node):
        """
        Move a vdisk while it is exposed and ensure that the data channel isn't interrupted
        :param vdisk_info: {'vDisk_name': <ovs.dal.hybrids.vdisk>}
        :param iscsi_node: { ovs.dal.hybrids.iscsinode
        :return:
        """
        vdisk_info_copy = {}
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            if len(vdisk_object.vpool.storagedrivers) >= 2:
                vdisk_info_copy[vdisk_name] = vdisk_object

        if len(vdisk_info_copy.keys()) == 0:
            raise ValueError('Not enough vDisks with at least 2 storagedrivers to test this scenario')

        iqns = []
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            cls.LOGGER.info('Exposing {0} on {1}.'.format(vdisk_name, iscsi_node.api_ip))
            iqns += cls._fetch_iqns(ISCSIHelper.expose_vdisk(iscsi_node.guid, vdisk_object.guid, username='root', password='rooter'))
        cls._validate_iscsi(iscsi_node)
        cls._write_data_to_target(iqns, screen=True)
        for vdisk_name, vdisk_object in vdisk_info.iteritems():
            cls.LOGGER.debug('Moving Vdisk {0}'.format(vdisk_name))
            # Ensured we had 2 std at the start
            target_storagerouter_guid = [std.storagerouter_guid for std in vdisk_object.vpool.storagedrivers
                                         if std.storagerouter_guid != vdisk_object.storagerouter_guid][0]
            VDiskSetup.move_vdisk(vdisk_guid=vdisk_object.guid, target_storagerouter_guid=target_storagerouter_guid)

    @classmethod
    def _write_data_to_target(cls, iqns, size=1 * 1024 ** 3, screen=False):
        """
        Write data to iqn target
        :param iqns: targets to write to
        :param size: size. If the size > volume size, the volume size will be written
        :param screen: offload to screen
        :return:
        """
        try:
            for iqn in iqns:
                cls._login_target(iqn)
            mapping = cls._associate_target_to_disk()
            associated_disks = [disk for iqn, disk in mapping.iteritems() if iqn in iqns]
            cls.LOGGER.debug('Working with the following mapping: {0}'.format(mapping))
            local_client = SSHClient(System.get_my_storagerouter(), 'root')
            screen_names = []
            try:
                fio_config = {'io_size': size, 'configuration': (50, 50), 'bs': '4k'}
                screen_names, output_files = DataWriter.write_data_fio(client=local_client, fio_configuration=fio_config, file_locations=associated_disks, screen=screen, nbd_device=True)
            finally:
                for screen_name in screen_names:
                    local_client.run(['screen', '-S', screen_name, '-X', 'quit'])
        except Exception as ex:
            cls.LOGGER.exception('Exception during write data. {0}'.format(str(ex)))
            raise
        finally:
            for iqn in iqns:
                try:
                    cls._disconnect_target(iqn)
                except Exception as ex:
                    cls.LOGGER.warning('Exception during disconnect: {0}.'.format(str(ex)))

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
        cls.LOGGER.info('Was able to match: {0}'.format(matching))
        leftover_found = ['{0}:{1}'.format(found['ip'], found['port']) for found in found_portals_dict.values() if found['in_use'] is False]
        leftover_dal = ['{0}:{1}'.format(found['ip'], found['port']) for found in defined_portal_dict.values() if found['in_use'] is False]
        assert len(leftover_found) == 0, 'The following portals could not be matched to the DAL ones: {0}'.format(', '.join(leftover_found))
        assert len(leftover_dal) == 0, 'The following DAL portals could not be matched to the real ones: {0}'.format(', '.join(leftover_dal))

    @classmethod
    def _login_target(cls, target_iqn, retries=5, delay=ISCSI_SYNC_TIME):
        """
        Logs into a specific target
        :param target_iqn: iqn of the target
        :return:
        """
        cmd = ['iscsiadm', '-m', 'node', '--login', '-T', target_iqn]
        local_client = SSHClient(System.get_my_storagerouter(), 'root')
        for retry in xrange(retries):
            try:
                local_client.run(cmd, timeout=10)
                return
            except CalledProcessError as ex:
                cls.LOGGER.warning('Could not login to the node on try {0}. Got {1}'.format(retry, str(ex)))
                if retry == retries - 1:
                    raise
                time.sleep(delay)

    @classmethod
    def _associate_target_to_disk(cls):
        """
        Maps IQN to disks
        :return: mapping object with iqn as key and disk as value (eg {'iqn.mydisk': '/dev/sdg'})
        :rtype: dict
        """
        cmd = """lsscsi --transport | awk 'BEGIN{FS=OFS=" "} $4!="-" && match($3, "^iqn.*") && split($3, arr, ",") {print arr[1]" "$4}'"""
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

    @classmethod
    def _fetch_iqns(cls, d):
        """
        Assumes all iqns in dict are valid iqns
        :param d:
        :type d: dict
        :return:
        """
        iqns = []
        for key, value in d.iteritems():
            # can be string for primary node, list for secondary nodes
            if isinstance(value, unicode):
                iqns.append(str(value))
            elif isinstance(value, list):
                for iqn in value:
                    iqns.append(iqn)
            else:
                raise RuntimeError('No suitable type found for iqn fetching')
        return iqns


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