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
    MAX_ROLLBACK_CHECKS = 20
    ROLLBACK_TIMEOUT = 45
    WRITE_AMOUNT_OF_TIMES = 2
    AMOUNT_VDISKS = 2
    REQUIRED_PACKAGES = ['fio']
    # False scenario = run a non clone scrub test, # True scenario = run a clone scrub test
    TYPE_TEST_RUN = [False, True]

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
    def validate_rollback():
        """
        Validate if scrubbing works on a vpool

        INFO: 1 vPool should be available on 1 storagerouter

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

        # check for possible missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver.storage_ip,
                                                             RollbackChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

        # start actual test
        for cloned in list(RollbackChecks.TYPE_TEST_RUN):
            start = time.time()
            RollbackChecks.LOGGER.info("Starting deployment of required vdisks")
            deployed_vdisks = RollbackChecks._deploy_vdisks(vpool=vpool, storagedriver=storagedriver, api=api,
                                                            cloned=cloned)
            RollbackChecks.LOGGER.info("Received vdisks to be rolledback: `{0}`".format(deployed_vdisks[0]))
            RollbackChecks._rollback_vdisks(stored_vdisks=deployed_vdisks[0], api=api, vpool=vpool)
            RollbackChecks.LOGGER.info("Finished rolling back vdisks, start deleting possible base vdisks: {0}"
                                       .format(deployed_vdisks[1]))
            end = time.time()
            # clean base disks from clones
            if cloned:
                RollbackChecks._delete_remaining_vdisks(base_vdisks=deployed_vdisks[1])
                RollbackChecks.LOGGER.info("Finished deleting base vdisks")
            else:
                RollbackChecks.LOGGER.info("Skipped deleting base vdisks")

            # display run time
            RollbackChecks.LOGGER.info("Run with clone status `{0}` took {1} seconds".format(cloned, int(end - start)))

        RollbackChecks.LOGGER.info("Finished to validate the rollback")

    @staticmethod
    def _delete_remaining_vdisks(base_vdisks):
        """
        Delete remaining base vdisks (when performing cloned=True)

        :param base_vdisks: vdisk_guids of a base_vdisks ['a15908c0-f7f0-402e-ad20-2be97e401cd3', ...]
        :type: list
        :return: None
        """

        for vdisk_guid in base_vdisks:
            RollbackChecks.LOGGER.info("Starting to remove base vDisk `{0}`".format(vdisk_guid))
            VDiskRemover.remove_vdisk(vdisk_guid)
            RollbackChecks.LOGGER.info("Finished to remove base vDisk `{0}`".format(vdisk_guid))

    @staticmethod
    def _deploy_vdisks(vpool, storagedriver, api, size=SIZE_VDISK, amount_vdisks=AMOUNT_VDISKS, cloned=False):
        """
        Deploy X amount of vdisks, write some data to it & snapshot

        :param vpool: a valid vpool object
        :type vpool: ovs.model.hybrids.vpool
        :param storagedriver: a valid storagedriver object
        :type storagedriver: ovs.mode.hybrids.storagedriver
        :param size: size of a single vdisk in bytes
        :type size: int
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :return: tuple[0]: stored vdisks, snapshot, location; tuple[1]: base_vdisks_guids that are used for clones
        [{
            'vdisk_guid': u 'b789b23e-1077-4d96-9ec2-a7cc3785686c',
            'snapshots': {
                0: {
                    'snapshot_name': 'integration-tests-rollback0-snapshot0',
                    'snapshot_guid': u 'fbd1c961-7d33-4bd3-8c92-c8a3c52eb74f',
                    'stored_data': 52428800
                },
                1: {
                    'snapshot_name': 'integration-tests-rollback0-snapshot1',
                    'snapshot_guid': u '15eb7119-d984-4c84-985c-1fb1cc44a95e',
                    'stored_data': 104857600
                }
            }
        }, {
            'vdisk_guid': u '9c2cd023-d15b-4994-8a62-07edc36d748c',
            'snapshots': {
                0: {
                    'snapshot_name': 'integration-tests-rollback1-snapshot0',
                    'snapshot_guid': u 'c7500fec-cc5a-4593-89dc-fca78dcb2783',
                    'stored_data': 52428800
                },
                1: {
                    'snapshot_name': 'integration-tests-rollback1-snapshot1',
                    'snapshot_guid': u 'e46bd42b-516d-4636-9d15-d9c1a8f489e4',
                    'stored_data': 104857600
                }
            }
        }], ['8858717a-e6d2-11e6-831d-00249b133798', '8c644a82-e6d2-11e6-8efe-00249b133798']
        :rtype: tuple
        """

        RollbackChecks.LOGGER.info("Starting deploying {0} vdisks with clone status: {1}".format(amount_vdisks, cloned))

        client = SSHClient(storagedriver.storage_ip, username='root')
        vdisks = []
        base_vdisks = []
        for vdisk_nr in xrange(amount_vdisks):
            # create a vdisk & collect results
            vdisk_name = RollbackChecks.VDISK_NAME + str(vdisk_nr)

            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name,
                                                 size=size, api=api, storagerouter_ip=storagedriver.storage_ip)
            # clone
            if cloned:
                clone_vdisk_name = vdisk_name + '_clone'
                RollbackChecks.LOGGER.info("Creating clone from vdisk `{0}` with new name `{1}`"
                                           .format(vdisk_name, clone_vdisk_name))
                base_vdisks.append(str(vdisk_guid))
                RollbackChecks.LOGGER.info("Stored old base vdisk guid in list: {0}".format(vdisk_guid))
                vdisk_guid = VDiskSetup.create_clone(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                                     new_vdisk_name=clone_vdisk_name,
                                                     storagerouter_ip=storagedriver.storage_ip, api=api)['vdisk_guid']
                vdisk_name = clone_vdisk_name

            vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            results = {'vdisk_guid': vdisk_guid, 'snapshots': {}}
            RollbackChecks.LOGGER.info("Finished deploying vdisk `{0}`".format(vdisk_name))

            RollbackChecks.LOGGER.info("Starting writing & snapshotting vdisk `{0}`".format(vdisk_name))
            for i in xrange(RollbackChecks.WRITE_AMOUNT_OF_TIMES):
                # write some data
                try:
                    RollbackChecks.LOGGER.info("Starting FIO on vdisk `{0}`".format(vdisk_name))
                    client.run(["fio", "--name=test", "--filename=/mnt/{0}/{1}.raw".format(vpool.name, vdisk_name),
                                "--ioengine=libaio", "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1",
                                "--size={0}b".format(size)])
                    RollbackChecks.LOGGER.info("Finished FIO on vdisk `{0}`".format(vdisk_name))

                except subprocess.CalledProcessError as ex:
                    raise VDiskNotFoundError("VDisk `/mnt/{0}/{1}.raw` does not seem to be present "
                                             "or has problems on storagerouter `{2}`: {3}"
                                             .format(vpool.name, vdisk_name, storagedriver.storage_ip, str(ex)))
                # create snapshot
                RollbackChecks.LOGGER.info("Starting snapshot creation on vdisk `{0}`"
                                           .format(vdisk_name))
                snapshot_guid = VDiskSetup.create_snapshot(snapshot_name=vdisk_name + '-snapshot{0}'.format(i),
                                                           vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                                           api=api, consistent=False, sticky=False)
                # save the current stored_data for comparison
                stored_data = vdisk.storagedriver_client.info_volume(str(vdisk.volume_id)).stored
                RollbackChecks.LOGGER.info("Logged `{0}` stored data for VDisk `{1}` in mapper"
                                           .format(stored_data, vdisk_name))
                # add details to snapshot mapper
                results['snapshots'][i] = {'snapshot_guid': snapshot_guid,
                                           'snapshot_name': vdisk_name + '-snapshot{0}'.format(i),
                                           'stored_data': stored_data}
                RollbackChecks.LOGGER.info("Snapshot creation finished on vdisk `{0}`".format(vdisk_name))
            vdisks.append(results)
            RollbackChecks.LOGGER.info("Finished writing & snapshotting vdisk `{0}`. Results: {1}"
                                       .format(vdisk_name, results))
        return vdisks, base_vdisks

    @staticmethod
    def _rollback_vdisks(stored_vdisks, vpool, api, amount_checks=MAX_ROLLBACK_CHECKS, timeout=ROLLBACK_TIMEOUT):
        """
        Rollback the given mapped vdisks

        :param stored_vdisks: dict with stored vdisks, snapshot, location, ...
        :type stored_vdisks: dict
        :param vpool: a valid vpool object
        :type vpool: ovs.model.hybrids.vpool
        :param amount_checks: amount of checks to perform after a vdisk has been rolled back
        :type amount_checks: int
        :param timeout: timeout between checks
        :type timeout: int
        :return: None
        """

        for stored_vdisk in stored_vdisks:
            # fetch vdisk
            vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid=stored_vdisk['vdisk_guid'])

            # Commencing rollback
            RollbackChecks.LOGGER.info("Starting rollback on vdisk `{0}` to first snapshot `{1}`"
                                       .format(vdisk.name, stored_vdisk['snapshots'][0]))

            VDiskSetup.rollback_to_snapshot(vdisk_name=vdisk.name + '.raw', vpool_name=vpool.name,
                                            snapshot_id=stored_vdisk['snapshots'][0]['snapshot_guid'], api=api)

            # Start checking when disk is rollback'ed
            tries = 0
            while tries < amount_checks:
                current_statistics = vdisk.storagedriver_client.info_volume(str(vdisk.volume_id)).stored
                if current_statistics < stored_vdisk['snapshots'][1]['stored_data']:
                    RollbackChecks.LOGGER.info("VDisk `{0}` matched the requirements for rollback with {1} < {2}"
                                               .format(stored_vdisk['vdisk_guid'], current_statistics,
                                                       stored_vdisk['snapshots'][1]['stored_data']))
                    break
                else:
                    tries += 1
                    RollbackChecks.LOGGER.warning("Try `{0}` when checking stored data on volumedriver for VDisk "
                                                  "`{1}`, with currently `{2}` but it should be less than `{3}`. "
                                                  "Now sleeping for `{4}` seconds ..."
                                                  .format(tries, stored_vdisk['vdisk_guid'], current_statistics,
                                                          stored_vdisk['snapshots'][1]['stored_data'], timeout))
                    time.sleep(timeout)

            # check if amount of tries has exceeded
            if tries == amount_checks:
                error_msg = "VDisk `{0}` should have been rollback'ed but max. amount of checks have exceeded!"\
                            .format(vdisk.name)
                RollbackChecks.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)
            else:
                RollbackChecks.LOGGER.info("Successfully finished rollback'ing on vdisk `{0}`".format(vdisk.name))

            # commencing deleting volumes
            RollbackChecks.LOGGER.info("Starting to remove VDisk `{0}`".format(vdisk.name))
            VDiskRemover.remove_vdisk(stored_vdisk['vdisk_guid'])
            RollbackChecks.LOGGER.info("Finished removing VDisk `{0}`".format(vdisk.name))


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
