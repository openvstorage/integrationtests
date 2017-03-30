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

import os
from ci.api_lib.helpers.storagerouter import StoragerouterHelper
from ci.api_lib.remove.arakoon import ArakoonRemover
from ci.api_lib.setup.arakoon import ArakoonSetup
from ci.autotests import gather_results
from ovs.extensions.generic.sshclient import SSHClient
from ovs.log.log_handler import LogHandler


class ArakoonArchiving(object):

    CASE_TYPE = 'FUNCTIONAL'
    TEST_NAME = "ci_scenario_archiving"
    LOGGER = LogHandler.get(source="scenario", name=TEST_NAME)

    def __init__(self):
        pass

    @staticmethod
    @gather_results(CASE_TYPE, LOGGER, TEST_NAME)
    def main(blocked):
        """
        Run all required methods for the test

        :param blocked: was the test blocked by other test?
        :return: results of test
        :rtype: dict
        """

        return ArakoonArchiving.test_archiving()

    @staticmethod
    def test_archiving(cluster_name='test_archiving', cluster_basedir='/var/tmp'):
        """
        Required method that has to follow our json output guideline
        This data will be sent to testrails to process it thereafter

        :param cluster_name: name of a non-existing arakoon cluster
        :type cluster_name: str
        :param cluster_basedir: absolute path for the new arakoon cluster
        :type cluster_basedir: str
        :return:
        """

        ArakoonArchiving.LOGGER.info('Starting Arakoon archiving')
        storagerouters = StoragerouterHelper.get_storagerouter_ips()
        assert len(storagerouters) >= 2, 'Environment has only `{0}` node(s)'.format(len(storagerouters))

        archived_files = []
        files_to_create = []
        storagerouters.sort()
        for index, storagerouter_ip in enumerate(storagerouters):

            # create required directories in cluster_basedir
            ovs_client = SSHClient(storagerouter_ip, username='ovs')
            for directory in ['/'.join([cluster_basedir, 'arakoon']), '/var/log/arakoon']:
                ovs_client.dir_create(os.path.dirname(directory))

            # create required files in cluster_basedir
            files_to_create = ['/'.join([cluster_basedir, 'arakoon', cluster_name, 'db', 'one.db']),
                               '/'.join([cluster_basedir, 'arakoon', cluster_name, 'tlogs', 'one.tlog'])]
            for filename in files_to_create:
                ovs_client.dir_create(os.path.dirname(filename))

            ovs_client.file_create(files_to_create)
            for filename in files_to_create:
                assert ovs_client.file_exists(filename), 'File `{0}` is not present on storagerouter `{1}`'\
                    .format(filename, storagerouter_ip)

            archived_files = ['/'.join(['/var/log/arakoon', cluster_name, 'archive', 'one.log'])]

            if index == 0:
                ArakoonArchiving.LOGGER.info('Starting setup of first arakoon instance of cluster `{0}` '
                                             'on storagerouter `{1}`'.format(cluster_name, storagerouter_ip))
                ArakoonSetup.add_arakoon(cluster_name=cluster_name, storagerouter_ip=storagerouter_ip,
                                         cluster_basedir=cluster_basedir)
                ArakoonArchiving.LOGGER.info('Finished setup of first arakoon instance of cluster `{0}`'
                                             'on storagerouter `{1}`'.format(cluster_name, storagerouter_ip))
            else:
                ArakoonArchiving.LOGGER.info('Starting extending arakoon instance of cluster `{0}` '
                                             'on storagerouter `{1}`'.format(cluster_name, storagerouter_ip))
                ArakoonSetup.extend_arakoon(cluster_name=cluster_name, master_storagerouter_ip=storagerouters[0],
                                            storagerouter_ip=storagerouter_ip, cluster_basedir=cluster_basedir)
                ArakoonArchiving.LOGGER.info('Finished extending arakoon instance of cluster `{0}` '
                                             'on storagerouter `{1}`'.format(cluster_name, storagerouter_ip))
            ArakoonArchiving.check_archived_directory(ovs_client, archived_files)

            # check required files if they are still present
            for filename in files_to_create:
                assert ovs_client.file_exists(filename) is False, 'File `{0}` is missing on storagerouter `{1}`'\
                    .format(filename, storagerouter_ip)

        ArakoonArchiving.LOGGER.info('Finished test, removing arakoon cluster `{0}`'.format(cluster_name))
        ArakoonRemover.remove_arakoon_cluster(cluster_name=cluster_name, master_storagerouter_ip=storagerouters[0])
        ArakoonArchiving.LOGGER.info('Finished removal of arakoon cluster `{0}`'.format(cluster_name))

        # check if required files are removed
        for storagerouter_ip in storagerouters:
            ovs_client = SSHClient(storagerouter_ip, username='ovs')
            ArakoonArchiving.check_archived_directory(ovs_client, archived_files)
            for filename in files_to_create:
                assert ovs_client.file_exists(filename) is False, 'File `{0}` is missing on storagerouter `{1}`'\
                    .format(filename, storagerouter_ip)
            # remove cluster_base_dir
            ovs_client.dir_delete("{0}/arakoon".format(cluster_basedir))

    @staticmethod
    def check_archived_directory(client, archived_files):
        """
        Verify if directory has been archived
        :param client: SSHClient object
        :param archived_files: Files to check
        :return: True if archived
        """
        for archived_file in archived_files:
            file_found = False
            archived_file = archived_file.rstrip('/')
            archived_directory = os.path.dirname(archived_file)
            archived_file_name = os.path.basename(archived_file)
            if client.dir_exists(archived_directory):
                files_in_directory = client.file_list(archived_directory)
                # checking just the last file
                file_name = files_in_directory[-1]
                if file_name.endswith('.tgz'):
                    out = client.run('tar -tf {0}/{1}'.format(archived_directory, file_name))
                    if archived_file_name in out:
                        file_found = True
            if file_found is False:
                return False
        return True


def run(blocked=False):
    """
    Run a test

    :param blocked: was the test blocked by other test?
    :return: results of test
    :rtype: dict
    """

    return ArakoonArchiving().main(blocked)

if __name__ == "__main__":
    run()
