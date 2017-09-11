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
from ci.api_lib.helpers.api import OVSClient
from ci.api_lib.helpers.exceptions import VDiskNotFoundError
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.logger import Logger
from ovs.extensions.generic.sshclient import SSHClient


class VDiskDeploymentChecks(CIConstants):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_vdisk_deployment"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    PREFIX = "integration-tests-deployment-"
    VDISK_SIZES = [200 * 1024 ** 3, 400 * 1024 ** 3, 800 * 1024 ** 3, 1600 * 1024 ** 3, 3200 * 1024 ** 3, 6400 * 1024 ** 3]
    VDISK_CREATE_TIMEOUT = 150
    VDISK_CHECK_TIMEOUT = 10
    VDISK_CHECK_AMOUNT = 30
    REQUIRED_PACKAGES = ['qemu', 'coreutils']

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME, log_components=[{'framework': ['ovs-workers']}, 'volumedriver'])
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
        return VDiskDeploymentChecks.validate_vdisk_deployment()

    @classmethod
    def validate_vdisk_deployment(cls):
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 1 storagerouter
        :return:
        """
        VDiskDeploymentChecks.LOGGER.info("Starting to validate the vdisk deployment")

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        vpool = vpools[0]  # just pick the first vpool you find
        assert len(vpool.storagedrivers) >= 1, "Not enough Storagedrivers to test"

        # setup base information
        storagedriver = vpool.storagedrivers[0]
        protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
        storage_ip = storagedriver.storage_ip
        edge_port = storagedriver.ports['edge']
        client = SSHClient(storagedriver.storage_ip, username='root')
        # =======
        # VIA API
        # =======
        for size in VDiskDeploymentChecks.VDISK_SIZES:
            api_disk_name = VDiskDeploymentChecks.PREFIX+str(size)+'-api'
            VDiskDeploymentChecks.LOGGER.info("Starting to create vdisk `{0}` on vPool `{1}` with size `{2}` "
                                              "on node `{3}`".format(api_disk_name, vpool.name, size,
                                                                     storagedriver.storagerouter.ip))
            VDiskSetup.create_vdisk(vdisk_name=api_disk_name+'.raw', vpool_name=vpool.name, size=size,
                                    storagerouter_ip=storagedriver.storagerouter.ip, api=api,
                                    timeout=VDiskDeploymentChecks.VDISK_CREATE_TIMEOUT)
            VDiskDeploymentChecks.LOGGER.info("Finished creating vdisk `{0}`".format(api_disk_name))
            VDiskDeploymentChecks._check_vdisk(vdisk_name=api_disk_name, vpool_name=vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(api_disk_name))
            VDiskRemover.remove_vdisk_by_name(api_disk_name, vpool.name, api)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(api_disk_name))

        # ========
        # VIA QEMU
        # ========
        for size in VDiskDeploymentChecks.VDISK_SIZES:
            qemu_disk_name = VDiskDeploymentChecks.PREFIX+str(size)+'-qemu'
            edge_info = {'port': edge_port,
                         'protocol': protocol,
                         'ip': storage_ip,
                         }
            if SystemHelper.get_ovs_version(storagedriver.storagerouter) == 'ee':
                edge_info.update(cls.get_shell_user())
            VMHandler.create_image(client, qemu_disk_name, size, edge_info)
            VDiskDeploymentChecks.LOGGER.info("Finished creating vdisk `{0}`".format(qemu_disk_name))
            VDiskDeploymentChecks._check_vdisk(vdisk_name=qemu_disk_name, vpool_name=vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(qemu_disk_name))
            VDiskRemover.remove_vdisk_by_name(qemu_disk_name, vpool.name, api)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(qemu_disk_name))

        # ============
        # VIA TRUNCATE
        # ============
        for size in VDiskDeploymentChecks.VDISK_SIZES:
            truncate_disk_name = VDiskDeploymentChecks.PREFIX+str(size)+'-trunc'
            VDiskDeploymentChecks.LOGGER.info("Starting to create vdisk `{0}` on vPool `{1}` on node `{2}` "
                                              "with size `{3}`".format(truncate_disk_name, vpool.name, storagedriver.storage_ip, size))
            client.run(["truncate", "-s", str(size), "/mnt/{0}/{1}.raw".format(vpool.name, truncate_disk_name)])
            VDiskDeploymentChecks.LOGGER.info("Finished creating vdisk `{0}`".format(truncate_disk_name))
            VDiskDeploymentChecks._check_vdisk(vdisk_name=truncate_disk_name, vpool_name=vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(truncate_disk_name))
            VDiskRemover.remove_vdisk_by_name(truncate_disk_name, vpool.name, api)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(truncate_disk_name))
        VDiskDeploymentChecks.LOGGER.info("Finished to validate the vdisk deployment")

    @staticmethod
    def _check_vdisk(vdisk_name, vpool_name, timeout=VDISK_CHECK_TIMEOUT, times=VDISK_CHECK_AMOUNT):
        """
        Check if a certain vdisk exists

        :param vdisk_name: name of a created vdisk (without file extension suffix)
        :type vdisk_name: str
        :param vpool_name: name of existing vpool
        :type vpool_name: str
        :param timeout: timeout during check of a newly created vdisk
        :type timeout: int
        :param times: check x amount of times with a timeout (total max time = timeout * times)
        :type times: int
        :return: does the vdisk exists after total max time
        :rtype: bool
        """

        for i in xrange(times):
            try:
                VDiskHelper.get_vdisk_by_name(vdisk_name=vdisk_name+'.raw', vpool_name=vpool_name)
            except VDiskNotFoundError:
                VDiskDeploymentChecks.LOGGER.info("VDisk with name `{0}` on vPool `{1}` not yet found, "
                                                  "sleeping for {2} seconds. Try {3}/{4}".format(vdisk_name,
                                                                                                 vpool_name, timeout,
                                                                                                 i+1, times))
                time.sleep(timeout)
            else:
                VDiskDeploymentChecks.LOGGER.info("VDisk with name `{0}` on vPool `{1}` found on try {2}/{3} "
                                                  "after {4} seconds".format(vdisk_name, vpool_name, i+1, times,
                                                                             i+1 * timeout))
                return True
        raise VDiskNotFoundError("VDisk with name {0} has not been found on vPool {1} after {2} seconds"
                                 .format(vdisk_name, vpool_name, times * timeout))


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VDiskDeploymentChecks().main(blocked)

if __name__ == "__main__":
    run()
