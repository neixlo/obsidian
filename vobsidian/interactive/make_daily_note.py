#!/usr/bin/env python
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import os
import datetime
import pathlib
import tzlocal
from gcsa.google_calendar import GoogleCalendar
from collections import defaultdict


TEMPLATE_AGENDA = """
# Agenda for {today_long}

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


## Notes


## Upcoming

{events_upcoming}
""".strip()

TEMPLATE_EVENT = """
### {start_hour} {summary}
* Start: {start}
* End: {end}
* Location: {location}
""".strip()


def format_event(event):
    txt = TEMPLATE_EVENT.format(
        summary=event.summary,
        description=event.description or 'No description',
        location=event.location,
        start=event.start.strftime('%A %b %d %-I:%M%p'),
        start_hour=event.start.strftime('%-I:%M%p'),
        end=event.end.strftime('%A %b %d %-I:%M%p'),
    )
    if event.attendees:
        snip = '* Attendees'
        for a in event.attendees:
            snip += '\n  * {}'.format(getattr(a, 'email', repr(a)))
        txt += '\n{}'.format(snip)
    if event.description:
        txt += '\n- Description:\n```\n{}\n```'.format(event.description.strip())
    return txt


def format_upcoming(upcoming, subtree, name_format):
    txt = []
    for days, events in upcoming.items():
        date = events[0].start
        txt.append('In [[{subtree}/{filename} | {days} days {pretty_date}]]:'.format(
            days=days,
            subtree=subtree,
            filename=date.strftime(name_format),
            pretty_date=date.strftime('%A - %B %d'),
        ))
        for event in events:
            txt.append('* {} {}'.format(event.start.strftime('%-I:%M%p'), event.summary))
        txt.append('')
    return '\n'.join(txt)


def build_note_for_date(events, date, args):
    events_today, events_upcoming = [], defaultdict(list)
    for event in events:
        event_start = force_datetime(event.start)
        is_today = force_datetime(event_start).replace(hour=0, minute=0, second=0, microsecond=0) <= date
        if is_today:
            events_today.append(format_event(event))
        else:
            events_upcoming[(event_start - date).days].append(event)

    txt = TEMPLATE_AGENDA.format(
        today=date.strftime('%Y-%m-%d'),
        today_long=date.strftime('%A - %B %d, %Y'),
        due=(date + datetime.timedelta(days=14)).strftime('%Y-%m-%d'),
        events_today='\n\n'.join(events_today),
        events_upcoming=format_upcoming(events_upcoming, args.subtree, args.name_format),
    )

    fnote = pathlib.Path(os.path.join(args.vault, args.subtree, date.strftime(args.name_format)))
    if fnote.exists():
        print('Skipping existing note {}'.format(fnote))
    else:
        with fnote.open('wt') as f:
            f.write(txt)
        print('Wrote:\n{}'.format(fnote))


def force_datetime(date):
    if isinstance(date, datetime.datetime):
        return date
    else:
        return datetime.datetime.combine(date, datetime.datetime.min.time()).astimezone(tzlocal.get_localzone())


def date_is_within_window(x, start, end):
    x = force_datetime(x)
    return x >= start and end <= end


def build_notes(events, now, args):
    events = list(events)
    for i in range(args.days):
        date = now + datetime.timedelta(days=i)
        end_date = date + datetime.timedelta(days=args.upcoming)
        build_note_for_date([e for e in events if date_is_within_window(e.start, date, end_date)], date, args)


def main():
    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument('--silent', action='store_true', help='print debug info.')
    parser.add_argument('--vault', default='{}/notes/Research'.format(os.environ['HOME']), help='where is your Obsidian root.')
    parser.add_argument('--subtree', default='Agenda', help='subtree of your Obsidian where agenda notes are stored.')
    parser.add_argument('--upcoming', default=7, help='How many days upcoming to show', type=int)
    parser.add_argument('--days', default=1, help='How many days to parse', type=int)
    parser.add_argument('--name_format', default='%Y-%m-%d.md', help='File name format')
    parser.add_argument('--calendars', help='calendar IDs', nargs='+')
    parser.add_argument('--fcredentials', help='credentials file', default=os.path.join(os.environ['HOME'], '.credentials', 'gcal.json'))
    args = parser.parse_args()

    now = datetime.datetime.now(tz=tzlocal.get_localzone()).replace(hour=0, minute=0, second=0, microsecond=0)

    events = []
    for g in args.calendars:
        calendar = GoogleCalendar(g, credentials_path=args.fcredentials)
        events.extend(list(calendar.get_events(now, now + datetime.timedelta(days=args.days - 1 + args.upcoming), single_events=True, order_by='startTime')))
    events.sort(key=lambda e: force_datetime(e.start))
    build_notes(events, now, args)


if __name__ == '__main__':
    main()
