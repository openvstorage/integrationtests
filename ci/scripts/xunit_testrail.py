# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/OVS_NON_COMMERCIAL
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This plugin is an extended version of the xunit plugin which also pushed to testrail each test updating it on the fly

It was designed for the `Hudson`_ continuous build system but will
probably work for anything else that understands an XUnit-formatted XML
representation of test results.

Add this shell command to your builder ::

    nosetests --with-xunit

And by default a file named nosetests.xml will be written to the
working directory.

In a Hudson builder, tick the box named "Publish JUnit test result report"
under the Post-build Actions and enter this value for Test report XMLs::

    **/nosetests.xml

If you need to change the name or location of the file, you can set the
``--xunit-file`` option.

Here is an abbreviated version of what an XML test report might look like::

    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="nosetests" tests="1" errors="1" failures="0" skip="0">
        <testcase classname="path_to_test_suite.TestSomething"
                  name="test_it" time="0">
            <error type="exceptions.TypeError" message="oops, wrong type">
            Traceback (most recent call last):
            ...
            TypeError: oops, wrong type
            </error>
        </testcase>
    </testsuite>

.. _Hudson: https://hudson.dev.java.net/

"""

import os
import re
import sys
import inspect
import datetime
import traceback
import ConfigParser
from time import time
from xml.sax import saxutils
from StringIO import StringIO

from ci.scripts import testrailapi
from nose.exc import SkipTest
from nose.loader import TestLoader
from nose.plugins.base import Plugin
from nose.pyversion import force_unicode, format_exception

import logging
log = logging.getLogger('xunit.testrail')


# Invalid XML characters, control characters 0-31 sans \t, \n and \r
CONTROL_CHARACTERS = re.compile(r"[\000-\010\013\014\016-\037]")

CRASH_FILE_LOG = "/var/log/testrunner_crash"


def xml_safe(value):
    """Replaces invalid XML characters with '?'."""
    return CONTROL_CHARACTERS.sub('?', value)


def escape_cdata(cdata):
    """Escape a string for an XML CDATA section."""
    return xml_safe(cdata).replace(']]>', ']]>]]&gt;<![CDATA[')


def nice_classname(obj):
    """Returns a nice name for class object or class instance.

        >>> nice_classname(Exception()) # doctest: +ELLIPSIS
        '...Exception'
        >>> nice_classname(Exception)
        'exceptions.Exception'

    """
    if inspect.isclass(obj):
        cls_name = obj.__name__
    else:
        cls_name = obj.__class__.__name__
    mod = inspect.getmodule(obj)
    if mod:
        name = mod.__name__
        # jython
        if name.startswith('org.python.core.'):
            name = name[len('org.python.core.'):]
        return "%s.%s" % (name, cls_name)
    else:
        return cls_name


def exc_message(exc_info):
    """Return the exception's message."""
    exc = exc_info[1]
    if exc is None:
        # str exception
        result = exc_info[0]
    else:
        try:
            result = str(exc)
        except UnicodeEncodeError:
            try:
                result = unicode(exc)
            except UnicodeError:
                # Fallback to args as neither str nor
                # unicode(Exception(u'\xe6')) work in Python < 2.6
                result = exc.args[0]
    return xml_safe(result)


def caseNameTestrailFormat(testName):
    match = re.search("c\d+_(.+)", testName)
    caseName = match.groups()[0] if match else testName
    return caseName


Q_AUTOMATED = "qAutomated"
AUTOTEST_DIR = os.path.join(os.sep, "opt", "OpenvStorage", "ci")
SCRIPTS_DIR = os.path.join(AUTOTEST_DIR, "scripts")
TESTS_DIR = os.path.join(AUTOTEST_DIR, "tests")
CONFIG_DIR = os.path.join(AUTOTEST_DIR, "config")

def formatDurations(dur):
    if not dur:
        return ""
    niceTime = lambda x: str(datetime.timedelta(seconds=int(x)))
    splits = dur.split("|")
    if len(splits) == 3:
        return "Past Runs Avg: " + niceTime(splits[2]) + " Min: " + niceTime(splits[0]) + " Max: " + niceTime(splits[1])
    else:
        return ""


