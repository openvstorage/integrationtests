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
OVS automatic test lib
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


class TestRunnerOutputFormat(object):
    CONSOLE = 'CONSOLE'
    LOGGER = 'LOGGER'
    XML = 'XML'
    TESTRAIL = 'TESTRAIL'


TESTRAIL_STATUS_ID_PASSED = '1'
TESTRAIL_STATUS_ID_BLOCKED = '2'
TESTRAIL_STATUS_ID_FAILED = '5'

BLOCKED_MESSAGE = "BLOCKED"

sys.path.append(SCRIPTS_DIR)


def get_config():
    """
    Get autotest config
    """
    global autotest_config
    autotest_config = ConfigParser.ConfigParser()
    autotest_config.read(AUTOTEST_CFG_FILE)

    return globals()['autotest_config']


def get_option(section, option):
    if get_config().has_option(section, option):
        return get_config().get(section, option)
    else:
        # @todo: add interactive part to ask for required parameters when run from cmd line
        return ""

TESTRAIL_FOLDER = get_config().get(section="main", option="output_folder")
TESTRAIL_KEY = get_config().get(section="testrail", option="key")
TESTRAIL_PROJECT = get_config().get(section="testrail", option="test_project")
TESTRAIL_QUALITYLEVEL = get_config().get(section="main", option="qualitylevel")
TESTRAIL_SERVER = get_config().get(section="testrail", option="server")


def _validate_run_parameters(tests=None, output_format=TestRunnerOutputFormat.CONSOLE, output_folder='/var/tmp',
                             project_name='', qualitylevel='', always_die=False, existing_plan_id=None,
                             interactive=False):

    if output_format not in ['CONSOLE', 'XML', 'TESTRAIL']:
        if interactive:
            output_format = check_input(predicate=lambda x: getattr(TestRunnerOutputFormat, x, False),
                                        msg='Enter output format - [CONSOLE / XML / TESTRAIL]')
        else:
            raise RuntimeError('output_format should be: CONSOLE | XML | TESTRAIL')
        output_format = getattr(TestRunnerOutputFormat, str(output_format))

    if type(always_die) != bool:
        if interactive:
            always_die = eval(check_input(predicate=lambda x: type(eval(x)) == bool,
                                          msg="Only boolean values allowed for always_die param\n" +
                                              "Do you want the tests to stop after error/failure?[True/False]"))
        else:
            raise RuntimeError('always_die parameter should be a boolean: True|False')

    if interactive:
        if not tests:
            tests = check_input(predicate=lambda x: x, msg='Enter test suite: ')

    if interactive:
        if output_format in (TestRunnerOutputFormat.XML, TestRunnerOutputFormat.TESTRAIL) and not output_folder:
            output_folder = check_input(predicate=lambda x: os.path.exists(x) and os.path.isdir(x),
                                        msg='Incorrect output_folder: {0}'.format(output_folder))
    elif not output_folder or not(os.path.exists(output_folder) and os.path.isdir(output_folder)):
        raise RuntimeError("Output folder incorrect: {0}".format(output_folder))

    version = _get_ovs_version()

    if output_format in TestRunnerOutputFormat.TESTRAIL:

        arguments = _parse_args(suite_name='test_results', output_format=output_format, output_folder=output_folder,
                                always_die=always_die, testrail_url=TESTRAIL_SERVER, testrail_key=TESTRAIL_KEY,
                                project_name=project_name, quality_level=qualitylevel, version=version,
                                existing_plan_id=existing_plan_id)
    else:
        arguments = _parse_args(suite_name='test_results', output_format=output_format, output_folder=output_folder,
                                always_die=always_die, project_name=project_name, quality_level=qualitylevel,
                                version=version, existing_plan_id=existing_plan_id)

    if tests:
        if type(tests) == list:
            tests_to_run = ','.join(map(_convert_test_spec, tests))
            arguments.append('--tests')
        else:
            tests_to_run = _convert_test_spec(tests)
        arguments.append(tests_to_run)

    print arguments
    return arguments


