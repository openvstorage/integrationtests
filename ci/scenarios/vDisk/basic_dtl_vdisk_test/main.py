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
import random
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.domain import DomainHelper
from ci.api_lib.helpers.storagedriver import StoragedriverHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class DTLChecks(CIConstants):

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_basic_dtl"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    SIZE_VDISK = 52428800  # 50 MB
    VDISK_NAME = "integration-tests-basic-dtl"

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}, 'volumedriver'])
    def main(blocked):
        """
        Run all required methods for the test
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return DTLChecks._execute_test()

    @classmethod
    def _execute_test(cls):
        """
        Validate if DTL is configured as desired
        REQUIREMENTS:
        * 1 vPool should be available with 1 storagedriver
        * 1 vPool should be available with 2 or more storagedrivers in 2 separate domains
        OPTIONAL:
        * 1 vPool with 1 storagedriver with disabled DTL
        :return:
        """
        cls.LOGGER.info("Starting to validate the basic DTL")
        ##########################
        # get deployment details #
        ##########################
        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        # Get a suitable vpools
        vpool_single_sd = None
        vpool_multi_sd = None
        vpool_dtl_disabled = None
        for vp in VPoolHelper.get_vpools():
            if vp.configuration['dtl_mode'] != VPoolHelper.DtlStatus.DISABLED:
                if len(vp.storagedrivers) == 1 and vpool_single_sd is None:
                    vpool_single_sd = vp
                    cls.LOGGER.info("vPool `{0}` has been chosen for SINGLE vPool DTL tests".format(vp.name))
                elif len(vp.storagedrivers) >= 2 and vpool_multi_sd is None:
                    vpool_multi_sd = vp
                    cls.LOGGER.info("vPool `{0}` has been chosen for MULTI vPool DTL tests".format(vp.name))
                else:
                    cls.LOGGER.info("vPool `{0}` is not suited for tests".format(vp.name))
            else:
                cls.LOGGER.info("vPool `{0}` with DISABLED DTL is available and will be tested!".format(vp.name))
                vpool_dtl_disabled = vp

        assert vpool_single_sd is not None, "A vPool should be available with 1 storagedriver"
        assert vpool_multi_sd is not None, "A vPool should be available with 2 or more storagedrivers"

        # pick a random storagedriver
        storagedriver_single = vpool_single_sd.storagedrivers[0]
        storagedriver_multi = random.choice(vpool_multi_sd.storagedrivers)
        storagedrivers = [storagedriver_single, storagedriver_multi]

        # check disabled DTL
        storagedriver_disabled_dtl = None
        if vpool_dtl_disabled is not None:
            storagedriver_disabled_dtl = random.choice(vpool_dtl_disabled.storagedrivers)
            storagedrivers.append(storagedriver_disabled_dtl)

        # key = amount of storagedrivers or a_s
        # value = list with the vpool & storagedriver to test
        vpools_to_test = {
            1: [{"vpool": vpool_single_sd, "storagedriver": storagedriver_single}],
            2: [{"vpool": vpool_multi_sd, "storagedriver": storagedriver_multi}]
        }

        # check if disabled DTL vpool needs to be added
        if vpool_dtl_disabled is not None:
            a_s = len(vpool_dtl_disabled.storagedrivers)
            v_s = {"vpool": vpool_dtl_disabled, "storagedriver": storagedriver_disabled_dtl}
            if a_s in vpools_to_test:
                vpools_to_test[a_s].append(v_s)
            else:
                vpools_to_test[a_s] = [v_s]

        ##############
        # start test #
        ##############

        for a_s, vpools in vpools_to_test.iteritems():
            start = time.time()
            for vpool in vpools:

                cls.LOGGER.info("Starting DTL test with vPool {0} and {1} storagedrivers".format(vpool['vpool'].name, len(vpool['vpool'].storagedrivers)))
                vdisk_name = "{0}-{1}-{2}".format(cls.VDISK_NAME, vpool['vpool'].name, str(len(vpool['vpool'].storagedrivers)))
                try:
                    vdisk_guid = VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool['vpool'].name,
                                                         size=cls.SIZE_VDISK,
                                                         storagerouter_ip=vpool['storagedriver'].storagerouter.ip)
                    # Fetch to validate if it was properly created
                    vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid=vdisk_guid)
                except TimeOutError:
                    cls.LOGGER.error("Creation of the vDisk has timed out.")
                    raise
                except RuntimeError as ex:
                    cls.LOGGER.info("Creation of vDisk failed: {0}".format(ex))
                    raise
                else:
                    #####################################
                    # check DTL status after deployment #
                    #####################################

                    correct_msg = "vDisk {0} with {1} storagedriver(s) has correct DTL status: ".format(vdisk_name, a_s)
                    if a_s == 1 and vdisk.dtl_status == VDiskHelper.DtlStatus.STANDALONE:
                        cls.LOGGER.info(correct_msg + vdisk.dtl_status)
                    elif a_s >= 2 and vdisk.dtl_status == VDiskHelper.DtlStatus.SYNC:
                        cls.LOGGER.info(correct_msg + vdisk.dtl_status)
                    elif vdisk.dtl_status == VDiskHelper.DtlStatus.DISABLED and vpool['vpool'].configuration['dtl_mode'] == VPoolHelper.DtlStatus.DISABLED:
                        cls.LOGGER.info(correct_msg + " Note: vdisk DTL is disabled but vPool DTL is also disabled!")
                    else:
                        error_msg = "vDisk {0} with {1} storagedriver(s) has WRONG DTL status: {2}".format(vdisk_name, a_s, vdisk.dtl_status)
                        cls.LOGGER.error(error_msg)
                        raise RuntimeError(error_msg)

                    ################################
                    # try to change the DTL config #
                    ################################

                    base_config = {
                        "sco_size": 4,
                        "dtl_mode": VPoolHelper.DtlStatus.SYNC,
                        "write_buffer": 512
                    }
                    if a_s == 1:
                        ########################################################################################
                        # change config to domain with non existing storagedrivers of this vpool (should fail) #
                        ########################################################################################
                        cls.LOGGER.info("Starting test: change config to domain with non existing storagedrivers "
                                              "of this vpool (should fail)")
                        base_config['dtl_target'] = [random.choice([domain_guid for domain_guid in
                                                                   DomainHelper.get_domain_guids()
                                                                   if domain_guid not in vpool['storagedriver'].
                                                                   storagerouter.regular_domains])]
                        cls.LOGGER.info("Changing dtl_target to: {0}"
                                              .format(DomainHelper.get_domain_by_guid(domain_guid=base_config['dtl_target'][0]).name))
                        try:
                            cls.LOGGER.info(base_config)
                            VDiskSetup.set_config_params(vdisk_name=vdisk_name + '.raw', vpool_name=vpool['vpool'].name, config=base_config)
                            error_msg = "Changing config to a domain with non existing storagedrivers should have failed with vdisk: {0}!".format(vdisk_name)
                            cls.LOGGER.error(error_msg)
                            raise Exception(error_msg)
                        except TimeOutError:
                            cls.LOGGER.error("Changing config to a same domain with only 1 storagedriver has timed out.")
                            raise
                        except RuntimeError:
                            cls.LOGGER.info("Changing config to a domain with non existing storagedrivers has failed as expected!")

                        ##############################################################################################
                        # change config to domain where there are other storagedrivers but not of ours (should fail) #
                        ##############################################################################################
                        cls.LOGGER.info("Starting test: change config to domain where there are other storagedrivers but not of ours (should fail)")

                        filtered_domains = list(set(DomainHelper.get_domain_guids()) - set(vpool['storagedriver'].storagerouter.regular_domains))
                        base_config['dtl_target'] = [filtered_domains[0]]
                        cls.LOGGER.info("Current vdisk domain location: {0}"
                                              .format(DomainHelper.get_domain_by_guid(domain_guid=vpool['storagedriver'].storagerouter.regular_domains[0]).name))
                        cls.LOGGER.info("Changing dtl_target to: {0}".format(DomainHelper.get_domain_by_guid(domain_guid=base_config['dtl_target'][0]).name))
                        try:
                            VDiskSetup.set_config_params(vdisk_name=vdisk_name + '.raw', vpool_name=vpool['vpool'].name, config=base_config)
                            error_msg = "Changing config to a same domain with only 1 storagedriver should have failed with vdisk: {0}!".format(vdisk_name)
                            cls.LOGGER.error(error_msg)
                            raise Exception(error_msg)
                        except TimeOutError:
                            cls.LOGGER.error("Changing config to a domain with non existing storagedrivers has timed out.")
                            raise
                        except RuntimeError:
                            cls.LOGGER.info("Changing config to a same domain with only 1 storagedriver has failed as expected!")
                    elif a_s >= 2:
                        #######################################################################
                        # change config to domain with active storagedrivers (should succeed) #
                        #######################################################################
                        cls.LOGGER.info("Starting test: change config to domain with active storagedrivers (should succeed)")

                        # change current target domain to other target domain
                        current_vdisk_domains = StoragedriverHelper.get_storagedriver_by_id(storagedriver_id=vdisk.storagedriver_id).storagerouter.regular_domains
                        cls.LOGGER.info("Currently the vdisk is living in: {0}".format(current_vdisk_domains))
                        vpool_domains = VPoolHelper.get_domains_by_vpool(vpool_name=vdisk.vpool.name)
                        cls.LOGGER.info("Currently the vpool {0} is available in: {1}".format(vdisk.vpool.name, vpool_domains))
                        future_domains = list(set(vpool_domains) - set(current_vdisk_domains))
                        cls.LOGGER.info("DTL will be moved to other domain: {0}".format(future_domains))
                        base_config['dtl_target'] = future_domains

                        # change settings
                        try:
                            VDiskSetup.set_config_params(vdisk_name=vdisk_name + '.raw', vpool_name=vpool['vpool'].name, config=base_config)
                        except TimeOutError:
                            cls.LOGGER.error("Changing config to a same domain with only 1 storagedriver has timed out.")
                            raise
                        except RuntimeError:
                            cls.LOGGER.error("Changing config to a same domain with only 1 storagedriver was unsuccesful!")
                            raise
                        cls.LOGGER.info("Changing config to a same domain with only 1 storagedriver was successful!")

                    cls.LOGGER.info("Removing vDisk {0}".format(vdisk.name))
                    VDiskRemover.remove_vdisk(vdisk_guid=vdisk.guid)
                    cls.LOGGER.info("Finished removing vDisk {0}".format(vdisk.name))

            end = time.time()

            # display run time
            cls.LOGGER.info("Run testing the DTL took {0} seconds".format(int(end - start)))

        cls.LOGGER.info("Finished to validate the basic DTL")


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return DTLChecks().main(blocked)

if __name__ == "__main__":
    run()
