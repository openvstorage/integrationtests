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
from ci.main import CONFIG_LOC
from ci.helpers.api import OVSClient
from ci.setup.vpool import VPoolSetup
from ci.remove.vpool import VPoolRemover
from ovs.log.log_handler import LogHandler
from ci.helpers.backend import BackendHelper
from ci.validate.roles import RoleValidation
from ci.helpers.storagerouter import StoragerouterHelper


class AddRemoveVPool(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_add_extend_remove_vpool")
    ADD_EXTEND_REMOVE_VPOOL_TIMEOUT = 60
    VPOOL_NAME = "integrationtests-vpool"
    PRESET_NAME = "default"

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

        assert len(storagerouter_ips) > 1, "We need at least 2 storagerouters with valid roles: {0}".format()
        alba_backends = BackendHelper.get_alba_backends()
        assert len(alba_backends) >= 2, "We need at least 2 or more backends!"

        hdd_backend = alba_backends[0]
        ssd_backend = alba_backends[1]

        # alba accelerated alba for vpool
        fragment_cache_nonaccel_config = {
            "strategy": {"cache_on_read": False, "cache_on_write": False},
            "location": "disk"
        }

        # normal alba backend for vpool
        fragment_cache_accel_config = {
            "strategy": {"cache_on_read": False, "cache_on_write": False},
            "location": "backend",
            "backend": {
                "name": ssd_backend.name,
                "preset": AddRemoveVPool.PRESET_NAME
            }
        }

        # add/extend vpool with normal backend
        for storagerouter_ip in storagerouter_ips:
            AddRemoveVPool.LOGGER.info("Add/extend vpool with normal backend with vPool `{0}` on storagerouter `{1}`"
                                       .format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
            assert AddRemoveVPool._add_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME,
                                             fragment_cache_cfg=fragment_cache_nonaccel_config, api=api,
                                             albabackend_name=hdd_backend.name, timeout=timeout,
                                             preset_name=AddRemoveVPool.PRESET_NAME, storagerouter_ip=storagerouter_ip)

        # delete vpool with normal backend
        for storagerouter_ip in storagerouter_ips:
            AddRemoveVPool.LOGGER.info("Deleting vpool with normal backend with vPool `{0}` on storagerouter `{1}`"
                                       .format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
            assert VPoolRemover.remove_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME, storagerouter_ip=storagerouter_ip,
                                             api=api, timeout=timeout)

        # add/extend vpool with accelerated backend
        for storagerouter_ip in storagerouter_ips:
            AddRemoveVPool.LOGGER.info("Add/extend vpool with accelerated backend with vPool `{0}` "
                                       "on storagerouter `{1}`".format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
            assert AddRemoveVPool._add_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME,
                                             fragment_cache_cfg=fragment_cache_accel_config, api=api,
                                             albabackend_name=hdd_backend.name, timeout=timeout,
                                             preset_name=AddRemoveVPool.PRESET_NAME, storagerouter_ip=storagerouter_ip)

        # delete vpool with accelerated backend
        for storagerouter_ip in storagerouter_ips:
            AddRemoveVPool.LOGGER.info("Deleting vpool with accelerated backend with vPool `{0}` on storagerouter `{1}`"
                                       .format(AddRemoveVPool.VPOOL_NAME, storagerouter_ip))
            assert VPoolRemover.remove_vpool(vpool_name=AddRemoveVPool.VPOOL_NAME, storagerouter_ip=storagerouter_ip,
                                             api=api, timeout=timeout)

        AddRemoveVPool.LOGGER.info("Finished to validate add-extend-remove vpool")

    @staticmethod
    def _add_vpool(vpool_name, fragment_cache_cfg, api, storagerouter_ip, albabackend_name,
                   preset_name, timeout):
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
            "global_write_buffer": 1,
            "global_read_buffer": 0,
            "deduplication": "non_dedupe",
            "dtl_transport": "tcp",
            "dtl_mode": "a_sync"
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