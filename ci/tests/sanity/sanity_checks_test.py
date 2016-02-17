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

from nose.plugins.skip import SkipTest
from ovs.dal.lists.backendlist import BackendList
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonInstaller
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.sshclient import SSHClient
from ci.tests.general import general, general_alba
from ci.tests.vpool.general_vpool import GeneralVPool
from ci.tests.backend import alba, general_backend

BACKEND_TYPE = general.get_config().get('backend', 'type')
GRID_IP = general.get_config().get('main', 'grid_ip')
SSH_USER = 'root'
SSH_PASS = general.get_config().get('mgmtcenter', 'password')
assert BACKEND_TYPE in general_backend.VALID_BACKEND_TYPES, "Please fill out a valid backend type in autotest.cfg file"

testsToRun = general.get_tests_to_run(general.get_test_level())
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


def setup():
    """
    Make necessary changes before being able to run the tests
    :return: None
    """
    print "Setup called " + __name__
    general_alba.add_alba_backend()
    GeneralVPool.add_vpool()


def teardown():
    """
    Removal actions of possible things left over after the test-run
    :return: None
    """
    vpool_name = general.get_config().get("vpool", "name")
    vpool = GeneralVPool.get_vpool_by_name(vpool_name)
    if vpool is not None:
        GeneralVPool.remove_vpool(vpool)
    general_alba.remove_alba_backend()


def ssh_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    issues_found = ''

    env_ips = general.get_ips()
    if len(env_ips) == 1:
        raise SkipTest()

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
    env_ips = general.get_ips()
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
    client = SSHClient(GRID_IP, username=SSH_USER, password=SSH_PASS)

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


def config_files_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=4,
                          tests_to_run=testsToRun)

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

    client = SSHClient(GRID_IP, username=SSH_USER, password=SSH_PASS)
    for config_file_to_check in config_files.iterkeys():
        if not client.file_exists(config_files[config_file_to_check]):
            issues_found += "Couldn't find {0}\n".format(config_file_to_check)

    assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)


def json_files_check_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=5,
                          tests_to_run=testsToRun)

    issues_found = ''

    srs = StorageRouterList.get_storagerouters()
    for sr in srs:
        config_contents = EtcdConfiguration.get('/ovs/framework/hosts/{0}/setupcompleted'.format(sr.machine_id), raw = True)
        if "true" not in config_contents:
            issues_found += "Setup not completed for node {0}\n".format(sr.name)

    assert issues_found == '', "Found the following issues while checking for the setupcompleted:{0}\n".format(issues_found)


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

    backend_name = general.get_config().get("backend", "name")
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
        raise SkipTest()

    # TODO: more than 1 backends present
    # TODO: different backends not just alba
    issues_found = ''

    my_backend_name = backends_present_on_env[0].name
    backend_services = ["ovs-alba-maintenance_{0}".format(my_backend_name),
                        "ovs-arakoon-{0}-abm".format(my_backend_name),
                        "ovs-arakoon-{0}-nsm_0".format(my_backend_name)]

    out, err = general.execute_command("initctl list | grep ovs-*")
    statuses = out.splitlines()

    for status_line in statuses:
        for service_to_check in backend_services:
            if service_to_check in status_line:
                if "running" not in status_line:
                    issues_found += "Backend service {0} not running.Has following status:{1}\n ".format(service_to_check, status_line)

    assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)


def check_backend_files_test():
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=8,
                          tests_to_run=testsToRun)

    backends_present_on_env = BackendList.get_backends()
    if len(backends_present_on_env) == 0:
        raise SkipTest()

    issues_found = ''

    my_backend_name = backends_present_on_env[0].name
    files_to_check = ["ovs/arakoon/{0}-abm/config".format(my_backend_name),
                      "ovs/arakoon/{0}-nsm_0/config".format(my_backend_name)]

    # check single or multinode setup
    env_ips = general.get_ips()
    if len(env_ips) == 1:
        # check files
        for file_to_check in files_to_check:
            out, err = general.execute_command('etcdctl ls --recursive /ovs | grep {0}'.format(file_to_check))
            if len(err):
                issues_found += "Error executing command to get {0} info:{1}\n".format(file_to_check, err)
            else:
                if len(out) == 0:
                    issues_found += "Couldn't find {0}\n".format(file_to_check)
        # check cluster arakoon master
        out, err = general.execute_command("arakoon --who-master -config {0}".format(ArakoonInstaller.ETCD_CONFIG_PATH.format('ovsdb')))
        if len(out) == 0:
            issues_found += "No arakoon master found in config files\n"
    # @TODO: check to see multi node setup
    assert issues_found == '', "Found the following issues while checking for the config files:{0}\n".format(issues_found)


def check_vpool_remove_sanity_test(vpool_name=''):
    """
    {0}
    """.format(general.get_function_name())

    general.check_prereqs(testcase_number=10,
                          tests_to_run=testsToRun)

    if not vpool_name:
        vpool_name = general.get_config().get("vpool", "name")

    vpool = GeneralVPool.get_vpool_by_name(vpool_name)
    assert vpool is not None, "No vpool found where one was expected"
    GeneralVPool.remove_vpool(vpool)

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

    env_ips = general.get_ips()

    for node_ip in env_ips:
        client = SSHClient(node_ip, username=SSH_USER, password=SSH_PASS)
        for vpool_service in vpool_services:
            out = general.execute_command_on_node(node_ip, "initctl list | grep ovs")
            for line in out.splitlines():
                if vpool_service in line:
                    issues_found += "Vpool service {0} still running.Has following status:{1}\n ".format(vpool_service, line)
        for config_file_to_check in vpool_config_files:
            if client.file_exists(config_file_to_check):
                issues_found += "{0} file still present on node {1}".format(config_file_to_check, node_ip)

    client = SSHClient(GRID_IP, username=SSH_USER, password=SSH_PASS)
    for directory in directories_to_check:
        if client.dir_exists(directory):
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
        backend_name = general.get_config().get("backend", "name")

    backend = general_backend.get_backend_by_name_and_type(backend_name, BACKEND_TYPE)
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
    env_ips = general.get_ips()
    for node_ip in env_ips:
        client = SSHClient(node_ip, username=SSH_USER, password=SSH_PASS)
        for file_to_check in files_to_check:
            if client.file_exists(file_to_check):
                issues_found += "File {0} still present after backend {1} removal on node {2}\n".format(file_to_check, backend_name, node_ip)

    assert issues_found == '', "Following issues where found with the backend:\n{0}".format(issues_found)
