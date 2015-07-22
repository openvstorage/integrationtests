"""
Autotests lib
"""

import os
import re
import sys
import time
import datetime
import StringIO
import subprocess
import ConfigParser
from xml.dom import minidom

import nose

from ci.scripts import testrailapi, testEnum
from ci.scripts import xunit_testrail


AUTOTEST_DIR = os.path.join(os.sep, "opt", "OpenvStorage", "ci")
CONFIG_DIR = os.path.join(AUTOTEST_DIR, "config")
SCRIPTS_DIR = os.path.join(AUTOTEST_DIR, "scripts")
TESTS_DIR = os.path.join(AUTOTEST_DIR, "tests")

AUTOTEST_CFG_FILE = os.path.join(CONFIG_DIR, "autotest.cfg")
OS_MAPPING_CFG_FILE = os.path.join(CONFIG_DIR, "os_mapping.cfg")

TESTRAIL_KEY = "cWFAY2xvdWRmb3VuZGVycy5jb206UjAwdDNy"


class TestRunnerOutputFormat(object):
    CONSOLE = 'CONSOLE'
    LOGGER = 'LOGGER'
    XML = 'XML'
    TESTRAIL = 'TESTRAIL'



TESTRAIL_STATUS_ID_PASSED = '1'
TESTRAIL_STATUS_ID_BLOCKED = '2'
TESTRAIL_STATUS_ID_FAILED = '5'

BLOCKED_MESSAGE = "BLOCKED"
Q_AUTOMATED = "qAutomated"

sys.path.append(SCRIPTS_DIR)


def run(test_spec=None,
        output_format=TestRunnerOutputFormat.CONSOLE,
        output_folder=None,
        always_die=False,
        testrail_url="testrail.openvstorage.com",
        project_name=None,
        quality_level=None,
        version=None,
        existing_plan_id=""):
    """
    Run only one test suite
    """
    if type(always_die) != bool:
        always_die = eval(check_input(predicate=lambda x: type(eval(x)) == bool,
                                      msg="Only boolean values allowed for always_die param\nDo you want the tests to stop after error/failure?[True/False]"))

    if not output_format:
        output_format = check_input(predicate=lambda x: getattr(TestRunnerOutputFormat, x, False),
                                    msg='Enter output format - [CONSOLE / XML / TESTRAIL]')
        output_format = getattr(TestRunnerOutputFormat, output_format)
    else:
        output_format = getattr(TestRunnerOutputFormat, str(output_format))
    if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL) and output_folder == None:
        output_folder = check_input(predicate=lambda x: os.path.exists(x) and os.path.isdir(x),
                                    msg='Incorrect parameter output_folder: %s is not a directory or does not exist: ' % output_folder)

    if output_format == TestRunnerOutputFormat.TESTRAIL:
        if not quality_level:
            quality_level = _getQualityLevel()

        if not project_name:
            project_name = _getProject()

        if not version:
            version = _getOvsVersion()

    if not test_spec:
        test_spec = check_input(predicate=lambda x: x,
                                msg='Enter test suite: ')

    arguments = _parseArgs(suite_name='test_results',
                           output_format=output_format,
                           output_folder=output_folder,
                           always_die=always_die,
                           testrail_url=testrail_url,
                           project_name=project_name,
                           quality_level=quality_level,
                           version=version,
                           existing_plan_id=existing_plan_id)

    tests = _convertTestSpec(test_spec)
    arguments.append(tests)

    _runTests(arguments)


def runMultiple(list_of_tests,
                output_format=TestRunnerOutputFormat.CONSOLE,
                output_folder=None,
                always_die=False,
                testrail_url="testrail.openvstorage.com",
                project_name=None,
                quality_level=None,
                version=None):
    """
    Run a selection of multiple test suites
    """
    if type(always_die) != bool:
        always_die = eval(check_input(predicate=lambda x: type(eval(x)) == bool,
                                      msg="Only boolean values allowed for always_die param\nDo you want the tests to stop after error/failure?[True/False]"))

    if not output_format:
        output_format = check_input(predicate=lambda x: getattr(TestRunnerOutputFormat, x, False),
                                    msg='Enter output format - [CONSOLE / XML / TESTRAIL]')
        output_format = getattr(TestRunnerOutputFormat, output_format)
    else:
        output_format = getattr(TestRunnerOutputFormat, str(output_format))

    if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL) and output_folder == None:
        output_folder = check_input(predicate=lambda x: os.path.exists(x) and os.path.isdir(x),
                                    msg='Incorrect parameter output_folder: %s is not a directory or does not exist: ' % output_folder)

    if output_format == TestRunnerOutputFormat.TESTRAIL:
        if not quality_level:
            quality_level = _getQualityLevel()

        if not project_name:
            project_name = _getProject()

        if not version:
            version = _getOvsVersion()

    arguments = _parseArgs(suite_name='test_results',
                           output_format=output_format,
                           output_folder=output_folder,
                           always_die=always_die,
                           testrail_url=testrail_url,
                           project_name=project_name,
                           quality_level=quality_level,
                           version=version,
                           list_of_tests=list_of_tests)
    _runTests(arguments)