def run(tests='', output_format=TestRunnerOutputFormat.CONSOLE, output_folder='/var/tmp',
        project_name='Open vStorage Engineering', always_die=False, qualitylevel='', existing_plan_id="",
        interactive=True):

    """
    Run only one test suite
    """

    print "tests: {0}".format(tests)
    arguments = _validate_run_parameters(tests, output_format, output_folder, project_name, qualitylevel,
                                         always_die, existing_plan_id, interactive)

    _run_tests(arguments)


def pushToTestrail(project_name, _, output_folder, version=None, filename="", milestone="", comment=""):
    """
    Push xml file with test results to Testrail
    """

    if not filename:
        def is_folder(path):
            return os.path.exists(path) and os.path.isdir(path)

        if not is_folder(output_folder):
            output_folder = check_input(predicate=is_folder(output_folder),
                                        msg='Incorrect output_folder: {0}'.format(output_folder))

        result_files = _get_testresult_files(output_folder)
        if not result_files:
            print "\nNo test_results files were found in {0}".format(output_folder)
            return

        else:
            files_to_ask_range = list(range(len(result_files)))
            files_to_ask = zip(files_to_ask_range, result_files)
            filename_index = eval(check_input(predicate=lambda x: eval(x) in files_to_ask_range,
                                              msg="Please choose results file \n" + "\n".join(
                                                  map(lambda x: str(x[0]) + "->" + str(x[1]), files_to_ask)) + ":\n"))
        filename = os.path.join(output_folder, result_files[filename_index])

    if not version:
        version = _get_ovs_version()

    url = _push_to_testrail(filename=filename, milestone=milestone, project_name=project_name, version=version,
                            plan_comment=comment)
    if url:
        print "\n" + url

    return url


def _convert_test_spec(test_spec):
    """
    When the test_spec is of the format top level_package.sub_package, then the test_spec needs to
    be converted to top level_package/sub_package or no tests are picked up.
    """
    test_spec_parts = test_spec.split('.')
    print "test_spec_parts: {0}".format(test_spec_parts)
    test_spec_path = os.path.join(TESTS_DIR, *test_spec_parts)
    print "test_spec_path: {0}".format(test_spec_path)

    if os.path.isdir(test_spec_path):
        return test_spec.replace('.', '/')
    else:
        return test_spec


def _parse_args(suite_name, output_format, output_folder, always_die, testrail_url=None,
                testrail_key=None, project_name=None, quality_level=None, version=None, existing_plan_id=""):
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
        arguments.append('--testrail-key')
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
        if not testrail_key:
            raise AttributeError("No testrail key specified")
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
        arguments.append('--testrail-key')
        arguments.append(testrail_key)
        arguments.append('--project-name')
        arguments.append(project_name)
        arguments.append('--push-name')
        arguments.append(version + "__" + quality_level + "__" + _get_hypervisor())
        arguments.append('--description')
        arguments.append(_get_description())
        arguments.append('--plan-id')
        arguments.append(existing_plan_id)
    else:
        raise AttributeError("Invalid output format! Specify one of CONSOLE|XML|TESTRAIL ")

    return arguments


def _run_tests(arguments):
    """
    Run the tests
    """
    nose.run(argv=arguments, addplugins=[xunit_testrail.xunit_testrail()])


def list_tests(args=None):
    """
    Lists all the tests that nose detects under TESTS_DIR
    """
    if not args:
        arguments = ['--where', TESTS_DIR, '--verbosity', '3', '--collect-only', '--with-testEnum']
    else:
        arguments = args + ['--collect-only', '--with-testEnum']

    fake_stdout = StringIO.StringIO()
    old_stdout = sys.stdout
    sys.stdout = fake_stdout

    try:
        nose.run(argv=arguments, addplugins=[testEnum.TestEnum()])
    except Exception:
        raise
    finally:
        sys.stdout = old_stdout

    all_cases = fake_stdout.getvalue().split()
    return all_cases


