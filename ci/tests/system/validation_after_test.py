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

import os
import time

from nose.plugins.skip import SkipTest

from ci.tests.general import general
from ci import autotests

testsToRun = general.get_tests_to_run(autotests.getTestLevel())


def setup():
    print "setup called " + __name__
    general.cleanup()


def teardown():
    pass


def ovs_2053_check_for_alba_warnings_test():
    """
    %s
    """ % general.get_function_name()

    general.check_prereqs(testcase_number=1,
                          tests_to_run=testsToRun)

    out = general.execute_command_on_node('127.0.0.1', "grep warn /var/log/upstart/*-asd-*.log | wc -l")
    assert out == '0', \
        "syncfs warnings detected in asd logs\n:{0}".format(out.splitlines())
