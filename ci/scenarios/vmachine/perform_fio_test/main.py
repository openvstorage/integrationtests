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
from ci.api_lib.helpers.exceptions import VDiskNotFoundError
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.system import SystemHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.autotests import gather_results
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ci.scenario_helpers.vm_handler import VMHandler
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class FioOnVDiskChecks(CIConstants):
    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "ci_scenario_fio_on_vdisk"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)
    VDISK_SIZE = 10 * 1024 ** 3
    AMOUNT_VDISKS = 5
    AMOUNT_TO_WRITE = 10 * 1024 ** 2
    PREFIX = "integration-tests-fio"
    REQUIRED_PACKAGES = ['blktap-openvstorage-utils', 'qemu', 'fio']
    VDISK_CHECK_TIMEOUT = 10
    VDISK_CHECK_AMOUNT = 30

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
        return FioOnVDiskChecks.start_test()

    @classmethod
    def start_test(cls):
        storagedriver, image_path = cls.setup()
        return cls.run_test(storagedriver, image_path)

    @classmethod
    def setup(cls):
        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"
        vpool = random.choice(vpools)
        assert len(vpool.storagedrivers) >= 1, "Not enough Storagedrivers to test"
        # check if enough images available
        images = cls.get_images()
        assert len(images) >= 1, 'We require an cloud init bootable image file.'
        # Setup base information
        storagedriver = vpool.storagedrivers[0]
        client = SSHClient(storagedriver.storagerouter, username='root')
        # Check if image exists
        assert client.file_exists(images[0]), "Image `{0}` does not exists on `{1}`!".format(images[0],
                                                                                             storagedriver.storage_ip)
        image_path = images[0]
        return storagedriver, image_path

    @classmethod
    def run_test(cls, storagedriver, image_path, amount_vdisks=AMOUNT_VDISKS, amount_to_write=AMOUNT_TO_WRITE,
                 logger=LOGGER):
        """
        Validate if fio works on a vdisk via edge
        INFO:
            * 1 vPool should be available on 1 storagerouter
            * Removes all tap-ctl connections with vdisk prefix equal to STATIC variable `FioOnVDiskChecks.VDISK_NAME`
        :param storagedriver: chosen storagedriver
        :param image_path: path to image to convert
        :param amount_vdisks: amount of vdisks to deploy and scrub
        :type amount_vdisks: int
        :param amount_to_write: amount of MegaByte to write on a single vdisk
        :type amount_to_write: int
        :param logger: logging instance
        :return:
        """
        logger.info("Starting to validate the fio on vdisks")
        cls.run_test_nbd(storagedriver, amount_vdisks, amount_to_write)
        logger.info("Finished validating fio on vdisks")

    @classmethod
    def run_test_nbd(cls, storagedriver, disk_amount, write_amount, logger=LOGGER):

        vpool = storagedriver.vpool
        client = SSHClient(storagedriver.storagerouter, username='root')
        edge_info = {'port': storagedriver.ports['edge'],
                     'protocol': storagedriver.cluster_node_config['network_server_uri'].split(':')[0],
                     'ip': storagedriver.storage_ip}
        if SystemHelper.get_ovs_version(storagedriver.storagerouter) == 'ee':
            edge_info.update(cls.get_shell_user())
        vdisk_info = {}
        try:
            for vdisk_number in xrange(disk_amount):
                vdisk_name = '{0}{1}-nbd'.format(cls.PREFIX, vdisk_number)
                vdisk_guid = VDiskSetup.create_vdisk(vdisk_name, vpool.name, cls.VDISK_SIZE, storagedriver.storagerouter.ip)
                vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                nbd_device = VMHandler.create_nbd_device(client, vdisk.name, edge_info)
                vdisk_info[nbd_device] = vdisk
                fio_configuration = {'io_size': write_amount, 'configuration': (0, 100)}
                DataWriter.write_data_fio(client, fio_configuration, file_locations=vdisk_info.keys(), screen=False,
                                          loop_screen=False)
                fio_configuration = {'io_size': write_amount, 'configuration': (100, 0)}
                DataWriter.write_data_fio(client, fio_configuration, file_locations=vdisk_info.keys(), screen=False,
                                          loop_screen=False)
                time.sleep(5)
        except Exception as ex:
            print ex
            logger.error('An exception occur while testing nbd: {0}'.format(str(ex)))
            raise
        finally:
            for nbd_d, vdisk in vdisk_info.iteritems():
                VMHandler.detach_nbd_device(client, nbd_d)
                VDiskRemover.remove_vdisk_by_name(vdisk.devicename, vdisk.vpool.name)

    @staticmethod
    def _get_vdisk(vdisk_name, vpool_name, timeout=60, logger=LOGGER):
        """
        Gets a vdisk that might take a while to be registered in the DAL due to events or other reasons
        Keeps polling until the timeout has been reached before throwing
        :param vdisk_name: devicename of the vdisk
        :param vpool_name: name of the vpool
        :param timeout: time to poll before raising
        :param logger: logging instance
        :return:
        """
        vdisk = None
        start = time.time()
        while vdisk is None:
            if time.time() - start > timeout:
                raise VDiskNotFoundError('Could not fetch the vdisk after {}s'.format(time.time() - start))
            try:
                vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name, vpool_name)
            except VDiskNotFoundError:
                logger.warning('Could not fetch the vdisk after {0}s.'.format(time.time() - start))
            time.sleep(0.5)
        return vdisk

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
