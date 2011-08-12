#!/usr/bin/env python
import argparse
import prod
from prod import username, pwd, dbname

parser = argparse.ArgumentParser(description='upgrades the specified app on host')
parser.add_argument('applications', type=str, nargs='+')
parser.add_argument('--host', type=str, default="localhost")
parser.add_argument('--dbname', type=str, default=dbname)
args = parser.parse_args()

from erpconnect import OpenERP, F
cx = OpenERP(args.host, args.dbname, username, pwd)
modules = cx.ir.module.module.search([F("name")==args.applications])
if not modules:
    print "module not found !"
    exit()

modules.write({'state':'to upgrade'})
cx.base.module.upgrade.execute("upgrade_module", [])
