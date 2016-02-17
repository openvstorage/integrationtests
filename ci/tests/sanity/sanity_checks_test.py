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

import os
import time
from nose.plugins.skip import SkipTest
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.lists.vpoollist import VPoolList
from ovs.dal.lists.pmachinelist import PMachineList
from ci.tests.general.connection import Connection
from ci.tests.general import general
from ci.tests.vpool import generic
from ci.tests.general.general import test_config
from ci.tests.backend import alba, generic as backend_generic
from ci import autotests

BACKEND_TYPE = test_config.get('backend', 'type')
GRID_IP = test_config.get('main', 'grid_ip')
assert BACKEND_TYPE in backend_generic.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

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
    generic.add_alba_backend()
    generic.add_generic_vpool()


def teardown():
    api = Connection.get_connection()
    vpool_name = general.test_config.get("vpool", "vpool_name")
    vpool_list = api.get_component_by_name('vpools', vpool_name)
    if vpool_list:
        general.api_remove_vpool(vpool_name)
    generic.remove_alba_backend()


def ssh_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    issues_found = ''

    env_ips = autotests._get_ips()
    if len(env_ips) == 1:
        raise SkipTest('Environment has only 1 node')

    for env_ip_connecting_from in env_ips:
        out = general.execute_command_on_node(env_ip_connecting_from, "cat ~/.ssh/known_hosts")
        for env_ip_connecting_to in env_ips:
            if env_ip_connecting_from != env_ip_connecting_to:
                if env_ip_connecting_to not in out:
                    issues_found += "Host key verification not found between {0} and {1}\n".format(env_ip_connecting_from, env_ip_connecting_to)

    assert issues_found == '', 'Following issues where found:\n{0}'.format(issues_found)


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
        raise SkipTest('No backend present at the time of the test')

    backend_name = general.test_config.get("backend", "name")
    backend = BackendList.get_by_name(backend_name)
    assert backend, "Test backend: not found in model"
    assert backend.backend_type.code == 'alba', "Backend: {0} not of type alba but of type: {1}".format(backend.name, backend.backend_type.code)
    assert backend.status == 'RUNNING', "Backend: {0} in state: {1}, expected state: running".format(backend.name, backend.status)


