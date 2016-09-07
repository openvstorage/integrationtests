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
Sanity check testsuite
"""

from ci.tests.general.general import General
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient


class TestSanity(object):
    """
    Sanity check testsuite
    """
    @staticmethod
    def ssh_check_test():
        """
        Verify SSH keys
        """
        issues_found = []
        env_ips = GeneralStorageRouter.get_all_ips()
        for env_ip_connecting_from in env_ips:
            out = General.execute_command_on_node(env_ip_connecting_from, "cat ~/.ssh/known_hosts")
            for env_ip_connecting_to in env_ips:
                if env_ip_connecting_from != env_ip_connecting_to:
                    if env_ip_connecting_to not in out:
                        issues_found.append('Host key verification not found between {0} and {1}'.format(env_ip_connecting_from, env_ip_connecting_to))

        assert len(issues_found) == 0, 'Following issues were found:\n - {0}'.format('\n - '.join(issues_found))

    @staticmethod
    def services_check_test():
        """
        Verify some services
        """
        # get env ips
        env_ips = GeneralStorageRouter.get_all_ips()
        non_running_services = []

        for env_ip in env_ips:
            non_running_services_on_node = []
            out = General.execute_command_on_node(env_ip, "initctl list | grep ovs-*")
            statuses = out.splitlines()

            non_running_services_on_node.extend([s for s in statuses if 'start/running' not in s])
            if len(non_running_services_on_node):
                non_running_services.append([env_ip, non_running_services_on_node])

        assert len(non_running_services) == 0, "Found non running services on {0}".format(non_running_services)

    @staticmethod
    def system_services_check_test():
        """
        Verify some system services
        """
        services_to_commands = {
            "nginx": """ps -efx|grep nginx|grep -v grep""",
            "rabbitmq-server": """ps -ef|grep rabbitmq-|grep -v grep""",
            "memcached": """ps -ef|grep memcached|grep -v grep""",
            "ovs-arakoon-ovsdb": """initctl list| grep ovsdb""",
            "ovs-snmp": """initctl list| grep ovs-snmp""",
            "ovs-support-agent": """initctl list| grep support""",
            "ovs-volumerouter-consumer": """initctl list| grep volumerou""",
            "ovs-watcher-framework": """initctl list| grep watcher-fr"""
        }

        errors = ''
        services_checked = 'Following services found running:\n'
        grid_ip = General.get_config().get('main', 'grid_ip')
        ssh_pass = General.get_config().get('mgmtcenter', 'password')
        client = SSHClient(grid_ip, username='root', password=ssh_pass)

        for service_to_check in services_to_commands.iterkeys():
            out, err = client.run(services_to_commands[service_to_check], debug=True)
            if len(err):
                errors += "Error when trying to run {0}:\n{1}".format(services_to_commands[service_to_check], err)
            else:
                if len(out):
                    services_checked += "{0}\n".format(service_to_check)
                else:
                    errors += "Couldn't find {0} running process\n".format(service_to_check)

        print services_checked
        assert len(errors) == 0, "Found the following errors while checking for the system services:{0}\n".format(errors)

    @staticmethod
    def config_files_check_test():
        """
        Verify some configuration files
        """
        issues_found = ''

        config_keys = {
            "/ovs/framework/memcache",
            "/ovs/arakoon/ovsdb/config"
        }

        for key_to_check in config_keys:
            if not Configuration.exists(key_to_check, raw = True):
                issues_found += "Couldn't find {0}\n".format(key_to_check)

        config_files = {
            "rabbitmq.config": "/etc/rabbitmq/rabbitmq.config",
        }
        grid_ip = General.get_config().get('main', 'grid_ip')
        ssh_pass = General.get_config().get('mgmtcenter', 'password')
        client = SSHClient(grid_ip, username='root', password=ssh_pass)
        for config_file_to_check in config_files.iterkeys():
            if not client.file_exists(config_files[config_file_to_check]):
                issues_found += "Couldn't find {0}\n".format(config_file_to_check)

        assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)

    @staticmethod
    def json_files_check_test():
        """
        Verify some configuration files in json format
        """
        issues_found = ''

        srs = GeneralStorageRouter.get_storage_routers()
        for sr in srs:
            config_contents = Configuration.get('/ovs/framework/hosts/{0}/setupcompleted'.format(sr.machine_id), raw = True)
            if "true" not in config_contents:
                issues_found += "Setup not completed for node {0}\n".format(sr.name)

        assert issues_found == '', "Found the following issues while checking for the setupcompleted:{0}\n".format(issues_found)
