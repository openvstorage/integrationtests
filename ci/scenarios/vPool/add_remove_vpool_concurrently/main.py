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
import random

from ci.api_lib.helpers.backend import BackendHelper
from ci.api_lib.helpers.exceptions import VPoolNotFoundError
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.setup.vpool import VPoolSetup
from ci.api_lib.validate.roles import RoleValidation
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.extensions.generic.logger import Logger


class VPoolTester(CIConstants):
    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_add_extend_remove_vpool_concur"
    NUMBER_OF_VPOOLS = 3
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))

    def __init__(self):
        VPoolTester.LOGGER.info("Initializing concurrent vpool testing.")
        VPoolTester.valid_storagerouters = []
        for storagerouter in StoragerouterHelper.get_storagerouters():
            try:
                RoleValidation.check_required_roles(VPoolSetup.REQUIRED_VPOOL_ROLES, storagerouter.ip, "LOCAL")
                VPoolTester.valid_storagerouters.append(storagerouter)
                VPoolTester.LOGGER.info('Added storagerouter {0} to list of eligible storagerouters'.format(storagerouter.ip))
            except RuntimeError:
                pass
        assert len(VPoolTester.valid_storagerouters) >= 1, 'At least one storagerouter with valid roles required: none found!'
        VPoolTester.alba_backends = BackendHelper.get_alba_backends()
        assert len(VPoolTester.alba_backends) >= 1, 'At least one backend required, none found!'
        VPoolTester.vpools = []
        super(VPoolTester, self).__init__()

    @classmethod
    def add_vpools(cls):
        """
        Add a predefined number of vpools concurrently.
        """
        VPoolTester.LOGGER.info("Starting to validate addition of vpools concurrently.")
        tasks = {}
        for i in range(1, VPoolTester.NUMBER_OF_VPOOLS + 1):
            sr = VPoolTester.valid_storagerouters[(i - 1) % len(VPoolTester.valid_storagerouters)]
            vpool_name = 'vpool{0}'.format(i)
            data = json.dumps({'call_parameters': {'backend_info': {'preset': 'default',
                                                                    'alba_backend_guid': random.choice(VPoolTester.alba_backends).guid},
                                                   'config_params': {'cluster_size': 4, 'dtl_mode': 'a_sync', 'dtl_transport': 'tcp', 'sco_size': 4, 'write_buffer': 128},
                                                   'connection_info': {'host': ''},  # Empty host will force the framework to fill in local details
                                                   'fragment_cache_on_read': False,
                                                   'fragment_cache_on_write': False,
                                                   'parallelism': {'proxies': 1},
                                                   'storage_ip': sr.ip,
                                                   'storagerouter_ip': sr.ip,
                                                   'vpool_name': vpool_name,
                                                   'writecache_size': 5}})
            tasks[vpool_name] = cls.api.post(api='storagerouters/{0}/add_vpool'.format(sr.guid), data=data)
        for vpool_name, task_id in tasks.iteritems():
            addition_completed = cls.api.wait_for_task(task_id, timeout=600)[0]
            if addition_completed is True:
                VPoolTester.LOGGER.info('Creation of {0} completed.'.format(vpool_name))
            try:
                vpool = VPoolHelper.get_vpool_by_name(vpool_name)
                if vpool.STATUSES.RUNNING is 'RUNNING':
                    VPoolTester.vpools.append(vpool)
            except VPoolNotFoundError:
                VPoolTester.LOGGER.exception('Unable to find vpool with name {0}.'.format(vpool_name))
        assert VPoolTester.NUMBER_OF_VPOOLS == len(VPoolTester.vpools), 'Failed to create {0} vpools: only {1} found!'.format(VPoolTester.NUMBER_OF_VPOOLS, len(VPoolTester.vpools))
    @classmethod
    def remove_vpools(cls):
        """
        Method to remove all vpools
        """
        VPoolTester.LOGGER.info("Starting to validate removal of vpools concurrently.")
        dels = {}
        for vpool in VPoolTester.vpools:
            for storagedriver in vpool.storagedrivers:
                dels[vpool.guid] = cls.api.post(api='vpools/{0}/shrink_vpool'.format(vpool.guid), data=json.dumps({'storagerouter_guid': storagedriver.storagerouter_guid}))
        for vpool_guid, task_id in dels.iteritems():
            deletion_completed = cls.api.wait_for_task(task_id, timeout=600)[0]
            if deletion_completed is True:
                VPoolTester.LOGGER.info('vpool with guid {0} is deleted successfully'.format(vpool_guid))
        VPoolTester.LOGGER.info('Concurrent removal of vpools finished.')
        leftover_vpools = []
        for vpool in VPoolTester.vpools:
            try:
                VPoolHelper.get_vpool_by_name(vpool.name)
                leftover_vpools.append(vpool)
            except VPoolNotFoundError:
                pass
        if len(leftover_vpools) > 0:
            raise RuntimeError('Following vpools are not removed: {}.'.format(', '.join([vpool.name for vpool in leftover_vpools])))

    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(self, blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        """
        _ = blocked
        try:
            self.add_vpools()
        except Exception:
            self.LOGGER.exception('Error during add_vpools, cleaning up.')
            raise
        finally:
            self.remove_vpools()
        self.LOGGER.info('Concurrent vpool addition and removal test finished.')


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VPoolTester().main(blocked)


if __name__ == "__main__":
    run()
