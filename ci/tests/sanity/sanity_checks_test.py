# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from nose.plugins.skip import SkipTest

from ovs.dal.lists.backendlist import BackendList

from ci.tests.general import general
from ci import autotests

testsToRun = general.get_tests_to_run(autotests.get_test_level())
services_to_commands = {
    "nginx": "ps aux |grep [/]usr/sbin/nginx",
    "rabbitmq-server": "ps aux |grep [r]abbitmq-server",
    "memcached": "ps aux |grep [m]emcached",
    "ovs-arakoon-ovsdb": "ps aux |grep [o]vsdb| grep -v config",
    "ovs-snmp": "ps aux | grep [o]vssnmp",
    "ovs-support-agent": "ps aux | grep [s]upport/agent",
    "ovs-volumerouter-consumer": "ps aux | grep [v]olumerouter",
    "ovs-watcher-framework": "ps aux | grep [w]atcher | grep framework"
}


def setup():
    print "Setup called " + __name__


def teardown():
    pass


def ssh_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    env_ips = autotests._get_ips()
    if len(env_ips) == 1:
        raise SkipTest()

    for env_ip_connecting_from in env_ips:
        out, err = general.execute_command_on_node(env_ip_connecting_from, "cat .ssh/known_hosts")
        for env_ip_connecting_to in env_ips:
            if env_ip_connecting_from != env_ip_connecting_to:
                assert env_ip_connecting_to in out, "Host key verification not found between {0} and {1}".format(env_ip_connecting_from, env_ip_connecting_to)


def services_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)

    # get env ips
    env_ips = autotests._get_ips()
    non_running_services = []

    for env_ip in env_ips:
        non_running_services_on_node = []
        out = general.execute_command_on_node(env_ip, "initctl list | grep ovs-*")
        statuses = out.splitlines()

        non_running_services_on_node.extend([s for s in statuses if 'start/running' not in s])
        if len(non_running_services_on_node):
            non_running_services.append([env_ip, non_running_services_on_node])

    assert len(non_running_services) == 0, "Found non running services on {0}".format(non_running_services)


def system_services_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    errors = ''
    services_checked = 'Following services found running:\n'

    for service_to_check in services_to_commands.iterkeys():
        out, err = general.execute_command(services_to_commands[service_to_check])
        if len(err):
            errors += "Error executing command to get {0} info:{1}\n".format(service_to_check, err)
        else:
            if len(out):
                errors += "Couldn't find any {0} running process:{1}".format(service_to_check, out)
            else:
                services_checked += "{0}\n".format(service_to_check)

    print services_checked
    assert len(errors) == 0, "Found the following errors while checking for the system services:{0}\n".format(errors)


def config_files_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)

    config_files = {
        "memcacheclient.cfg": "/opt/OpenvStorage/config/memcacheclient.cfg",
        "rabbitmqclient.cfg": "/opt/OpenvStorage/config/rabbitmqclient.cfg",
        "ovsdb.cfg": "/opt/OpenvStorage/config/arakoon/ovsdb/ovsdb.cfg"
    }

    for config_file_to_check in config_files.iterkeys():
        out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(config_files[config_file_to_check]))
        assert len(err) == 0, "Error executing command to get {0} info:{1}".format(config_file_to_check, err)
        assert 'not' not in out, "Couldn't find {0}".format(config_file_to_check)


def json_files_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=5,
                          tests_to_run=testsToRun)

    out, err = general.execute_command("cat /opt/OpenvStorage/config/ovs.json")
    assert len(err) == 0, "Error found when trying to read ovs.json file:\n{0}".format(err)
    lines = out.splitlines()
    setup_completed_found = False

    for line in lines:
        if "setupcompleted" in line:
            setup_completed_found = True
            assert "true" in line, "OVS setup complete flag has the wrong value:\n{0}".format(line)

    assert setup_completed_found, "OVS setup complete flag was never found in ovs.json file"


# backend setup validation
def check_model_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=6,
                          tests_to_run=testsToRun)

    backends_present_on_env = BackendList.get_backends()
    if len(backends_present_on_env) == 0:
        raise SkipTest()

    for be in backends_present_on_env:
        if be.backend_type.code == 'alba':
            assert be.name == general.test_config.get("backend", "backend_name")
            assert be.status == 'RUNNING'


def check_backend_services_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=7,
                          tests_to_run=testsToRun)

    backends_present_on_env = BackendList.get_backends()
    if len(backends_present_on_env) == 0:
        raise SkipTest()

    # TODO: more than 1 back ends present
    # TODO: different backends not just alba

    my_backend_name = backends_present_on_env[0].name
    backend_services = ["ovs-alba-rebalancer_{0}".format(my_backend_name),
                        "ovs-alba-maintenance_{0}".format(my_backend_name),
                        "ovs-arakoon-{0}-abm".format(my_backend_name),
                        "ovs-arakoon-{0}-nsm_0".format(my_backend_name)]

    out = general.execute_command("initctl list | grep ovs-*")
    statuses = out.splitlines()

    for status_line in statuses:
        for service_to_check in backend_services:
            if service_to_check in status_line:
                assert "running" in status_line, "Backend service {0} not running.Has following status:{1}\n ".format(service_to_check, status_line)


def check_backend_files_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=8,
                          tests_to_run=testsToRun)

    backends_present_on_env = BackendList.get_backends()
    if len(backends_present_on_env) == 0:
        raise SkipTest()

    my_backend_name = backends_present_on_env[0].name
    files_to_check = ["/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-abm.cfg".format(my_backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-nsm_0/{0}-nsm_0.cfg".format(my_backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-rebalancer.json".format(my_backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-maintenance.json".format(my_backend_name)]

    # check single or multinode setup
    env_ips = autotests._get_ips()
    if len(env_ips) == 1:
        # check files
        for file_to_check in files_to_check:
            out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(file_to_check))
            assert len(err) == 0, "Error executing command to get {0} info:{1}".format(file_to_check, err)
            assert 'not' not in out, "Couldn't find {0}".format(file_to_check)
        # check cluster arakoon master
        out_abm, err = general.execute_command("/usr/bin/arakoon --who-master {0}".format(files_to_check[0]))
        out_nsm, err = general.execute_command("/usr/bin/arakoon --who-master -config {0}".format(files_to_check[1]))
        assert len(out_abm) and len(out_nsm), "No arakoon master found in config files"
    else:
        nsm_config_file_found = False
        for node_ip in env_ips:
            out, err = general.execute_command_on_node(node_ip, '[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(files_to_check[0]))
            assert len(err) == 0, "Error executing command to get {0} info:{1}".format(files_to_check[0], err)
            assert 'not' not in out, "Couldn't find {0} on node {1}".format(files_to_check[0], node_ip)
            out, err = general.execute_command_on_node(node_ip, '[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(files_to_check[1]))
            if 'not' not in out:
                nsm_config_file_found = True
                out_nsm, err = general.execute_command("/usr/bin/arakoon --who-master -config {0}".format(files_to_check[1]))
                assert len(out_nsm), "No arakoon master found in the namespace manager config file found on node {0}".format(node_ip)
            out_abm, err = general.execute_command("/usr/bin/arakoon --who-master {0}".format(files_to_check[0]))
            assert len(out_abm), "No arakoon master found in the alba manager config file on {0}".format(node_ip)
        assert nsm_config_file_found, "No namespace manager config file found on any of the nodes"
