#!/bin/bash
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