# Copyright (C) 2018 iNuron NV
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
"""
NBD integtration test
"""

import random
from ci.api_lib.helpers.vdisk import VDiskHelper
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.remove.vdisk import VDiskRemover
from ci.scenario_helpers.ci_constants import CIConstants
from ci.scenario_helpers.data_writing import DataWriter
from ovs.extensions.generic.logger import Logger
from ovs_extensions.generic.sshclient import SSHClient

# todo if this test is to be used, change paths by api_lib calls
from source.tools.nbd import NBDManager
from source.tools.servicefactory import ServiceFactory


class NBDIntegration(CIConstants):
    """
    Integration tests for NBD io
    """

    CASE_TYPE = 'AT_QUICK'
    TEST_NAME = "nbd_integration_test"
    LOGGER = Logger('scenario-{0}'.format(TEST_NAME))
    VDISK_NAME = 'vdisk_nbd_integration_test'

    AMOUNT_TO_WRITE = 5 * 1024
    VDISK_SIZE = 100 * 1024
    DEFAULT_PORT = 26203

    ip = '10.100.196.1'  # todo change ip to node with nbd installed on local env

    def __init__(self):
        cluster_info = self.setup()

        self.vd = VDiskHelper.get_vdisk_by_guid(cluster_info.get('target_vdisk'))
        credentials = 'tcp://root:rooter@{0}:{1}/{2}'.format(self.ip, self.DEFAULT_PORT, self.VDISK_NAME)

        # Initialize NBD device
        self.mgr = NBDManager()
        self.nbd_path = self.mgr.create_service(credentials)  # Create the service
        self.nbd = self.nbd_path.lstrip('/dev/')  # NBD number
        self.mgr.start_device(nbd_path=self.nbd_path)  # Start the service

        self.local_client = SSHClient('127.0.0.1', username='root')

        # Fio output file path
        self.fio_target_file_path = '/tmp/ovs_integration_test_{0}_output'.format(self.nbd)

    def main(self, blocked):
        """
        Run all required methods for the test.
        :param blocked: was the test blocked by other test?
        :type blocked: bool
        :return: results of test
        :rtype: dict
        """

        self.LOGGER.info('Starting')
        _ = blocked
        return self.start_test()

    def start_test(self):
        # type: () -> None
        """
        Start test and clean up file and config mgmt afterwards
        :return:
        """
        try:
            self.run_test()
        except Exception as ex:
            self.LOGGER.exception(ex)
        finally:  # Whatever happens, clean up
            self.cleanup()

    @classmethod
    def setup(cls):
        # type: () -> Dict[str, str]
        """
        Setup environment for testing
        :return: Dict
        """

        # target selection: storagerouter ip + vpool, vdisk creation
        vpool = None
        for vp in VPoolHelper.get_vpools():
            if len(vp.storagedrivers) >= 1:
                vpool = vp
                break
        assert vpool is not None, 'Found no vpool'

        vd = VDiskSetup.create_vdisk(size=cls.VDISK_SIZE,
                                     storagerouter_ip=cls.ip,
                                     vdisk_name=cls.VDISK_NAME,
                                     vpool_name=vpool.name)
        assert vd is not None, 'Found no vdisk'

        cluster_info = {'target_vdisk': vd}  # Store in dict for consistency accros tests
        return cluster_info

    def run_test(self):
        # type: (None) -> None
        """
        Start the test
        :return: None
        """
        if not ServiceFactory.get_manager().get_service_status('ovs-{0}-{1}'.format(self.nbd, self.VDISK_NAME), client=self.local_client) == 'active':
            raise RuntimeError('Service state is not marked as "active"')

        screen_names = []
        fio_config = {'io_size': self.AMOUNT_TO_WRITE, 'configuration': random.choice(self.DATA_TEST_CASES), 'bs': '4k'}

        try:
            screen_names, output_files = DataWriter.write_data_fio(client=self.local_client,
                                                                   fio_configuration=fio_config,
                                                                   file_locations=[self.fio_target_file_path])
        finally:
            for screen_name in screen_names:
                self.local_client.run(['screen', '-S', screen_name, '-X', 'quit'])

    def cleanup(self):
        # type: () -> None
        """
        Clean up created service in configmanagement and file system
        :return: None
        """
        self.mgr.destroy_device(nbd_path=self.nbd_path)
        VDiskRemover.remove_vdisk(self.vd.guid)


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return NBDIntegration().main(blocked)


if __name__ == "__main__":
    run()
