# Copyright 2014 Open vStorage NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ci.tests.general import general
from ci import autotests

testsToRun = general.get_tests_to_run(autotests.getTestLevel())


def setup():
    print "Setup called " + __name__


def teardown():
    pass


def services_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    # get env ips
    env_ips = autotests._get_ips()
    non_running_services = []

    for env_ip in env_ips:
        non_running_services_on_node = []
        out = general.execute_command_on_node(env_ip, "initctl list | grep ovs-*")
        statuses = out.splitlines()

        non_running_services_on_node.extend([s for s in statuses if 'start/running' not in s])
        non_running_services.append([env_ip, non_running_services_on_node])

    for node_services in non_running_services:
        assert len(node_services[1]) == 0, "Found non running services on node {0}\n{1}".format(node_services[0], node_services[1])


def non_visible_services_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=2,
                          tests_to_run=testsToRun)

    # check nginx
    out, err = general.execute_command("ps aux |grep [/]usr/sbin/nginx")
    assert len(err) == 0, "Error executing command to get nginx info:{0}".format(err)
    assert 'nginx' in out, "Couldn't find any nginx running process:{0}".format(out)

    # check rabbitmq-server
    out, err = general.execute_command("ps aux |grep [r]abbitmq-server")
    assert len(err) == 0, "Error executing command to get rabbitmq-server info:{0}".format(err)
    assert 'rabbitmq-server' in out, "Couldn't find any rabbitmq-server running process:{0}".format(out)

    # check memcached
    out, err = general.execute_command("ps aux |grep [m]emcached")
    assert len(err) == 0, "Error executing command to get memcached info:{0}".format(err)
    assert 'memcache' in out, "Couldn't find any memcache running process:{0}".format(out)


def config_files_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=3,
                          tests_to_run=testsToRun)

    # check memcacheclient.cfg
    location = "/opt/OpenvStorage/config/memcacheclient.cfg"
    out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(location))
    assert len(err) == 0, "Error executing command to get memcacheclient.cfg info:{0}".format(err)
    assert 'not' not in out, "Couldn't find memcacheclient.cfg"

    # check rabbitmqclient.cfg
    location = "/opt/OpenvStorage/config/rabbitmqclient.cfg"
    out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(location))
    assert len(err) == 0, "Error executing command to get rabbitmqclient.cfg info:{0}".format(err)
    assert 'not' not in out, "Couldn't find rabbitmqclient.cfg"

    # check ovsdb.cfg
    location = "/opt/OpenvStorage/config/arakoon/ovsdb/ovsdb.cfg"
    out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(location))
    assert len(err) == 0, "Error executing command to get ovsdb.cfg info:{0}".format(err)
    assert 'not' not in out, "Couldn't find ovsdb.cfg"
