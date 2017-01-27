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
from ci.setup.vpool import VPoolSetup
from ci.setup.vdisk import VDiskSetup
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ci.helpers.exceptions import VDiskNotFoundError
from ovs.extensions.generic.sshclient import SSHClient


class ScrubbingChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_scrubbing")
    AMOUNT_VDISKS_TO_SCRUB = 5
    SIZE_VDISK = 52428800  # 50M
    PREFIX = "integration-tests-scrubbing-"
    MAX_SCRUBBING_CHECKS = 20
    SCRUBBING_TIMEOUT = 45
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
                ScrubbingChecks._execute()
                return {'status': 'PASSED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                ScrubbingChecks.LOGGER.error("Scrubbing checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def _execute():
        """
        Validate if scrubbing works on a vpool
        INFO: 1 vPool should be available on 1 storagerouter

        :return: None
        """

        ScrubbingChecks.LOGGER.info("Starting to validate the scrubbing")
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
                                                             ScrubbingChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

        # start actual test
        for cloned in list(ScrubbingChecks.TYPE_TEST_RUN):
            start = time.time()
            ScrubbingChecks.LOGGER.info("Starting deployment of required vdisks")
            deployed_vdisks = ScrubbingChecks._deploy_vdisks(vpool=vpool, storagedriver=storagedriver, api=api,
                                                             cloned=cloned)
            ScrubbingChecks.LOGGER.info("Received vdisks to be scrubbed: `{0}`".format(deployed_vdisks[0]))
            ScrubbingChecks._validate_scrubbing(vdisk_stored_mapper=deployed_vdisks[0])
            ScrubbingChecks.LOGGER.info("Finished scrubbing vdisks, start deleting possible base vdisks: {0}"
                                        .format(deployed_vdisks[1]))
            end = time.time()
            # clean base disks from clones
            if cloned:
                ScrubbingChecks._delete_remaining_vdisks(base_vdisks=deployed_vdisks[1])
                ScrubbingChecks.LOGGER.info("Finished deleting base vdisks")
            else:
                ScrubbingChecks.LOGGER.info("Skipped deleting base vdisks")

            # display run time
            ScrubbingChecks.LOGGER.info("Run with clone status `{0}` took {1} seconds".format(cloned, int(end-start)))

        ScrubbingChecks.LOGGER.info("Finished to validate the scrubbing")

    @staticmethod
    def _delete_remaining_vdisks(base_vdisks):
        """
        Delete remaining base vdisks (when performing cloned=True)

        :param base_vdisks: vdisk_guids of a base_vdisks ['a15908c0-f7f0-402e-ad20-2be97e401cd3', ...]
        :type: list
        :return: None
        """

        for vdisk_guid in base_vdisks:
            ScrubbingChecks.LOGGER.info("Starting to remove base vDisk `{0}`".format(vdisk_guid))
            VDiskRemover.remove_vdisk(vdisk_guid)
            ScrubbingChecks.LOGGER.info("Finished to remove base vDisk `{0}`".format(vdisk_guid))

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
        ScrubbingChecks.LOGGER.info("Execute scrub command...")
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
                    ScrubbingChecks.LOGGER.warning("Try `{0}` when checking stored data on volumedriver for VDisk "
                                                   "`{1}`, with currently `{2}` but it should be less than `{3}`. "
                                                   "Now sleeping for `{4}` seconds ..."
                                                   .format(tries, vdisk_guid, current_statistics, vdisk_stored,
                                                           timeout))
                    time.sleep(timeout)

            # check if amount of tries has exceeded
            if tries == amount_checks:
                error_msg = "VDisk `{0}` should have been scrubbed but stored data > {1}`".format(vdisk_guid,
                                                                                                  vdisk_stored)
                ScrubbingChecks.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)

            # commencing deleting volumes
            ScrubbingChecks.LOGGER.info("Starting to remove vDisk `{0}`".format(vdisk.name))
            VDiskRemover.remove_vdisk(vdisk_guid)
            ScrubbingChecks.LOGGER.info("Finished removing vDisk `{0}`".format(vdisk.name))

    @staticmethod
    def _deploy_vdisks(vpool, storagedriver, api, amount_vdisks=AMOUNT_VDISKS_TO_SCRUB, size=SIZE_VDISK, cloned=False):

        """
        :param vpool: chosen vpool
        :type vpool: ovs.model.hybrid.vpool
        :param storagedriver: chosen storagedriver
        :type storagedriver: ovs.model.hybrid.storagedriver
        :param amount_vdisks: amount of vdisks to deploy and scrub
        :type amount_vdisks: int
        :param size: size of a single vdisk in bytes
        :type size: int
        :param cloned: deploy cloned disks
        :type cloned: bool
        :return: tuple with disk_to_be_scrubbed and potential clones ({}, [])
        :rtype: tuple
        """

        ScrubbingChecks.LOGGER.info("Start deploying vdisks for scrubbing with clone status: {0}".format(cloned))
        client = SSHClient(storagedriver.storage_ip, username='root')

        vdisk_stored_mapper = {}
        base_vdisks = []
        for vdisk_nr in xrange(amount_vdisks):
            vdisk_name = ScrubbingChecks.PREFIX + str(vdisk_nr)
            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name, vpool_name=vpool.name,
                                                 size=size, api=api, storagerouter_ip=storagedriver.storage_ip)
            ScrubbingChecks.LOGGER.info("Vdisk created with guid: {0}".format(vdisk_guid))

            # create a clone from it
            if cloned:
                clone_vdisk_name = vdisk_name + '_clone'
                ScrubbingChecks.LOGGER.info("Creating clone from vdisk `{0}` with new name `{1}`"
                                            .format(vdisk_name, clone_vdisk_name))
                base_vdisks.append(str(vdisk_guid))
                ScrubbingChecks.LOGGER.info("Stored old base vdisk guid in list: {0}".format(vdisk_guid))
                vdisk_guid = VDiskSetup.create_clone(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name,
                                                     new_vdisk_name=clone_vdisk_name,
                                                     storagerouter_ip=storagedriver.storage_ip, api=api)['vdisk_guid']
                vdisk_name = clone_vdisk_name

            ScrubbingChecks.LOGGER.info("Fetching vdisk object with name {0} and guid {1}"
                                        .format(vdisk_name, vdisk_guid))
            vdisk_obj = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            try:
                # write the double amount of possible diskspace
                for _ in xrange(2):
                    client.run(["fio", "--name=test", "--filename=/mnt/{0}/{1}.raw"
                               .format(vpool.name, vdisk_name),
                                "--ioengine=libaio", "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1",
                                "--size={0}b".format(ScrubbingChecks.SIZE_VDISK)])

            except subprocess.CalledProcessError:
                raise VDiskNotFoundError("VDisk `/mnt/{0}/{1}.raw` does not seem to be present "
                                         "or has problems on storagerouter `{2}`".format(vpool.name, vdisk_name,
                                                                                         storagedriver.storage_ip))
            # create snapshot after writing test
            VDiskSetup.create_snapshot(snapshot_name=vdisk_name+'-snapshot01', vdisk_name=vdisk_name+'.raw',
                                       vpool_name=vpool.name, api=api, consistent=False, sticky=False)

            # save the stored data to the mapper
            stored_data = vdisk_obj.storagedriver_client.info_volume(str(vdisk_obj.volume_id)).stored
            vdisk_stored_mapper[vdisk_guid] = stored_data
            ScrubbingChecks.LOGGER.info("Logged `{0}` stored data for VDisk `{1}` in mapper"
                                        .format(stored_data, vdisk_guid))

        return vdisk_stored_mapper, base_vdisks


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
