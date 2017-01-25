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
import random
from ci.helpers.api import OVSClient
from ci.helpers.vpool import VPoolHelper
from ci.helpers.vdisk import VDiskHelper
from ci.helpers.storagedriver import StoragedriverHelper
from ci.helpers.system import SystemHelper
from ci.main import CONFIG_LOC
from ci.setup.vdisk import VDiskSetup
from ci.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler


class MigrateTester(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_vdisk_migrate_offline"
    AMOUNT_TO_WRITE = 1 * 1024 ** 3  # in MegaByte
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    SLEEP_TIME = 30
    REQUIRED_PACKAGES = ['blktap-openvstorage-utils', 'fio']
    AMOUNT_VDISKS = 5

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        status depends on attributes in class: ci.helpers.testtrailapi.TestrailResult
        case_type depends on attributes in class: ci.helpers.testtrailapi.TestrailCaseType

        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                MigrateTester._execute_test()
                return {'status': 'PASSED', 'case_type': MigrateTester.CASE_TYPE, 'errors': None}
            except Exception as ex:
                return {'status': 'FAILED', 'case_type': MigrateTester.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': MigrateTester.CASE_TYPE, 'errors': None}

    @staticmethod
    def _execute_test(amount_vdisks=AMOUNT_VDISKS):
        """
        Executes a offline migration

        :param amount_vdisks: amount of vdisks to test
        :type amount_vdisks: int
        :return:
        """

        MigrateTester.LOGGER.info("Starting offline migrate test.")

        with open(CONFIG_LOC, "r") as config_file:
            config = json.load(config_file)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        # Get a suitable vpool
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 2:
                vpool = vp
                break
        assert vpool is not None, "Not enough vPools to test. Requires 1 with at least 2 storagedrivers and found 0."

        ##########################
        # Setup base information #
        ##########################

        # Executor storagedriver_1 is current system
        std_1 = None
        for std in vpool.storagedrivers:
            if SystemHelper.get_local_storagerouter().guid == std.storagerouter_guid:
                std_1 = std
                break
        assert std_1 is not None, 'Could not find the right storagedriver for storagerouter {0}' \
            .format(SystemHelper.get_local_storagerouter().guid)

        # Get a random other storagedriver to migrate to
        std_2 = random.choice([st for st in vpool.storagedrivers if st != std_1])

        # Cache to validate properties
        values_to_check = {
            'source_std': std_1.serialize(),
            'target_std': std_2.serialize()
        }

        # Check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(std_1.storage_ip, MigrateTester.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), std_1.storage_ip, missing_packages)

        ###############################
        # start deploying & migrating #
        ###############################

        for i in xrange(amount_vdisks):

            ################
            # create vdisk #
            ################

            vdisk_name = "{0}_{1}".format(MigrateTester.TEST_NAME, i)
            try:
                vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                                     size=10*1024**3, storagerouter_ip=std_1.storagerouter.ip,
                                                     api=api)
                # Fetch to validate if it was properly created
                vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                values_to_check['vdisk'] = vdisk.serialize()
            except RuntimeError as ex:
                MigrateTester.LOGGER.info("Creation of vdisk failed: {0}".format(ex))
                raise
            else:

                ################
                # move vdisk #
                ################

                time.sleep(MigrateTester.SLEEP_TIME)
                try:
                    MigrateTester.LOGGER.info("Moving vdisk {0} from {1} to storagerouter {2}"
                                              .format(vdisk_guid, std_1.storage_ip, std_2.storage_ip))
                    VDiskSetup.move_vdisk(vdisk_guid=vdisk_guid,
                                          target_storagerouter_guid=std_2.storagerouter_guid, api=api)
                    time.sleep(MigrateTester.SLEEP_TIME)

                    #################
                    # validate move #
                    #################

                    MigrateTester.LOGGER.info("Validating move...")
                    MigrateTester._validate_move(values_to_check)
                except Exception as ex:
                    MigrateTester.LOGGER.exception('Failed during migation: {0}'.format(ex))
                    raise
                else:
                    MigrateTester._cleanup_vdisk(vdisk_name, vpool.name)

        MigrateTester.LOGGER.info("Finished offline migrate test.")

    @staticmethod
    def _validate_move(values_to_check):
        """
        Validates the move test. Checks IO, and checks for dal changes
        :param values_to_check: dict with values to validate if they updated
        :type values_to_check: dict
        :return:
        """
        # Fetch dal object
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values_to_check['target_std']['guid'])
        try:
            MigrateTester._validate_dal(values_to_check)
        except ValueError as ex:
            MigrateTester.LOGGER.warning('DAL did not automatically change after a move. Got {0}'.format(ex))
            source_std.invalidate_dynamics([])
            target_std.invalidate_dynamics([])
            # Properties should have been reloaded
            values_to_check['source_std'] = StoragedriverHelper.get_storagedriver_by_guid(
                values_to_check['source_std']['guid']).serialize()
            values_to_check['target_std'] = StoragedriverHelper.get_storagedriver_by_guid(
                values_to_check['target_std']['guid']).serialize()
            MigrateTester._validate_dal(values_to_check)

    @staticmethod
    def _validate_dal(values):
        """
        Validates the move test. Checks for dal changes
        :param values: dict with values to validate if they updated
        :type values: dict
        :return:
        """
        # Fetch them from the dal
        source_std = StoragedriverHelper.get_storagedriver_by_guid(values['source_std']['guid'])
        target_std = StoragedriverHelper.get_storagedriver_by_guid(values['target_std']['guid'])
        vdisk = VDiskHelper.get_vdisk_by_guid(values['vdisk']['guid'])
        if values['source_std'] == source_std.serialize():
            # DAL values did not update - expecting a change in vdisks_guids
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            # Expecting changes in vdisks_guids
            if vdisk.guid in source_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for source storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for source storagedriver.')
        if values['target_std'] == target_std.serialize():
            raise ValueError('Expecting changes in the target Storagedriver but nothing changed.')
        else:
            if vdisk.guid not in target_std.vdisks_guids:
                raise ValueError('Vdisks guids were not updated after move for target storagedriver.')
            else:
                MigrateTester.LOGGER.info('All properties are updated for target storagedriver.')
        if values["vdisk"] == vdisk.serialize():
            raise ValueError('Expecting changes in the vdisk but nothing changed.')
        else:
            if vdisk.storagerouter_guid == target_std.storagerouter.guid:
                MigrateTester.LOGGER.info('All properties are updated for vdisk.')
            else:
                ValueError('Expected {0} but found {1} for vdisk.storagerouter_guid'.format(vdisk.storagerouter_guid,
                                                                                            vdisk.storagerouter_guid))
        MigrateTester.LOGGER.info('Move vdisk was successful according to the dal (which fetches volumedriver info).')

    @staticmethod
    def _cleanup_vdisk(vdisk_name, vpool_name, blocking=True):
        """
        Attempt to cleanup vdisk
        :param vdisk_name: name of the vdisk
        :param vpool_name: name of the vpool
        :param blocking: boolean to determine whether errors should raise or not
        :return:
        """
        # Cleanup vdisk
        try:
            VDiskRemover.remove_vdisk_by_name('{0}.raw'.format(vdisk_name), vpool_name)
        except Exception as ex:
            MigrateTester.LOGGER.error(str(ex))
            if blocking is True:
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

    return MigrateTester().main(blocked)

if __name__ == "__main__":
    print run()
