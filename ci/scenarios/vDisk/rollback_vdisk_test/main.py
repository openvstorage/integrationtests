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

import json
import time
import subprocess
from ci.main import CONFIG_LOC
from ci.helpers.api import OVSClient
from ci.setup.vdisk import VDiskSetup
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ci.helpers.exceptions import VDiskNotFoundError
from ovs.extensions.generic.sshclient import SSHClient


class RollbackChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_rollback")
    SIZE_VDISK = 52428800
    VDISK_NAME = "integration-tests-rollback"
    MAX_ROLLBACK_CHECKS = 10
    ROLLBACK_TIMEOUT = 45
    WRITE_AMOUNT_OF_TIMES = 2
    REQUIRED_PACKAGES = ['fio']

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                RollbackChecks.validate_rollback()
                return {'status': 'PASSED', 'case_type': RollbackChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                RollbackChecks.LOGGER.error("Rollback checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': RollbackChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': RollbackChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_rollback(size=SIZE_VDISK, amount_checks=MAX_ROLLBACK_CHECKS, timeout=ROLLBACK_TIMEOUT):
        """
        Validate if scrubbing works on a vpool

        INFO: 1 vPool should be available on 1 storagerouter

        :param size: size of a single vdisk in bytes
        :type size: int
        :param amount_checks: amount of times to check if stored data has changed
        :type amount_checks: int
        :param timeout: specify a timeout
        :type timeout: int
        :return:
        """

        RollbackChecks.LOGGER.info("Starting to validate the rollback")
        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        vpool = vpools[0]  # just pick the first vpool you find
        assert len(vpool.storagedrivers) >= 1, "Not enough Storagedrivers to test"

        # create vdisks and write some stuff on it
        storagedriver = vpool.storagedrivers[0]  # just pick the first storagedriver you find
        client = SSHClient(storagedriver.storage_ip, username='root')

        # check for possible missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver.storage_ip,
                                                             RollbackChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

        RollbackChecks.LOGGER.info("Starting deploying vdisk `{0}`".format(RollbackChecks.VDISK_NAME))

        # create a vdisk & collect results
        vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=RollbackChecks.VDISK_NAME + '.raw', vpool_name=vpool.name,
                                             size=size, api=api, storagerouter_ip=storagedriver.storage_ip)
        vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
        results = {'vdisk_guid': vdisk_guid, 'snapshots': {}}

        RollbackChecks.LOGGER.info("Finished deploying vdisk `{0}`".format(RollbackChecks.VDISK_NAME))
        RollbackChecks.LOGGER.info("Starting writing & snapshotting vdisk `{0}`".format(RollbackChecks.VDISK_NAME))

        for i in xrange(RollbackChecks.WRITE_AMOUNT_OF_TIMES):
            try:
                RollbackChecks.LOGGER.info("Starting FIO on vdisk `{0}` write cycle {1}/{2}"
                                           .format(RollbackChecks.VDISK_NAME, i+1,
                                                   RollbackChecks.WRITE_AMOUNT_OF_TIMES))
                # perform fio test
                client.run(["fio", "--name=test",
                            "--filename=/mnt/{0}/{1}.raw".format(vpool.name, RollbackChecks.VDISK_NAME),
                            "--ioengine=libaio", "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1",
                            "--size={0}b".format(RollbackChecks.SIZE_VDISK)])
                RollbackChecks.LOGGER.info("Finished FIO on vdisk `{0}` write cycle {1}/{2}"
                                           .format(RollbackChecks.VDISK_NAME, i+1,
                                                   RollbackChecks.WRITE_AMOUNT_OF_TIMES))

            except subprocess.CalledProcessError as ex:
                raise VDiskNotFoundError("VDisk `/mnt/{0}/{1}.raw` does not seem to be present "
                                         "or has problems on storagerouter `{2}`: {3}"
                                         .format(vpool.name, RollbackChecks.VDISK_NAME, storagedriver.storage_ip,
                                                 ex.message))

            RollbackChecks.LOGGER.info("Starting snapshot creation on vdisk `{0}`".format(RollbackChecks.VDISK_NAME))

            # create snapshot
            snapshot_guid = VDiskSetup.create_snapshot(snapshot_name=RollbackChecks.VDISK_NAME + '-snapshot{0}'
                                                       .format(i), vdisk_name=RollbackChecks.VDISK_NAME + '.raw',
                                                       vpool_name=vpool.name, api=api, consistent=False, sticky=False)
            # save the current stored_data for comparison
            stored_data = vdisk.storagedriver_client.info_volume(str(vdisk.volume_id)).stored
            RollbackChecks.LOGGER.info("Logged `{0}` stored data for VDisk `{1}` in mapper"
                                       .format(stored_data, RollbackChecks.VDISK_NAME))
            # add details to snapshot mapper
            results['snapshots'][i] = {'snapshot_guid': snapshot_guid,
                                       'snapshot_name': RollbackChecks.VDISK_NAME + '-snapshot{0}'.format(i),
                                       'stored_data': stored_data}

            RollbackChecks.LOGGER.info("Snapshot creation finished on vdisk `{0}`".format(RollbackChecks.VDISK_NAME))

        RollbackChecks.LOGGER.info("Finished writing & snapshotting vdisk `{0}`. Results: {1}"
                                   .format(RollbackChecks.VDISK_NAME, results))

        # Commencing rollback
        RollbackChecks.LOGGER.info("Starting rollback on vdisk `{0}` to first snapshot `{1}`"
                                   .format(RollbackChecks.VDISK_NAME, results['snapshots'][0]))
        VDiskSetup.rollback_to_snapshot(vdisk_name=RollbackChecks.VDISK_NAME + '.raw',
                                        vpool_name=vpool.name, snapshot_id=results['snapshots'][0]['snapshot_guid'],
                                        api=api)

        # Start checking when disk is rollback'ed
        tries = 0
        while tries < amount_checks:
            current_statistics = vdisk.storagedriver_client.info_volume(str(vdisk.volume_id)).stored
            if current_statistics < results['snapshots'][1]['stored_data']:
                RollbackChecks.LOGGER.info("VDisk `{0}` matched the requirements for rollback with {1} < {2}"
                                           .format(vdisk_guid, current_statistics,
                                                   results['snapshots'][1]['stored_data']))
                break
            else:
                tries += 1
                RollbackChecks.LOGGER.warning("Try `{0}` when checking stored data on volumedriver for VDisk "
                                              "`{1}`, with currently `{2}` but it should be less than `{3}`. "
                                              "Now sleeping for `{4}` seconds ..."
                                              .format(tries, vdisk_guid, current_statistics,
                                                      results['snapshots'][1]['stored_data'], timeout))
                time.sleep(timeout)

        # check if amount of tries has exceeded
        if tries == amount_checks:
            error_msg = "VDisk `{0}` should have been rollback'ed but max. amount of checks have exceeded!"\
                .format(RollbackChecks.VDISK_NAME)
            RollbackChecks.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        else:
            RollbackChecks.LOGGER.info("Successfully finished rollback'ing on vdisk `{0}`"
                                       .format(RollbackChecks.VDISK_NAME))

        # commencing deleting volumes
        RollbackChecks.LOGGER.info("Starting to remove VDisk `{0}`".format(RollbackChecks.VDISK_NAME))
        VDiskRemover.remove_vdisk(vdisk_guid)
        RollbackChecks.LOGGER.info("Finished removing VDisk `{0}`".format(RollbackChecks.VDISK_NAME))


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return RollbackChecks().main(blocked)

if __name__ == "__main__":
    run()
