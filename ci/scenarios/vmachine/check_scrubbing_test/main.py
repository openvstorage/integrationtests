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
    SIZE_VDISK = 52428800
    PREFIX = "integration-tests-scrubbing-"
    MAX_SCRUBBING_CHECKS = 10
    SCRUBBING_TIMEOUT = 45
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
                ScrubbingChecks.validate_scrubbing()
                return {'status': 'PASSED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                ScrubbingChecks.LOGGER.error("Scrubbing checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': ScrubbingChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_scrubbing(amount_vdisks=AMOUNT_VDISKS_TO_SCRUB, size=SIZE_VDISK, amount_checks=MAX_SCRUBBING_CHECKS,
                           timeout=SCRUBBING_TIMEOUT):
        """
        Validate if scrubbing works on a vpool

        INFO: 1 vPool should be available on 1 storagerouter

        :param amount_vdisks: amount of vdisks to deploy and scrub
        :type amount_vdisks: int
        :param size: size of a single vdisk in bytes
        :type size: int
        :param amount_checks: amount of times to check if stored data has changed
        :type amount_checks: int
        :param timeout: specify a timeout
        :type timeout: int
        :return:
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
        client = SSHClient(storagedriver.storage_ip, username='root')

        # check for possible missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver.storage_ip,
                                                             ScrubbingChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

        vdisk_stored_mapper = {}
        for vdisk in xrange(amount_vdisks):
            vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=ScrubbingChecks.PREFIX+str(vdisk), vpool_name=vpool.name,
                                                 size=size, api=api, storagerouter_ip=storagedriver.storage_ip)
            vdisk_obj = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
            try:
                # write the double amount of possible diskspace
                for _ in xrange(2):
                    client.run(["fio", "--name=test", "--filename=/mnt/{0}/{1}.raw".format(vpool.name, ScrubbingChecks.PREFIX+str(vdisk)),
                                "--ioengine=libaio", "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1", "--size={0}b".format(ScrubbingChecks.SIZE_VDISK)])

            except subprocess.CalledProcessError:
                raise VDiskNotFoundError("VDisk `/mnt/{0}/{1}.raw` does not seem to be present "
                                         "or has problems on storagerouter `{2}`".format(vpool.name,
                                                                                         ScrubbingChecks.PREFIX +
                                                                                         str(vdisk),
                                                                                         storagedriver.storage_ip))
            # create snapshot after writing test
            VDiskSetup.create_snapshot(snapshot_name=ScrubbingChecks.PREFIX+str(vdisk)+'-snapshot01',
                                       vdisk_name=ScrubbingChecks.PREFIX+str(vdisk)+'.raw', vpool_name=vpool.name,
                                       api=api, consistent=False, sticky=False)

            # save the stored data to the mapper
            stored_data = vdisk_obj.storagedriver_client.info_volume(str(vdisk_obj.volume_id)).stored
            vdisk_stored_mapper[vdisk_guid] = stored_data
            ScrubbingChecks.LOGGER.info("Logged `{0}` stored data for VDisk `{1}` in mapper"
                                        .format(stored_data, vdisk_guid))

        # start scrubbing and check if scrubbed
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
                error_msg = "VDisk `{0}` should have been scrubbed but stored data != `{1} <= {2}`".format(
                        vdisk_guid, current_statistics, vdisk_stored)
                ScrubbingChecks.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)

            # commencing deleting volumes
            ScrubbingChecks.LOGGER.info("Starting to remove VDisk `{0}`".format(vdisk_guid))
            VDiskRemover.remove_vdisk(vdisk_guid)
            ScrubbingChecks.LOGGER.info("Finished removing VDisk `{0}`".format(vdisk_guid))


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
