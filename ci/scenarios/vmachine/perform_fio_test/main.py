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
import subprocess
from ci.main import CONFIG_LOC
from ci.main import SETTINGS_LOC
from ci.helpers.api import OVSClient
from ci.setup.vdisk import VDiskSetup
from ci.helpers.vpool import VPoolHelper
from ci.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler
from ci.helpers.system import SystemHelper
from ci.helpers.exceptions import ImageConvertError
from ovs.extensions.generic.sshclient import SSHClient


class FioOnVDiskChecks(object):

    CASE_TYPE = 'AT_QUICK'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_fio_on_vdisk")
    VDISK_SIZE = 1073741824  # 1 GB
    AMOUNT_VDISKS = 3
    AMOUNT_TO_WRITE = 10  # in MegaByte
    PREFIX = "integration-tests-fio-"
    REQUIRED_PACKAGES = ['blktap-openvstorage-utils', 'qemu', 'fio']

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
                FioOnVDiskChecks.validate_fio_on_vdisks()
                return {'status': 'PASSED', 'case_type': FioOnVDiskChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                FioOnVDiskChecks.LOGGER.error("Fio on vdisk checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': FioOnVDiskChecks.CASE_TYPE, 'errors': ex}
        else:
            return {'status': 'BLOCKED', 'case_type': FioOnVDiskChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_fio_on_vdisks(amount_vdisks=AMOUNT_VDISKS, amount_to_write=AMOUNT_TO_WRITE):
        """
        Validate if fio works on a vdisk via edge

        INFO:
            * 1 vPool should be available on 1 storagerouter
            * Removes all tap-ctl connections with vdisk prefix equal to STATIC variable `FioOnVDiskChecks.PREFIX`

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

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

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
        assert client.file_exists(images[0]), "Image `{0}` does not exists!".format(images[0])
        image_path = images[0]

        # deploy vdisks via edge & link blktap
        for vdisk in xrange(amount_vdisks):
            try:
                # check if image exists
                disk_name = FioOnVDiskChecks.PREFIX+str(vdisk)
                protocol = storagedriver.cluster_node_config['network_server_uri'].split(':')[0]
                storage_ip = storagedriver.storage_ip
                edge_port = storagedriver.ports['edge']

                FioOnVDiskChecks.LOGGER.info("Starting to convert disk `{0}` to storagedriver `{1}` with port `{2}`, "
                                             "protocol `{3}` & diskname `{4}`"
                                             .format(image_path, storage_ip, edge_port, protocol, disk_name))
                FioOnVDiskChecks.LOGGER.info("Converting image...")
                client.run("qemu-img convert {0} openvstorage+{1}:{2}:{3}/{4}"
                           .format(image_path, protocol, storage_ip, edge_port, disk_name))
                FioOnVDiskChecks.LOGGER.info("Creating a tap blk device for image...")
                tap_dir = client.run("tap-ctl create -a openvstorage+{0}:{1}:{2}/{3}".format(protocol, storage_ip,
                                                                                             edge_port, disk_name))
                FioOnVDiskChecks.LOGGER.info("Created a tap blk device at location `{0}`".format(tap_dir))
                FioOnVDiskChecks.LOGGER.info("Finished putting vdisk `{0}` in the vPool!".format(disk_name))
                FioOnVDiskChecks.LOGGER.info("Starting fio test on vdisk `{0}` with blktap `{1}`"
                                             .format(disk_name, tap_dir))
                client.run("fio --name=test --filename={0} --ioengine=libaio --iodepth=4 --rw=write --bs=4k "
                           "--direct=1 --size={1}M --output-format=json --output={2}.json"
                           .format(tap_dir, amount_to_write, disk_name))
                client.run("fio --name=test --filename={0} --ioengine=libaio --iodepth=4 --rw=read --bs=4k "
                           "--direct=1 --size={1}M --output-format=json --output={2}.json"
                           .format(tap_dir, amount_to_write, disk_name))
                FioOnVDiskChecks.LOGGER.info("Finished fio test on vdisk `{0}` with blktap `{1}`"
                                             .format(disk_name, tap_dir))
                # deleting (remaining) tapctl connections
                tap_conn = client.run("tap-ctl list | grep {0}".format(FioOnVDiskChecks.PREFIX)).split()
                if len(tap_conn) != 0:
                    FioOnVDiskChecks.LOGGER.info("Deleting tapctl connections ...".format(disk_name, tap_dir))
                    for index, tap_c in enumerate(tap_conn):
                        if 'pid' in tap_c:
                            pid = tap_c.split('=')[1]
                            minor = tap_conn[index+1].split('=')[1]
                            client.run("tap-ctl destroy -p {0} -m {1}".format(pid, minor))
                else:
                    error_msg = "At least 1 blktap connection should be available " \
                                "but we found none on ip address `{0}`!".format(storage_ip)
                    FioOnVDiskChecks.LOGGER.error(error_msg)
                    raise RuntimeError(error_msg)

                # remove vdisk
                VDiskRemover.remove_vdisk_by_name(disk_name+'.raw', vpool.name)

            except subprocess.CalledProcessError as ex:
                raise ImageConvertError("Could not convert/tap image `{0}` on `{1}`, failed with error {2}"
                                        .format(image_path, storage_ip, ex))

        # deploy a simple vdisk via api and delete it again
        api_disk_name = FioOnVDiskChecks.PREFIX+'api.raw'
        VDiskSetup.create_vdisk(vdisk_name=api_disk_name, vpool_name=vpool.name,
                                size=FioOnVDiskChecks.VDISK_SIZE,
                                storagerouter_ip=storagedriver.storagerouter.ip, api=api)
        VDiskRemover.remove_vdisk_by_name(api_disk_name, vpool.name)

        # @TODO: add tgt

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
