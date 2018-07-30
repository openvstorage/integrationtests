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
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class VDiskCloneChecks(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = "ci_scenario_vdisk_clone"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    PREFIX = "integration-tests-clone-"
    VDISK_SIZE = 10737418240  # 10GB
    CLONE_CREATE_TIMEOUT = 180
    CLONE_SLEEP_AFTER_CREATE = 5
    CLONE_SLEEP_BEFORE_CHECK = 5
    CLONE_SLEEP_BEFORE_DELETE = 5

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(blocked):
        """
        Run all required methods for the test
        Based on: https://github.com/openvstorage/home/issues/29 &
                  https://github.com/openvstorage/framework/issues/884

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return VDiskCloneChecks.validate_vdisk_clone()

    @classmethod
    def validate_vdisk_clone(cls):
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 2 storagerouters
        :return:
        """
        cls.LOGGER.info("Starting to validate clone vdisks")
        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"
        try:
            vpool = next((vpool for vpool in vpools if len(vpool.storagedrivers) >= 2))
        except StopIteration:
            assert False, "Not enough Storagedrivers to test"
        # Setup base information
        storagedriver_source = vpool.storagedrivers[0]
        storagedriver_destination = vpool.storagedrivers[1]

        vdisks = []
        try:
            # Create required vdisk for test
            original_vdisk_name = '{0}_{1}'.format(cls.PREFIX, str(1).zfill(3))
            cls.LOGGER.info("Creating the vdisk: {0} to clone".format(original_vdisk_name))
            original_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_vdisk(vdisk_name=original_vdisk_name,
                                        vpool_name=vpool.name,
                                        size=cls.VDISK_SIZE,
                                        storagerouter_ip=storagedriver_source.storagerouter.ip))
            vdisks.append(original_vdisk)
            time.sleep(cls.CLONE_SLEEP_AFTER_CREATE)
            ###############
            # Clone vdisk #
            ###############
            cloned_vdisk_name = original_vdisk_name+'-clone-nosnapshot'
            cloned_vdisk = VDiskHelper.get_vdisk_by_guid(VDiskSetup.create_clone(vdisk_name=original_vdisk_name,
                                                                                 vpool_name=vpool.name,
                                                                                 new_vdisk_name=cloned_vdisk_name,
                                                                                 storagerouter_ip=storagedriver_destination.storagerouter.ip)['vdisk_guid'])
            vdisks.append(cloned_vdisk)
            time.sleep(cls.CLONE_SLEEP_BEFORE_CHECK)
            ######################################
            # clone vdisk from existing snapshot #
            ######################################
            cloned_vdisk_name = original_vdisk_name + '-clone-snapshot'
            snapshot_id = VDiskSetup.create_snapshot(vdisk_name=original_vdisk_name, vpool_name=vpool.name, snapshot_name=cls.PREFIX+'snapshot')
            cloned_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_clone(vdisk_name=original_vdisk_name, vpool_name=vpool.name,
                                        new_vdisk_name=cloned_vdisk_name,
                                        storagerouter_ip=storagedriver_destination.storagerouter.ip,
                                        snapshot_id=snapshot_id)['vdisk_guid'])
            vdisks.append(cloned_vdisk)
        finally:
            VDiskRemover.remove_vdisks_with_structure(vdisks)
        cls.LOGGER.info("Finished validating clone vdisks")


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VDiskCloneChecks().main(blocked)


if __name__ == "__main__":
    run()
