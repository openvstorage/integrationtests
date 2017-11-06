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
        self.LOGGER.info("Initializing concurrent vpool testing.")
        self.valid_storagerouters = []
        for storagerouter in StoragerouterHelper.get_storagerouters():
            try:
                RoleValidation.check_required_roles(VPoolSetup.REQUIRED_VPOOL_ROLES, storagerouter.ip, "LOCAL")
                self.valid_storagerouters.append(storagerouter)
                self.LOGGER.info("Added {0} to list of eligible storagerouters.".format(storagerouter.ip))
            except RuntimeError as ex:
                self.LOGGER.warning("Did not add {0} to list of eligible storagerouters: {1}.".format(storagerouter.ip, ex))

        assert len(self.valid_storagerouters) >= 1, 'At least one storagerouter with valid roles required: none found!'

        self.alba_backends = BackendHelper.get_alba_backends()
        assert len(self.alba_backends) >= 1, 'At least one backend required, none found!'
        self.vpools = []
        super(VPoolTester, self).__init__()

    def add_vpools(self):
        """
        Add a predefined number of vpools concurrently.
        """
        self.LOGGER.info("Starting to validate addition of vpools concurrently.")
        tasks = {}
        for i in range(1, self.NUMBER_OF_VPOOLS + 1):
            sr = self.valid_storagerouters[(i - 1) % len(self.valid_storagerouters) ]
            vpool_name = 'vpool{0}'.format(i)
            data = json.dumps({'call_parameters': {'backend_info': {'preset': 'default',
                                                                    'alba_backend_guid': random.choice(self.alba_backends).guid},
                                                   'config_params': {'cluster_size': 4, 'dtl_mode': 'a_sync', 'dtl_transport': 'tcp', 'sco_size': 4, 'write_buffer': 128},
                                                   'connection_info': {'host': ''},  # Empty host will force the framework to fill in local details
                                                   'fragment_cache_on_read': False,
                                                   'fragment_cache_on_write': False,
                                                   'parallelism': {'proxies': 1},
                                                   'storage_ip': sr.ip,
                                                   'storagerouter_ip': sr.ip,
                                                   'vpool_name': vpool_name,
                                                   'writecache_size': 5}})
            tasks[vpool_name] = self.api.post(api='storagerouters/{0}/add_vpool'.format(sr.guid), data=data)
        for vpool_name, task in tasks.iteritems():
            self.LOGGER.info('-> {0} running: {1}'.format(vpool_name, self.api.wait_for_task(task)[0]))
            try:
                self.vpools.append(VPoolHelper.get_vpool_by_name(vpool_name))
            except VPoolNotFoundError as ex:
                self.LOGGER.exception('Unable to find {0}: {1}.'.format(vpool_name, ex))

        assert self.NUMBER_OF_VPOOLS == len(self.vpools), 'Failed to create {0} vpools: only {1} found!'.format(self.NUMBER_OF_VPOOLS, len(self.vpools))

    def remove_vpools(self):
        """
        Method to remove all vpools
        """
        self.LOGGER.info("Starting to validate removal of vpools concurrently.")
        dels = {}
        for vpool in self.vpools:
            dels[vpool.guid] = self.api.post(api='vpools/{0}/shrink_vpool'.format(vpool.guid), data=json.dumps({'storagerouter_guid': vpool.storagedrivers[0].storagerouter.guid}))
        for vpool_name, task in dels.iteritems():
            self.LOGGER.info('-> deleting vpool nr {0}: {1}'.format(vpool_name, self.api.wait_for_task(task)[0]))
        self.LOGGER.info("Concurrent removal of vpools finished.")
        leftover_vpools = []
        for vpool in self.vpools:
            try:
                VPoolHelper.get_vpool_by_name(vpool.name)
                leftover_vpools.append(vpool)
            except VPoolNotFoundError:
                pass
        if len(leftover_vpools) > 0:
            raise RuntimeError('Following vpools are not removed: {}'.format(', '.join([vpool.name for vpool in leftover_vpools])))



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
            self.LOGGER.exception('Error during add vpools, cleaning up.')
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
