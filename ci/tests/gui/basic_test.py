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


from ci.tests.general   import general
from vpool              import Vpool
from browser_ovs        import BrowserOvs
from ci                 import autotests

testsToRun = general.getTestsToRun(autotests.getTestLevel())


def setup():

    print "setup called " + __name__


def teardown():
    pass


def ovs_login_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 1,
                         testsToRun     = testsToRun)

    try:
        bt = BrowserOvs()
        bt.login()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        bt.teardown()


def vpool_add_test():
    """
    """

    general.checkPrereqs(testCaseNumber = 2,
                         testsToRun     = testsToRun)


    """
    vpt.set_username('admin')
    vpt.set_password('admin')
    vpt.set_url('https://10.100.131.71/')
    vpt.set_debug(True)

    vpt.set_vpool_name('saio')
    vpt.set_vpool_type('Swift S3')
    vpt.set_vpool_host('10.100.131.91')
    vpt.set_vpool_port(8080)
    vpt.set_vpool_access_key('test:tester')
    vpt.set_vpool_secret_key('testing')

    vpt.set_vpool_temp_mp('/var/tmp')
    vpt.set_vpool_md_mp('/mnt/metadata/saio')
    vpt.set_vpool_cache_mp('/mnt/cache/saio')
    vpt.set_vpool_vrouter_port(12323)
    vpt.set_vpool_storage_ip('172.22.131.10')
    """

    try:
        vpt = Vpool()
        vpt.login()
        vpt.add_vpool()
    except Exception as ex:
        print str(ex)
        raise
    finally:
        vpt.teardown()
