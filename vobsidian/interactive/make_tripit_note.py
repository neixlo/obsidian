import requests
from requests_oauthlib import OAuth1
import json
import pathlib
import os
import urllib
from argparse import ArgumentParser
from requests_oauthlib import OAuth1Session
from collections import defaultdict


def get_oauth(args):
    with open(args.fcredentials) as f:
        creds = json.load(f)

    if 'OAUTH_TOKEN' not in creds:
        client_key = creds['CLIENT_KEY']
        client_secret = creds['CLIENT_SECRET']
        request_token_url = 'https://api.tripit.com/oauth/request_token'
        oauth = OAuth1Session(client_key, client_secret=client_secret)
        fetch_response = oauth.fetch_request_token(request_token_url)

        base_authorization_url = 'https://www.tripit.com/oauth/authorize'
        authorization_url = oauth.authorization_url(base_authorization_url) + '&oauth_callback=https://example.org'
        _ = input('Press Enter once you have authorized the app:\n{}'.format(authorization_url))

        fetch_response = oauth.fetch_request_token('https://api.tripit.com/oauth/access_token')
        creds['OAUTH_TOKEN_SECRET'] = fetch_response['oauth_token_secret']
        creds['OAUTH_TOKEN'] = fetch_response['oauth_token']
        with open(args.fcredentials, 'w') as fp:
            json.dump(creds, fp, indent=2)
    return creds


TEMPLATE_TRIP = """
# Trip:: {display_name}

Start:: {start_date}
End:: {end_date}
Location:: {primary_location}

```
TripitID:: {id}
TripitURL:: {relative_url}
```

```itinerary
initialDate: {start_date}
initialView: listMonth
```
""".strip()


HEADER_DEFAULT = """
## {field}
""".strip()


TEMPLATE_TOP = """
```itinerary-event
title: {display_name}
start: {StartDateTime[date]}T{StartDateTime[time]}
end: {EndDateTime[date]}T{EndDateTime[time]}
startTimeZone: {StartDateTime[timezone]}
endTimeZone: {EndDateTime[timezone]}
color: brown
tag:
- lodging
```
""".strip()

TEMPLATE_LODGING = """
### {display_name}

[Map]({map_query})

{top}

* Room: {room_type}
* Address: {Address[address]}
* Price: {total_cost}
* Booking:
    * Name: {booking_site_name}
    * Confirmation #: {booking_site_conf_num}
    * Phone: {booking_site_phone}
""".strip()

TEMPLATE_FLIGHT = """
### {start_city_name} to {end_city_name} on {marketing_airline} {marketing_flight_number}

[Map](map_query)

{top}

* From: {start_city_name}, {start_country_code} ({start_airport_code})
* To: {end_city_name}, {end_country_code} ({end_airport_code})
* Flight: {marketing_airline} {marketing_flight_number}
    * Duration: {duration}
    * Distance: {distance}
    * Aircraft: {aircraft_display_name}
""".strip()

TEMPLATE_TRAIN = """
### {start_station_name} to {end_station_name} on {service_class} {train_number}

[Map](map_query)

{top}

* From: {StartStationAddress[city]}, {StartStationAddress[country]} ({start_station_name})
* To: {EndStationAddress[city]}, {EndStationAddress[country]} ({end_station_name})
* Train: {service_class} {train_number}
    * Coach: {coach_number}
    * Seats: {seats}
""".strip()


TEMPLATE_TRANSPORT = """
### {carrier_name}

{top}

* Confirmation {confirmation_num}
* Booking:
    * Name: {booking_site_name}
    * Confirmation #: {booking_site_conf_num}
    * Phone: {booking_site_phone}

""".strip()


def force_keys(o, keys):
    for k in keys:
        if k not in o:
            o[k] = None


def get_map_query(*args):
    params = dict(
        api=1,
        query=' '.join(args),
    )
    return 'https://www.google.com/maps/search/?{}'.format(urllib.parse.urlencode(params))


