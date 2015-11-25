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
This plugin enumerates the tests in a format that can be copy pasted as input for running tests.
"""
from nose.plugins.base import Plugin


class TestEnum(Plugin):
    """
    Nose plugin to enumerate tests
    """
    name = 'testEnum'
    score = 400

    def __init__(self):
        Plugin.__init__(self)
        self._tests = []

    def options(self, parser, env):
        Plugin.options(self, parser, env)

    def configure(self, options, conf):
        Plugin.configure(self, options, conf)
        self.config = conf

    def startTest(self, test):
        testinfo = test.address()
        import os

        os.write(1, str(testinfo) + "\n")
        testName = '%s:%s' % (testinfo[1], testinfo[2])
        if testName not in self._tests:
            self._tests.append(testName)
        return None

    def setOutputStream(self, stream):
        class DummyStream(object):
            writeln = flush = write = lambda self, *args: None

        return DummyStream()

    def finalize(self, result):
        for testName in self._tests:
            print testName
        return None

