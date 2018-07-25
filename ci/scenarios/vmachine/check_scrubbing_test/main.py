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
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.setup.vpool import VPoolSetup
from ci.api_lib.helpers.system import SystemHelper
from ci.scenario_helpers.data_writing import DataWriter
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class ScrubbingChecks(CIConstants):

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_scrubbing"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    AMOUNT_VDISKS_TO_SCRUB = 5
    SIZE_VDISK = 50 * 1024 ** 2
    PREFIX = "integration-tests-scrubbing"
    MAX_SCRUBBING_CHECKS = 20
    SCRUBBING_TIMEOUT = 90
    REQUIRED_PACKAGES = ['fio']
    TYPE_TEST_RUN = ['originals', 'clones']

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}, 'volumedriver'])
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return ScrubbingChecks.start_test()

    @classmethod
    def setup(cls):
        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"
        vpool = vpools[0]  # Just pick the first vpool you find
        assert len(vpool.storagedrivers) >= 1, "Not enough Storagedrivers to test"
        storagedriver = vpool.storagedrivers[0]  # just pick the first storagedriver you find
        source_str = storagedriver.storagerouter
        client = SSHClient(source_str, username='root')
        is_ee = SystemHelper.get_ovs_version(source_str) == 'ee'
        if is_ee is True:
            fio_bin_loc = cls.FIO_BIN_EE['location']
            fio_bin_url = cls.FIO_BIN_EE['url']
        else:
            fio_bin_loc = cls.FIO_BIN['location']
            fio_bin_url = cls.FIO_BIN['url']
        client.run(['wget', fio_bin_url, '-O', fio_bin_loc])
        client.file_chmod(fio_bin_loc, 755)
        return storagedriver, fio_bin_loc, is_ee

    @classmethod
    def start_test(cls):
        storagedriver, fio_bin_loc, is_ee = cls.setup()
        for test_run_type in cls.TYPE_TEST_RUN:
            cloned = test_run_type == 'clones'
            created_vdisks = cls.create_vdisks(storagedriver, cloned=cloned)
            try:
                if cloned is True:
                    vdisks = created_vdisks['clones']
                else:
                    vdisks = created_vdisks['parents']
                stored_map = cls._prepare_for_scrubbing(vdisks, storagedriver, fio_bin_loc, is_ee)
                cls._validate_scrubbing(stored_map)
            finally:
                for vdisk_type, vdisk_list in created_vdisks.iteritems():
                    VDiskRemover.remove_vdisks_with_structure(vdisk_list)

    @staticmethod
    def _validate_scrubbing(vdisk_stored_mapper, amount_checks=MAX_SCRUBBING_CHECKS, timeout=SCRUBBING_TIMEOUT):
        """
        Execute and validate if given vdisks have been scrubbed
        :param vdisk_stored_mapper: vdisks that have been deployed to be scrubbed
        :type vdisk_stored_mapper: dict
        :param amount_checks: amount of times to check if stored data has changed
        :type amount_checks: int
        :param timeout: specify a timeout
        :type timeout: int
        :return:
        """
        # start scrubbing and check if scrubbed
        ScrubbingChecks.LOGGER.info("Execute scrub command.")
        VPoolSetup.execute_scrubbing()
        for vdisk_guid, vdisk_stored in vdisk_stored_mapper.iteritems():
            # check if scrubbing has worked
            vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            tries = 0
            while tries < amount_checks:
                current_statistics = vdisk.storagedriver_client.info_volume(str(vdisk.volume_id)).stored
                if current_statistics < vdisk_stored:
                    ScrubbingChecks.LOGGER.info("VDisk `{0}` matched the requirements for scrubbing with {1} < {2}"
                                                .format(vdisk_guid, current_statistics, vdisk_stored))
                    break
                else:
                    tries += 1
                    ScrubbingChecks.LOGGER.warning("Try `{0}` when checking stored data on volumedriver for VDisk `{1}`,"
                                                   " with currently `{2}` but it should be less than `{3}`. "
                                                   "Now sleeping for `{4}` seconds ..."
                                                   .format(tries, vdisk_guid, current_statistics, vdisk_stored, timeout))
                    time.sleep(timeout)
            # check if amount of tries has exceeded
            if tries == amount_checks:
                error_msg = "VDisk `{0}` should have been scrubbed but stored data > {1}`".format(vdisk_guid, vdisk_stored)
                ScrubbingChecks.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)

    @classmethod
    def _prepare_for_scrubbing(cls, vdisks, storagedriver, fio_bin_location, is_ee):
        """
        Writes data to the vdisks
        :param vdisks: list of vdisks
        :return:
        """
        client = SSHClient(storagedriver.storagerouter, username='root')
        edge_configuration = {'fio_bin_location': fio_bin_location, 'hostname': storagedriver.storage_ip,
                              'port': storagedriver.ports['edge'],
                              'protocol': storagedriver.cluster_node_config['network_server_uri'].split(':')[0],
                              'volumenames': []}
        if is_ee is True:
            edge_configuration.update(cls.get_shell_user())
        for vdisk in vdisks:
            edge_configuration['volumenames'].append(vdisk.devicename.rsplit('.', 1)[0].split('/', 1)[1])
        for i in xrange(2):  # Will write to max of volume size. Loop over it to avoid this issue:
            DataWriter.write_data_fio(client=client,
                                      fio_configuration={'io_size': cls.SIZE_VDISK, 'configuration': (0, 100)},
                                      edge_configuration=edge_configuration,
                                      screen=False,
                                      loop_screen=False)
        for vdisk in vdisks:  # Snapshot to give the volumedriver a point of reference to scrub towards
            VDiskSetup.create_snapshot(snapshot_name='{}_snapshot01'.format(vdisk.name),
                                       vdisk_name=vdisk.name,
                                       vpool_name=vdisk.vpool.name, consistent=False, sticky=False)
        stored_map = {}
        for vdisk in vdisks:
            stored_map[vdisk.guid] = vdisk.statistics['stored']
            cls.LOGGER.info("Logged {0} stored data for VDisk {1} in mapper".format(vdisk.statistics['stored'], vdisk.name))
        return stored_map

    @classmethod
    def create_vdisks(cls, storagedriver, amount_vdisks=AMOUNT_VDISKS_TO_SCRUB, size=SIZE_VDISK, cloned=False):
        vpool = storagedriver.vpool
        cls.LOGGER.info("Start deploying vdisks for scrubbing with clone status: {0}".format(cloned))
        vdisks = {'parents': [],  # Non cloned
                  'clones': []}  # Cloned
        if cloned is True:
            parent_vdisk_name = '{0}_clone_parent_{1}'.format(cls.PREFIX, str(0).zfill(3))
            parent_vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=parent_vdisk_name,
                                                        vpool_name=vpool.name,
                                                        size=size,
                                                        storagerouter_ip=storagedriver.storagerouter.ip)
            parent_vdisk = VDiskHelper.get_vdisk_by_guid(parent_vdisk_guid)
            vdisks['parents'].append(parent_vdisk)
            for vdisk_nr in xrange(amount_vdisks):
                clone_vdisk_name = '{0}_clone{1}'.format(parent_vdisk.name, str(len(vdisks['clones']) + 1).zfill(3))
                cloned_vdisk = VDiskHelper.get_vdisk_by_guid(
                    VDiskSetup.create_clone(vdisk_name=parent_vdisk_name, vpool_name=vpool.name,
                                            new_vdisk_name=clone_vdisk_name,
                                            storagerouter_ip=storagedriver.storagerouter.ip)['vdisk_guid'])
                vdisks['clones'].append(cloned_vdisk)
        else:
            for vdisk_nr in xrange(amount_vdisks):
                vdisk_name = '{0}_{1}'.format(cls.PREFIX, str(vdisk_nr).zfill(3))
                vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name,
                                                     vpool_name=vpool.name,
                                                     size=size,
                                                     storagerouter_ip=storagedriver.storagerouter.ip)
                vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                vdisks['parents'].append(vdisk)
        return vdisks


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return ScrubbingChecks().main(blocked)


if __name__ == "__main__":
    run()
