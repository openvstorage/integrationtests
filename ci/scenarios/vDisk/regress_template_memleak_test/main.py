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
from ci.api_lib.setup.vdisk import VDiskSetup
from ci.api_lib.helpers.vpool import VPoolHelper
from ci.api_lib.remove.vdisk import VDiskRemover
from ovs.log.log_handler import LogHandler
from ci.api_lib.helpers.statistics import StatisticsHelper
from ovs.extensions.generic.sshclient import SSHClient


class VDiskTemplateChecks(object):

    CASE_TYPE = 'FUNCTIONAL'
    LOGGER = LogHandler.get(source="scenario", name="ci_scenario_vdisk_template_memleak")
    PREFIX = "integration-tests-templ-memleak-"
    VDISK_SIZE = 1073741824  # 1 GB
    AMOUNT_VDISKS = 10
    AMOUNT_TO_WRITE = 10  # in MegaByte
    TEMPLATE_CREATE_TIMEOUT = 180
    TEMPLATE_SLEEP_AFTER_CREATE = 5
    TEMPLATE_SLEEP_BEFORE_CHECK = 5
    TEMPLATE_SLEEP_BEFORE_DELETE = 5

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
                VDiskTemplateChecks.validate_vdisk_clone()
                return {'status': 'PASSED', 'case_type': VDiskTemplateChecks.CASE_TYPE, 'errors': None}
            except Exception as ex:
                VDiskTemplateChecks.LOGGER.error("Clone vdisk checks failed with error: {0}".format(str(ex)))
                return {'status': 'FAILED', 'case_type': VDiskTemplateChecks.CASE_TYPE, 'errors': str(ex)}
        else:
            return {'status': 'BLOCKED', 'case_type': VDiskTemplateChecks.CASE_TYPE, 'errors': None}

    @staticmethod
    def validate_vdisk_clone(amount_vdisks=AMOUNT_VDISKS, amount_to_write=AMOUNT_TO_WRITE):
        """
        Validate if vdisk deployment works via various ways
        INFO: 1 vPool should be available on 2 storagerouters

        :return:
        """

        VDiskTemplateChecks.LOGGER.info("Starting to regress template memleak vdisks")

        with open(CONFIG_LOC, "r") as JSON_CONFIG:
            config = json.load(JSON_CONFIG)

        api = OVSClient(
            config['ci']['grid_ip'],
            config['ci']['user']['api']['username'],
            config['ci']['user']['api']['password']
        )

        vpools = VPoolHelper.get_vpools()
        assert len(vpools) >= 1, "Not enough vPools to test"

        try:
            vpool = next((vpool for vpool in vpools if len(vpool.storagedrivers) >= 2))
        except StopIteration:
            assert False, "Not enough Storagedrivers to test"

        # setup base information
        storagedriver_source = vpool.storagedrivers[0]
        client = SSHClient(storagedriver_source.storage_ip, username='root')

        # create required vdisk for test
        vdisk_name = VDiskTemplateChecks.PREFIX + '1'
        assert VDiskSetup.create_vdisk(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                       size=VDiskTemplateChecks.VDISK_SIZE, api=api,
                                       storagerouter_ip=storagedriver_source.storagerouter.ip) is not None
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_AFTER_CREATE)

        ##################
        # template vdisk #
        ##################

        VDiskSetup.set_vdisk_as_template(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, api=api)
        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_AFTER_CREATE)

        ######################
        # log current memory #
        ######################

        memory_usage_beginning = StatisticsHelper.get_current_memory_usage(storagedriver_source.storage_ip)
        VDiskTemplateChecks.LOGGER.info("Starting memory usage monitor: {0}/{1}"
                                        .format(memory_usage_beginning[0], memory_usage_beginning[1]))
        pid = int(client.run("pgrep -a volumedriver | grep {0} | cut -d ' ' -f 1".format(vpool.name),
                             allow_insecure=True))
        VDiskTemplateChecks.LOGGER.info(
            "Starting extended memory monitor on pid {0}: \n{1}"
            .format(pid, StatisticsHelper.get_current_memory_usage_of_process(storagedriver_source.storage_ip, pid)))

        ##################################################################
        # create vdisks from template, perform fio and delete them again #
        ##################################################################

        for vdisk in xrange(amount_vdisks):
            # create vdisk from template
            clone_vdisk_name = vdisk_name + '-template-' + str(vdisk)
            VDiskSetup.create_from_template(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name,
                                            new_vdisk_name=clone_vdisk_name + '.raw',
                                            storagerouter_ip=storagedriver_source.storagerouter.ip, api=api)
            # perform fio test
            client.run(["fio", "--name=test", "--filename=/mnt/{0}/{1}.raw".format(vpool.name, clone_vdisk_name),
                        "--ioengine=libaio", "--iodepth=4", "--rw=write", "--bs=4k", "--direct=1",
                        "--size={0}M".format(amount_to_write), "--output-format=json",
                        "--output={0}.json".format(vdisk_name)])
            # delete vdisk
            time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_BEFORE_DELETE)
            VDiskRemover.remove_vdisk_by_name(vdisk_name=clone_vdisk_name + '.raw', vpool_name=vpool.name)

        ###################
        # remove template #
        ###################

        time.sleep(VDiskTemplateChecks.TEMPLATE_SLEEP_BEFORE_DELETE)
        VDiskRemover.remove_vtemplate_by_name(vdisk_name=vdisk_name + '.raw', vpool_name=vpool.name, api=api)

        ######################
        # log current memory #
        ######################

        memory_usage_ending = StatisticsHelper.get_current_memory_usage(storagedriver_source.storage_ip)
        VDiskTemplateChecks.LOGGER.info("Finished memory usage monitor: {0}/{1}"
                                        .format(memory_usage_ending[0], memory_usage_ending[1]))
        pid = int(client.run("pgrep -a volumedriver | grep {0} | cut -d ' ' -f 1".format(vpool.name),
                             allow_insecure=True))
        VDiskTemplateChecks.LOGGER.info(
            "Finished extended memory monitor on pid {0}: \n{1}"
            .format(pid, StatisticsHelper.get_current_memory_usage_of_process(storagedriver_source.storage_ip, pid)))

        VDiskTemplateChecks.LOGGER.info("Finished to regress template memleak vdisks")


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """
    return VDiskTemplateChecks().main(blocked)

if __name__ == "__main__":
    run()
