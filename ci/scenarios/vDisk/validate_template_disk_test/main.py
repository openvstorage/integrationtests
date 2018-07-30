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

from ci.api_lib.helpers.api import HttpException
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class VDiskTemplateChecks(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = "ci_scenario_vdisk_template"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    PREFIX = "integration-tests-template"
    VDISK_SIZE = 10 * 1024 ** 3  # 10GB
    TEMPLATE_CREATE_TIMEOUT = 180
    TEMPLATE_SLEEP_AFTER_CREATE = 5
    TEMPLATE_SLEEP_BEFORE_CHECK = 5
    TEMPLATE_SLEEP_BEFORE_DELETE = 5

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
        _ = blocked
        return VDiskTemplateChecks.validate_vdisk_clone()

    @classmethod
    def validate_vdisk_clone(cls):
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 2 storagerouters
        :return:
        """
        cls.LOGGER.info("Starting to validate template vdisks")
        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"
        try:
            vpool = next((vpool for vpool in vpools if len(vpool.storagedrivers) >= 2))
        except StopIteration:
            assert False, "Not enough Storagedrivers to test"
        # setup base information
        storagedriver_source = vpool.storagedrivers[0]
        vdisks = []
        try:
            # create required vdisk for test
            parent_vdisk_name = '{0}_{1}'.format(cls.PREFIX, str(1).zfill(3))
            parent_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_vdisk(vdisk_name=parent_vdisk_name,
                                        vpool_name=vpool.name,
                                        size=cls.VDISK_SIZE,
                                        storagerouter_ip=storagedriver_source.storagerouter.ip))
            vdisks.append(parent_vdisk)
            time.sleep(cls.TEMPLATE_SLEEP_AFTER_CREATE)
            # Create vdisk template  #
            VDiskSetup.set_vdisk_as_template(vdisk_name=parent_vdisk_name, vpool_name=vpool.name)
            time.sleep(cls.TEMPLATE_SLEEP_AFTER_CREATE)
            clone_vdisk_name = '{0}_from-template'.format(parent_vdisk_name)
            clone_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_from_template(vdisk_name=parent_vdisk_name,
                                                vpool_name=vpool.name,
                                                new_vdisk_name=clone_vdisk_name,
                                                storagerouter_ip=storagedriver_source.storagerouter.ip)['vdisk_guid'])
            vdisks.append(clone_vdisk)
            time.sleep(cls.TEMPLATE_SLEEP_BEFORE_DELETE)
            try:
                # try to delete template with clones (should fail) #
                VDiskRemover.remove_vtemplate_by_name(vdisk_name=parent_vdisk_name, vpool_name=vpool.name)
                error_msg = "Removing vtemplate `{0}` should have failed!"
                cls.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)
            except HttpException:
                cls.LOGGER.info("Removing vtemplate `{0}` has failed as expected (because of leftover clones)!".format(parent_vdisk_name))
        finally:
            while len(vdisks) > 0:
                vdisk = vdisks.pop()
                VDiskRemover.remove_vdisk(vdisk.guid)
        try:
            # template vdisk from clone (should fail) #
            parent_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_vdisk(vdisk_name=parent_vdisk_name,
                                        vpool_name=vpool.name,
                                        size=cls.VDISK_SIZE,
                                        storagerouter_ip=storagedriver_source.storagerouter.ip))
            vdisks.append(parent_vdisk)
            # create a clone from the vdisk
            clone_vdisk_name = '{0}_clone'.format(parent_vdisk_name)
            cloned_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_clone(vdisk_name=parent_vdisk_name,
                                        vpool_name=vpool.name,
                                        new_vdisk_name=clone_vdisk_name,
                                        storagerouter_ip=storagedriver_source.storagerouter.ip)['vdisk_guid'])
            vdisks.append(cloned_vdisk)
            # try to create a vTemplate from a clone
            try:
                VDiskSetup.set_vdisk_as_template(vdisk_name=clone_vdisk_name, vpool_name=vpool.name)
                error_msg = "Setting vdisk `{0}` as template should have failed!".format(clone_vdisk_name)
                cls.LOGGER.error(error_msg)
                raise RuntimeError(error_msg)
            except RuntimeError:
                cls.LOGGER.info("Setting vdisk `{0}` as template failed as expected (because vdisk is clone)!".format(clone_vdisk_name))
        finally:
            parent_vdisks = []
            while len(vdisks) > 0:  # Remove clones first
                vdisk = vdisks.pop()
                if vdisk.parent_vdisk_guid is None:
                    parent_vdisks.append(vdisk)
                    continue
                VDiskRemover.remove_vdisk(vdisk.guid)
            for parent_vdisk in parent_vdisks:
                VDiskRemover.remove_vdisk(parent_vdisk.guid)
        cls.LOGGER.info("Finished to validate template vdisks")


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
