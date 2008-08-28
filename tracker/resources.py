# -*- coding: UTF-8 -*-
# Copyright (C) 2007-2008 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2008 Gautier Hayoun <gautier.hayoun@itaapy.com>
# Copyright (C) 2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
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
from datetime import date, datetime, time, timedelta

# Import from itools
from itools.csv import Table as BaseTable, Record
from itools.datatypes import Boolean, Date, DateTime, Integer, String, Unicode
from itools.datatypes import Enumerate
from itools.gettext import MSG
from itools.ical import Time
from itools.stl import stl
from itools.web import get_context, STLForm
from itools.xapian import OrQuery, AndQuery, RangeQuery

# Import from ikaaro
from ikaaro.calendar_ import CalendarBase
from ikaaro.calendar_views import MonthlyView
from ikaaro.calendar_views import WeeklyView
from ikaaro.forms import DateWidget, MultilineWidget, Select, TextWidget
from ikaaro.messages import MSG_CHANGES_SAVED
from ikaaro.table import Table, TableView
from ikaaro.registry import register_object_class


resolution = timedelta.resolution


class TrackerMonthlyView(MonthlyView):

    monthly_template = '/ui/tracker/monthly_template.xml'

    def get_with_new_url(self):
        return False



class TrackerWeeklyView(WeeklyView):

    weekly_template_fd = '/ui/tracker/weekly_template_fd.xml'
    weekly_template = '/ui/tracker/weekly_template.xml'


    def get_weekly_templates(self):
        root = get_context().root
        template = root.get_resource(self.weekly_template)
        template_fd = root.get_resource(self.weekly_template_fd)
        return template, template_fd


    def get_with_new_url(self):
        return False


    # Get timetables as a list of string containing time start of each one
    def get_timetables_grid_ns(self, resource, start_date):
        """Build namespace to give as grid to gridlayout factory.
        """
        ns_timetables = []
        for start, end in resource.get_timetables():
            for value in (start, end):
                value = Time.encode(value)
                if value not in ns_timetables:
                    ns_timetables.append(value)
        return ns_timetables



class ResourcesView(TableView):

    def get_widgets(self, resource, context):
        return resource.get_form()


    def get_item_value(self, resource, context, item, column):
        if column == 'index':
            id = item.id
            return id, '../resources/;edit_record?id=%s' % id
        return TableView.get_item_value(self, resource, context, item, column)



class Resource(Record):

    def get_end(self):
        return self.get_value('dtend')


    def get_ns_event(self, day, resource_name=None, conflicts_list=[],
                     timetable=None, grid=False,
                     starts_on=True, ends_on=True, out_on=True):
        context = get_context()
        here = context.resource
        issue = here.parent.get_resource(self.get_value('issue'))
        users = context.root.get_resource('/users')
        user = self.get_value('resource')
        user_title = users.get_resource(user).get_title()
        ns = {}
        ns['resource'] = {'name': user, 'title': user_title}
        ns['issue'] = {'number': issue.name, 'title': issue.get_value('title'),
                       'url': '../%s/;edit' % issue.name}

        ###############################################################
        # Set dtstart and dtend values using '...' for events which
        # appear into more than one cell
        start = self.get_value('dtstart')
        end = self.get_value('dtend')
        ns['start'] = Time.encode(start.time())
        ns['end'] = Time.encode(end.time())
        ns['TIME'] = None
        if grid:
            # Neither a full day event nor a multiple days event
            if start.time() != time(0,0) and end.time() != time(0,0)\
              and start.date() == end.date():
                ns['TIME'] = '%s - %s' % (ns['start'], ns['end'])
            else:
                ns['start'] = ns['end'] = None
        elif not out_on:
            if start.date() != end.date():
                value = ''
                if starts_on:
                    value = ns['start']
                    if ends_on:
                        value = value + '-'
                    else:
                        value = value + '...'
                if ends_on:
                    value = value + ns['end']
                    if not starts_on:
                        value = '...' + value
                ns['TIME'] = '(' + value + ')'

        print ns
        return ns



class ListOfUsers(Enumerate):

    @classmethod
    def get_options(cls):
        tracker = get_context().resource.parent
        return [{'name': x['id'], 'value': x['title']}
                for x in tracker.get_members_namespace('')]