def _get_hypervisor():
    """
    Get hypervisor
    """
    from ovs.dal.lists.pmachinelist import PMachineList
    return list(PMachineList.get_pmachines())[0].hvtype


def _get_description(plan_comment="", durations=""):
    """
    Generate description for pushing to Testrail
    """
    description = ""
    node_ips = ""
    for ip in _get_ips():
        node_ips += "* " + ip + "\n"
    for item, value in (("ip", "%s" % node_ips),
                        ("testsuite", durations),
                        ("Hypervisor", _get_hypervisor()),
                        ("hardware", _get_hardware_info()),
                        ("package", _get_package_info()),
                        ("Comment ", ('*' * 40 + "\n" + plan_comment) if plan_comment else '')):
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


def _get_ovs_version():
    """
    Retrieve version of ovs installation
    """
    packages = _get_package_info()
    main_pkg = [pck for pck in packages.splitlines() if "openvstorage " in pck]
    if not main_pkg:
        return ""

    return re.split("\s*", main_pkg[0])[1]


def _get_testresult_files(folder):
    """
    List all xml results files in folder
    """
    xml_files = [f for f in os.listdir(folder) if ".xml" in f]
    xml_files.sort(reverse=True)

    return xml_files


def _get_hardware_info():
    """
    Get hardware info for env
    """
    child_process = subprocess.Popen("dmidecode | grep -A 12 'Base Board Information'", shell=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    (sysinfo, _error) = child_process.communicate()

    exitcode = child_process.returncode
    if exitcode != 0:
        sysinfo = "NO MOTHERBOARD INFORMATION FOUND"

    child_process = subprocess.Popen("lshw -short", shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    (lshwinfo, _error) = child_process.communicate()
    exitcode = child_process.returncode

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
    return "### " + sysinfo + '\n### Disk Information\n' + diskinfo + '\n### Processor Information\n' +\
           '* ' + '\n* '.join(cpuinfo) + '\n### Memory Information\n' + '* ' + ' '.join(meminfo)


def _get_package_info():
    """
    Retrieve package information for installation
    """
    command = "dpkg-query -W -f='${binary:Package} ${Version}\t${Description}\n' | grep 'openvstorage'"

    child_process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)

    (output, _error) = child_process.communicate()
    return output


def _get_durations(xml_file):
    """
    Extract test durations from xml file
    """

    def parse_to_readable_form(test_durations):
        def get_textual_values(seconds):
            if not seconds:
                return "%2i %5s, %2i %7s, %2i %7s\n" % (0, 'hours', 0, 'minutes', 0, 'seconds')
            hours = seconds / 60 / 60
            rest = seconds % (60 * 60)
            minutes = rest / 60
            hours_text = 'hour' if hours == 1 else 'hours'
            minutes_text = 'minute' if minutes == 1 else 'minutes'
            seconds_text = 'second' if rest == 1 else 'seconds'
            return "%2i %5s, %2i %7s, %2i %7s\n" % (hours, hours_text, minutes, minutes_text, rest, seconds_text)

        dur = ''
        for key in sorted(test_durations.keys()):
            dur += "%30s: " % key + get_textual_values(test_durations[key])

        dur += '\n%30s: ' % 'Total Duration' + get_textual_values(sum(test_durations.values()))
        return dur

    durations = {}
    for child in xml_file.childNodes:
        suite = child.getAttribute('classname').split('.')[-2]
        if suite == '<nose':
            continue

        if suite not in durations:
            durations[suite] = 0
        durations[suite] += int(child.getAttribute('time'))
    return parse_to_readable_form(durations)


def _get_cases(xml_file, testrail_api, project_ini, project_name, project_id):
    """
    Retrieve test cases from xml file
    """
    all_cases = {}
    ran_cases = {}
    suite_name = ''
    suite_id = ''
    suite_name_to_id = {}
    section_name_to_id = {}

    all_sections = {}

    for child in xml_file.childNodes:
        classname = child.getAttribute('classname')
        if classname.startswith(('<nose', 'nose', '&lt;nose')):
            continue

        option = classname.split('.')[-2]

        if child.childNodes and child.childNodes[0].getAttribute('type') == 'nose.plugins.skip.SkipTest' and \
           child.childNodes[0].getAttribute('message') != BLOCKED_MESSAGE:
            continue
        case = child.getAttribute('name')
        match = re.search("c\d+_(.+)", case)
        case = match.groups()[0] if match else case

        previous_suite_name = suite_name
        suite_name = project_ini.get(project_name, option).split(';')[0]
        section_names = project_ini.get(project_name, option).split(';')[1].split(',')
        section_name = section_names[-1]

        if suite_name != previous_suite_name:
            suite = testrail_api.get_suite_by_name(suite_name)
            suite_id = suite['id']
            suite_name_to_id[suite_name] = suite_id
            all_cases[suite_name] = testrail_api.get_cases(project_id, suite['id'])

        section = testrail_api.get_section_by_name(section_name)

        if suite['id'] not in all_sections:
            all_sections[suite['id']] = testrail_api.get_sections(project_id, suite['id'])
        section_id = section['id']

        if suite_id in section_name_to_id:
            section_name_to_id[suite_id][section_name] = section_id
        else:
            section_name_to_id[suite_id] = {section_name: section_id}
        case_id = [caseObj for caseObj in all_cases[suite_name] if
                   caseObj['section_id'] == section_id and caseObj['title'] == case]
        if not case_id:
            new_case = testrail_api.add_case(section_id, case)
            all_cases[suite_name].append(new_case)

        ran_cases[suite_name] = ran_cases[suite_name].add(case) or \
            ran_cases[suite_name] if ran_cases.get(suite_name) else set([case])

    return all_cases, ran_cases, suite_name_to_id, section_name_to_id


def _push_to_testrail(filename, milestone, project_name, version, plan_comment):
    """
    Push xml file to Testrail
    """
    test_result_file = filename
    if not os.path.exists(test_result_file):
        raise Exception("Test result file {0} was not found on system".format(test_result_file))
    if not os.path.isfile(test_result_file):
        raise Exception("{0} is not a valid file".format(test_result_file))

    testrail_api = testrailapi.TestrailApi(TESTRAIL_SERVER, key=TESTRAIL_KEY)
    project = testrail_api.get_project_by_name(project_name)
    project_id = project['id']

    milestone_id = None
    if milestone:
        milestone = testrail_api.get_milestone_by_name(project_id, milestone)
        milestone_id = milestone['id']

    today = datetime.datetime.today()
    date = today.strftime('%a %b %d %H:%M:%S')
    name = '%s_%s' % (version, date)

    project_mapping_file = os.path.join(CONFIG_DIR, "project_testsuite_mapping.cfg")
    project_map = ConfigParser.ConfigParser()
    project_map.read(project_mapping_file)

    if not project_map.has_section(project_name):
        raise Exception(
            "Config file {0} does not contain section for specified project {0}".format(project_mapping_file,
                                                                                        project_name))

    error_messages = []

    xmlfile = minidom.parse(test_result_file).childNodes[0]
    durations = _get_durations(xmlfile)
    added_suites = []
    plan_id = None
    suite_to_run = {}
    case_name_to_test_id = {}

    all_cases, ran_cases, suite_name_to_id, section_name_to_id = _get_cases(xml_file=xmlfile, testrail_api=testrail_api,
                                                                            project_ini=project_map,
                                                                            project_name=project_name,
                                                                            project_id=project_id)
    testcase_ids_to_select = []

    def add_plan():
        description = _get_description(plan_comment=plan_comment, durations=durations)
        this_plan_id = testrail_api.add_plan(project_id, name, description, milestone_id or None)['id']
        return this_plan_id

    for child in xmlfile.childNodes:
        classname = child.getAttribute('classname')

        if classname.startswith(('<nose', 'nose')):
            if child.childNodes[0].childNodes and \
                    child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                error_messages.append(child.childNodes[0].childNodes[0].data)
            else:
                error_messages.append(child.childNodes[0].getAttribute('message'))
            continue

        suite = classname.split('.')[-2]

        is_blocked = False

        if child.childNodes and "SkipTest" in child.childNodes[0].getAttribute('type'):
            if child.childNodes[0].getAttribute('message') == BLOCKED_MESSAGE:
                is_blocked = True
            else:
                continue

        if not project_map.has_option(project_name, suite):
            raise Exception("Testsuite '%s' is not configured for project '%s' in '%s'" % (suite, project_name,
                                                                                           project_mapping_file))

        suite_name = project_map.get(project_name, suite)

        create_run = False
        if suite_name not in added_suites:
            create_run = True
            if suite_name not in suite_name_to_id:
                continue
            added_suites.append(suite_name)
            testcase_ids_to_select = [c['id'] for c in all_cases[suite_name] if c['title'] in ran_cases[suite_name]]

        case_name = child.getAttribute('name')

        if plan_id is None:
            create_run = False
            plan_id = add_plan()

            entry = testrail_api.add_plan_entry(plan_id, suite_name_to_id[suite_name], suite_name, include_all=False,
                                                case_ids=testcase_ids_to_select)
            run_id = entry['runs'][0]['id']
            suite_to_run[suite_name] = run_id

        if create_run:
            entry = testrail_api.add_plan_entry(plan_id, suite_name_to_id[suite_name], suite_name, include_all=False,
                                                case_ids=testcase_ids_to_select)
            run_id = entry['runs'][0]['id']
            suite_to_run[suite_name] = run_id

        run_id = suite_to_run[suite_name]
        if case_name not in case_name_to_test_id:
            all_tests_for_run = testrail_api.get_tests(run_id=run_id)
            for t in all_tests_for_run:
                case_name_to_test_id[t['title'] + str(run_id)] = t['id']

        test_id = case_name_to_test_id[case_name + str(run_id)]

        comment = ''
        if not child.childNodes:
            status_id = TESTRAIL_STATUS_ID_PASSED
        elif child.childNodes[0].getAttribute('type') == 'nose.plugins.skip.SkipTest':
            if is_blocked:
                status_id = TESTRAIL_STATUS_ID_BLOCKED
                if child.childNodes[0].childNodes and \
                   child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                    comment = child.childNodes[0].childNodes[0].data
            else:
                continue
        else:
            status_id = TESTRAIL_STATUS_ID_FAILED
            if child.childNodes[0].childNodes and \
               child.childNodes[0].childNodes[0].nodeType == minidom.DocumentType.CDATA_SECTION_NODE:
                comment = child.childNodes[0].childNodes[0].data
            else:
                comment = child.childNodes[0].getAttribute('message')
        elapsed = int(child.getAttribute('time'))
        if elapsed == 0:
            elapsed = 1
        testrail_api.add_result(test_id=test_id, status_id=status_id, comment=comment, version=version,
                                elapsed='%ss' % elapsed, custom_fields={'custom_hypervisor': _get_hypervisor()})

    xmlfile.unlink()
    del xmlfile

    if error_messages:
        print "\nSome testsuites failed to start because an error occured during setup:\n{0}".format(error_messages)

    if not plan_id:
        return False
    return "http://%s/index.php?/plans/view/%s" % (TESTRAIL_SERVER, plan_id)


def _get_ips():
    """
    Get node ips based on model information
    """
    ips = []
    from ovs.dal.lists.pmachinelist import PMachineList
    pms = PMachineList.get_pmachines()
    for machine in pms:
        ips.append(str(machine.ip))
    return ips


def _save_config(config):
    """
    Save autotest config file
    """
    with open(AUTOTEST_CFG_FILE, "wb") as fCfg:
        config.write(fCfg)
    globals()['autotestCfg'] = None
    get_config()


def get_test_level():
    """
    Read test level from config file
    """
    config = get_config()
    return config.get(section="main", option="testlevel")


def set_test_level(test_level):
    """
    Set test level : 1,2,3,8-12,15
    """
    testlevel_regex = "^([0-9]|[1-9][0-9])([,-]([1-9]|[1-9][0-9])){0,}$"
    if not re.match(testlevel_regex, test_level):
        print('Wrong testlevel specified\neg: 1,2,3,8-12,15')
        return False

    config = get_config()
    config.set(section="main", option="testlevel", value=test_level)
    _save_config(config)

    return True


def get_hypervisor_info():
    """
    Retrieve info about hypervisor (ip, username, password)
    """
    config = get_config()
    hi = config.get(section="main", option="hypervisorinfo")
    hpv_list = hi.split(",")
    if not len(hpv_list) == 3:
        print "No hypervisor info present in config"
        return
    return hpv_list


def set_hypervisor_info(ip, username, password):
    """
    Set info about hypervisor( ip, username and password )

    @param ip:         Ip address of hypervisor
    @type ip:          String

    @param username:   Username fort hypervisor
    @type username:    Srting

    @param password:    Password of hypervisor
    @type password:    String

    @return:           None
    """

    ipaddress_regex = \
        "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"

    if not re.match(ipaddress_regex, ip):
        print("Invalid ipaddress specified")
        return False

    if type(username) != str or type(password) != str:
        print("Username and password need to be str format")
        return False

    value = ','.join([ip, username, password])
    config = get_config()
    config.set(section="main", option="hypervisorinfo", value=value)
    _save_config(config)

    return True


def list_os():
    """
    List os' configured in os_mapping
    """

    os_mapping_config = ConfigParser.ConfigParser()
    os_mapping_config.read(OS_MAPPING_CFG_FILE)

    return os_mapping_config.sections()


def get_os_info(os_name):
    """
    Get info about an os configured in os_mapping
    """
    os_mapping_config = ConfigParser.ConfigParser()
    os_mapping_config.read(OS_MAPPING_CFG_FILE)

    if not os_mapping_config.has_section(os_name):
        print("No configuration found for os {0} in config".format(os_name))
        return

    return dict(os_mapping_config.items(os_name))


def set_os(os_name):
    """
    Set current os to be used by tests
    """
    os_list = list_os()
    if os_name not in os_list:
        print("Invalid os specified, available options are {0}".format(str(os_list)))
        return False

    config = get_config()
    config.set(section="main", option="os", value=os_name)
    _save_config(config)

    return True


def get_os():
    """
    Retrieve current configured os for autotests
    """
    config = get_config()

    return config.get(section="main", option="os")


def set_template_server(template_server):
    """
    Set current template server to be used by tests
    """

    config = get_config()
    config.set(section="main", option="template_server", value=template_server)
    _save_config(config)

    return True


def get_template_server():
    """
    Retrieve current configured template server for autotests
    """
    config = get_config()

    return config.get(section="main", option="template_server")


def get_username():
    """
    Get username to use in tests
    """
    config = get_config()
    return config.get(section="main", option="username")


def set_username(username):
    """
    Set username to use in tests
    """
    config = get_config()
    config.set(section="main", option="username", value=username)
    _save_config(config)

    return True


def get_password():
    """
    Get password to use in tests
    """
    config = get_config()
    return config.get(section="main", option="username")


def set_password(password):
    """
    Set password to use in tests
    """
    config = get_config()
    config.set(section="main", option="password", value=password)
    _save_config(config)

    return True
