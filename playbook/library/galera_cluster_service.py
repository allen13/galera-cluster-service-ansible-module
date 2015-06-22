#!/usr/bin/python
# -*- coding: utf-8 -*-

DOCUMENTATION = '''
---
module: galera_cluster_service
short_description: Start and join nodes of a galera cluster.
description:
   - Start and join nodes of a galera cluster.
version_added: "0.1"
options:
  login_user:
    description:
      - The username used to authenticate with
    required: false
    default: null
  login_password:
    description:
      - The password used to authenticate with
    required: false
    default: null
  login_host:
    description:
      - Host running the database
    required: false
    default: localhost
  login_port:
    description:
      - Port of the MySQL server. Requires login_host be defined as other then localhost if login_port is used
    required: false
    default: 3306
  login_unix_socket:
    description:
      - The path to a Unix domain socket for local connections
    required: false
    default: null
  state:
    description:
      - The service state
    required: false
    default: present
    choices: [ "started", "stopped", "restarted"]
  collation:
    description:
      - Collation mode
    required: false
    default: null
  encoding:
    description:
      - Encoding mode
    required: false
    default: null
  target:
    description:
      - Location, on the remote host, of the dump file to read from or write to. Uncompressed SQL
        files (C(.sql)) as well as bzip2 (C(.bz2)), gzip (C(.gz)) and xz compressed files are supported.
    required: false
notes:
   - Requires the MySQLdb Python package on the remote host. For Ubuntu, this
     is as easy as apt-get install python-mysqldb. (See M(apt).)
   - Both I(login_password) and I(login_user) are required when you are
     passing credentials. If none are present, the module will attempt to read
     the credentials from C(~/.my.cnf), and finally fall back to using the MySQL
     default login of C(root) with no password.
requirements: [ ConfigParser ]
author: "Timothy Allen (@allen13)"
'''

EXAMPLES = '''
# Start and join galera service with the openstack group
- galera_cluster_service: state=started cluster_group=openstack
'''

import ConfigParser
import os
import pipes
import stat
import subprocess
try:
    import MySQLdb
except ImportError:
    mysqldb_found = False
else:
    mysqldb_found = True

# ===========================================
# MySQL module specific support methods.
#

def cluster_size(cursor):
    cursor.execute("show status like 'wsrep_cluster_size%'")
    result = cursor.fetchone()
    cluster_size = int(result[1])
    return cluster_size

def incoming_addresses(cursor):
    cursor.execute("show status like 'wsrep_incoming_addresses'")
    result = cursor.fetchone()
    return result

def strip_quotes(s):
    """ Remove surrounding single or double quotes

    >>> print strip_quotes('hello')
    hello
    >>> print strip_quotes('"hello"')
    hello
    >>> print strip_quotes("'hello'")
    hello
    >>> print strip_quotes("'hello")
    'hello

    """
    single_quote = "'"
    double_quote = '"'

    if s.startswith(single_quote) and s.endswith(single_quote):
        s = s.strip(single_quote)
    elif s.startswith(double_quote) and s.endswith(double_quote):
        s = s.strip(double_quote)
    return s


def config_get(config, section, option):
    """ Calls ConfigParser.get and strips quotes

    See: http://dev.mysql.com/doc/refman/5.0/en/option-files.html
    """
    return strip_quotes(config.get(section, option))


def load_mycnf():
    config = ConfigParser.RawConfigParser()
    mycnf = os.path.expanduser('~/.my.cnf')
    if not os.path.exists(mycnf):
        return False
    try:
        config.readfp(open(mycnf))
    except (IOError):
        return False
    # We support two forms of passwords in .my.cnf, both pass= and password=,
    # as these are both supported by MySQL.
    try:
        passwd = config_get(config, 'client', 'password')
    except (ConfigParser.NoOptionError):
        try:
            passwd = config_get(config, 'client', 'pass')
        except (ConfigParser.NoOptionError):
            return False
    try:
        creds = dict(user=config_get(config, 'client', 'user'),passwd=passwd)
    except (ConfigParser.NoOptionError):
        return False
    return creds

# ===========================================
# Module execution.
#

def main():
    module = AnsibleModule(
        argument_spec = dict(
            login_user=dict(default=None),
            login_password=dict(default=None),
            login_host=dict(default="localhost"),
            login_port=dict(default=3306, type='int'),
            login_unix_socket=dict(default=None),
            name=dict(aliases=['db']),
            encoding=dict(default=""),
            collation=dict(default=""),
            target=dict(default=None),
            state=dict(required=True, choices=[ "started", "stopped", "restarted"]),
        )
    )

    if not mysqldb_found:
        module.fail_json(msg="the python mysqldb module is required")

    db = module.params["name"]
    encoding = module.params["encoding"]
    collation = module.params["collation"]
    state = module.params["state"]
    target = module.params["target"]
    socket = module.params["login_unix_socket"]
    login_port = module.params["login_port"]
    if login_port < 0 or login_port > 65535:
        module.fail_json(msg="login_port must be a valid unix port number (0-65535)")

    # make sure the target path is expanded for ~ and $HOME
    if target is not None:
        target = os.path.expandvars(os.path.expanduser(target))

    # Either the caller passes both a username and password with which to connect to
    # mysql, or they pass neither and allow this module to read the credentials from
    # ~/.my.cnf.
    login_password = module.params["login_password"]
    login_user = module.params["login_user"]
    if login_user is None and login_password is None:
        mycnf_creds = load_mycnf()
        if mycnf_creds is False:
            login_user = "root"
            login_password = ""
        else:
            login_user = mycnf_creds["user"]
            login_password = mycnf_creds["passwd"]
    elif login_password is None or login_user is None:
        module.fail_json(msg="when supplying login arguments, both login_user and login_password must be provided")
    login_host = module.params["login_host"]

    if state in ['dump','import']:
        if target is None:
            module.fail_json(msg="with state=%s target is required" % (state))
	if db == 'all':
            connect_to_db = 'mysql'
            db = 'mysql'
            all_databases = True
        else:
            connect_to_db = db
            all_databases = False
    else:
        if db == 'all':
            module.fail_json(msg="name is not allowed to equal 'all' unless state equals import, or dump.")
        connect_to_db = ''
    try:
        if socket:
            try:
                socketmode = os.stat(socket).st_mode
                if not stat.S_ISSOCK(socketmode):
                    module.fail_json(msg="%s, is not a socket, unable to connect" % socket)
            except OSError:
                module.fail_json(msg="%s, does not exist, unable to connect" % socket)
            db_connection = MySQLdb.connect(host=module.params["login_host"], unix_socket=socket, user=login_user, passwd=login_password, db=connect_to_db)
        elif login_port != 3306 and module.params["login_host"] == "localhost":
            module.fail_json(msg="login_host is required when login_port is defined, login_host cannot be localhost when login_port is defined")
        else:
            db_connection = MySQLdb.connect(host=module.params["login_host"], port=login_port, user=login_user, passwd=login_password, db=connect_to_db)
        cursor = db_connection.cursor()
    except Exception, e:
        errno, errstr = e.args
        if "Unknown database" in str(e):
                module.fail_json(msg="ERROR: %s %s" % (errno, errstr))
        else:
                module.fail_json(msg="unable to connect, check login credentials (login_user, and login_password, which can be defined in ~/.my.cnf), check that mysql socket exists and mysql server is running (ERROR: %s %s)" % (errno, errstr))

    changed = True


    module.exit_json(changed=changed, cluster_size=cluster_size(cursor), incoming_addresses=incoming_addresses(cursor))

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.database import *
if __name__ == '__main__':
    main()
