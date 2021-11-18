import urllib
from pytablewriter import MarkdownTableWriter
from dataclasses import dataclass, fields
from datetime import datetime


@dataclass
class DefaultEvent:
    start: datetime
    end: datetime
    summary: str
    location: str

    time_fields = ['start', 'end']
    relative_link_fields = ['summary']
    location_link_fields = ['location']

    def convert_time(self, v, show_day=False, show_year=False):
        format_str = '%-I:%M%p'
        if show_day:
            format_str = '%a %b %d %-I:%M%p'
            if show_year:
                format_str = '%a %b %d, %Y %-I:%M%p'
        return v.strftime(format_str)

    def is_time_field(self, f): return f in {'start', 'end'}
    def is_relative_link_field(self, f): return f in {'summary'}
    def is_location_link_field(self, f): return f in {'location'}

    @classmethod
    def get_field_names(cls):
        return [f.name for f in fields(cls)]

    def format(self):
        row = []
        for f in self.get_field_names():
            v = getattr(self, f)
            if self.is_time_field(f):
                v = self.convert_time(v)
            elif self.is_relative_link_field(f):
                v = link_relative(v)
            elif self.is_location_link_field(f):
                v = link_location(v)
            row.append(v)
        return row


def get_map_query(*args):
    params = dict(
        api=1,
        query=' '.join(args),
    )
    return 'https://www.google.com/maps/search/?{}'.format(urllib.parse.urlencode(params))


def get_map_md(raw):
    mapped = []
    for line in raw.splitlines():
        query = line.strip()
        if query:
            params = dict(
                api=1,
                query=query,
            )
            url = 'https://www.google.com/maps/search/?{}'.format(urllib.parse.urlencode(params))
            mapped.append('[{}]({})'.format(query, url))
    return '\n'.join(mapped).strip()


def link_relative(heading):
    return '[[#{heading}]]'.format(heading=heading)


def link_location(location):
    if location is None:
        return ''
    elif location.startswith('http'):
        return '[link]({})'.format(location)
    else:
        return '[{}]({})'.format(location, get_map_query(location))


def make_event_table(events, ignore_duplicates=True, Event=DefaultEvent):
    headers = Event.get_field_names()
    seen = set()
    rows = []
    for e in events:
        if ignore_duplicates and e.summary in seen:
            continue
        seen.add(link_relative(e.summary))
        rows.append(e.format())
    return MarkdownTableWriter(headers=headers, value_matrix=rows).dumps()
