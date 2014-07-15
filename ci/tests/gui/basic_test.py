# Copyright 2014 CloudFounders NV
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from vpool_test import VpoolTest
vpt = VpoolTest('chrome')

def setup():
    print "setup called ..."
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

    vpt.set_vpool_temp_mp('/var/tmp')
    vpt.set_vpool_md_mp('/mnt/metadata/ceph')
    vpt.set_vpool_cache_mp('/mnt/cache/ceph')
    vpt.set_vpool_vrouter_port(12323)
    vpt.set_vpool_storage_ip('172.22.131.10')

def teardown():
    vpt.teardown()

def ovs_login_test():
    setup()
    print 'url: {0}'.format(vpt.get_vpool_url())
    print 'user: {0}'.format(vpt.get_username())
    print 'pass: {0}'.format(vpt.get_password())

    vpt.login_test()


def vpool_add_test():
    try:
        vpt.add_vpool_test()
    except Exception as ex:
        print str(ex)
        vpt.teardown()
        print 'Browser shutdown ...'
        raise