def runAll(output_format=TestRunnerOutputFormat.CONSOLE,
           output_folder=None,
           always_die=False,
           specialSuitesToRun=None,
           randomize=False,
           testrail_url="testrail.openvstorage.com",
           project_name=None,
           quality_level=None,
           version=None,
           existing_plan_id=""):
    """
    Run all test suites
    """
    _ = specialSuitesToRun
    _ = randomize

    if type(always_die) != bool:
        always_die = eval(check_input(predicate=lambda x: type(eval(x)) == bool,
                                      msg="Only boolean values allowed for always_die param\nDo you want the tests to stop after error/failure?[True/False]"))

    if not output_format:
        output_format = check_input(predicate=lambda x: getattr(TestRunnerOutputFormat, x, False),
                                    msg='Enter output format - [CONSOLE / XML / TESTRAIL]')
        output_format = getattr(TestRunnerOutputFormat, output_format)
    else:
        output_format = getattr(TestRunnerOutputFormat, str(output_format))

    if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL) and output_folder == None:
        output_folder = check_input(predicate=lambda x: os.path.exists(x) and os.path.isdir(x),
                                    msg='Incorrect parameter output_folder: %s is not a directory or does not exist: ' % output_folder)

    if output_format == TestRunnerOutputFormat.TESTRAIL:
        if not quality_level:
            quality_level = _getQualityLevel()

        if not project_name:
            project_name = _getProject()

        if not version:
            version = _getOvsVersion()

    toRun = None
    arguments = _parseArgs(suite_name='test_results',
                           output_format=output_format,
                           output_folder=output_folder,
                           always_die=always_die,
                           testrail_url=testrail_url,
                           project_name=project_name,
                           quality_level=quality_level,
                           version=version,
                           list_of_tests=toRun,
                           existing_plan_id=existing_plan_id)

    _runTests(arguments)


def pushToTestrail(project=None,
                   qualityLevel=None,
                   version=None,
                   testrailIP="testrail.openvstorage.com",
                   folder="/var/tmp",
                   fileName="",
                   milestone="",
                   comment="",
                   quality_level=None,
                   createInexistentSuites=None,
                   createInexistentCases=None):
    """
    Push xml file with test results to Testrail
    """
    _ = qualityLevel

    if not fileName:
        folderPred = lambda x: os.path.exists(x) and os.path.isdir(x)
        if not folderPred(folder):
            folder = check_input(predicate=folderPred,
                                 msg='Incorrect parameter output_folder: %s is not a directory or does not exist' % folder)

        resultFiles = _getResultFiles(folder)
        if not resultFiles:
            print "\nWARNING: No test_results.xml files were found in '%s'. Please verify if the 'folder' parameter has been set correctly" % folder
            return

        else:
            filesToAskRange = list(range(len(resultFiles)))
            filesToAsk = zip(filesToAskRange, resultFiles)
            fileNameIdx = eval(check_input(predicate=lambda x: eval(x) in filesToAskRange,
                                           msg="Please chose results file \n" + "\n".join(
                                               map(lambda x: str(x[0]) + "->" + str(x[1]), filesToAsk)) + ":\n"))
        fileName = os.path.join(folder, resultFiles[fileNameIdx])

    print fileName

    if not quality_level:
        quality_level = _getQualityLevel()

    if not project:
        project = _getProject()

    if not version:
        version = _getOvsVersion()

    url = _pushToTestrail(IP=testrailIP,
                          fileName=fileName,
                          milestone=milestone,
                          project=project,
                          version=version,
                          qlevel=quality_level,
                          planComment=comment,
                          createInexistentSuites=createInexistentSuites,
                          createInexistentCases=createInexistentCases)
    if url:
        print "\n" + url

    return url