class BaseResources(BaseTable):

    schema = {
        'dtstart': DateTime(mandatory=True, index='keyword'),
        'dtend': DateTime(mandatory=True, index='keyword'),
        'issue': String(mandatory=True, index='keyword'),
        'resource': ListOfUsers(mandatory=True, index='keyword'),
        'comment': Unicode}

    form = [
        Select('resource', title=u'Resource'),
        DateWidget('dtstart', title=u'Start YYYY-MM-DD HH:MM'),
        DateWidget('dtend', title=u'End'),
        MultilineWidget('comment', title=u'Comment'),
        TextWidget('issue', title=u'Issue')]

    record_class = Resource



class Resources(Table, CalendarBase):

    class_id = 'resources'
    class_version = '20071216'
    class_title = MSG(u'Resources')
    class_description = MSG(u'Resources assigned to issues')
    class_handler = BaseResources

    class_views = ['weekly_view', 'monthly_view', 'edit_timetables']


    def get_action_url(self, **kw):
        issue = kw.get('issue', None)
        if issue:
            return get_context().uri.resolve('../%s/;edit' % issue)
        return None


    def get_events_to_display(self, start, end):
        results = self.parent.get_search_results(get_context())
        results = [result.name for result in results.get_documents()]
        dtstart = str(start)
        dtend = str(end)
        dtstart_limit = str(start + resolution)
        dtend_limit = str(end + resolution)
        query = OrQuery(RangeQuery('dtstart', dtstart, dtend),
                        RangeQuery('dtend', dtstart_limit, dtend_limit),
                        AndQuery(RangeQuery('dtstart', None, dtstart),
                                 RangeQuery('dtend', dtend, None)))
        resources = self.handler.search(query)

        resource_names, events = {}, []
        for record in resources:
            if record.get_value('issue') in results:
                e_dtstart = record.get_value('dtstart')
                events.append((0, e_dtstart, record))
        events.sort(lambda x, y : cmp(x[1], y[1]))
        return {0:self.name}, events


    monthly_view = TrackerMonthlyView()
    weekly_view = TrackerWeeklyView()



class EditResourcesForm(STLForm):

    access = 'is_allowed_to_edit'
    title = MSG(u'Edit resources')
    icon = 'edit.png'
    template = '/ui/tracker/edit_resources.xml'

    schema = {
        'resource': String,
        'dtstart': Date,
        'dtend': Date,
        'tstart': Time,
        'tend': Time,
        'comment': Unicode,
        }

    query_schema = {
        'resource': String,
        'dtstart': Date,
        'dtend': Date,
        'tstart': Time,
        'tend': Time,
        'time_select': String,
        'comment': Unicode,
        'batch_start': Integer(default=0),
        'batch_size': Integer(default=20),
        'sort_by': String,
        'reverse': Boolean(default=False),
        }


    def get_namespace(self, resource, context):
        query = context.query
        q_resource = query.get('resource') or ''
        dtstart = query.get('dtstart', date.today())
        dtend = query.get('dtend', date.today())
        tstart = query['tstart']
        tend = query['tend']
        time_select = query['time_select']
        comment = query['comment']

        namespace = {}
        # New assignment
        namespace['issue'] = {'number': resource.name,
                              'title': resource.get_title()}
        namespace['users'] = resource.parent.get_members_namespace(q_resource)
        namespace['dtstart'] = dtstart
        namespace['tstart'] = tstart
        namespace['dtend'] = dtend
        namespace['tend'] = tend
        namespace['comment'] = comment
        namespace['time_select'] = resource.get_time_select('time_select',
                                                            time_select)
        # Existent ones
        resources = resource.get_resources()
        template = resource.get_resource(ResourcesView.template)
        ns_table = ResourcesView().get_namespace(resources, context)
        namespace['table'] = stl(template, ns_table)

        return namespace


    def action(self, resource, context, form):
        tstart = form['tstart'] or time(0,0)
        tend = form['tend'] or time(0,0)
        record = {}
        record['issue'] = resource.name
        record['resource'] = form['resource']
        record['dtstart'] = datetime.combine(form['dtstart'], tstart)
        record['dtend'] = datetime.combine(form['dtend'], tend)
        resources = resource.get_resources()
        resources.handler.add_record(record)
        context.message = MSG_CHANGES_SAVED



###########################################################################
# Register
###########################################################################
register_object_class(Resources)
