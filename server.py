# -*- coding: UTF-8 -*-
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2006-2007 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
from os import fdopen
import sys
from tempfile import mkstemp

# Import from itools
from itools.datatypes import Boolean, Integer, String, Tokens
from itools.handlers import ConfigFile, SafeDatabase
from itools.uri import get_absolute_reference2
from itools import vfs
from itools.web import Server as BaseServer
from itools.xapian import Catalog

# Import from ikaaro
from folder import Folder
from metadata import Metadata
from registry import get_object_class
from utils import is_pid_running
from versioning import VersioningAware
from website import WebSite



class ServerConfig(ConfigFile):

    schema = {
        'modules': Tokens(default=()),
        'listen-address': String(default=''),
        'listen-port': Integer(default=8080),
        'smtp-host': String(default=''),
        'smtp-from': String(default=''),
        'smtp-login': String(default=''),
        'smtp-password': String(default=''),
        'debug': Boolean(default=False),
    }




def ask_confirmation(message, confirm=False):
    if confirm is True:
        print message + 'Y'
        return True

    sys.stdout.write(message)
    sys.stdout.flush()
    line = sys.stdin.readline()
    line = line.strip().lower()
    return line == 'y'



def get_config(target):
    return ServerConfig('%s/config.conf' % target)



def load_modules(config):
    """Load Python packages and modules.
    """
    modules = config.get_value('modules')
    for name in modules:
        name = name.strip()
        exec('import %s' % name)



def get_pid(target):
    try:
        pid = open('%s/pid' % target).read()
    except IOError:
        return None

    pid = int(pid)
    if is_pid_running(pid):
        return pid
    return None



def get_root(database, target):
    path = '%s/database/.metadata' % target
    metadata = database.get_handler(path, cls=Metadata)
    cls = get_object_class(metadata.format)
    # Build the root object
    root = cls(metadata)
    root.name = root.class_title.message
    return root



class Server(BaseServer):

    def __init__(self, target, address=None, port=None, debug=False,
                 read_only=False):
        target = get_absolute_reference2(target)
        self.target = target

        # Load the config
        config = get_config(target)
        load_modules(config)

        # Find out the IP to listen to
        if not address:
            address = config.get_value('listen-address').strip()

        # Find out the port to listen
        if not port:
            port = config.get_value('listen-port')

        # Contact Email
        self.smtp_from = config.get_value('smtp-from')

        # The database
        events_log = '%s/log/events' % target.path
        database = SafeDatabase('%s/database.commit' % target.path,
                                events_log)
        self.database = database
        # The catalog
        self.catalog = Catalog('%s/catalog' % target, read_only=read_only)

        # Find out the root class
        root = get_root(database, target)

        # Logs
        path = target.path
        access_log = '%s/log/access' % path
        error_log = '%s/log/error' % path
        if debug or config.get_value('debug'):
            debug_log = events_log
        else:
            debug_log = None

        # Events
        self.objects_added = set()
        self.objects_changed = set()
        self.objects_removed = set()

        # Initialize
        BaseServer.__init__(self, root, address=address, port=port,
                            access_log=access_log, error_log=error_log,
                            debug_log=debug_log, pid_file='%s/pid' % path)


    #######################################################################
    # API / Private
    #######################################################################
    def get_pid(self):
        return get_pid(self.target.path)


    def send_email(self, message):
        # Check the SMTP host is defined
        config = get_config(self.target)
        if not config.get_value('smtp-host'):
            raise ValueError, '"smtp-host" is not set in config.conf'

        spool = self.target.resolve2('spool')
        spool = str(spool.path)
        tmp_file, tmp_path = mkstemp(dir=spool)
        file = fdopen(tmp_file, 'w')
        try:
            file.write(message.as_string())
        finally:
            file.close()


    def get_databases(self):
        return [self.database, self.catalog]


    def abort_transaction(self, context):
        # Clear events
        self.objects_removed.clear()
        self.objects_added.clear()
        self.objects_changed.clear()
        # Follow-up
        BaseServer.abort_transaction(self, context)


    def before_commit(self):
        root = self.root
        catalog = self.catalog
        # Removed
        for path in self.objects_removed:
            catalog.unindex_document(path)
        self.objects_removed.clear()

        # Added
        for path in self.objects_added:
            object = root.get_resource(path)
            if isinstance(object, VersioningAware):
                object.commit_revision()
            catalog.index_document(object)
        self.objects_added.clear()

        # Changed
        for path in self.objects_changed:
            object = root.get_resource(path)
            if isinstance(object, VersioningAware):
                object.commit_revision()
            catalog.unindex_document(path)
            catalog.index_document(object)
        self.objects_changed.clear()


    #######################################################################
    # API / Public
    #######################################################################
    def init_context(self, context):
        BaseServer.init_context(self, context)
        # Set the list of needed resources. The method we are going to
        # call may need external resources to be rendered properly, for
        # example it could need an style sheet or a javascript file to
        # be included in the html head (which it can not control). This
        # attribute lets the interface to add those resources.
        context.styles = []
        context.scripts = []
        context.message = None


    def find_site_root(self, context):
        hostname = context.uri.authority.host

        # Check first the root
        root = self.root
        if hostname in root.get_property('vhosts'):
            context.site_root = root
            return

        # Check the sub-sites
        for site in root.search_objects(object_class=WebSite):
            if hostname in site.get_property('vhosts'):
                context.site_root = site
                return

        # Default to root
        context.site_root = root


    def remove_object(self, object):
        objects_removed = self.objects_removed
        objects_added = self.objects_added

        if isinstance(object, Folder):
            for x in object.traverse_objects():
                path = str(x.get_canonical_path())
                if path in objects_added:
                    objects_added.remove(path)
                objects_removed.add(path)
        else:
            path = str(object.get_canonical_path())
            if path in objects_added:
                objects_added.remove(path)
            objects_removed.add(path)


    def add_object(self, object):
        if isinstance(object, Folder):
            for x in object.traverse_objects():
                path = str(x.get_canonical_path())
                self.objects_added.add(path)
        else:
            path = str(object.get_canonical_path())
            self.objects_added.add(path)


    def change_object(self, object):
        path = str(object.get_canonical_path())
        self.objects_changed.add(path)

