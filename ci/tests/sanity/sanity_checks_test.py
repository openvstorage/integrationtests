# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Sanity check testsuite
"""

import re
from ci.tests.general.general import General
from ci.tests.general.general_alba import GeneralAlba
from ci.tests.general.general_backend import GeneralBackend
from ci.tests.general.general_pmachine import GeneralPMachine
from ci.tests.general.general_storagerouter import GeneralStorageRouter
from nose.plugins.skip import SkipTest
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.extensions.generic.sshclient import SSHClient


class TestSanity(object):
    """
    Sanity check testsuite
    """
    tests_to_run = General.get_tests_to_run(General.get_test_level())

    #########
    # TESTS #
    #########

    @staticmethod
    def ssh_check_test():
        """
        Verify SSH keys
        """
        General.check_prereqs(testcase_number=1,
                              tests_to_run=TestSanity.tests_to_run)

        issues_found = ''

        env_ips = GeneralPMachine.get_all_ips()
        if len(env_ips) == 1:
            raise SkipTest('Environment has only 1 node')

        for env_ip_connecting_from in env_ips:
            out = General.execute_command_on_node(env_ip_connecting_from, "cat ~/.ssh/known_hosts")
            for env_ip_connecting_to in env_ips:
                if env_ip_connecting_from != env_ip_connecting_to:
                    if env_ip_connecting_to not in out:
                        issues_found += "Host key verification not found between {0} and {1}\n".format(env_ip_connecting_from, env_ip_connecting_to)

        assert issues_found == '', 'Following issues where found:\n{0}'.format(issues_found)

    @staticmethod
    def services_check_test():
        """
        Verify some services
        """
        General.check_prereqs(testcase_number=2,
                              tests_to_run=TestSanity.tests_to_run)

        # get env ips
        env_ips = GeneralPMachine.get_all_ips()
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
        General.check_prereqs(testcase_number=3,
                              tests_to_run=TestSanity.tests_to_run)

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
        General.check_prereqs(testcase_number=4,
                              tests_to_run=TestSanity.tests_to_run)

        issues_found = ''

        etcd_keys = {
            "/ovs/framework/memcache",
            "/ovs/arakoon/ovsdb/config"
        }

        for key_to_check in etcd_keys:
            if not EtcdConfiguration.exists(key_to_check, raw = True):
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
        General.check_prereqs(testcase_number=5,
                              tests_to_run=TestSanity.tests_to_run)

        issues_found = ''

        srs = GeneralStorageRouter.get_storage_routers()
        for sr in srs:
            config_contents = EtcdConfiguration.get('/ovs/framework/hosts/{0}/setupcompleted'.format(sr.machine_id), raw = True)
            if "true" not in config_contents:
                issues_found += "Setup not completed for node {0}\n".format(sr.name)

        assert issues_found == '', "Found the following issues while checking for the setupcompleted:{0}\n".format(issues_found)

    @staticmethod
    def check_model_test():
        """
        Verify ALBA backend
        """
        General.check_prereqs(testcase_number=6,
                              tests_to_run=TestSanity.tests_to_run)

        backends_present_on_env = GeneralBackend.get_backends()
        if len(backends_present_on_env) == 0:
            raise SkipTest('No backend present at the time of the test')

        backend_name = General.get_config().get("backend", "name")
        backend = GeneralBackend.get_by_name(name=backend_name)
        assert backend, "Test backend: not found in model"
        assert backend.backend_type.code == 'alba', "Backend: {0} not of type alba but of type: {1}".format(backend.name, backend.backend_type.code)
        assert backend.status == 'RUNNING', "Backend: {0} in state: {1}, expected state: running".format(backend.name, backend.status)

    @staticmethod
    def check_backend_services_test():
        """
        Verify ALBA backend related services
        """
        General.check_prereqs(testcase_number=7,
                              tests_to_run=TestSanity.tests_to_run)

        backends_present_on_env = GeneralBackend.get_backends()
        if len(backends_present_on_env) == 0:
            raise SkipTest('No backend present at the time of the test')

        # TODO: more than 1 backends present
        # TODO: different backends not just alba
        issues_found = ''

        my_backend_name = backends_present_on_env[0].name
        backend_services = ["ovs-alba-maintenance_{0}".format(my_backend_name),
                            "ovs-arakoon-{0}-abm".format(my_backend_name),
                            "ovs-arakoon-{0}-nsm_0".format(my_backend_name)]

        out, err = General.execute_command("initctl list | grep ovs-*")
        statuses = out.splitlines()

        for status_line in statuses:
            for service_to_check in backend_services:
                if service_to_check in status_line:
                    if "running" not in status_line:
                        issues_found += "Backend service {0} not running.Has following status:{1}\n ".format(service_to_check, status_line)

        assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)

    @staticmethod
    def check_backend_files_test():
        """
        Verify ALBA backend related files
        """
        General.check_prereqs(testcase_number=8,
                              tests_to_run=TestSanity.tests_to_run)

        backends_present_on_env = GeneralBackend.get_backends()
        if len(backends_present_on_env) == 0:
            raise SkipTest('No backend present at the time of the test')

        issues_found = ''

        my_backend_name = backends_present_on_env[0].name
        files_to_check = ["ovs/arakoon/{0}-abm/config".format(my_backend_name),
                          "ovs/arakoon/{0}-nsm_0/config".format(my_backend_name)]

        # check single or multi-node setup
        env_ips = GeneralPMachine.get_all_ips()
        if len(env_ips) == 1:
            # check files
            for file_to_check in files_to_check:
                out, err = General.execute_command('etcdctl ls --recursive /ovs | grep {0}'.format(file_to_check))
                if len(err):
                    issues_found += "Error executing command to get {0} info:{1}\n".format(file_to_check, err)
                else:
                    if len(out) == 0:
                        issues_found += "Couldn't find {0}\n".format(file_to_check)
            # check cluster arakoon master
            out, err = General.execute_command("arakoon --who-master -config {0}".format(ArakoonInstaller.ETCD_CONFIG_PATH.format('ovsdb')))
            if len(out) == 0:
                issues_found += "No arakoon master found in config files\n"
        # @TODO: check to see multi node setup
        assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)

    @staticmethod
    def check_backend_removal_test():
        """
        Verify backend was removed properly
        """
        General.check_prereqs(testcase_number=10,
                              tests_to_run=TestSanity.tests_to_run)

        backend_name = General.get_config().get("backend", "name")
        backend = GeneralBackend.get_by_name(backend_name)
        if not backend:
            raise ValueError('Perhaps we should always make sure there is an ALBA backend')
        if backend and backend.alba_backend is None:
            raise ValueError('Backend with name {0} is not an ALBA backend'.format(backend_name))

        GeneralAlba.unclaim_disks(backend.alba_backend)
        GeneralAlba.remove_alba_backend(backend.alba_backend)

        issues_found = ''
        backends_present_on_env = GeneralBackend.get_backends()
        for backend in backends_present_on_env:
            if backend.name == backend_name:
                issues_found += 'Backend {0} still present in the model with status {1}\n'.format(backend_name, backend.status)

        backend_services = ["ovs-alba-rebalancer_{0}".format(backend_name),
                            "ovs-alba-maintenance_{0}".format(backend_name),
                            "ovs-arakoon-{0}-abm".format(backend_name),
                            "ovs-arakoon-{0}-nsm_0".format(backend_name)]

        out, err = General.execute_command("initctl list | grep ovs-*")
        statuses = out.splitlines()

        for status_line in statuses:
            for service_to_check in backend_services:
                if service_to_check in status_line:
                    issues_found += "Backend service {0} still present.Has following status:{1}\n ".format(service_to_check, status_line)

        files_to_check = ["/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-abm.cfg".format(backend_name),
                          "/opt/OpenvStorage/config/arakoon/{0}-nsm_0/{0}-nsm_0.cfg".format(backend_name),
                          "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-rebalancer.json".format(backend_name),
                          "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-maintenance.json".format(backend_name)]

        # Check single or multi-node setup
        env_ips = GeneralPMachine.get_all_ips()
        ssh_pass = General.get_config().get('mgmtcenter', 'password')
        for node_ip in env_ips:
            client = SSHClient(node_ip, username='root', password=ssh_pass)
            for file_to_check in files_to_check:
                if client.file_exists(file_to_check):
                    issues_found += "File {0} still present after backend {1} removal on node {2}\n".format(file_to_check, backend_name, node_ip)

        assert issues_found == '', "Following issues where found with the backend:\n{0}".format(issues_found)

    @staticmethod
    def check_license_headers_test():
        """
        Check license headers
        """
        license_header = re.compile('Copyright 201[4-9] iNuron NV')
        license_to_check = ['',
                            'Licensed under the Open vStorage Modified Apache License (the "License");',
                            'you may not use this file except in compliance with the License.',
                            'You may obtain a copy of the License at',
                            '',
                            '    http://www.openvstorage.org/license',
                            '',
                            'Unless required by applicable law or agreed to in writing, software',
                            'distributed under the License is distributed on an "AS IS" BASIS,',
                            'WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.',
                            'See the License for the specific language governing permissions and',
                            'limitations under the License.']

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
                            continue

                        files_with_diff_licenses[storagerouter.guid].append(file_name)
                        break

        for storagerouter in storagerouters:
            assert len(files_with_diff_licenses[storagerouter.guid]) == 0, 'Following files were found with different licenses:\n - {0}'.format('\n - '.join(files_with_diff_licenses[storagerouter.guid]))
