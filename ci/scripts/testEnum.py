# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

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

    def start_test(self, test):
        testinfo = test.address()
        import os

        os.write(1, str(testinfo) + "\n")
        test_name = '%s:%s' % (testinfo[1], testinfo[2])
        if test_name not in self._tests:
            self._tests.append(test_name)
        return None

    def set_output_stream(self, stream):
        class DummyStream(object):
            writeln = flush = write = lambda self, *args: None

        return DummyStream()

    def finalize(self, result):
        for test_name in self._tests:
            print test_name
        return None

