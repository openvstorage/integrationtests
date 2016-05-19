#!/bin/bash
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

pip install --upgrade pip
pip install pysnmp==4.2.5
pip install splinter
pip install ipcalc>=1.1.0
pip install nose>=1.3.1

chown -R ovs:ovs /opt/OpenvStorage/ci

find /opt/OpenvStorage -name *.pyc -exec rm -rf {} \;

wget https://bitbucket.org/ariya/phantomjs/downloads/phantomjs-1.9.8-linux-x86_64.tar.bz2
mkdir -p /opt/phantomjs
tar -xjvf phantomjs-1.9.8-linux-x86_64.tar.bz2 --strip-components 1 /opt/phantomjs/
ln -s /opt/phantomjs/bin/phantomjs /usr/bin/phantomjs