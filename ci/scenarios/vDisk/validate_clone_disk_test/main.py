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
from ci.main import CONFIG_LOC
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.validate.vdisk import VDiskValidation
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.log.log_handler import LogHandler


class VDiskCloneChecks(CIConstants):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_vdisk_clone"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    PREFIX = "integration-tests-clone-"
    VDISK_SIZE = 10737418240  # 10GB
    CLONE_CREATE_TIMEOUT = 180
    CLONE_SLEEP_AFTER_CREATE = 5
    CLONE_SLEEP_BEFORE_CHECK = 5
    CLONE_SLEEP_BEFORE_DELETE = 5

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
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
        return VDiskCloneChecks.validate_vdisk_clone()

    @staticmethod
    def validate_vdisk_clone():
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 2 storagerouters

        :return:
        """

        VDiskCloneChecks.LOGGER.info("Starting to validate clone vdisks")

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        try:
            vpool = next((vpool for vpool in vpools if len(vpool.storagedrivers) >= 2))
        except StopIteration:
            assert False, "Not enough Storagedrivers to test"

        # setup base information
        storagedriver_source = vpool.storagedrivers[0]
        storagedriver_destination = vpool.storagedrivers[1]

        # create required vdisk for test
        vdisk_name = VDiskCloneChecks.PREFIX+'1'
        assert VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                       size=VDiskCloneChecks.VDISK_SIZE, api=api,
                                       storagerouter_ip=storagedriver_source.storagerouter.ip) is not None
        time.sleep(VDiskCloneChecks.CLONE_SLEEP_AFTER_CREATE)

        #################################
        # clone vdisk from new snapshot #
        #################################

        new_vdisk_name = vdisk_name+'-clone-nosnapshot'
        assert VDiskSetup.create_clone(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name,
                                       new_vdisk_name=new_vdisk_name+'.raw',
                                       storagerouter_ip=storagedriver_destination.storagerouter.ip, api=api) is not None
        time.sleep(VDiskCloneChecks.CLONE_SLEEP_BEFORE_CHECK)
        assert VDiskValidation.check_required_vdisk(vdisk_name=new_vdisk_name+'.raw', vpool_name=vpool.name) is not None
        time.sleep(VDiskCloneChecks.CLONE_SLEEP_BEFORE_DELETE)
        assert VDiskRemover.remove_vdisk_by_name(vdisk_name=new_vdisk_name + '.raw', vpool_name=vpool.name)

        ######################################
        # clone vdisk from existing snapshot #
        ######################################

        new_vdisk_name = vdisk_name + '-clone-snapshot'
        snapshot_id = VDiskSetup.create_snapshot(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name,
                                                 snapshot_name=VDiskCloneChecks.PREFIX+'snapshot', api=api)
        assert VDiskSetup.create_clone(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                       new_vdisk_name=new_vdisk_name + '.raw',
                                       storagerouter_ip=storagedriver_destination.storagerouter.ip, api=api,
                                       snapshot_id=snapshot_id)
        time.sleep(VDiskCloneChecks.CLONE_SLEEP_BEFORE_CHECK)
        assert VDiskValidation.check_required_vdisk(vdisk_name=new_vdisk_name + '.raw',
                                                    vpool_name=vpool.name) is not None
        time.sleep(VDiskCloneChecks.CLONE_SLEEP_BEFORE_DELETE)
        assert VDiskRemover.remove_vdisk_by_name(vdisk_name=new_vdisk_name + '.raw', vpool_name=vpool.name)

        # remove parent vdisk
        assert VDiskRemover.remove_vdisk_by_name(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name)

        VDiskCloneChecks.LOGGER.info("Finished validating clone vdisks")


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
