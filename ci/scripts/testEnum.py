"""
This plugin enumerates the tests in a format that can be copy pasted as input for running tests.
"""
from nose2.plugins.base import Plugin


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

