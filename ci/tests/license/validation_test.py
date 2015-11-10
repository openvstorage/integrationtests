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
script to update files in the codebase:
- starting from root folder (argument after all options : /folder/ovs/)
- all .py files
-- option to specify other files (option --extensions="cfg,txt")
-- extensions without dot and comma separated, no spaces
-- "cfg,txt" OK
-- ".cfg, .txt" NOK
- check if it doesn't exist
- add to all files (but check first if it exists) (option --fix)
-- text: "license see http://www.openvstorage.com/licenses/opensource/"
    (second argument after folder : "license see... ")
only works for text files (no binary files)
call: script.py [--extensions="cfg,txt"] [--fix] /folder/ovs "license text"
help: script.py --help
"""

from ci.tests.general import general
import os

license_to_check = """Copyright 2014 iNuron NV

Licensed under the Open vStorage Non-Commercial License, Version 1.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.openvstorage.org/OVS_NON_COMMERCIAL

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
extensions = ['py', 'js', 'html', 'css']
folders_to_check = ['/opt/OpenvStorage']
# define files and directories to skip checking
# relative paths to the root
skip_files = ['/webapps/frontend/index.html',
              '/config/gunicorn.cfg.py',
              '/config/django/django_gunicorn_ovs.cfg.py']
skip_dirs = ['/webapps/frontend/lib',
             '/webapps/api/static/rest_framework/css',
             '/webapps/frontend/css',
             '/webapps/api/static/rest_framework/js',
             '/.hg',
             '/scripts/',
             '/extensions/db/arakoon/']
# define files and directories to except from skip
# should be subdirectories of the skip directories
# or files inside the skip_dirs
except_skip_dirs = ['/webapps/frontend/lib/ovs']
except_skip_files = ['/webapps/frontend/css/ovs.css']


def list_files(dir_, extensions=[]):
    """
    list all files in dir
    """
    files = []
    files_dirs = os.listdir(dir_)
    for file in files_dirs:
        path = os.path.join(dir_, file)
        if os.path.isfile(path):
            if extensions:
                for extension in extensions:
                    if path.endswith(extension):
                        files.append(path)
                        break
            else:
                files.append(path)
    return files


def list_dirs(dir_):
    """
    list all directories in dir
    """
    dirs = []
    files_dirs = os.listdir(dir_)
    for file in files_dirs:
        path = os.path.join(dir_, file)
        if os.path.isdir(path):
            dirs.append(path)
    return dirs


def get_all_files(root_folder, extensions=[]):
    """
    recursively get all files in root_folder
    """
    for skip_dir in skip_dirs:
        dirskip = False
        if skip_dir in root_folder:
            dirskip = True
            for except_skip_dir in except_skip_dirs:
                if skip_dir in except_skip_dir:
                    dirskip = False
                    break
            if dirskip:
                return []
    files_to_process = []
    if not os.path.exists(root_folder):
        raise ValueError('Root folder {0} does not exist'.format(root_folder))
    files_to_process.extend(list_files(root_folder, extensions))
    for dir_ in list_dirs(root_folder):
        dir_path = os.path.join(root_folder, dir_)
        files_to_process.extend(get_all_files(dir_path, extensions))
    return files_to_process


def get_comment_style(fextension):
    """
    get the comment style for the specific extension
    extension: (before, after)
    """
    comments = {'py': ('# ', ''),
                'cfg': ('# ', ''),
                'js': ('// ', ''),
                'html': ('<!--', ' -->'),
                'css': ('/*', '*/')}
    values = comments.get(fextension, ('# ', ''))
    return values


def check_license_headers_test():
    license_splitlines = license_to_check.splitlines()
    files_with_diff_licenses = ''
    for root_folder in folders_to_check:
        files_to_process = get_all_files(root_folder, extensions)
        # os.write(1, 'Total files to process (based on extensions {0}): {1}'.format(str(extensions), len(files_to_process)))

        for file in files_to_process:
            skip = False
            for skip_file in skip_files:
                if file.endswith(skip_file):
                    # os.write(1, 'skipping file {0}'.format(file))
                    skip = True
                    break
            for skip_dir in skip_dirs:
                dirskip = False
                if skip_dir in file:
                    dirskip = True
                    for except_skip_dir in except_skip_dirs:
                        if except_skip_dir in file:
                            dirskip = False
                            break
                if dirskip:
                    skip = True
                    # os.write(1, 'skipped file {0}'.format(file))
                    break
            for except_skip_file in except_skip_files:
                if except_skip_file in file:
                    skip = False
                    break
            if not skip:
                out, err = general.execute_command('cat {0}'.format(file))
                lines_to_check = out.splitlines()
                offset = 0
                before, after = get_comment_style(file.split('.')[-1])
                if after:
                    offset = 1

                for line_index in range(0, len(license_splitlines)):
                    if license_splitlines[line_index] not in lines_to_check[line_index + offset]:
                        # os.write(1, 'File {0} has a different license\n{1}\n{2}\n'.format(file, lines_to_check[line_index], license_splitlines[line_index]))
                        files_with_diff_licenses += file + '\n'
                        break
    # os.write(1, 'Done processing...')
    assert files_with_diff_licenses == '', 'Following files were found with different licenses:\n {0}'.format(files_with_diff_licenses)

