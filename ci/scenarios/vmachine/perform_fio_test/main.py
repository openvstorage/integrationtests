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
import subprocess
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.api_lib.helpers.exceptions import ImageConvertError, VDiskNotFoundError
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.autotests import gather_results
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class FioOnVDiskChecks(object):

    CASE_TYPE = 'AT_QUICK'
    TEST = "ci_scenario_fio_on_vdisk"
    LOGGER = LogHandler.get(source="scenario", name=TEST)
    VDISK_SIZE = 1073741824  # 1 GB
    AMOUNT_VDISKS = 5
    AMOUNT_TO_WRITE = 10  # in MegaByte
    PREFIX = "integration-tests-fio-"
    REQUIRED_PACKAGES = ['blktap-openvstorage-utils', 'qemu', 'fio']
    VDISK_CHECK_TIMEOUT = 10
    VDISK_CHECK_AMOUNT = 30

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST)
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """
        return FioOnVDiskChecks.validate_fio_on_vdisks()

    @staticmethod
    def validate_fio_on_vdisks(amount_vdisks=AMOUNT_VDISKS, amount_to_write=AMOUNT_TO_WRITE):
        """
        Validate if fio works on a vdisk via edge

        INFO:
            * 1 vPool should be available on 1 storagerouter
            * Removes all tap-ctl connections with vdisk prefix equal to STATIC variable `FioOnVDiskChecks.VDISK_NAME`

        :param amount_vdisks: amount of vdisks to deploy and scrub
        :type amount_vdisks: int
        :param amount_to_write: amount of MegaByte to write on a single vdisk
        :type amount_to_write: int
        :return:
        """

        FioOnVDiskChecks.LOGGER.info("Starting to validate the fio on vdisks")

        with open(SETTINGS_LOC, "r") as JSON_SETTINGS:
            settings = json.load(JSON_SETTINGS)

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        vpool = vpools[0]  # just pick the first vpool you find
        assert len(vpool.storagedrivers) >= 1, "Not enough Storagedrivers to test"

        # check if enough images available
        images = settings['images']
        assert len(images) >= 1, "Not enough images in `{0}`".format(SETTINGS_LOC)

        # setup base information
        storagedriver = vpool.storagedrivers[0]
        client = SSHClient(storagedriver.storage_ip, username='root')

        # check if there are missing packages
        missing_packages = SystemHelper.get_missing_packages(storagedriver.storage_ip,
                                                             FioOnVDiskChecks.REQUIRED_PACKAGES)
        assert len(missing_packages) == 0, "Missing {0} package(s) on `{1}`: {2}"\
            .format(len(missing_packages), storagedriver.storage_ip, missing_packages)

        # check if image exists
        assert client.file_exists(images[0]), "Image `{0}` does not exists on `{1}`!"\
            .format(images[0], storagedriver.storage_ip)
        image_path = images[0]

        # =================
        # VIA EDGE / BLKTAP
        # =================
        for vdisk in xrange(amount_vdisks):
            try:
                disk_name = FioOnVDiskChecks.PREFIX+str(vdisk)+"-blktap"
                protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
                storage_ip = storagedriver.storage_ip
                edge_port = storagedriver.ports['edge']

                FioOnVDiskChecks.LOGGER.info("Starting to convert disk `{0}` to storagedriver `{1}` with port `{2}`, "
                                             "protocol `{3}` & diskname `{4}`"
                                             .format(image_path, storage_ip, edge_port, protocol, disk_name))
                FioOnVDiskChecks.LOGGER.info("Converting image...")
                client.run(["qemu-img", "convert", image_path, "openvstorage+{0}:{1}:{2}/{3}"
                           .format(protocol, storage_ip, edge_port, disk_name)])
                FioOnVDiskChecks.LOGGER.info("Creating a tap blk device for image...")
                tap_dir = client.run(["tap-ctl", "create", "-a", "openvstorage+{0}:{1}:{2}/{3}"
                                     .format(protocol, storage_ip, edge_port, disk_name)])
                FioOnVDiskChecks.LOGGER.info("Created a tap blk device at location `{0}`".format(tap_dir))
                FioOnVDiskChecks.LOGGER.info("Finished putting vdisk `{0}` in the vPool!".format(disk_name))
                FioOnVDiskChecks.LOGGER.info("Starting fio test on vdisk `{0}` with blktap `{1}`".format(disk_name,
                                                                                                         tap_dir))
                client.run(["fio", "--name=write-test", "--filename={0}".format(tap_dir), "--ioengine=libaio",
                            "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1", "--size={0}M".format(amount_to_write),
                            "--output-format=json", "--output={0}-write.json".format(disk_name)])
                client.run(["fio", "--name=read-test", "--filename={0}".format(tap_dir), "--ioengine=libaio",
                            "--iodepth=4", "--rw=read", "--bs=4k", "--direct=1", "--size={0}M".format(amount_to_write),
                            "--output-format=json", "--output={0}-read.json".format(disk_name)])
                FioOnVDiskChecks.LOGGER.info("Finished fio test on vdisk `{0}` with blktap `{1}`"
                                             .format(disk_name, tap_dir))
                # deleting (remaining) tapctl connections
                tap_conn = client.run("tap-ctl list | grep {0}".format(FioOnVDiskChecks.PREFIX),
                                      allow_insecure=True).split()
                if len(tap_conn) != 0:
                    FioOnVDiskChecks.LOGGER.info("Deleting tapctl connections ...".format(disk_name, tap_dir))
                    for index, tap_c in enumerate(tap_conn):
                        if 'pid' in tap_c:
                            pid = tap_c.split('=')[1]
                            minor = tap_conn[index+1].split('=')[1]
                            client.run(["tap-ctl", "destroy", "-p", pid, "-m", minor])
                else:
                    error_msg = "At least 1 blktap connection should be available " \
                                "but we found none on ip address `{0}`!".format(storage_ip)
                    FioOnVDiskChecks.LOGGER.error(error_msg)
                    raise RuntimeError(error_msg)

                # remove vdisk
                VDiskRemover.remove_vdisk_by_name(disk_name+'.raw', vpool.name)

            except subprocess.CalledProcessError as ex:
                raise ImageConvertError("Could not convert/tap image `{0}` on `{1}`, failed with error {2}"
                                        .format(image_path, storagedriver.storage_ip, ex))

        # ========
        # VIA FUSE
        # ========
        for vdisk in xrange(amount_vdisks):
            try:
                disk_name = FioOnVDiskChecks.PREFIX + str(vdisk) + "-fuse"
                disk_location = "/mnt/{0}/{1}.raw".format(vpool.name, disk_name)
                FioOnVDiskChecks.LOGGER.info("Truncating vdisk `{0}` on `{1}` vPool `{2}`..."
                                             .format(disk_name, storagedriver.storage_ip, vpool.name))
                client.run(["truncate", "-s", str(FioOnVDiskChecks.VDISK_SIZE), disk_location])
                FioOnVDiskChecks.LOGGER.info("Finished putting vdisk `{0}` in the vPool!".format(disk_name))
                FioOnVDiskChecks.LOGGER.info("Starting fio test on vdisk `{0}`".format(disk_name))
                client.run(["fio", "--name=write-test", "--filename={0}".format(disk_location), "--ioengine=libaio",
                            "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1", "--size={0}M".format(amount_to_write),
                            "--output-format=json", "--output={0}-write.json".format(disk_name)])
                client.run(["fio", "--name=read-test", "--filename={0}".format(disk_location), "--ioengine=libaio",
                            "--iodepth=4", "--rw=read", "--bs=4k", "--direct=1", "--size={0}M".format(amount_to_write),
                            "--output-format=json", "--output={0}-read.json".format(disk_name)])
                FioOnVDiskChecks.LOGGER.info("Finished fio test on vdisk `{0}` on location `{1}` with ip {2}"
                                             .format(disk_name, disk_location, storagedriver.storage_ip))
                FioOnVDiskChecks._check_vdisk(vdisk_name=disk_name, vpool_name=vpool.name)
                FioOnVDiskChecks.LOGGER.info("Removing vdisk `{0}` from the vPool!".format(disk_name))
                VDiskRemover.remove_vdisk_by_name(disk_name + '.raw', vpool.name)
                FioOnVDiskChecks.LOGGER.info("Finished removing vdisk `{0}` from the vPool!".format(disk_name))

            except subprocess.CalledProcessError as ex:
                raise ImageConvertError("Failed to truncate vdisk on vPool `{0}` on storagedriver `{1}` with error: {2}"
                                        .format(vpool.name, storagedriver.storage_ip, ex))

        FioOnVDiskChecks.LOGGER.info("Finished validating fio on vdisks")

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
                VDiskHelper.get_vdisk_by_name(vdisk_name=vdisk_name + '.raw', vpool_name=vpool_name)
            except VDiskNotFoundError:
                FioOnVDiskChecks.LOGGER.info("VDisk with name `{0}` on vPool `{1}` not yet found, "
                                             "sleeping for {2} seconds. Try {3}/{4}".format(vdisk_name,
                                                                                            vpool_name, timeout,
                                                                                            i + 1, times))
                time.sleep(timeout)
            else:
                FioOnVDiskChecks.LOGGER.info("VDisk with name `{0}` on vPool `{1}` found on try {2}/{3} "
                                             "after {4} seconds".format(vdisk_name, vpool_name, i + 1, times,
                                                                        i + 1 * timeout))
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
    return FioOnVDiskChecks().main(blocked)

if __name__ == "__main__":
    run()