class Tee(object):
    def __init__(self, encoding, *args):
        self._encoding = encoding
        self._streams = args

    def write(self, data):
        data = force_unicode(data, self._encoding)
        for s in self._streams:
            s.write(data)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        for s in self._streams:
            s.flush()

    def isatty(self):
        return False


class xunit_testrail(Plugin):
    """This plugin provides test results in the standard XUnit XML format."""
    name = 'xunit_testrail'
    score = 2000
    encoding = 'UTF-8'
    error_report_file = None

    def __init__(self):
        self._timer = 0.0
        self._capture_stack = []
        self._currentStdout = None
        self._currentStderr = None

    def _timeTaken(self):
        if hasattr(self, '_timer'):
            taken = time() - self._timer
        else:
            # test died before it ran (probably error in setup())
            # or success/failure added before test started probably
            # due to custom TestResult munging
            taken = 0.0
        return taken

    def _quoteattr(self, attr):
        """Escape an XML attribute. Value can be unicode."""
        attr = xml_safe(attr)
        if isinstance(attr, unicode):
            attr = attr.encode(self.encoding)
        return saxutils.quoteattr(attr)

    def options(self, parser, env):
        """Sets additional command line options."""
        Plugin.options(self, parser, env)
        parser.add_option('--xunit_file2',
                          action='store',
                          dest='xunit_file2',
                          metavar="FILE",
                          default=env.get('NOSE_XUNIT_FILE', 'nosetests.xml'),
                          help=("Path to xml file to store the xunit report in. "
                                "Default is nosetests.xml in the working directory "
                                "[NOSE_XUNIT_FILE]"))

        parser.add_option('--testrail-ip',
                          action="store",
                          dest="testrailIp",
                          metavar="FILE",
                          default="testrail.openvstorage.com",
                          help="Url of testrail server")

        parser.add_option('--project-name',
                          action="store",
                          dest="projectName",
                          metavar="FILE",
                          default="Open vStorage Engineering",
                          help="Testrail project name")

        parser.add_option('--push-name',
                          action="store",
                          dest="pushName",
                          metavar="FILE",
                          default="AT push results",
                          help="Testrail push name")

        parser.add_option('--description',
                          action="store",
                          dest="description",
                          metavar="FILE",
                          default="",
                          help="Testrail description")

        parser.add_option('--plan-id',
                          action="store",
                          dest="planId",
                          metavar="FILE",
                          default="",
                          help="Existing plan id")

    def configure(self, options, config):
        """Configures the xunit plugin."""
        self.enableOpt = 'enable_plugin_xunit_testrail'
        Plugin.configure(self, options, config)
        self.config = config
        self.enabled = True
        if self.enabled:
            self.stats = {'errors': 0,
                          'failures': 0,
                          'passes': 0,
                          'skipped': 0}
            self.errorlist = []
            self.error_report_file = open(options.xunit_file2, 'w')

            projectMapping = os.path.join(CONFIG_DIR, "project_testsuite_mapping.cfg")
            self.projectIni = ConfigParser.ConfigParser()
            self.projectIni.read(projectMapping)

            self.testrailIp = options.testrailIp
            if self.testrailIp:
                self.testrailApi = testrailapi.TestrailApi(self.testrailIp, key="cWFAY2xvdWRmb3VuZGVycy5jb206UjAwdDNy")

                allStatuses = self.testrailApi.getStatuses()
                self.ongoingStatus = [s for s in allStatuses if s['name'].lower() == 'ongoing'][0]
                self.passedStatus = [s for s in allStatuses if s['name'].lower() == 'passed'][0]
                self.failedStatus = [s for s in allStatuses if s['name'].lower() == 'failed'][0]
                self.skippedStatus = [s for s in allStatuses if s['name'].lower() == 'skipped'][0]
                self.blockedStatus = [s for s in allStatuses if s['name'].lower() == 'blocked'][0]

                nameSplits = options.pushName.split("_")
                name = nameSplits[0]
                today = datetime.datetime.today()
                name += "_" + today.strftime('%a %b %d %H:%M:%S')

                self.version = nameSplits[0]
                self.hypervisor = nameSplits[2]
                self.projectName = options.projectName

                allProjects = self.testrailApi.getProjects()

                self.projectID = [p for p in allProjects if p['name'] == self.projectName]
                if not self.projectID:
                    raise Exception("No project on {0} named: '{1}'".format(self.testrailIp, self.projectName))
                self.projectID = self.projectID[0]['id']

                self.existingPlan = bool(options.planId)
                if options.planId:
                    plan = self.testrailApi.getPlan(options.planId)
                    os.write(1, "\nContinuing with plan {0}\n".format(plan['url']))
                else:

                    milestoneID = None
                    description = options.description

                    plan = self.testrailApi.addPlan(self.projectID, name, description, milestoneID or None)
                    os.write(1, "\nNew test plan: " + plan['url'] + "\n")

                self.plan = plan
                self.suiteName = ""

                self.testsCaseIdsToSelect = list()

    def report(self, stream):
        """Writes an Xunit-formatted XML file
        The file includes a report of test errors and failures.
        """
        self.stats['encoding'] = self.encoding
        self.stats['total'] = (self.stats['errors'] + self.stats['failures']
                               + self.stats['passes'] + self.stats['skipped'])
        self.error_report_file.write(
            '<?xml version="1.0" encoding="%(encoding)s"?>'
            '<testsuite name="nosetests" tests="%(total)d" '
            'errors="%(errors)d" failures="%(failures)d" '
            'skip="%(skipped)d">' % self.stats)
        self.error_report_file.write(''.join(self.errorlist))
        self.error_report_file.write('</testsuite>')
        self.error_report_file.close()
        if self.config.verbosity > 1:
            stream.writeln("-" * 70)
            stream.writeln("XML: %s" % self.error_report_file.name)

    def _startCapture(self):
        log.info('_startCapture...')
        self._capture_stack.append((sys.stdout, sys.stderr))
        self._currentStdout = StringIO()
        self._currentStderr = StringIO()
        sys.stdout = Tee(self.encoding, self._currentStdout, sys.stdout)
        sys.stderr = Tee(self.encoding, self._currentStderr, sys.stderr)

    def startContext(self, context):
        pass

    def stopContext(self, context):
        pass

    def beforeTest(self, test):
        log.info('beforeTest...')
        """Initializes a timer before starting a test."""
        self._timer = time()
        self._startCapture()

    def _endCapture(self):
        log.info('_endCapture...')
        if self._capture_stack:
            import pprint
            pprint.pprint(self._capture_stack)
            sys.stdout, sys.stderr = self._capture_stack.pop()

    def afterTest(self, test):
        log.info('afterTest...')
        self._endCapture()
        self._currentStdout = None
        self._currentStderr = None

    def finalize(self, test):
        while self._capture_stack:
            self._endCapture()

    def _getCapturedStdout(self):
        if self._currentStdout:
            value = self._currentStdout.getvalue()
            if value:
                return '<system-out><![CDATA[%s]]></system-out>' % escape_cdata(value)
        return ''

    def _getCapturedStderr(self):
        if self._currentStderr:
            value = self._currentStderr.getvalue()
            if value:
                return '<system-err><![CDATA[%s]]></system-err>' % escape_cdata(value)
        return ''

    def startTest(self, test):
        """Initializes a timer before starting a test."""
        test_id = test.id()
        if self.testrailIp:
            try:
                testName = test_id.split('.')[-1]
                suiteName = test_id.split('.')[-3]

                bCreateNewRun = False
                if suiteName != self.suiteName:
                    bCreateNewRun = True
                    allTests = [t for c in TestLoader().loadTestsFromDir(os.path.dirname(test.context.__file__)) for t in c._tests]
                    allTestNames = [caseNameTestrailFormat(t.id().split('.')[-1]) for t in allTests]
                    os.write(1, str(allTestNames) + "\n")

                self.suiteName = suiteName

                allSuites = self.testrailApi.getSuites(self.projectID)

                suiteNameTestrail = self.projectIni.get(self.projectName, suiteName)
                suiteID = [s for s in allSuites if str(s['name']) == suiteNameTestrail]
                if not suiteID:
                    if bCreateNewRun:
                        suiteID = self.testrailApi.addSuite(self.projectID, suiteNameTestrail)
                        sectionID = self.testrailApi.addSection(self.projectID, suiteID['id'], Q_AUTOMATED)
                        for testNameToAdd in allTestNames:
                            self.testrailApi.addCase(sectionId=sectionID['id'], title=testNameToAdd)
                    else:
                        raise Exception("Suite %s not found on testrail" % suiteNameTestrail)
                else:
                    suiteID = suiteID[0]

                sectionName = Q_AUTOMATED
                allSections = self.testrailApi.getSections(self.projectID, suiteID['id'])
                sectionID = [sect for sect in allSections if sect['name'] == sectionName]
                if not sectionID:
                    raise Exception("Section %s not found on testrail" % sectionName)

                sectionID = sectionID[0]

                allCases = self.testrailApi.getCases(self.projectID, suiteID['id'])
                if bCreateNewRun:
                    for testNameToAdd in allTestNames:
                        if not [caseObj for caseObj in allCases if
                                caseObj['section_id'] == sectionID['id'] and caseObj['title'] == testNameToAdd]:
                            self.testrailApi.addCase(sectionId=sectionID['id'], title=testNameToAdd)
                    allCases = self.testrailApi.getCases(self.projectID, suiteID['id'])
                caseName = caseNameTestrailFormat(testName)

                caseItem = [caseObj for caseObj in allCases if
                            caseObj['section_id'] == sectionID['id'] and caseObj['title'] == caseName]
                if not caseItem:
                    raise Exception("Could not find case name %s on testrail" % caseName)
                self.caseItem = caseItem[0]

                if bCreateNewRun:
                    runID = None
                    if self.existingPlan:
                        run = [r for e in self.plan['entries'] for r in e['runs'] if r['suite_id'] == suiteID['id']]
                        if run:
                            runID = run[0]['id']
                    if runID is None:
                        self.testsCaseIdsToSelect = [c['id'] for c in allCases if c['title'] in allTestNames]
                        entry = self.testrailApi.addPlanEntry(self.plan['id'],
                                                              suiteID['id'],
                                                              suiteNameTestrail,
                                                              includeAll=False,
                                                              caseIds=self.testsCaseIdsToSelect)
                        runID = entry['runs'][0]['id']
                    self.runID = runID

                allTestsForRun = self.testrailApi.getTests(self.runID)

                test = [t for t in allTestsForRun if t['case_id'] == self.caseItem['id']][0]
                self.testId = test['id']

                self.durations = self.caseItem.get("custom_at_avg_duration", "")

                testStatus = self.ongoingStatus['id']
                self.testrailApi.addResult(testId=self.testId,
                                           statusId=testStatus,
                                           comment='',
                                           version=self.version,
                                           customFields={'custom_hypervisor': self.hypervisor})

                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                os.write(1, now + "|" + formatDurations(self.durations) + "-->")

            except:
                etype, value, tb = sys.exc_info()
                excStr = str(traceback.format_exception(etype, value, tb))
                with open(CRASH_FILE_LOG, "a") as f:
                    f.write(excStr + "\n\n")

    def addError(self, test, err, capt=None):
        """
        Add error output to Xunit report.
        """
        taken = self._timeTaken()

        if issubclass(err[0], SkipTest):
            result_type = 'skipped'
            self.stats['skipped'] += 1
        else:
            result_type = 'error'
            self.stats['errors'] += 1
        tb = ''.join(traceback.format_exception(*err))
        test_id = test.id()
        self.errorlist.append(
            '<testcase classname=%(cls)s name=%(name)s time="%(taken)d">'
            '<%(type)s type=%(errtype)s message=%(message)s><![CDATA[%(tb)s]]>'
            '</%(type)s></testcase>' %
            {'cls': self._quoteattr('.'.join(test_id.split('.')[:-1])),
             'name': self._quoteattr(test_id.split('.')[-1]),
             'taken': taken,
             'type': result_type,
             'errtype': self._quoteattr(nice_classname(err[0])),
             'message': self._quoteattr(exc_message(err)),
             'tb': escape_cdata(tb),
            })

        if self.testrailIp:
            elapsed = '%ss' % (int(taken) or 1)

            try:
                if str(result_type) == 'skipped':
                    if "BLOCKED" in str(err):
                        testStatus = self.blockedStatus['id']
                    else:
                        testStatus = self.skippedStatus['id']
                else:
                    testStatus = self.failedStatus['id']

                self.testrailApi.addResult(testId=self.testId,
                                           statusId=testStatus,
                                           comment=exc_message(err),
                                           version=self.version,
                                           elapsed=elapsed,
                                           customFields={'custom_hypervisor': self.hypervisor})
            except:
                etype, value, tb = sys.exc_info()
                excStr = str(traceback.format_exception(etype, value, tb))
                with open(CRASH_FILE_LOG, "a") as f:
                    f.write(excStr + "\n\n")

    def addFailure(self, test, err, capt=None, tb_info=None):
        """Add failure output to Xunit report.
        """
        taken = self._timeTaken()
        tb = ''.join(traceback.format_exception(*err))
        self.stats['failures'] += 1
        test_id = test.id()
        self.errorlist.append(
            '<testcase classname=%(cls)s name=%(name)s time="%(taken)d">'
            '<failure type=%(errtype)s message=%(message)s><![CDATA[%(tb)s]]>'
            '</failure></testcase>' %
            {'cls': self._quoteattr('.'.join(test_id.split('.')[:-1])),
             'name': self._quoteattr(test_id.split('.')[-1]),
             'taken': taken,
             'errtype': self._quoteattr(nice_classname(err[0])),
             'message': self._quoteattr(exc_message(err)),
             'tb': escape_cdata(tb),
            })

        if self.testrailIp:
            elapsed = (int(taken) or 1)

            try:
                if type == 'skipped':
                    testStatus = self.skippedStatus['id']
                else:
                    testStatus = self.failedStatus['id']

                self.testrailApi.addResult(testId=self.testId,
                                           statusId=testStatus,
                                           comment=exc_message(err),
                                           version=self.version,
                                           elapsed='%ss' % elapsed,
                                           customFields={'custom_hypervisor': self.hypervisor})
            except:
                etype, value, tb = sys.exc_info()
                excStr = str(traceback.format_exception(etype, value, tb))
                with open(CRASH_FILE_LOG, "a") as f:
                    f.write(excStr + "\n\n")

    def addSuccess(self, test, capt=None):
        """Add success output to Xunit report.
        """
        taken = self._timeTaken()
        self.stats['passes'] += 1
        test_id = test.id()
        self.errorlist.append(
            '<testcase classname=%(cls)s name=%(name)s '
            'time="%(taken)d" />' %
            {'cls': self._quoteattr('.'.join(test_id.split('.')[:-1])),
             'name': self._quoteattr(test_id.split('.')[-1]),
             'taken': taken,
             'systemout': self._getCapturedStdout(),
             'systemerr': self._getCapturedStderr(),
             })
        if self.testrailIp:
            elapsed = (int(taken) or 1)

            try:
                results = self.testrailApi.getResults(self.testId)
                if any([r['status_id'] == self.failedStatus['id'] for r in results]):
                    return

                self.testrailApi.addResult(testId=self.testId,
                                           statusId=self.passedStatus['id'],
                                           comment="",
                                           version=self.version,
                                           elapsed='%ss' % elapsed,
                                           customFields={'custom_hypervisor': self.hypervisor})
                if self.durations:
                    timeStats = self.caseItem['custom_at_avg_duration']
                    timeStats = map(int, timeStats.split("|"))

                    timeStats[2] = (timeStats[2] + elapsed) / 2
                    if elapsed < timeStats[0]:
                        timeStats[0] = elapsed
                    if elapsed > timeStats[1]:
                        timeStats[1] = elapsed
                else:
                    timeStats = [elapsed, elapsed, elapsed]

                self.testrailApi.updateCase(caseId=self.caseItem['id'],
                                            customFields={'custom_at_avg_duration': "|".join(map(str, timeStats))})
            except:
                etype, value, tb = sys.exc_info()
                excStr = str(traceback.format_exception(etype, value, tb))
                with open(CRASH_FILE_LOG, "a") as f:
                    f.write(excStr + "\n\n")