def _parseArgs(suite_name,
               output_format,
               output_folder,
               always_die,
               list_of_tests=None,
               testrail_url=None,
               project_name=None,
               quality_level=None,
               version=None,
               existing_plan_id=""):
    """
    Parse arguments in the format expected by nose
    """
    # Default arguments. First argument is a dummy as it is stripped within nose.
    arguments = ['', '--where', TESTS_DIR]
    if always_die:
        arguments.append('-x')
    if output_format == TestRunnerOutputFormat.CONSOLE:
        arguments.append('--verbosity')
        arguments.append('3')
    elif output_format == TestRunnerOutputFormat.XML:
        if not output_folder:
            raise AttributeError("No output folder for the XML result files specified")
        if not os.path.exists(output_folder):
            raise AttributeError("Given output folder doesn't exist. Please create it first!")
        arguments.append('--verbosity')
        arguments.append('3')
        arguments.append('--with-xunit_testrail')
        arguments.append('--xunit_file2')
        arguments.append(os.path.join(output_folder, '%s.xml' % (suite_name + str(time.time()))))
        arguments.append('--testrail-ip')
        arguments.append("")
        arguments.append('--project-name')
        arguments.append("")
        arguments.append('--push-name')
        arguments.append("")
        arguments.append('--description')
        arguments.append("")
    elif output_format == TestRunnerOutputFormat.TESTRAIL:
        if not output_folder:
            raise AttributeError("No output folder for the XML result files specified")
        if not os.path.exists(output_folder):
            raise AttributeError("Given output folder doesn't exist. Please create it first!")
        if not testrail_url:
            raise AttributeError("No testrail ip specified")
        if not project_name:
            raise AttributeError("No testrail project name specified")
        if not quality_level:
            raise AttributeError("No quality_level specified")
        if not version:
            raise AttributeError("No version specified")

        arguments.append('--verbosity')
        arguments.append('3')
        arguments.append('--with-xunit_testrail')
        arguments.append('--xunit_file2')
        arguments.append(os.path.join(output_folder, '%s.xml' % (suite_name + str(time.time()))))
        arguments.append('--testrail-ip')
        arguments.append(testrail_url)
        arguments.append('--project-name')
        arguments.append(project_name)
        arguments.append('--push-name')
        arguments.append(version + "__" + quality_level + "__" + _getHypervisor())
        arguments.append('--description')
        arguments.append(_getDescription())
        arguments.append('--plan-id')
        arguments.append(existing_plan_id)
    else:
        raise AttributeError("Invalid output format! Specify one of ")

    if list_of_tests:
        tests = ','.join(map(_convertTestSpec, list_of_tests))
        arguments.append('--tests')
        arguments.append(tests)

    return arguments


def _convertTestSpec(test_spec):
    """
    When the test_spec is of the format toplevel_package.sub_package, then the test_spec needs to
    be converted to toplevel_package/sub_package or no tests are picked up.
    """
    test_spec_parts = test_spec.split('.')
    test_spec_path = os.path.join(TESTS_DIR, *test_spec_parts)
    if os.path.isdir(test_spec_path):
        return test_spec.replace('.', '/')
    else:
        return test_spec


def _runTests(arguments):
    """
    Run the tests
    """
    nose.run(argv=arguments, addplugins=[xunit_testrail.xunit_testrail()])


def listTests(args=None):
    '''
    Lists all the tests that nose detects under TESTS_DIR
    '''
    if not args:
        arguments = ['--where', TESTS_DIR, '--verbosity', '3', '--collect-only', '--with-testEnum']
    else:
        arguments = args + ['--collect-only', '--with-testEnum']

    fakeStdout = StringIO.StringIO()
    oldStdout = sys.stdout
    sys.stdout = fakeStdout

    try:
        nose.run(argv=arguments, addplugins=[testEnum.TestEnum()])
    except Exception:
        raise
    finally:
        sys.stdout = oldStdout

    allCases = fakeStdout.getvalue().split()
    return allCases


def _getHypervisor():
    """
    Get hypervisor
    """
    from ovs.dal.lists.pmachinelist import PMachineList
    return list(PMachineList.get_pmachines())[0].hvtype


def _getDescription(planComment="", durations=""):
    """
    Generate description for pushing to Testrail
    """
    description = ""
    mgmtNodeIP = _get_ip("pubbr")
    for item, value in (("ip", "* %s" % mgmtNodeIP),
                        ("testsuite", durations),
                        ("Hypervisor", _getHypervisor()),
                        ("hardware", _getHardwareInfo()),
                        ("package", _getPackageInfo()),
                        ("Comment ", ('*' * 40 + "\n" + planComment) if planComment else '')):
        description += "# %s INFO \n%s\n" % (item.upper(), value)

    return description


