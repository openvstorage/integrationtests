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
from ci.api_lib.helpers.api import HttpException
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ovs.log.log_handler import LogHandler


class VDiskTemplateChecks(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST = "ci_scenario_vdisk_template"
    LOGGER = LogHandler.get(source="scenario", name=TEST)
    PREFIX = "integration-tests-template-"
    VDISK_SIZE = 10 * 1024 ** 3  # 10GB
    TEMPLATE_CREATE_TIMEOUT = 180
    TEMPLATE_SLEEP_AFTER_CREATE = 5
    TEMPLATE_SLEEP_BEFORE_CHECK = 5
    TEMPLATE_SLEEP_BEFORE_DELETE = 5

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST)
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
        return VDiskTemplateChecks.validate_vdisk_clone()

    @staticmethod
    def validate_vdisk_clone():
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 2 storagerouters

        :return:
        """

        VDiskTemplateChecks.LOGGER.info("Starting to validate template vdisks")

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

        # create required vdisk for test
        vdisk_name = VDiskTemplateChecks.PREFIX + '1'
        assert VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                       size=VDiskTemplateChecks.VDISK_SIZE, api=api,
                                       storagerouter_ip=storagedriver_source.storagerouter.ip) is not None
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_AFTER_CREATE)

        ##########################
        # create vdisk template  #
        ##########################

        VDiskSetup.set_vdisk_as_template(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, api=api)
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_AFTER_CREATE)
        clone_vdisk_name = vdisk_name + '-from-template'
        VDiskSetup.create_from_template(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                        new_vdisk_name=clone_vdisk_name + '.raw',
                                        storagerouter_ip=storagedriver_source.storagerouter.ip, api=api)
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_BEFORE_DELETE)

        try:
            ####################################################
            # try to delete template with clones (should fail) #
            ####################################################

            VDiskRemover.remove_vtemplate_by_name(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, api=api)
            error_msg = "Removing vtemplate `{0}` should have failed!"
            VDiskTemplateChecks.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        except HttpException:
            VDiskTemplateChecks.LOGGER.info("Removing vtemplate `{0}` has failed successfully "
                                            "(because of leftover clones)!".format(vdisk_name))

        VDiskRemover.remove_vdisk_by_name(vdisk_name=clone_vdisk_name + '.raw', vpool_name=vpool.name)
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_BEFORE_DELETE)
        VDiskRemover.remove_vtemplate_by_name(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, api=api)

        ###########################################
        # template vdisk from clone (should fail) #
        ###########################################

        # create vdisk
        VDiskSetup.create_vdisk(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name, api=api,
                                size=VDiskTemplateChecks.VDISK_SIZE,
                                storagerouter_ip=storagedriver_source.storagerouter.ip)

        # create a clone from the vdisk
        clone_vdisk_name = vdisk_name + '_clone'
        VDiskSetup.create_clone(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name,
                                new_vdisk_name=clone_vdisk_name+'.raw', api=api,
                                storagerouter_ip=storagedriver_source.storagerouter.ip)

        # try to create a vTemplate from a clone
        try:
            VDiskSetup.set_vdisk_as_template(vdisk_name=clone_vdisk_name+'.raw', vpool_name=vpool.name, api=api)
            error_msg = "Setting vdisk `{0}` as template should have failed!".format(clone_vdisk_name)
            VDiskTemplateChecks.LOGGER.error(error_msg)
            raise RuntimeError(error_msg)
        except RuntimeError:
            VDiskTemplateChecks.LOGGER.info("Setting vdisk `{0}` as template failed successfully "
                                            "(because vdisk is clone)!".format(clone_vdisk_name))

        # cleanup vdisk tree
        VDiskRemover.remove_vdisk_by_name(vdisk_name=clone_vdisk_name+'.raw', vpool_name=vpool.name)
        VDiskRemover.remove_vdisk_by_name(vdisk_name=vdisk_name+'.raw', vpool_name=vpool.name)

        VDiskTemplateChecks.LOGGER.info("Finished to validate template vdisks")


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VDiskTemplateChecks().main(blocked)

if __name__ == "__main__":
    run()