def build_note_for_trip(trip, objects, args):
    fnote = pathlib.Path(os.path.join(args.vault, args.subtree, '{}-{}.md'.format(trip['start_date'], trip['display_name'].replace(' ', '_'))))
    if fnote.exists():
        print('Skipping existing note {}'.format(fnote))
    else:
        txt = TEMPLATE_TRIP.format(
            **trip,
        )

        if 'LodgingObject' in objects:
            txt += '\n\n' + HEADER_DEFAULT.format(field='Lodging')
        for obj in objects.get('LodgingObject', []):
            for k in ['name', 'conf_num', 'phone']:
                if 'booking_site_{}'.format(k) not in obj:
                    obj['booking_site_{}'.format(k)] = obj.get('supplier_{}'.format(k))
            force_keys(obj, ['total_cost', 'room_type'])
            if 'Address' not in obj:
                obj['Address'] = dict(address=None)
            txt += '\n\n' + TEMPLATE_LODGING.format(top=TEMPLATE_TOP.format(**obj), map_query=get_map_query(obj['display_name'], obj['Address']['address'] or ''), **obj)

        if 'AirObject' in objects:
            txt += '\n\n' + HEADER_DEFAULT.format(field='Flight')
        for obj in objects.get('AirObject', []):
            if isinstance(obj['Segment'], dict):
                obj['Segment'] = [obj['Segment']]
            for s in obj['Segment']:
                s['display_name'] = '{} to {} ({}{})'.format(s['start_city_name'], s['end_city_name'], s['marketing_airline'], s['marketing_flight_number'])
                txt += '\n\n' + TEMPLATE_FLIGHT.format(top=TEMPLATE_TOP.format(**s), map_query=get_map_query(s['start_city_name'], s['start_airport_code'], 'Airport'), **s)

        if 'RailObject' in objects:
            txt += '\n\n' + HEADER_DEFAULT.format(field='Rail')
        for obj in objects.get('RailObject', []):
            if isinstance(obj['Segment'], dict):
                obj['Segment'] = [obj['Segment']]
            for s in obj['Segment']:
                s['display_name'] = '{} to {} ({}{})'.format(s['start_station_name'], s['end_station_name'], s['service_class'], s['train_number'])
                txt += '\n\n' + TEMPLATE_TRAIN.format(top=TEMPLATE_TOP.format(**s), map_query=get_map_query(s['start_station_name']), **s)

        for k, v in objects.items():
            if k.endswith('Object') and k not in ['LodgingObject', 'WeatherObject', 'AirObject', 'RailObject', 'TransportObject']:
                print(k)
                print(v)
                raise NotImplementedError()

        with fnote.open('wt') as f:
            f.write(txt)
        print('Wrote:\n{}'.format(fnote))


def build_notes(tripit, args):
    trips = tripit['Trip']
    if isinstance(trips, dict):
        trips = [trips]
    for trip in trips:
        objects = defaultdict(list)
        for k in ['WeatherObject', 'AirObject', 'LodgingObject', 'RailObject', 'TransportObject']:
            all_objects = tripit.get(k, [])
            if isinstance(all_objects, dict):
                all_objects = [all_objects]
            for o in all_objects:
                if o['trip_id'] == trip['id']:
                    objects[k].append(o)
        build_note_for_trip(trip, objects, args)


def main():
    parser = ArgumentParser()
    parser.add_argument('--fcredentials', default=os.path.join(os.environ['HOME'], '.credentials', 'tripit.json'))
    parser.add_argument('--silent', action='store_true', help='print debug info.')
    parser.add_argument('--vault', default='{}/notes/Research'.format(os.environ['HOME']), help='where is your Obsidian root.')
    parser.add_argument('--subtree', default='Trips', help='subtree of your Obsidian where trip notes are stored.')
    parser.add_argument('--trip', help='Which trip to pull. Use all to pull everything')
    args = parser.parse_args()

    print('Logging into TripIt')
    creds = get_oauth(args)
    auth = OAuth1(creds['CLIENT_KEY'], creds['CLIENT_SECRET'], creds['OAUTH_TOKEN'], creds['OAUTH_TOKEN_SECRET'])

    timestamp = 0
    if args.trip == 'all':
        tripit = requests.get('https://api.tripit.com/v1/list/trip/traveler/all/past/true/include_objects/true/modified_since/{timestamp}/format/json/page_size/500'.format(timestamp=timestamp), auth=auth).json()
    else:
        tripit = requests.get('https://api.tripit.com/v1/get/trip/id/{}/include_objects/true/format/json'.format(args.trip), auth=auth).json()

    build_notes(tripit, args)


if __name__ == '__main__':
    main()