def check_backend_services_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=7,
                          tests_to_run=testsToRun)

    backends_present_on_env = BackendList.get_backends()
    if len(backends_present_on_env) == 0:
        raise SkipTest('No backend present at the time of the test')

    # TODO: more than 1 backends present
    # TODO: different backends not just alba

    my_backend_name = backends_present_on_env[0].name
    backend_services = ["ovs-alba-rebalancer_{0}".format(my_backend_name),
                        "ovs-alba-maintenance_{0}".format(my_backend_name),
                        "ovs-arakoon-{0}-abm".format(my_backend_name),
                        "ovs-arakoon-{0}-nsm_0".format(my_backend_name)]

    out, err = general.execute_command("initctl list | grep ovs-*")
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
        raise SkipTest('No backend present at the time of the test')

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
        out_abm, err = general.execute_command("/usr/bin/arakoon --who-master -config {0}".format(files_to_check[0]))
        out_nsm, err = general.execute_command("/usr/bin/arakoon --who-master -config {0}".format(files_to_check[1]))
        assert len(out_abm) and len(out_nsm), "No arakoon master found in config files"
    else:
        nsm_config_file_found = False
        for node_ip in env_ips:
            out = general.execute_command_on_node(node_ip, '[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(files_to_check[0]))
            assert 'not' not in out, "Couldn't find {0} on node {1}".format(files_to_check[0], node_ip)
            out = general.execute_command_on_node(node_ip, '[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(files_to_check[1]))
            if 'not' not in out:
                nsm_config_file_found = True
                out_nsm = general.execute_command_on_node(node_ip, "/usr/bin/arakoon --who-master -config {0}".format(files_to_check[1]))
                assert len(out_nsm), "No arakoon master found in the namespace manager config file found on node {0}".format(node_ip)
            out_abm = general.execute_command_on_node(node_ip, "/usr/bin/arakoon --who-master -config {0}".format(files_to_check[0]))
            assert len(out_abm), "No arakoon master found in the alba manager config file on {0}".format(node_ip)
        assert nsm_config_file_found, "No namespace manager config file found on any of the nodes"


def check_vpool_sanity_test(vpool_name=''):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=9,
                          tests_to_run=testsToRun)

    if not vpool_name:
        vpool_name = general.test_config.get("vpool", "vpool_name")

    issues_found = ""
    vpool_services = ["ovs-arakoon-voldrv",
                      "ovs-watcher-volumedriver",
                      "ovs-albaproxy_{0}".format(vpool_name),
                      "ovs-dtl_{0}".format(vpool_name),
                      "ovs-volumedriver_{0}".format(vpool_name)]

    vpool_config_files = ["/opt/OpenvStorage/config/arakoon/voldrv/voldrv.cfg",
                          "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}.json".format(vpool_name),
                          "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}_alba.cfg".format(vpool_name),
                          "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}_alba.json".format(vpool_name)]

    storagedriver_partitions = {"WRITE": {"SCO": False,
                                          "FD": False,
                                          "DTL": False,
                                          "FCACHE": False},
                                "READ": {"None": False},
                                "DB": {"TLOG": False,
                                       "MD": False,
                                       "MDS": False},
                                "SCRUB": {"None": False}}

    directories_to_check = ["/mnt/{0}/".format(vpool_name)]
    # TODO: extend the check to all folders created for vpool (/mnt/storage, /mnt/ssd)

    # check vpool is modeled
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    # TODO: think of a way to skip the test if there's no vpool to check(mainly for full autotest runs)
    if not vpool:
        raise SkipTest('No vpool present at the time of the test')
    # assert vpool.name == vpool_name, "No vpool found modeled with {0} name".format(vpool_name)

    # @TODO check services on each node after implementing vpool extension to all nodes
    env_ips = [GRID_IP]
    # env_ips = autotests._get_ips()
    for node_ip in env_ips:
        for vpool_service in vpool_services:
            out = general.execute_command_on_node(node_ip, "initctl list | grep {0}".format(vpool_service))
            if "running" not in out:
                issues_found += "Vpool service {0} not running.Has following status:{1}\n ".format(vpool_service, out)
        for config_file_to_check in vpool_config_files:
            out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(config_file_to_check))
            if len(err):
                issues_found += "Error executing command to get {0} info:{1}".format(config_file_to_check, err)
            if 'not' in out:
                issues_found += "Couldn't find {0} on node {1}".format(config_file_to_check, node_ip)

    # WRITE/FCACHE only for alba
    backend_name = general.test_config.get("backend", "name")
    be = BackendList.get_by_name(backend_name)
    if not be.backend_type.name == 'ALBA':
        storagedriver_partitions["WRITE"]["FCACHE"] = True
    for sd in vpool.storagedrivers:
        for part in sd.partitions:
            storagedriver_partitions[str(part.role)][str(part.sub_role)] = True
    for role in storagedriver_partitions.iterkeys():
        for sub_role in storagedriver_partitions[role].iterkeys():
            if not storagedriver_partitions[role][sub_role]:
                issues_found += "Couldn't find {0} partition role with {1} subrole".format(role, sub_role)

    for directory in directories_to_check:
        out, err = general.execute_command('[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(directory))
        if len(err):
            issues_found += "Error executing command to get {0} info:{1}".format(directory, err)
        if 'not' in out:
            issues_found += "Couldn't find {0}".format(directory)

    # checking if we can truncate and dd
    # create volume
    local_vsa = general.get_local_vsa()
    sd = [sd for sd in vpool.storagedrivers if sd.storagerouter.ip == local_vsa.ip][0]
    pmachine_type = PMachineList.get_pmachines()[0].hvtype
    if pmachine_type == 'VMWARE':
        file_name = os.path.join(sd.mountpoint, "validate_vpool" + str(time.time()).replace(".", "") + "-flat.vmdk")
    else:
        file_name = os.path.join(sd.mountpoint, "validate_vpool" + str(time.time()).replace(".", "") + ".raw")

    cmd = "truncate {0} --size 10000000".format(file_name)
    out, error = general.execute_command(cmd)
    if error:
        issues_found += "Exception occurred while running {0}:\n{1}\n{2}".format(cmd, out, error)

    time.sleep(10)
    general.execute_command("rm {0}".format(file_name))

    assert len(issues_found) == 0, "Following issues found with vpool {0}\n{1}\n".format(vpool_name, issues_found)


def check_vpool_remove_sanity_test(vpool_name=''):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=10,
                          tests_to_run=testsToRun)

    if not vpool_name:
        vpool_name = general.test_config.get("vpool", "vpool_name")

    api = Connection.get_connection()
    vpool_list = api.get_component_by_name('vpools', vpool_name)
    assert vpool_list, "No vpool found where one was expected"
    general.api_remove_vpool(vpool_name)

    issues_found = ""

    vpool_services = ["ovs-albaproxy_{0}".format(vpool_name),
                      "ovs-dtl_{0}".format(vpool_name),
                      "ovs-volumedriver_{0}".format(vpool_name)]

    vpool_config_files = ["/opt/OpenvStorage/config/storagedriver/storagedriver/{0}.json".format(vpool_name),
                          "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}_alba.cfg".format(vpool_name),
                          "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}_alba.json".format(vpool_name)]

    storagedriver_partitions = {"WRITE": {"SCO": False,
                                          "FD": False,
                                          "DTL": False,
                                          "FCACHE": False},
                                "READ": {"None": False},
                                "DB": {"TLOG": False,
                                       "MD": False,
                                       "MDS": False},
                                "SCRUB": {"MDS": False}}

    directories_to_check = ["/mnt/{0}/".format(vpool_name)]
    # TODO: extend the check to all folders created for vpool (/mnt/storage, /mnt/ssd)

    # check vpool is not modeled anymore
    vpool = VPoolList.get_vpool_by_name(vpool_name)
    if vpool:
        issues_found += "Vpool still found in model:\n{0}".format(vpool)

    env_ips = autotests._get_ips()

    for node_ip in env_ips:
        out = general.execute_command_on_node(node_ip, "initctl list | grep ovs")
        for vpool_service in vpool_services:
            if vpool_service in out:
                issues_found += "Vpool service {0} still running.Has following status:{1}\n ".format(vpool_service, out)
        for config_file_to_check in vpool_config_files:
            out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(config_file_to_check))
            if len(err):
                issues_found += "Error executing command to get {0} info:{1}".format(config_file_to_check, err)
            if 'not' not in out:
                issues_found += "{0} file still present on node {1}".format(config_file_to_check, node_ip)

    for directory in directories_to_check:
        out, err = general.execute_command('[ -d {0} ] && echo "Dir exists" || echo "Dir does not exists"'.format(directory))
        if len(err):
            issues_found += "Error executing command to get {0} info:{1}".format(directory, err)
        if 'not' not in out:
            issues_found += "Directory {0} still present".format(directory)

    if vpool:
        for sd in vpool.storagedrivers:
            for part in sd.partitions:
                storagedriver_partitions[str(part.role)][str(part.sub_role)] = True
        for role in storagedriver_partitions.iterkeys():
            for sub_role in storagedriver_partitions[role].iterkeys():
                if storagedriver_partitions[role][sub_role]:
                    issues_found += "Still found {0} partition role with {1} subrole after vpool deletion".format(role, sub_role)

    assert len(issues_found) == 0, "Following issues found with vpool {0}\n{1}\n".format(vpool_name, issues_found)


