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
from ci.helpers.api import OVSClient
from ci.setup.vdisk import VDiskSetup
from ci.setup.vpool import VPoolSetup
from ci.helpers.vpool import VPoolHelper
from ci.remove.vpool import VPoolRemover
from ci.remove.vdisk import VDiskRemover
from ci.setup.backend import BackendSetup
from ovs.log.log_handler import LogHandler
from ci.remove.backend import BackendRemover
from ci.helpers.backend import BackendHelper
from ci.validate.roles import RoleValidation
from ci.helpers.storagerouter import StoragerouterHelper


class AddRemoveVPool(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_add_extend_remove_vpool")
    ADD_EXTEND_REMOVE_VPOOL_TIMEOUT = 60
    VPOOL_NAME = "integrationtests-vpool"
    PRESET = \
        {
            "name": "ciaddremovevpool",
            "compression": "snappy",
            "encryption": "none",
            "policies": [
              [
                1,1,1,1
              ]
            ],
            "fragment_size": 2097152
        }
    PREFIX = "integration-tests-vpool-"
    VDISK_SIZE = 1073741824  # 1 GB
    VDISK_CREATE_TIMEOUT = 60
    PRESET_CREATE_TIMEOUT = 60
    PRESET_REMOVE_TIMEOUT = 60
    CHECK_VPOOL_TIMEOUT = 10
    AMOUNT_CHECK_VPOOL = 30

    def __init__(self):
        pass

    @staticmethod
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        if not blocked:
            try:
                AddRemoveVPool.validate_add_extend_remove_vpool()
                return {'status': 'PASSED', 'case_type': AddRemoveVPool.CASE_TYPE, 'errors': None}
            except Exception as ex:
                AddRemoveVPool.LOGGER.error("Add-extend-remove vPool failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': AddRemoveVPool.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': AddRemoveVPool.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_add_extend_remove_vpool(timeout=ADD_EXTEND_REMOVE_VPOOL_TIMEOUT):
        """
        Validate if we can add, extend and/or remove a vPool, testing the following scenarios:
            * Normal with no accelerated backend
            * Accelerated vPool with hdd_backend & ssd_backend

        INFO:
            * at least 2 storagerouters should be available
            * at least 2 backends should be available with default preset

        :param timeout: specify a timeout
        :type timeout: int
        :return:
        """

        AddRemoveVPool.LOGGER.info("Starting to validate add-extend-remove vpool")

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        storagerouter_ips = []
        for storagerouter_ip in StoragerouterHelper.get_storagerouter_ips():
            try:
                RoleValidation.check_required_roles(VPoolSetup.REQUIRED_VPOOL_ROLES, storagerouter_ip, "LOCAL")
                storagerouter_ips.append(storagerouter_ip)
                AddRemoveVPool.LOGGER.info("Added `{0}` to list of eligible storagerouters".format(storagerouter_ip))
            except RuntimeError as ex:
                AddRemoveVPool.LOGGER.warning("Did not add `{0}` to list of eligible "
                                              "storagerouters because: {1}".format(storagerouter_ip, ex))
                pass

        # filter storagerouters without required roles
        assert len(storagerouter_ips) > 1, "We need at least 2 storagerouters with valid roles: {0}"\
            .format(storagerouter_ips)
        alba_backends = BackendHelper.get_alba_backends()
        assert len(alba_backends) >= 2, "We need at least 2 or more backends!"

        # global vdisk details
        vdisk_deployment_ip = storagerouter_ips[0]

        # determine backends (2)
        hdd_backend = alba_backends[0]
        ssd_backend = alba_backends[1]

        # add preset to all alba_backends (we only use the first two as seen above)
        for alba_backend in alba_backends[0:2]:
            AddRemoveVPool.LOGGER.info("Adding custom preset to backend {0}".format(alba_backend.name))
            assert BackendSetup.add_preset(albabackend_name=alba_backend.name, preset_details=AddRemoveVPool.PRESET,
                                           api=api, timeout=AddRemoveVPool.PRESET_CREATE_TIMEOUT), \
                'Failed to add preset to backend {0}'.format(alba_backend.name)
            AddRemoveVPool.LOGGER.info("Finshed adding custom preset to backend {0}".format(alba_backend.name))

        # vpool configs, regressing https://github.com/openvstorage/alba/issues/560 & more
        vpool_configs = {
            "no_fragment_cache_on_disk": {
                "strategy": {"cache_on_read": False, "cache_on_write": False},
                "location": "disk"
            },
            "no_fragment_cache_on_accel": {
                "strategy": {"cache_on_read": False, "cache_on_write": False},
                "location": "backend",
                "backend": {
                    "name": ssd_backend.name,
                    "preset": AddRemoveVPool.PRESET['name']
                }
            }
        }

        for cfg_name, cfg in vpool_configs.iteritems():
            # create vpool
            for storagerouter_ip in storagerouter_ips:
                AddRemoveVPool.LOGGER.info("Add/extend vPool `{0}` on storagerouter `{1}`"
                                           .format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
                assert AddRemoveVPool._add_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME,
                                                 fragment_cache_cfg=cfg, api=api,
                                                 albabackend_name=hdd_backend.name, timeout=timeout,
                                                 preset_name=AddRemoveVPool.PRESET['name'],
                                                 storagerouter_ip=storagerouter_ip)

            # deploy a vdisk
            vdisk_name = AddRemoveVPool.PREFIX + cfg_name
            AddRemoveVPool.LOGGER.info("Starting to create vdisk `{0}` on vPool `{1}` with size `{2}` "
                                       "on node `{3}`".format(vdisk_name, AddRemoveVPool.VPOOL_NAME,
                                                              AddRemoveVPool.VDISK_SIZE, vdisk_deployment_ip))
            VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=AddRemoveVPool.VPOOL_NAME,
                                    size=AddRemoveVPool.VDISK_SIZE,
                                    storagerouter_ip=vdisk_deployment_ip, api=api,
                                    timeout=AddRemoveVPool.VDISK_CREATE_TIMEOUT)
            AddRemoveVPool.LOGGER.info("Finished creating vdisk `{0}`".format(vdisk_name))
            AddRemoveVPool.LOGGER.info("Starting to delete vdisk `{0}`".format(vdisk_name))
            VDiskRemover.remove_vdisk_by_name(vdisk_name + '.raw', AddRemoveVPool.VPOOL_NAME)
            AddRemoveVPool.LOGGER.info("Finished deleting vdisk `{0}`".format(vdisk_name))

            # delete vpool
            for storagerouter_ip in storagerouter_ips:
                AddRemoveVPool.LOGGER.info("Deleting vpool `{0}` on storagerouter `{1}`"
                                           .format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
                AddRemoveVPool._check_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME)
                assert VPoolRemover.remove_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME,
                                                 storagerouter_ip=storagerouter_ip,
                                                 api=api, timeout=timeout)

        # delete presets
        for alba_backend in alba_backends[0:2]:
            AddRemoveVPool.LOGGER.info("Removing custom preset from backend {0}".format(alba_backend.name))
            assert BackendRemover.remove_preset(albabackend_name=alba_backend.name,
                                                preset_name=AddRemoveVPool.PRESET['name'],
                                                api=api, timeout=AddRemoveVPool.PRESET_REMOVE_TIMEOUT), \
                'Failed to remove preset from backend {0}'.format(alba_backend.name)
            AddRemoveVPool.LOGGER.info("Finshed removing custom preset from backend {0}".format(alba_backend.name))

        AddRemoveVPool.LOGGER.info("Finished to validate add-extend-remove vpool")

    @staticmethod
    def _check_vpool(vpool_name, timeout=CHECK_VPOOL_TIMEOUT, amount_checks=AMOUNT_CHECK_VPOOL):
        """
        Check if the vPool is in running state with a while loop
        MAX TIME = timeout * amount_checks

        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :param timeout: max timeout between checks
        :type timeout: int
        :param amount_checks: max amount of checks before throwing error
        :type amount_checks: int
        :return: bool on success, RuntimeError on failure
        :rtype: bool
        :raises: RuntimeError
        """

        AddRemoveVPool.LOGGER.info("Starting to check if vPool `{0}` is in RUNNING state".format(vpool_name))
        amount_checked = 0
        while amount_checked <= amount_checks:
            status = VPoolHelper.get_vpool_by_name(vpool_name=vpool_name).status
            if status == 'RUNNING':
                AddRemoveVPool.LOGGER.info("vPool `{0}` is in RUNNING state on try {1}/{2}!"
                                           .format(vpool_name, amount_checked, amount_checks))
                return True
            else:
                AddRemoveVPool.LOGGER.info("vPool `{0}` is NOT in RUNNING state, but in `{4}`! "
                                           "Sleeping for {1} seconds, try {2}/{3}".format(vpool_name, timeout,
                                                                                          amount_checked, amount_checks,
                                                                                          status))
                time.sleep(timeout)

        error_msg = "VPool `{0}` failed to go into RUNNING state after {1} seconds!"\
                    .format(vpool_name, timeout * amount_checks)
        AddRemoveVPool.LOGGER.error(error_msg)
        raise RuntimeError(error_msg)

    @staticmethod
    def _add_vpool(vpool_name, fragment_cache_cfg, api, storagerouter_ip, albabackend_name,
                   preset_name, timeout, dtl_mode="a_sync", deduplication_mode="non_dedupe", dtl_transport="tcp"):
        """
        Add a vpool

        :param vpool_name: name of a vpool
        :type vpool_name: str
        :param fragment_cache_cfg: details of a vpool its fragment cache
        :type fragment_cache_cfg: dict
        :param api: fragment_cache_cfg a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param albabackend_name: name of a existing albabackend
        :type albabackend_name: str
        :param timeout: specify a timeout
        :type timeout: int
        :param preset_name: name of a existing preset
        :type preset_name: str
        :return:
        """

        storagedriver_cfg = {
            "sco_size": 4,
            "cluster_size": 4,
            "volume_write_buffer": 512,
            "strategy": "none",
            "global_write_buffer": 2,
            "global_read_buffer": 0,
            "deduplication": deduplication_mode,
            "dtl_transport": dtl_transport,
            "dtl_mode": dtl_mode
        }

        vpool_cfg = {
            "backend_name": albabackend_name,
            "preset": preset_name,
            "storage_ip": storagerouter_ip,
            "fragment_cache": fragment_cache_cfg,
            "storagedriver": storagedriver_cfg
        }

        return VPoolSetup.add_vpool(vpool_name=vpool_name, vpool_details=vpool_cfg, api=api,
                                    storagerouter_ip=storagerouter_ip, albabackend_name=albabackend_name,
                                    timeout=timeout)


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return AddRemoveVPool().main(blocked)

if __name__ == "__main__":
    run()
