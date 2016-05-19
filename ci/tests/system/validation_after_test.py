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

"""
Validation testsuite
"""

import re
from ci.tests.general.general import General
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ci.tests.general.general_vdisk import GeneralVDisk
from ci.tests.general.general_vpool import GeneralVPool
from ovs.extensions.generic.sshclient import CalledProcessError
from ovs.extensions.generic.sshclient import SSHClient
from nose.tools import assert_equal
from nose.tools import assert_raises
from nose.tools import assert_true


class TestAfterCare(object):
    """
    Testsuite to check stuff after tests have been executed
    """
    @staticmethod
    def ovs_2053_check_for_alba_warnings_test():
        """
        Check ALBA warning presence
        """
        out = General.execute_command_on_node('127.0.0.1', 'grep "warning: syncfs" /var/log/upstart/*-asd-*.log | wc -l')
        assert out == '0', \
            "syncfs warnings detected in asd logs\n:{0}".format(out.splitlines())

    @staticmethod
    def ovs_2493_detect_could_not_acquire_lock_events_test():
        """
        Verify lock errors
        """
        errorlist = ""
        command = "grep -C 1 'Could not acquire lock' /var/log/ovs/lib.log"
        gridips = GeneralPMachine.get_all_ips()

        for gridip in gridips:
            out = General.execute_command_on_node(gridip, command + " | wc -l")
            if not out == '0':
                errorlist += "node %s \n:{0}\n\n".format(General.execute_command_on_node(gridip, command).splitlines()) % gridip

        assert len(errorlist) == 0, "Lock errors detected in lib logs on \n" + errorlist

    @staticmethod
    def ovs_2468_verify_no_mds_files_left_after_remove_vpool_test():
        """
        Verify MDS presence after vpool removal
        """
        vpools = GeneralVPool.get_vpools()
        vpool_names = [vpool.name for vpool in vpools]
        command = "find /mnt -name '*mds*'"
        mdsvpoolnames = []

        out = General.execute_command(command + " | wc -l")
        if not out == '0':
            mdsvpoolnames = [line.split('/')[-1] for line in General.execute_command(command)[0].splitlines()]

        mds_files_still_in_filesystem = ""

        for mdsvpoolname in mdsvpoolnames:
            if mdsvpoolname.split('_')[1] not in vpool_names:
                mds_files_still_in_filesystem += mdsvpoolname + "\n"

        assert len(mds_files_still_in_filesystem) == 0,\
            "MDS files still present in filesystem after remove vpool test:\n %s" % mds_files_still_in_filesystem

    @staticmethod
    def test_basic_logrotate():
        """
        Verify current openvstorage logrotate configuration
        Apply the openvstorage logrotate on custom logfile and see if it rotates as predicted
        Update ownership of custom file and verify logrotate raises issue
        """
        storagerouters = GeneralStorageRouter.get_storage_routers()
        logrotate_content = """{0} {{
    rotate 5
    size 20M
    compress
    copytruncate
    notifempty
}}

{1} {{
    su ovs ovs
    rotate 10
    size 19M
    compress
    delaycompress
    notifempty
    create 666 ovs ovs
    postrotate
        /usr/bin/pkill -SIGUSR1 arakoon
    endscript
}}"""
        if len(storagerouters) == 0:
            raise ValueError('No Storage Routers found in the model')

        logrotate_include_dir = '/etc/logrotate.d'
        logrotate_cfg_file = '/etc/logrotate.conf'
        logrotate_cron_file = '/etc/cron.daily/logrotate'
        logrotate_ovs_file = '{0}/openvstorage-logs'.format(logrotate_include_dir)
        expected_logrotate_content = logrotate_content.format('/var/log/ovs/*.log', '/var/log/arakoon/*/*.log')

        # Verify basic logrotate configurations
        for storagerouter in storagerouters:
            root_client = SSHClient(endpoint=storagerouter, username='root')
            assert_true(expr=root_client.file_exists(filename=logrotate_cfg_file),
                        msg='Logrotate config {0} does not exist on Storage Router {1}'.format(logrotate_cfg_file, storagerouter.name))
            assert_true(expr=root_client.file_exists(filename=logrotate_ovs_file),
                        msg='Logrotate file {0} does not exist on Storage Router {1}'.format(logrotate_ovs_file, storagerouter.name))
            assert_true(expr=root_client.file_exists(filename=logrotate_cron_file),
                        msg='Logrotate file {0} does not exist on Storage Router {1}'.format(logrotate_cron_file, storagerouter.name))
            assert_true(expr='include {0}'.format(logrotate_include_dir) in root_client.file_read(filename=logrotate_cfg_file).splitlines(),
                        msg='Logrotate on Storage Router {0} does not include {1}'.format(storagerouter.name, logrotate_include_dir))
            assert_true(expr='/usr/sbin/logrotate /etc/logrotate.conf' in root_client.file_read(filename=logrotate_cron_file).splitlines(),
                        msg='Logrotate will not be executed on Storage Router {0}'.format(storagerouter.name))
            actual_file_contents = root_client.file_read(filename=logrotate_ovs_file).rstrip('\n')
            assert_equal(first=expected_logrotate_content,
                         second=actual_file_contents,
                         msg='Logrotate contents does not match expected contents on Storage Router {0}'.format(storagerouter.name))

        # Create custom logrotate file for testing purposes
        custom_logrotate_cfg_file = '/opt/OpenvStorage/ci/logrotate-conf'
        custom_logrotate_dir = '/opt/OpenvStorage/ci/logrotate'
        custom_logrotate_file1 = '{0}/logrotate_test_file1.log'.format(custom_logrotate_dir)
        custom_logrotate_file2 = '{0}/logrotate_test_file2.log'.format(custom_logrotate_dir)
        custom_logrotate_content = logrotate_content.format(custom_logrotate_file1, custom_logrotate_file2)
        local_sr = GeneralStorageRouter.get_local_storagerouter()
        root_client = SSHClient(endpoint=local_sr, username='root')
        root_client.file_write(filename=custom_logrotate_cfg_file, contents=custom_logrotate_content)

        # No logfile present --> logrotate should fail
        assert_raises(excClass=CalledProcessError,
                      callableObj=root_client.run,
                      command='logrotate {0}'.format(custom_logrotate_cfg_file))

        ##########################################
        # Test 1st logrotate configuration entry #
        ##########################################
        root_client.dir_create(directories=custom_logrotate_dir)
        root_client.dir_chown(directories=custom_logrotate_dir,
                              user='ovs',
                              group='ovs',
                              recursive=True)
        root_client.run(command='touch {0}'.format(custom_logrotate_file1))
        root_client.run(command='touch {0}'.format(custom_logrotate_file2))
        root_client.file_chmod(filename=custom_logrotate_file1, mode=666)
        root_client.file_chmod(filename=custom_logrotate_file2, mode=666)

        # Write data to the file less than size for rotation and verify rotation
        GeneralVDisk.write_to_volume(location=custom_logrotate_file1,
                                     count=15,
                                     bs='1M',
                                     input_type='zero',
                                     root_client=root_client)
        root_client.run('logrotate {0}'.format(custom_logrotate_cfg_file))
        assert_equal(first=len(root_client.file_list(directory=custom_logrotate_dir)),
                     second=2,
                     msg='More files than expected present in {0}'.format(custom_logrotate_dir))

        # Write data to file larger than size in configuration and verify amount of rotations
        files_to_delete = []
        for counter in range(7):
            expected_file = '{0}.{1}.gz'.format(custom_logrotate_file1, counter + 1 if counter < 5 else 5)
            GeneralVDisk.write_to_volume(location=custom_logrotate_file1,
                                         count=30,
                                         bs='1M',
                                         input_type='zero',
                                         root_client=root_client)
            root_client.run('logrotate {0}'.format(custom_logrotate_cfg_file))
            assert_equal(first=len(root_client.file_list(directory=custom_logrotate_dir)),
                         second=counter + 3 if counter < 5 else 7,
                         msg='Not the expected amount of files present in {0}'.format(custom_logrotate_dir))
            assert_true(expr=root_client.file_exists(filename=expected_file),
                        msg='Logrotate did not create the expected file {0}'.format(expected_file))
            user_info = General.get_owner_group_for_path(path=expected_file,
                                                         root_client=root_client)
            assert_equal(first='root',
                         second=user_info['user']['name'],
                         msg='Expected file to be owned by user "root", but instead its owned by "{0}"'.format(user_info['user']['name']))
            assert_equal(first='root',
                         second=user_info['group']['name'],
                         msg='Expected file to be owned by group "root", but instead its owned by "{0}"'.format(user_info['group']['name']))
            files_to_delete.append(expected_file)
        root_client.file_delete(filenames=files_to_delete)

        ##########################################
        # Test 2nd logrotate configuration entry #
        ##########################################
        root_client.file_chown(filenames=custom_logrotate_file2,
                               user='ovs',
                               group='ovs')

        # Write data to the file less than size for rotation and verify rotation
        GeneralVDisk.write_to_volume(location=custom_logrotate_file2,
                                     count=15,
                                     bs='1M',
                                     input_type='zero',
                                     root_client=root_client)
        root_client.run('logrotate {0}'.format(custom_logrotate_cfg_file))
        assert_equal(first=len(root_client.file_list(directory=custom_logrotate_dir)),
                     second=2,
                     msg='More files than expected present in {0}'.format(custom_logrotate_dir))

        # Write data to file larger than size in configuration and verify amount of rotations
        for counter in range(12):
            if counter == 0:  # Delaycompress --> file is not compressed during initial cycle
                expected_file = '{0}.1'.format(custom_logrotate_file2)
            else:
                expected_file = '{0}.{1}.gz'.format(custom_logrotate_file2, counter + 1 if counter < 10 else 10)
            GeneralVDisk.write_to_volume(location=custom_logrotate_file2,
                                         count=30,
                                         bs='1M',
                                         input_type='zero',
                                         root_client=root_client)
            root_client.run('logrotate {0}'.format(custom_logrotate_cfg_file))
            assert_equal(first=len(root_client.file_list(directory=custom_logrotate_dir)),
                         second=counter + 3 if counter < 10 else 12,
                         msg='Not the expected amount of files present in {0}'.format(custom_logrotate_dir))
            assert_true(expr=root_client.file_exists(filename=expected_file),
                        msg='Logrotate did not create the expected file {0}'.format(expected_file))
            user_info = General.get_owner_group_for_path(path=expected_file,
                                                         root_client=root_client)
            assert_equal(first='ovs',
                         second=user_info['user']['name'],
                         msg='Expected file to be owned by user "root", but instead its owned by "{0}"'.format(user_info['user']['name']))
            assert_equal(first='ovs',
                         second=user_info['group']['name'],
                         msg='Expected file to be owned by group "root", but instead its owned by "{0}"'.format(user_info['group']['name']))

        root_client.dir_delete(directories=custom_logrotate_dir)
        root_client.file_delete(filenames=custom_logrotate_cfg_file)

    @staticmethod
    def check_license_headers_test():
        """
        Check license headers
        """
        license_header = re.compile('Copyright \(C\) 201[4-9] iNuron NV')
        license_to_check = ["",
                            " This file is part of Open vStorage Open Source Edition (OSE),",
                            " as available from",
                            "",
                            "     http://www.openvstorage.org and",
                            "     http://www.openvstorage.com.",
                            "",
                            " This file is free software; you can redistribute it and/or modify it",
                            " under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)",
                            " as published by the Free Software Foundation, in version 3 as it comes",
                            " in the LICENSE.txt file of the Open vStorage OSE distribution.",
                            "",
                            " Open vStorage is distributed in the hope that it will be useful,",
                            " but WITHOUT ANY WARRANTY of any kind."]

        exclude_dirs = ['/opt/OpenvStorage/config/templates/cinder-unit-tests/',
                        '/opt/OpenvStorage/config/templates/cinder-volume-driver/',
                        '/opt/OpenvStorage/webapps/frontend/css/',
                        '/opt/OpenvStorage/webapps/frontend/lib/',
                        '/opt/OpenvStorage/ovs/extensions/db/arakoon/arakoon/arakoon/',
                        '/opt/OpenvStorage/ovs/extensions/db/arakoon/pyrakoon/pyrakoon/']
        include_dirs = ['/opt/OpenvStorage/webapps/frontend/lib/ovs/']
        exclude_files = ['/opt/OpenvStorage/ovs/extensions/generic/fakesleep.py']
        include_files = ['/opt/OpenvStorage/webapps/frontend/css/ovs.css']
        extension_comments_map = {'.py': ['#'],
                                  '.sh': ['#'],
                                  '.js': ['//'],
                                  '.html': ['<!--', '-->'],
                                  '.css': ['/*', '*', '*/']}

        storagerouters = GeneralStorageRouter.get_storage_routers()
        files_with_diff_licenses = {}
        for storagerouter in storagerouters:
            root_client = SSHClient(storagerouter, username='root')
            files_with_diff_licenses[storagerouter.guid] = []
            for root_folder in ['/opt/OpenvStorage', '/opt/asd-manager']:
                if not root_client.dir_exists(root_folder):
                    raise ValueError('Root folder {0} does not exist'.format(root_folder))

                unfiltered_files = root_client.file_list(directory=root_folder,
                                                         abs_path=True,
                                                         recursive=True)
                filtered_files = General.filter_files(files=unfiltered_files,
                                                      extensions=extension_comments_map.keys(),
                                                      exclude_dirs=exclude_dirs,
                                                      include_dirs=include_dirs,
                                                      exclude_files=exclude_files,
                                                      include_files=include_files)
                for file_name in filtered_files:
                    # Read file
                    with open(file_name, 'r') as utf_file:
                        data = utf_file.read().decode("utf-8-sig").encode("utf-8")
                        lines_to_check = data.splitlines()

                    # Check relevant comment type for current file
                    comments = []
                    for extension, cmts in extension_comments_map.iteritems():
                        if file_name.endswith(extension):
                            comments = cmts
                            break
                    if len(comments) == 0:
                        raise ValueError('Something must have gone wrong filtering the files, because file {0} does not have a correct extension'.format(file_name))

                    # Search license header
                    index = 0
                    lic_header_found = False
                    for index, line in enumerate(lines_to_check):
                        for comment in comments:
                            line = line.replace(comment, '', 1)
                        if re.match(license_header, line.strip()):
                            lic_header_found = True
                            break

                    # License header not found, continuing
                    if lic_header_found is False:
                        files_with_diff_licenses[storagerouter.guid].append(file_name)
                        continue

                    # License header found, checking rest of license
                    index += 1
                    for license_line in license_to_check:
                        line_to_check = lines_to_check[index]
                        for comment in comments:
                            line_to_check = line_to_check.replace(comment, '', 1)
                        if license_line.strip() == line_to_check.strip():
                            index += 1
                        else:
                            files_with_diff_licenses[storagerouter.guid].append(file_name)
                            break

        for storagerouter in storagerouters:
            assert len(files_with_diff_licenses[storagerouter.guid]) == 0, 'Following files were found with different licenses:\n - {0}'.format('\n - '.join(files_with_diff_licenses[storagerouter.guid]))
