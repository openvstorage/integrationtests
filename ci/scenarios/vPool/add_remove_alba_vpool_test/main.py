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
from ci.api_lib.helpers.api import TimeOutError
from ci.api_lib.helpers.backend import BackendHelper
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.backend import BackendRemover
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.remove.vpool import VPoolRemover
from ci.api_lib.setup.backend import BackendSetup
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.setup.vpool import VPoolSetup
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.validate.roles import RoleValidation
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ovs.dal.exceptions import ObjectNotFoundException
from ovs.extensions.generic.logger import Logger


class AddRemoveVPool(CIConstants):

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_add_extend_remove_vpool"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    ADD_EXTEND_REMOVE_VPOOL_TIMEOUT = 60
    ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING = 300
    VPOOL_NAME = "integrationtests-vpool"
    PRESET = {"name": "ciaddremovevpool",
              "compression": "snappy",
              "encryption": "none",
              "policies": [[1, 1, 1, 1]],
              "fragment_size": 2 * 1024 ** 2}
    PREFIX = "integration-tests-vpool-"
    VDISK_SIZE = 1 * 1024 ** 3
    VDISK_CREATE_TIMEOUT = 60
    PRESET_CREATE_TIMEOUT = 60
    PRESET_REMOVE_TIMEOUT = 60
    CHECK_VPOOL_TIMEOUT = 10
    AMOUNT_CHECK_VPOOL = 30

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}])
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        _ = blocked
        return AddRemoveVPool.validate_add_extend_remove_vpool()

    @classmethod
    def validate_add_extend_remove_vpool(cls, timeout=ADD_EXTEND_REMOVE_VPOOL_TIMEOUT):
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
        cls.LOGGER.info("Starting to validate add-extend-remove vpool")


        storagerouter_ips = []
        for storagerouter_ip in StoragerouterHelper.get_storagerouter_ips():
            try:
                RoleValidation.check_required_roles(VPoolSetup.REQUIRED_VPOOL_ROLES, storagerouter_ip, "LOCAL")
                storagerouter_ips.append(storagerouter_ip)
                cls.LOGGER.info("Added `{0}` to list of eligible storagerouters".format(storagerouter_ip))
            except RuntimeError as ex:
                cls.LOGGER.warning("Did not add `{0}` to list of eligible "
                                              "storagerouters because: {1}".format(storagerouter_ip, ex))
                pass

        # Filter storagerouters without required roles
        assert len(storagerouter_ips) > 1, "We need at least 2 storagerouters with valid roles: {0}"\
            .format(storagerouter_ips)
        alba_backends = BackendHelper.get_alba_backends()
        assert len(alba_backends) >= 2, "We need at least 2 or more backends!"

        # Global vdisk details
        vdisk_deployment_ip = storagerouter_ips[0]

        # Determine backends (2)
        hdd_backend = alba_backends[0]
        ssd_backend = alba_backends[1]

        # Add preset to all alba_backends (we only use the first two as seen above)
        for alba_backend in alba_backends[0:2]:
            cls.LOGGER.info("Adding custom preset to backend {0}".format(alba_backend.name))
            preset_result = BackendSetup.add_preset(albabackend_name=alba_backend.name,
                                                    preset_details=cls.PRESET,
                                                    timeout=cls.PRESET_CREATE_TIMEOUT)
            assert preset_result is True, 'Failed to add preset to backend {0}'.format(alba_backend.name)
            cls.LOGGER.info("Finished adding custom preset to backend {0}".format(alba_backend.name))

        # Vpool configs, regressing https://github.com/openvstorage/alba/issues/560 & more
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
                    "preset": cls.PRESET['name']
                }
            }
        }

        for cfg_name, cfg in vpool_configs.iteritems():
            # Create vpool
            block_cache_cfg = None
            if SystemHelper.get_ovs_version().lower() == 'ee':
                block_cache_cfg = cfg
            for storagerouter_ip in storagerouter_ips:
                cls.LOGGER.info("Add/extend vPool `{0}` on storagerouter `{1}`".format(cls.VPOOL_NAME, storagerouter_ip))
                start = time.time()
                try:
                    cls._add_vpool(vpool_name=cls.VPOOL_NAME, fragment_cache_cfg=cfg,
                                              block_cache_cfg=block_cache_cfg, albabackend_name=hdd_backend.name, timeout=timeout,
                                              preset_name=cls.PRESET['name'], storagerouter_ip=storagerouter_ip)
                except TimeOutError:
                    cls.LOGGER.warning('Adding/extending the vpool has timed out after {0}s. Polling for another {1}s.'
                                                  .format(timeout, cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING - timeout))
                    # Lets be a bit forgiving and give the fwk 5 mins to actually complete the task
                    vpool = VPoolHelper.get_vpool_by_name(cls.VPOOL_NAME)
                    while vpool.status != 'RUNNING':
                        if time.time() - start > cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING:
                            raise RuntimeError('The vpool was not added or extended after {0}s'.format(cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING))
                        cls.LOGGER.warning('Vpool status is still {0} after {1}s.'.format(vpool.status, time.time() - start))
                        time.sleep(1)
                        vpool.discard()
                    cls.LOGGER.warning('The vpool was added or extended after {0}s.'.format(time.time() - start))
                except RuntimeError as ex:
                    cls.LOGGER.error('Adding/extending the vpool has failed with {0}.'.format(str(ex)))
                    raise
                # Check #proxies
                vpool = VPoolHelper.get_vpool_by_name(cls.VPOOL_NAME)
                for storagedriver in vpool.storagedrivers:
                    assert len(storagedriver.alba_proxies) == 2, 'The vpool did not get setup with 2 proxies. Found {} instead.'.format(len(storagedriver.alba_proxies))
            # Deploy a vdisk
            vdisk_name = cls.PREFIX + cfg_name
            cls.LOGGER.info("Starting to create vdisk `{0}` on vPool `{1}` with size `{2}` on node `{3}`"
                                       .format(vdisk_name, cls.VPOOL_NAME, cls.VDISK_SIZE, vdisk_deployment_ip))
            VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw',
                                    vpool_name=cls.VPOOL_NAME,
                                    size=cls.VDISK_SIZE,
                                    storagerouter_ip=vdisk_deployment_ip,
                                    timeout=cls.VDISK_CREATE_TIMEOUT)
            cls.LOGGER.info("Finished creating vdisk `{0}`".format(vdisk_name))
            cls.LOGGER.info("Starting to delete vdisk `{0}`".format(vdisk_name))
            VDiskRemover.remove_vdisk_by_name(vdisk_name, cls.VPOOL_NAME)
            cls.LOGGER.info("Finished deleting vdisk `{0}`".format(vdisk_name))

            # Delete vpool
            for storagerouter_ip in storagerouter_ips:
                storagedrivers_to_delete = len(vpool.storagedrivers)
                cls.LOGGER.info("Deleting vpool `{0}` on storagerouter `{1}`".format(cls.VPOOL_NAME, storagerouter_ip))
                try:
                    VPoolRemover.remove_vpool(vpool_name=cls.VPOOL_NAME, storagerouter_ip=storagerouter_ip, timeout=timeout)
                except TimeOutError:
                    try:
                        vpool.discard()  # Discard is needed to update the vpool status as it was running before
                        while vpool.status != 'RUNNING':
                            cls.LOGGER.warning('Removal/shrinking the vpool has timed out after {0}s. Polling for another {1}s.'
                                                          .format(timeout, cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING - timeout))
                            if time.time() - start > cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING:
                                raise RuntimeError('The vpool was not removed or extended after {0}s'.format(cls.ADD_EXTEND_REMOVE_VPOOL_TIMEOUT_FORGIVING))
                            cls.LOGGER.warning('Vpool status is still {0} after {1}s.'.format(vpool.status, time.time() - start))
                            time.sleep(1)
                            vpool.discard()
                    except ObjectNotFoundException:
                        if storagedrivers_to_delete != 1:  # Should be last one
                            raise
                except RuntimeError as ex:
                    cls.LOGGER.error('Shrinking/removing the vpool has failed with {0}.'.format(str(ex)))
                    raise
            cls.LOGGER.info('Vpool has been fully removed.')
        # Delete presets
        for alba_backend in alba_backends[0:2]:
            cls.LOGGER.info("Removing custom preset from backend {0}".format(alba_backend.name))
            remove_preset_result = BackendRemover.remove_preset(albabackend_name=alba_backend.name,
                                                                preset_name=cls.PRESET['name'],
                                                                timeout=cls.PRESET_REMOVE_TIMEOUT)
            assert remove_preset_result is True, 'Failed to remove preset from backend {0}'.format(alba_backend.name)
            cls.LOGGER.info("Finshed removing custom preset from backend {0}".format(alba_backend.name))

        cls.LOGGER.info("Finished to validate add-extend-remove vpool")

    @classmethod
    def _add_vpool(cls, vpool_name, fragment_cache_cfg, storagerouter_ip, albabackend_name, preset_name, timeout,
                   block_cache_cfg=None, dtl_mode="a_sync", deduplication_mode="non_dedupe", dtl_transport="tcp"):
        """
        Add a vpool
        :param vpool_name: name of a vpool
        :type vpool_name: str
        :param fragment_cache_cfg: details of a vpool its fragment cache
        :type fragment_cache_cfg: dict
        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :param albabackend_name: name of a existing albabackend
        :type albabackend_name: str
        :param timeout: specify a timeout
        :type timeout: int
        :param block_cache_cfg: details of a vpool its block cache
        :type block_cache_cfg: dict
        :param preset_name: name of a existing preset
        :type preset_name: str
        :return:
        """
        vpool_cfg = {}
        if block_cache_cfg is not None:
            if not isinstance(block_cache_cfg, dict):
                raise TypeError('Block cache configuration should be a dict like the fragment cache.')
            vpool_cfg.update({"block_cache": block_cache_cfg})

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
        vpool_cfg.update({
            "backend_name": albabackend_name,
            "preset": preset_name,
            "storage_ip": storagerouter_ip,
            "fragment_cache": fragment_cache_cfg,
            "storagedriver": storagedriver_cfg
        })
        return VPoolSetup.add_vpool(vpool_name=vpool_name, vpool_details=vpool_cfg, storagerouter_ip=storagerouter_ip, timeout=timeout)


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