def check_input(predicate, msg):
    while True:
        try:
            result = raw_input(msg)
            if predicate(result):
                return result
        except Exception:
            continue


def _getQualityLevel():
    """
    Retrieve quality level of installation
    """
    cmd = "awk '/deb/ {print $3;}' /etc/apt/sources.list.d/ovsaptrepo.list"
    childProc = subprocess.Popen(cmd,
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

    return childProc.communicate()[0].replace("/", "").strip()


def _getProject():
    """
    Retrieve project name for pushing
    """
    return "Open vStorage Engineering"


def _getOvsVersion():
    """
    Retrieve version of ovs installation
    """
    packages = _getPackageInfo()
    mainP = [pck for pck in packages.splitlines() if "openvstorage " in pck]
    if not mainP:
        return ""

    return re.split("\s*", mainP[0])[2]

def _getResultFiles(folder):
    """
    List all xml results files in folder
    """
    xmlFiles = [f for f in os.listdir(folder) if ".xml" in f]

    xmlFiles.sort(reverse=True)
    return xmlFiles


def _getHardwareInfo():
    """
    Get hardware info for env
    """
    childProc = subprocess.Popen("dmidecode | grep -A 12 'Base Board Information'",
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

    (sysinfo, _error) = childProc.communicate()

    exitcode = childProc.returncode
    if exitcode != 0:
        sysinfo = "NO MOTHERBOARD INFORMATION FOUND"

    childProc = subprocess.Popen("lshw -short",
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

    (lshwinfo, _error) = childProc.communicate()
    exitcode = childProc.returncode

    if exitcode != 0:
        lshwinfo = "NO HARDWARE INFORMATION FOUND"
    else:
        lshwinfo = lshwinfo.split('\n')

    diskinfo = ''
    meminfo = []
    cpuinfo = []
    for line in lshwinfo:
        if line.find("disk") >= 0:
            if line.find('DVD-ROM') >= 0 or line.find('CD-ROM') >= 0:
                continue
            l = line.split()
            l.pop(2)
            l.pop(0)
            for part in l:
                diskinfo += '%13s' % part
            diskinfo += '\n'
        elif line.find('System Memory') >= 0 or line.find("System memory") >= 0:
            l = line.split()
            index = l.index('memory') + 1
            for item in l[index:]:
                meminfo.append(item)
        elif line.find('processor') >= 0 and line.find('CPU [empty]') == -1:
            l = line.split()
            index = l.index('processor') + 1
            cinfo = " ".join(l[index:])
            cpuinfo.append(cinfo)
    return "### " + sysinfo + '\n### Disk Information\n' + diskinfo + '\n### Processor Information\n' + '* ' + '\n* '.join(
        cpuinfo) + '\n### Memory Information\n' + '* ' + ' '.join(meminfo)


def _getPackageInfo():
    """
    Retrieve package information for installation
    """
    command = "dpkg -l \*openvstorage\* | grep openvstorage"

    childProc = subprocess.Popen(command,
                                 shell=True,
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)

    (output, _error) = childProc.communicate()
    output = re.sub("     ", " ", re.sub("     ", " ", output))
    return output


def _getDurations(xmlfile):
    """
    Extract test durations from xml file
    """

    def parseToReadableForm(durations):
        def getTextualValues(seconds):
            if not seconds:
                return "%2i %5s, %2i %7s, %2i %7s\n" % (0, 'hours', 0, 'minutes', 0, 'seconds')
            hours = seconds / 60 / 60
            rest = seconds % (60 * 60)
            minutes = rest / 60
            rest = rest % 60
            hoursText = 'hour' if hours == 1 else 'hours'
            minutesText = 'minute' if minutes == 1 else 'minutes'
            secondsText = 'second' if rest == 1 else 'seconds'
            return "%2i %5s, %2i %7s, %2i %7s\n" % (hours, hoursText, minutes, minutesText, rest, secondsText)

        dur = ''
        for key in sorted(durations.keys()):
            dur += "%30s: " % key + getTextualValues(durations[key])

        dur += '\n%30s: ' % 'Total Duration' + getTextualValues(sum(durations.values()))
        return dur

    durations = {}
    for child in xmlfile.childNodes:
        suite = child.getAttribute('classname').split('.')[-2]
        if suite == '<nose':
            continue

        if suite not in durations:
            durations[suite] = 0
        durations[suite] += int(child.getAttribute('time'))
    return parseToReadableForm(durations)


def _getCases(xmlfile, testrailApi, projectIni, projectName, projectID, createInexistentSuites, createInexistentCases):
    """
    Retrieve test cases from xml file
    """
    allCases = {}
    ranCases = {}
    suiteName = ''
    sectionName = ''
    suiteNameToId = {}
    sectionNameToId = {}

    allSections = {}
    allSuites = testrailApi.getSuites(projectID)

    for child in xmlfile.childNodes:
        classname = child.getAttribute('classname')
        if classname.startswith(('<nose', 'nose', '&lt;nose')):
            continue

        suite = classname.split('.')[-2]

        if child.childNodes and \
                        child.childNodes[0].getAttribute('type') == 'nose.plugins.skip.SkipTest' and \
                        child.childNodes[0].getAttribute('message') != BLOCKED_MESSAGE:
            continue
        case = child.getAttribute('name')
        match = re.search("c\d+_(.+)", case)
        case = match.groups()[0] if match else case

        prevSuiteName = suiteName
        if not projectIni.has_section(projectName):
            print 'Project "%s" not found in project_testsuite_mapping.cfg' % projectName
            sys.exit(1)
        if not projectIni.has_option(projectName, suite):
            print 'Suite "%s" not found in project_testsuite_mapping.cfg' % suite
            sys.exit(1)
        suiteName = projectIni.get(projectName, suite)
        if suiteName != prevSuiteName:
            suiteID = [s for s in allSuites if s['name'] == suiteName]

            if not suiteID:
                if not createInexistentSuites:
                    print "Suite %s not found on testrail, manually create it or set createInexistentSuites param to True" % suiteName
                    sys.exit(1)
                else:
                    newSuite = testrailApi.addSuite(projectID, suiteName)
                    allSuites.append(newSuite)
                    suiteID = newSuite['id']
            else:
                suiteID = suiteID[0]['id']
            suiteNameToId[suiteName] = suiteID
            allCases[suiteName] = testrailApi.getCases(projectID, suiteID)
        else:
            if not suiteID:
                print "Suite %s not found on testrail, manually create it or set createInexistentSuites param to True" % suiteName
                sys.exit(1)

        sectionName = determineSectionName(suite, case)
        if suiteID not in allSections:
            allSections[suiteID] = testrailApi.getSections(projectID, suiteID)
        sectionID = [sect for sect in allSections[suiteID] if sect['name'] == sectionName]
        if not sectionID:
            if createInexistentCases:
                newSection = testrailApi.addSection(projectID, suiteID, sectionName)
                allSections[suiteID].append(newSection)
                sectionID = newSection['id']
                sectionNameToId[suiteID] = {sectionName: sectionID}
            else:
                print "Section %s under suiteId %s not found on testrail, manually create it or set createInexistentSuites param to True" % (
                    sectionName, suiteID)
                sys.exit(1)
        else:
            sectionID = sectionID[0]['id']

        if suiteID in sectionNameToId:
            sectionNameToId[suiteID][sectionName] = sectionID
        else:
            sectionNameToId[suiteID] = {sectionName: sectionID}
        caseID = [caseObj for caseObj in allCases[suiteName] if
                  caseObj['section_id'] == sectionID and caseObj['title'] == case]
        if createInexistentCases:
            if not caseID:
                newCase = testrailApi.addCase(sectionID, case)
                caseID = newCase['id']
                allCases[suiteName].append(newCase)

        ranCases[suiteName] = ranCases[suiteName].add(case) or ranCases[suiteName] if ranCases.get(suiteName) else set(
            [case])

    return allCases, ranCases, suiteNameToId, sectionNameToId


def determineSectionName(suite, caseName):
    """
    Determine section name for suite
    """
    _ = suite
    _ = caseName
    return Q_AUTOMATED


def _pushToTestrail(IP, fileName, milestone, project, version, qlevel, planComment, createInexistentSuites, createInexistentCases):
    """
    Push xml file to Testrail
    """
    testResultFile = fileName
    if not os.path.exists(testResultFile):
        raise Exception("Testresultfile '%s' was not found on system" % testResultFile)
    if not os.path.isfile(testResultFile):
        raise Exception("Invalid file given")

    testrailApi = testrailapi.TestrailApi(IP, key=TESTRAIL_KEY)

    allProjects = testrailApi.getProjects()
    projectID = [p for p in allProjects if p['name'] == project]
    if not projectID:
        raise Exception("No project found on %s with name '%s'" % (IP, project))
    projectID = projectID[0]['id']

    milestonesForProject = testrailApi.getMilestones(projectID)

    milestoneID = None
    if milestone:
        milestoneID = [m for m in milestonesForProject if m['name'] == milestone]
        if not milestoneID:
            dueDate = datetime.datetime.now() + datetime.timedelta(hours=24)
            dueDate = time.mktime(dueDate.timetuple())
            milestoneID = testrailApi.addMilestone(projectID, milestone, dueOn=int(dueDate))

            milestoneID = milestoneID['id']
        else:
            milestoneID = milestoneID[0]['id']

    today = datetime.datetime.today()
    date = today.strftime('%a %b %d %H:%M:%S')
    name = '%s.%s__%s' % (version, qlevel, date)

    projectMapping = os.path.join(CONFIG_DIR, "project_testsuite_mapping.cfg")
    projectIni = ConfigParser.ConfigParser()
    projectIni.read(projectMapping)

    if not projectIni.has_section(project):
        raise Exception(
            "Config file '%s' does not contain section for specified project '%s'" % (projectMapping, project))

    errorMessages = []

    xmlfile = minidom.parse(testResultFile).childNodes[0]
    durations = _getDurations(xmlfile)
    addedSuites = []
    planID = None
    suiteToRunDict = {}
    caseNameToTestId = {}

    # additionalResultsFile = getAdditionalResultsFile(testResultFile)

    allCases, ranCases, suiteNameToId, sectionNameToId = _getCases(xmlfile=xmlfile,
                                                                   testrailApi=testrailApi,
                                                                   projectIni=projectIni,
                                                                   projectName=project,
                                                                   projectID=projectID,
                                                                   createInexistentSuites=createInexistentSuites,
                                                                   createInexistentCases=createInexistentCases)
    testsCaseIdsToSelect = []

    def addPlan():
        description = _getDescription(planComment=planComment, durations=durations)
        planID = testrailApi.addPlan(projectID, name, description, milestoneID or None)['id']
        print planID
        return planID

    for child in xmlfile.childNodes:
        classname = child.getAttribute('classname')

        if classname.startswith(('<nose', 'nose')):
            if child.childNodes[0].childNodes and \
                    child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                errorMessages.append(child.childNodes[0].childNodes[0].data)
            else:
                errorMessages.append(child.childNodes[0].getAttribute('message'))
            continue

        suite = classname.split('.')[-2]

        isBlocked = False

        if child.childNodes and "SkipTest" in child.childNodes[0].getAttribute('type'):
            if child.childNodes[0].getAttribute('message') == BLOCKED_MESSAGE:
                isBlocked = True
            else:
                continue

        if not projectIni.has_option(project, suite):
            raise Exception(
                "Testsuite '%s' is not configured for project '%s' in '%s'" % (suite, project, projectMapping))

        suiteName = projectIni.get(project, suite)

        if suiteName not in addedSuites:
            createRun = True
            if not suiteName in suiteNameToId:
                continue
            addedSuites.append(suiteName)
            testsCaseIdsToSelect = [c['id'] for c in allCases[suiteName] if c['title'] in ranCases[suiteName]]

        caseName = child.getAttribute('name')

        sectionName = determineSectionName(suite, caseName)
        sectionID = sectionNameToId[suiteNameToId[suiteName]][sectionName]
        # print "%-20s %-50s %-50s" % (suite, caseName, sectionName)
        caseID = [case for case in allCases[suiteName] if case['title'] == caseName and case['section_id'] == sectionID]
        if not caseID:
            print "Case %s from suite %s section %s not found. Could be that CREATE_INEXISTENT_TESTSUITE is not set to True" % (
                caseName, suiteName, sectionID)
            print  [(c['title'], c['section_id']) for c in allCases[suiteName]]
            continue
        caseID = caseID[0]['id']

        if planID == None:
            createRun = False
            planID = addPlan()

            entry = testrailApi.addPlanEntry(planID, suiteNameToId[suiteName], suiteName, includeAll=False,
                                             caseIds=testsCaseIdsToSelect)
            runID = entry['runs'][0]['id']
            suiteToRunDict[suiteName] = runID

        if createRun:
            entry = testrailApi.addPlanEntry(planID, suiteNameToId[suiteName], suiteName, includeAll=False,
                                             caseIds=testsCaseIdsToSelect)
            runID = entry['runs'][0]['id']
            suiteToRunDict[suiteName] = runID
            createRun = False

        runID = suiteToRunDict[suiteName]
        if caseName not in caseNameToTestId:
            allTestsForRun = testrailApi.getTests(runId=runID)
            for t in allTestsForRun:
                caseNameToTestId[t['title'] + str(runID)] = t['id']

        testID = caseNameToTestId[caseName + str(runID)]

        comment = ''
        if not child.childNodes:
            status_id = TESTRAIL_STATUS_ID_PASSED
            # if additionalResultsFile and \
            #   additionalResultsFile.checkSection(sectionName = suite) and \
            #   additionalResultsFile.checkParam(sectionName = suite, paramName = caseName):
            #   comment = additionalResultsFile.getValue(sectionName = suite, paramName = caseName, raw = True).replace('||', '\n')
        elif child.childNodes[0].getAttribute('type') == 'nose.plugins.skip.SkipTest':
            if isBlocked:
                status_id = TESTRAIL_STATUS_ID_BLOCKED
                if child.childNodes[0].childNodes and child.childNodes[0].childNodes[
                    0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                    comment = child.childNodes[0].childNodes[0].data
            else:
                continue
        else:
            status_id = TESTRAIL_STATUS_ID_FAILED
            if child.childNodes[0].childNodes and child.childNodes[0].childNodes[
                0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                comment = child.childNodes[0].childNodes[0].data
            else:
                comment = child.childNodes[0].getAttribute('message')
        elapsed = int(child.getAttribute('time'))
        if elapsed == 0:
            elapsed = 1
        testrailApi.addResult(testId=testID,
                              statusId=status_id,
                              comment=comment,
                              version=version,
                              elapsed='%ss' % elapsed,
                              customFields={'custom_hypervisor': _getHypervisor()})

    xmlfile.unlink()
    del xmlfile

    if errorMessages:
        print "\nSome testsuites were not able to start because an error occured in their 'setup'"
        failedSetupSuiteName = 'FAILED_TEST_SETUP'

        suiteID = [s for s in testrailApi.getSuites(projectID) if s['name'] == failedSetupSuiteName]
        if not suiteID:
            suiteID = testrailApi.addSuite(projectID, failedSetupSuiteName)['id']
        else:
            suiteID = suiteID[0]['id']
        qAutoSectionName = "qAutomated"
        sectionID = [s for s in testrailApi.getSections(projectID, suiteID) if s['name'] == qAutoSectionName]
        if not sectionID:
            sectionID = testrailApi.addSection(projectID, suiteID, qAutoSectionName)['id']
        else:
            sectionID = sectionID[0]['id']
        caseName = "FailedSetup"
        caseID = [c for c in testrailApi.getCases(projectID, suiteID, sectionID) if c['title'] == caseName]
        if not caseID:
            caseID = testrailApi.addCase(sectionID, caseName)['id']
        else:
            caseID = caseID[0]['id']
        if not planID:
            planID = addPlan()
        runID = testrailApi.addPlanEntry(planID, suiteID, failedSetupSuiteName, includeAll=False, caseIds=[caseID])['runs'][0]['id']
        testrailApi.addResultForCase(runID, caseID, '5', ("\n" + "=" * 70 + "\n").join(errorMessages))

    if not planID:
        return False
    return "http://%s/index.php?/plans/view/%s" % (IP, planID)


def _get_ip(iface='eth0'):
    """
    Get ip of interface using SIOCGIFADDR ioctl
    """
    import socket, struct, fcntl

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sockfd = sock.fileno()
    SIOCGIFADDR = 0x8915

    # set ifreq.ifr_name, ifreq.ifr_addr.sa_family and pad with 0
    ifreq = struct.pack('16sH14s', iface, socket.AF_INET, '\x00' * 14)
    try:
        res = fcntl.ioctl(sockfd, SIOCGIFADDR, ifreq)
    except Exception:
        return None
    ip = struct.unpack('16sH2x4s8x', res)[2]
    # ip is packed in a in_addr c struct
    return socket.inet_ntoa(ip)


def getConfigIni():
    """
    Get autotest config
    """
    global autotestCfg
    autotestCfg = ConfigParser.ConfigParser()
    autotestCfg.read(AUTOTEST_CFG_FILE)

    return globals()['autotestCfg']


def _saveConfigIni(atCfg):
    """
    Save autotest config file
    """
    with open(AUTOTEST_CFG_FILE, "wb") as fCfg:
        atCfg.write(fCfg)
    globals()['autotestCfg'] = None
    getConfigIni()


def getTestLevel():
    """
    Read test level from config file
    """
    autotestCfgL = getConfigIni()

    return autotestCfgL.get(section="main", option="testlevel")


def setTestLevel(testLevel):
    """
    Set test level : 1,2,3,8-12,15
    """
    testLevelRegex = "^([0-9]|[1-9][0-9])([,-]([1-9]|[1-9][0-9])){0,}$"
    if not re.match(testLevelRegex, testLevel):
        print('Wrong testlevel specified\neg: 1,2,3,8-12,15')
        return False

    atCfg = getConfigIni()
    atCfg.set(section="main", option="testlevel", value=testLevel)
    _saveConfigIni(atCfg)

    return True


def getHypervisorInfo():
    """
    Retrieve info about hypervisor (ip, username, password)
    """
    autotestCfgL = getConfigIni()

    hi = autotestCfgL.get(section="main", option="hypervisorinfo")
    hiList = hi.split(",")
    if not len(hiList) == 3:
        print "No hypervisor info present in config"
        return
    return hiList


def setHypervisorInfo(ip, username, password):
    """
    Set info about hypervisor( ip, username and password )

    @param ip:         Ip address of hypervisor
    @type ip:          String

    @param username:   Username fort hypervisor
    @type username:    Srting

    @param pasword:    Password of hypervisor
    @type password:    String

    @return:           None
    """

    ipaddress_regex = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"

    if not re.match(ipaddress_regex, ip):
        print("Invalid ipaddress specified")
        return False

    if type(username) != str or type(password) != str:
        print("Username and password need to be str format")
        return False

    value = ','.join([ip, username, password])
    atCfg = getConfigIni()
    atCfg.set(section="main", option="hypervisorinfo", value=value)
    _saveConfigIni(atCfg)

    return True


def listOs():
    """
    List os' configured in os_mapping
    """

    osMappingCfg = ConfigParser.ConfigParser()
    osMappingCfg.read(OS_MAPPING_CFG_FILE)

    osNames = osMappingCfg.sections()

    return osNames


def getOsInfo(osName):
    """
    Get info about an os configured in os_mapping
    """
    osMappingCfg = ConfigParser.ConfigParser()
    osMappingCfg.read(OS_MAPPING_CFG_FILE)

    if not osMappingCfg.has_section(osName):
        print("No configuration found for os {0} in config".format(osName))
        return

    osInfo = dict(osMappingCfg.items(osName))

    return osInfo


def setOs(osName):
    """
    Set current os to be used by tests
    """
    osList = listOs()
    if not osName in osList:
        print("Invalid os specified, available options are {0}".format(str(osList)))
        return False

    atCfg = getConfigIni()
    atCfg.set(section="main", option="os", value=osName)
    _saveConfigIni(atCfg)

    return True


def getOs():
    """
    Retrieve current configured os for autotests
    """
    autotestCfgL = getConfigIni()

    osName = autotestCfgL.get(section="main", option="os")

    return osName


def setTemplateServer(templateServer):
    """
    Set current template server to be used by tests
    """

    atCfg = getConfigIni()
    atCfg.set(section="main", option="template_server", value=templateServer)
    _saveConfigIni(atCfg)

    return True


def getTemplateServer():
    """
    Retrieve current configured template server for autotests
    """
    autotestCfgL = getConfigIni()

    templateServer = autotestCfgL.get(section = "main", option = "template_server")

    return templateServer

def getUserName():
    """
    Get username to use in tests
    """
    autotestCfgL = getConfigIni()
    username = autotestCfgL.get(section = "main", option = "username")
    return username

def setUserName(username):
    """
    Set username to use in tests
    """
    atCfg = getConfigIni()
    atCfg.set(section = "main", option = "username", value = username)
    _saveConfigIni(atCfg)

    return True


def getPassword():
    """
    Get password to use in tests
    """
    autotestCfgL = getConfigIni()
    username = autotestCfgL.get(section = "main", option = "username")
    return username

def setPassword(password):
    """
    Set password to use in tests
    """
    atCfg = getConfigIni()
    atCfg.set(section = "main", option = "password", value = password)
    _saveConfigIni(atCfg)

    return True
