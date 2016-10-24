#!/usr/bin/env bash

cd /opt/OpenvStorage
export OVS_LOGTYPE_OVERRIDE=file
python -c "from ci.main import Workflow; Workflow.main()"
