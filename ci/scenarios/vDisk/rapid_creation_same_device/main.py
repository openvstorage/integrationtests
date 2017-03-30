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
import random
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ovs.lib.vdisk import VDiskController
from ovs.log.log_handler import LogHandler
from ci.autotests import gather_results


class VDiskControllerTester(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST = "ci_scenario_rapid_create_delete_same_device"
    LOGGER = LogHandler.get(source="scenario", name=TEST)

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST)
    def main(blocked):
        """
        Run all required methods for the test
        status depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.api_lib.helpers.testtrailapi.TestrailCaseType
        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        VDiskControllerTester._execute_test()

    @staticmethod
    def _execute_test():
        """
        Mimics the healthcheck creating and deleting disks with the same name/devicename back to back
        :return: None
        """
        local_sr = SystemHelper.get_local_storagerouter()
        VDiskControllerTester.LOGGER.info("Starting creation/deletion test.")
        # Elect vpool
        assert len(local_sr.storagedrivers) > 0, 'Node {0} has no storagedriver. Cannot test {1}'.format(local_sr.ip, VDiskControllerTester.TEST)
        random_storagedriver = local_sr.storagedrivers[random.randint(0, len(local_sr.storagedrivers) - 1)]
        vpool = random_storagedriver.vpool
        disk_size = 1024 ** 3
        disk_name = 'ci_scenario_rapid_create_delete_same_device'
        exceptions = []
        for loop in xrange(0, 100):
            test_passed = False
            try:
                VDiskControllerTester.LOGGER.info("Creating new disk.")
                try:
                    VDiskController.create_new(disk_name, disk_size, random_storagedriver.guid)
                except Exception as ex:
                    VDiskControllerTester.LOGGER.error('Creation failed. Got {0}'.format(str(ex)))
                    exceptions.append('Creation failed. Got {0}'.format(str(ex)))
                    continue
                VDiskControllerTester.LOGGER.info("Fetching new disk.")
                try:
                    vdisk = VDiskHelper.get_vdisk_by_name('{0}.raw'.format(disk_name), vpool.name)
                except Exception as ex:
                    VDiskControllerTester.LOGGER.error('Fetch failed. Got {0}'.format(str(ex)))
                    exceptions.append('Fetch failed. Got {0}'.format(str(ex)))
                    continue
                VDiskControllerTester.LOGGER.info("Deleting new disk.")
                try:
                    VDiskController.delete(vdisk_guid=vdisk.guid)
                except Exception as ex:
                    VDiskControllerTester.LOGGER.error('Delete failed. Got {0}'.format(str(ex)))
                    exceptions.append('Delete failed. Got {0}'.format(str(ex)))
                test_passed = True
            except Exception as ex:
                VDiskControllerTester.LOGGER.error('Unexpected exception occurred during the the loop. Got {0}.'.format(str(ex)))
            finally:
                try:
                    VDiskControllerTester._cleanup_vdisk(disk_name, vpool.name, not test_passed)
                except Exception as ex:
                    VDiskControllerTester.LOGGER.error("Auto cleanup failed with {0}.".format(str(ex)))
                    exceptions.append('Auto cleanup failed. Got {0}'.format(str(ex)))

        assert len(exceptions) == 0, 'Exception occurred during the creation of vdisks with the same devicename. Got {0}'.format(', '.join(exceptions))

        VDiskControllerTester.LOGGER.info("Finished create/delete test.")

    @staticmethod
    def _cleanup_vdisk(vdisk_name, vpool_name, fail=True):
        """
        Attempt to cleanup vdisk
        :param vdisk_name: name of the vdisk
        :param vpool_name: name of the vpool
        :param fail: boolean to determine whether errors should raise or not
        :return:
        """
        # Cleanup vdisk using the controller
        try:
            VDiskRemover.remove_vdisk_by_name('{0}.raw'.format(vdisk_name), vpool_name)
        except Exception as ex:
            VDiskControllerTester.LOGGER.error(str(ex))
            if fail is True:
                raise
            else:
                pass


def run(blocked=False):
    """
    Run a test
    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VDiskControllerTester().main(blocked)

if __name__ == "__main__":
    print run()
