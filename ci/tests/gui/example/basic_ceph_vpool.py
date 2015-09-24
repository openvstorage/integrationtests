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

from ci.tests.gui.example.vpool_helper import VpoolTest
from ci.tests.api.connection import Connection

vpt = VpoolTest('chrome')
conn = Connection('10.100.131.71', 'admin', 'admin')
conn.authenticate()


def setup():
    vpt.set_username('admin')
    vpt.set_password('admin')
    vpt.set_url('https://10.100.131.71/')
    vpt.set_debug(True)

    vpt.set_vpool_name('ceph')
    vpt.set_vpool_type('Ceph S3')
    vpt.set_vpool_host('10.100.131.91')
    vpt.set_vpool_port(80)
    vpt.set_vpool_access_key('0OMK2V3HQJ4JNDT766UF')
    vpt.set_vpool_secret_key('RCz00qAo+jgRlPLVdXoP1RUZfU5RzjOFRQJBJxyR')

    vpt.set_vpool_temp_mp('/var/tmp/{0}'.format(vpt.get_vpool_name()))
    vpt.set_vpool_md_mp('/mnt/md/{0}'.format(vpt.get_vpool_name()))
    vpt.set_vpool_readcache_mp('/mnt/cache1/{0}/read'.format(vpt.get_vpool_name()))
    vpt.set_vpool_writecache_mp('/mnt/cache1/{0}/write'.format(vpt.get_vpool_name()))
    vpt.set_vpool_dtl_mp('/mnt/cache1/{0}/dtl'.format(vpt.get_vpool_name()))
    vpt.set_vpool_vrouter_port(12323)
    vpt.set_vpool_storage_ip('172.22.131.10')


def teardown():
    vpt.teardown()


def wait_for_tasks_to_complete():
    count = 10
    while count > 0:
        if not conn.get_active_tasks():
            break
        print "Waiting for tasks to complete ..."


def ceph_add_extend_remove_test():
    setup()
    try:
        vpt.login_test()
        vpt.add_vpool_test()
        wait_for_tasks_to_complete()
        vpt.login_test()
        vpt.add_gsrs_to_vpool_test()
        vpt.login_test()
        vpt.remove_vpool_test()
        wait_for_tasks_to_complete()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        vpt.teardown()
