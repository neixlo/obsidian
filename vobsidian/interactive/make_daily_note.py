#!/usr/bin/env python
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import os
import re
import datetime
import pathlib
import tzlocal
from collections import defaultdict
from pyicloud import PyiCloudService
from .. import common as C


TEMPLATE_AGENDA = """
# Agenda for {today_long}

## Notes


## Tasks

Outstanding
```tasks
not done
due before {due}
```

Finished
```tasks
done on {today}
```

## Today

{events_today}

## Upcoming

{events_upcoming}
""".strip()


class AppleEvent(C.DefaultEvent):
    pass


def convert_apple_events(events):
    return [AppleEvent(summary=e['title'], start=e['localStartDate'], end=e['localEndDate'], location=e.get('location', None)) for e in events]


def format_upcoming(upcoming, subtree, name_format):
    txt = []
    for days, events in upcoming.items():
        date = events[0]['localStartDate']
        name = '### In [[{subtree}/{filename} | {days} days {pretty_date}]]:'.format(
            days=days,
            subtree=subtree,
            filename=date.strftime(name_format),
            pretty_date=date.strftime('%A - %B %d'),
        )
        txt.append(name)
        table = C.make_event_table(Event=C.DefaultEvent, events=convert_apple_events(events))
        txt.append(table)
        txt.append('')
    return '\n'.join(txt)


def build_note_for_date(events, date, args):
    events_today, events_upcoming = [], defaultdict(list)
    for event in events:
        is_today = event['localStartDate'].replace(hour=0, minute=0, second=0, microsecond=0) <= date
        if is_today:
            events_today.append(event)
        else:
            events_upcoming[(event['localStartDate'] - date).days].append(event)

    txt = TEMPLATE_AGENDA.format(
        today=date.strftime('%Y-%m-%d'),
        today_long=date.strftime('%A - %B %d, %Y'),
        due=(date + datetime.timedelta(days=14)).strftime('%Y-%m-%d'),
        events_today=C.make_event_table(Event=C.DefaultEvent, events=convert_apple_events(events_today)),
        events_upcoming=format_upcoming(events_upcoming, args.subtree, args.name_format),
    )

    fnote = pathlib.Path(os.path.join(args.vault, args.subtree, date.strftime(args.name_format)))
    if fnote.exists():
        if args.overwrite:
            print('Overwriting non-notes section')
            with fnote.open('rt') as f:
                content = f.read()
                existing_notes = re.findall(r'(## Notes.+)\n## Tasks', content, re.DOTALL)
                assert len(existing_notes) == 1, 'Invalid number of note sections = {}'.format(len(existing_notes))
            with fnote.open('wt') as f:
                f.write(txt.replace('## Notes', existing_notes[0]))
        else:
            print('Skipping existing note {}'.format(fnote))
    else:
        with fnote.open('wt') as f:
            f.write(txt)
        print('Wrote:\n{}'.format(fnote))


def date_is_within_window(x, start, end):
    return x >= start and end <= end


def build_notes(events, now, args):
    events = list(events)
    for i in range(args.days):
        date = now + datetime.timedelta(days=i)
        end_date = date + datetime.timedelta(days=args.upcoming)
        build_note_for_date([e for e in events if date_is_within_window(e['localStartDate'], date, end_date)], date, args)


def fix_dates(event):
    for k in ['lastModifiedDate', 'localEndDate', 'localStartDate', 'createdDate', 'startDate', 'endDate']:
        concat, year, month, day, hour, minute, _ = event[k]
        date = datetime.datetime(year=year, month=month, day=day, hour=hour, minute=minute, tzinfo=tzlocal.get_localzone())
        event[k] = date


def main():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--silent', action='store_true', help='print debug info.')
    parser.add_argument('--vault', default='{}/notes/Research'.format(os.environ['HOME']), help='where is your Obsidian root.')
    parser.add_argument('--subtree', default='Agenda', help='subtree of your Obsidian where agenda notes are stored.')
    parser.add_argument('--upcoming', default=7, help='How many days upcoming to show', type=int)
    parser.add_argument('--days', default=1, help='How many days to parse', type=int)
    parser.add_argument('--name_format', default='%Y-%m-%d.md', help='File name format')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite exsting note but keep Note section')
    parser.add_argument('--calendars', help='calendar IDs', nargs='+', default=[''])
    parser.add_argument('--apple_id', help='What is your apple ID? Log in first using `icloud --username=USERID`')
    args = parser.parse_args()

    now = datetime.datetime.now(tz=tzlocal.get_localzone()).replace(hour=0, minute=0, second=0, microsecond=0)

    api = PyiCloudService(args.apple_id)
    events = api.calendar.events(now, now + datetime.timedelta(days=args.days - 1 + args.upcoming))
    for e in events:
        fix_dates(e)

    events.sort(key=lambda e: e['localStartDate'])
    build_notes(events, now, args)


if __name__ == '__main__':
    main()
