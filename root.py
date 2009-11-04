# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2008 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2007-2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007-2008 Nicolas Deram <nicolas@itaapy.com>
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

# Import from itools
from itools.core import freeze
from itools.datatypes import String
from itools.gettext import MSG
from itools.handlers import RWDatabase
from itools.web import BaseView

# Import from ikaaro
from folder import Folder
from registry import get_resource_class
from user import UserFolder
from utils import crypt_password
from website import WebSite



class CtrlView(BaseView):

    access = True
    query_schema = {'name': String}


    def http_get(self):
        context.response.set_header('content-type', 'text/plain')
        name = context.query['name']

        # Read-Only
        if name == 'read-only':
            database = context.database
            return 'no' if isinstance(database, RWDatabase) else 'yes'

        return '?'



class Root(WebSite):

    class_id = 'iKaaro'
    class_title = MSG(u'iKaaro')
    class_icon16 = 'icons/16x16/root.png'
    class_icon48 = 'icons/48x48/root.png'
    class_control_panel = ['browse_users', 'add_user', 'edit_virtual_hosts',
                           'edit_security_policy', 'edit_languages',
                           'edit_contact_options',
                           'edit_search_engine_optimizations']
    class_roles = freeze(['admins'])


    __fixed_handlers__ = ['users', 'ui']



    def init_resource(self, email, password, admins=('0',), **kw):
        WebSite.init_resource(self, admins=admins, **kw)
        # User folder
        users = self.make_resource('users', UserFolder, title={'en': u'Users'})
        # Default User
        password = crypt_password(password)
        user_class = get_resource_class('user')
        users.make_resource('0', user_class, email=email, password=password)


    def _get_names(self):
        return [ x for x in Folder._get_names(self) if x ]


    def get_document_types(self):
        return WebSite.get_document_types(self) + [WebSite]


    #######################################################################
    # Web services
    #######################################################################
    _ctrl = CtrlView()

