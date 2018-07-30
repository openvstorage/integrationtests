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

from ci.api_lib.helpers.service import ServiceHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class VDiskTemplateChecks(CIConstants):

    CASE_TYPE = 'FUNCTIONALITY'
    TEST_NAME = "ci_scenario_advanced_vdisk_template"
    LOGGER = Logger("scenario_{0}".format(TEST_NAME))
    PREFIX = "integration-tests-advanced-template"
    VDISK_SIZE = 10 * 1024 ** 3  # 10GB
    TEMPLATE_CREATE_TIMEOUT = 180
    TEMPLATE_SLEEP_AFTER_CREATE = 5
    TEMPLATE_SLEEP_BEFORE_CHECK = 5
    TEMPLATE_SLEEP_BEFORE_DELETE = 5
    MIN_AMOUNT_VDISKS = 500
    MAX_RETRY = 2

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
        return VDiskTemplateChecks.validate_vdisks_clone()

    @classmethod
    def validate_vdisks_clone(cls):
        """
        Validate if multiple vdisks can be cloned from one template
        INFO: 1 vPool should be available with a volume potentials of 500
        :return:
        """
        cls.LOGGER.info("Starting to validate template vdisks")
        vpool = VPoolHelper.get_vpool_by_name('myvpool03')
        assert vpool is not None, "Vpool `{0}` not found".format('myvpool03')
        # setup base information
        vdisks = []
        try:
            # create required vdisk for test
            storagedriver = vpool.storagedrivers[0]
            parent_vdisk_name = cls.PREFIX
            parent_vdisk = VDiskHelper.get_vdisk_by_guid(
                VDiskSetup.create_vdisk(vdisk_name=parent_vdisk_name,
                                        vpool_name=vpool.name,
                                        size=cls.VDISK_SIZE,
                                        storagerouter_ip=storagedriver.storagerouter.ip))
            vdisks.append(parent_vdisk)
            time.sleep(cls.TEMPLATE_SLEEP_AFTER_CREATE)
            # Create vdisk template  #
            VDiskSetup.set_vdisk_as_template(vdisk_name=parent_vdisk_name, vpool_name=vpool.name)
            time.sleep(cls.TEMPLATE_SLEEP_AFTER_CREATE)
            for i in xrange(cls.MIN_AMOUNT_VDISKS):
                try:
                    storagedriver_source = next((storagedriver for storagedriver in vpool.storagedrivers if
                                                 vpool.storagedriver_client.volume_potential(
                                                     str(storagedriver.storagedriver_id)) > 0))
                except StopIteration:
                    assert False, "Not enough volume potential to test"
                clone_vdisk_name = '{0}_from-template_{1}'.format(parent_vdisk_name, str(i).zfill(3))
                cls.LOGGER.info("Creating volume `{0}` on `{1}`".format(clone_vdisk_name, storagedriver_source.storagerouter.ip))
                success = False
                retry = 0
                # Retry to create a vdisk from template after restarting the proxies
                while not success:
                    try:
                        clone_vdisk = VDiskHelper.get_vdisk_by_guid(
                            VDiskSetup.create_from_template(vdisk_name=parent_vdisk_name,
                                                            vpool_name=vpool.name,
                                                            new_vdisk_name=clone_vdisk_name,
                                                            storagerouter_ip=storagedriver_source.storagerouter.ip)['vdisk_guid'])
                        success = True
                    except RuntimeError as ex:
                        success = False
                        if retry >= cls.MAX_RETRY:
                            raise RuntimeError(ex)
                        retry += 1
                        cls.LOGGER.warning(
                            "Creating volume from template failed. Restarting the proxies. ({0}/{1})".format(retry, cls.MAX_RETRY))
                        for proxy in storagedriver_source.alba_proxies:
                            ServiceHelper.restart_service(proxy.service_guid, storagedriver_source.storagerouter)
                            time.sleep(17)

                vdisks.append(clone_vdisk)
        finally:
            while len(vdisks) > 0:
                vdisk = vdisks.pop()
                VDiskRemover.remove_vdisk(vdisk.guid)

        cls.LOGGER.info("Finished to validate advanced template vdisks")


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