def check_backend_removal_test(backend_name=''):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=11,
                          tests_to_run=testsToRun)

    if not backend_name:
        backend_name = general.test_config.get("backend", "name")

    backend = backend_generic.get_backend_by_name_and_type(backend_name, BACKEND_TYPE)
    if backend:
        alba_backend = alba.get_alba_backend(backend['alba_backend_guid'])
        alba.unclaim_disks(alba_backend)
        alba.remove_alba_backend(backend['alba_backend_guid'])

    issues_found = ''
    backends_present_on_env = BackendList.get_backends()
    for backend in backends_present_on_env:
        if backend.name == backend_name:
            issues_found += 'Backend {0} still present in the model with status {1}\n'.format(backend_name, backend.status)

    backend_services = ["ovs-alba-rebalancer_{0}".format(backend_name),
                        "ovs-alba-maintenance_{0}".format(backend_name),
                        "ovs-arakoon-{0}-abm".format(backend_name),
                        "ovs-arakoon-{0}-nsm_0".format(backend_name)]

    out, err = general.execute_command("initctl list | grep ovs-*")
    statuses = out.splitlines()

    for status_line in statuses:
        for service_to_check in backend_services:
            if service_to_check in status_line:
                issues_found += "Backend service {0} still present.Has following status:{1}\n ".format(service_to_check, status_line)

    files_to_check = ["/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-abm.cfg".format(backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-nsm_0/{0}-nsm_0.cfg".format(backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-rebalancer.json".format(backend_name),
                      "/opt/OpenvStorage/config/arakoon/{0}-abm/{0}-maintenance.json".format(backend_name)]

    # check single or multinode setup
    env_ips = autotests._get_ips()
    if len(env_ips) == 1:
        # check files
        for file_to_check in files_to_check:
            out, err = general.execute_command('[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(file_to_check))
            if 'not' not in out:
                issues_found += "File {0} still present after backend {1} removal\n".format(file_to_check, backend_name)
    else:
        for node_ip in env_ips:
            for file_to_check in files_to_check:
                out = general.execute_command_on_node(node_ip, '[ -f {0} ] && echo "File exists" || echo "File does not exists"'.format(file_to_check))
                if 'not' not in out:
                    issues_found += "File {0} still present after backend {1} removal on node {2}\n".format(file_to_check, backend_name, node_ip)

    assert issues_found == '', "Following issues where found with the backend:\n{0}".format(issues_found)
