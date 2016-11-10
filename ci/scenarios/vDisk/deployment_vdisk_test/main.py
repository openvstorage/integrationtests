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
from ci.helpers.vpool import VPoolHelper
from ci.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ovs.extensions.generic.sshclient import SSHClient


class VDiskDeploymentChecks(object):

    CASE_TYPE = 'FUNCTIONALITY'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_vdisk_deployment")
    PREFIX = "integration-tests-deployment-"
    VDISK_SIZES = [2147483648000, 4294967296000, 8589934592000, 17179869184000, 34359738368000, 68719476736000]
    VDISK_CREATE_TIMEOUT = 180
    VDISK_SLEEP_BEFORE_DELETE = 8
    REQUIRED_PACKAGES = ['qemu', 'coreutils']

    def __init__(self):
        pass

    @staticmethod
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
        if not blocked:
            try:
                VDiskDeploymentChecks.validate_vdisk_deployment()
                return {'status': 'PASSED', 'case_type': VDiskDeploymentChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                VDiskDeploymentChecks.LOGGER.error("Fio on vdisk checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': VDiskDeploymentChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': VDiskDeploymentChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_vdisk_deployment():
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 1 storagerouter

        :return:
        """

        VDiskDeploymentChecks.LOGGER.info("Starting to validate the fio on vdisks")

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

        # check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver.storage_ip,
                                                             VDiskDeploymentChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

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
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(api_disk_name))
            VDiskRemover.remove_vdisk_by_name(api_disk_name+'.raw', vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(api_disk_name))

        # ========
        # VIA QEMU
        # ========
        for size in VDiskDeploymentChecks.VDISK_SIZES:
            qemu_disk_name = VDiskDeploymentChecks.PREFIX+str(size)+'-qemu'
            create_command = "qemu-img create openvstorage+{0}:{1}:{2}/{3} {4}B".format(protocol, storage_ip, edge_port,
                                                                                        qemu_disk_name, size)
            VDiskDeploymentChecks.LOGGER.info("Starting to create vdisk `{0}` on node `{1}` "
                                              "with edgeport `{2}` and size `{3}` via `{4}`"
                                              .format(qemu_disk_name, storage_ip, edge_port, size, protocol))
            client.run(create_command)
            VDiskDeploymentChecks.LOGGER.info("Finished creating vdisk `{0}`".format(qemu_disk_name))
            time.sleep(VDiskDeploymentChecks.VDISK_SLEEP_BEFORE_DELETE)
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(qemu_disk_name))
            VDiskRemover.remove_vdisk_by_name(qemu_disk_name+'.raw', vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(qemu_disk_name))

        # ============
        # VIA TRUNCATE
        # ============
        for size in VDiskDeploymentChecks.VDISK_SIZES:
            truncate_disk_name = VDiskDeploymentChecks.PREFIX+str(size)+'-trunc'
            VDiskDeploymentChecks.LOGGER.info("Starting to create vdisk `{0}` on vPool `{1}` on node `{2}` "
                                              "with size `{3}`".format(truncate_disk_name, vpool.name,
                                                                       storagedriver.storage_ip, size))
            client.run("truncate -s {0} /mnt/{1}/{2}.raw".format(size, vpool.name, truncate_disk_name))
            VDiskDeploymentChecks.LOGGER.info("Finished creating vdisk `{0}`".format(truncate_disk_name))
            time.sleep(VDiskDeploymentChecks.VDISK_SLEEP_BEFORE_DELETE)
            VDiskDeploymentChecks.LOGGER.info("Starting to delete vdisk `{0}`".format(truncate_disk_name))
            VDiskRemover.remove_vdisk_by_name(truncate_disk_name+'.raw', vpool.name)
            VDiskDeploymentChecks.LOGGER.info("Finished deleting vdisk `{0}`".format(truncate_disk_name))


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
