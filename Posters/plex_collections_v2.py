#!/usr/bin/env python3

import re
import os
import yaml
import requests
import json
import click
import hashlib
import pprint as pretty
import urllib.parse as parse
import logging
from plexapi.server import PlexServer
from progress.bar import Bar

CONFIG_FILE = 'config-v2.yaml'
POSTER_ITEM_LIMIT = 5
DEBUG = False
DRY_RUN = False
FORCE = False
LIBRARY_IDS = False
CONFIG = dict()


global found_count
global missing_count

found_count = 0
missing_count = 0


def init(debug=False, dry_run=False, force=False, library_ids=False):
    global DEBUG
    global DRY_RUN
    global FORCE
    global LIBRARY_IDS
    global CONFIG

    DEBUG = debug
    DRY_RUN = dry_run
    FORCE = force
    LIBRARY_IDS = library_ids

    with open(CONFIG_FILE, 'r') as stream:
        try:
            CONFIG = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)

    CONFIG['headers'] = {'X-Plex-Token': CONFIG['plex_token'], 'Accept': 'application/json'}
    CONFIG['plex_images_url'] = '%s/library/metadata/%%s/%%s?url=%%s' % CONFIG['plex_url']
    CONFIG['plex_images_upload_url'] = '%s/library/metadata/%%s/%%s?includeExternalMedia=1' % CONFIG['plex_url']
    CONFIG['plex_summary_url'] = '%s/library/sections/%%s/all?type=18&id=%%s&summary.value=%%s' % CONFIG['plex_url']

    if DEBUG:
        print('CONFIG: ')
        pretty.pprint(CONFIG)


def setup():
    try:
        data = dict()
        data['plex_url'] = click.prompt('Please enter your Plex URL', type=str)
        data['plex_token'] = click.prompt('Please enter your Plex Token', type=str)

        with open(CONFIG_FILE, 'w') as outfile:
            yaml.dump(data, outfile, default_flow_style=False)
    except (KeyboardInterrupt, SystemExit):
        raise


def update():
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        if plex_section.type != 'movie':
            continue

        if LIBRARY_IDS and int(plex_section.key) not in LIBRARY_IDS:
            print('ID: %s Name: %s - SKIPPED' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
            continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))
        plex_collections = plex_section.collection()
        lib_id = click.prompt('Please confirm library ID to be updated or type 0 to skip', type=str)
        if (lib_id != str(plex_section.key)):
            print('Invalid ID, skipping library.')
            continue

        for k, plex_collection in enumerate(plex_collections):
            print('\r\n> %s [%s/%s]' % (plex_collection.title, k + 1, len(plex_collections)))

            if 'titleSort' in plex_collection._data.attrib:
                if plex_collection._data.attrib['titleSort'].endswith('***'):
                    print('Skipping. (Skip marker found)')
                    continue
            
            update_poster(plex_collection, plex_section)
        
        global found_count
        global missing_count

        print('Found: '+str(found_count))
        print('Missing: '+str(missing_count))

        found_count = 0
        missing_count = 0
                


def list_libraries():
    plex = PlexServer(CONFIG['plex_url'], CONFIG['plex_token'])
    plex_sections = plex.library.sections()

    for plex_section in plex_sections:
        #if plex_section.type != 'movie':
        #    continue

        print('ID: %s Name: %s' % (str(plex_section.key).ljust(4, ' '), plex_section.title))

def update_poster(plex_collection, plex_section):
    poster_found = False
    global found_count
    global missing_count

    if check_poster(plex_collection, plex_section):
        found_count=found_count+1
        return

    print("Collection Poster Not Found!")
    missing_count=missing_count+1
    #check_for_default_poster(plex_collection)

def check_poster(plex_collection, plex_section):
    plex_collection_id = plex_collection.ratingKey
    file_path = 'imgs/'+str(plex_section.key)+'-'+plex_section.title+'/'+plex_collection.title
    poster_path = ''

    #print(file_path)
    if os.path.isfile(file_path + '.jpg'):
        poster_path = file_path + '.jpg'
    elif os.path.isfile(file_path + ' Collection.jpg'):
        poster_path = file_path + ' Collection.jpg'
    elif os.path.isfile(file_path + '.png'):
        poster_path = file_path + '.png'
    elif os.path.isfile(file_path + ' Collection.png'):
        poster_path = file_path + ' Collection.png'
    elif os.path.isfile(file_path + '.jpeg'):
        poster_path = file_path + '.jpeg'
    elif os.path.isfile(file_path + ' Collection.jpeg'):
        poster_path = file_path + ' Collection.jpeg'
    

    if poster_path != '':
        if DEBUG:
            print("Collection Poster Exists")
        key = get_sha1(poster_path)
        poster_exists = check_if_poster_is_uploaded(key, plex_collection_id)

        if poster_exists:
            print("Using Collection Poster")
            return True

        if DRY_RUN:
            print("Would Set Collection Poster: %s" % (poster_path))
            return True

        requests.post(CONFIG['plex_images_upload_url'] % (plex_collection_id, 'posters'),
                      data=open(poster_path, 'rb'), headers=CONFIG['headers'])
        print(" Collection Poster Set")
        return True


def check_if_poster_is_uploaded(key, plex_collection_id):
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, 'posters', ''))
    key_prefix = 'upload://posters/'
    for image in images.get('Metadata'):
        if image.get('selected'):
            if image.get('ratingKey') == key_prefix + key:
                return True
        if image.get('ratingKey') == key_prefix + key:
            if DRY_RUN:
                print("Would Change Selected Poster to: " + image.get('ratingKey'))
                return True

            requests.put(CONFIG['plex_images_url'] % (plex_collection_id, 'poster', image.get('ratingKey')),
                         data={}, headers=CONFIG['headers'])
            return True


def check_for_default_poster(plex_collection):
    plex_collection_id = plex_collection.ratingKey
    images = get_plex_data(CONFIG['plex_images_url'] % (plex_collection_id, 'posters', ''))
    first_non_default_image = ''

    for image in images.get('Metadata'):
        if image.get('selected') and image.get('ratingKey') != 'default://':
            return True
        if first_non_default_image == '' and image.get('ratingKey') != 'default://':
            first_non_default_image = image.get('ratingKey')

    if first_non_default_image != '':
        print('Default Plex Generated Poster Detected')

        if DRY_RUN:
            print("Would Change Selected Poster to: " + first_non_default_image)
            return True

        requests.put(CONFIG['plex_images_url'] % (plex_collection_id, 'poster', first_non_default_image),
                     data={}, headers=CONFIG['headers'])
        return True

  
def get_plex_data(url):
    r = requests.get(url, headers=CONFIG['headers'])
    return json.loads(r.text).get('MediaContainer')


def get_sha1(file_path):
    h = hashlib.sha1()

    with open(file_path, 'rb') as file:
        while True:
            # Reading is buffered, so we can read smaller chunks.
            chunk = file.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()


@click.group()
def cli():
    if not os.path.isfile(CONFIG_FILE):
        click.confirm('Configuration not found, would you like to set it up?', abort=True)
        setup()
        exit(0)
    pass


@cli.command('setup', help='Set Configuration Values')
def command_setup():
    setup()


@cli.command('run', help='Update Collection Posters',
             epilog="eg: plex_collections.py run posters --dry-run --library=5 --library=8")

@click.option('--debug', '-v', default=False, is_flag=True)
@click.option('--dry-run', '-d', default=False, is_flag=True)
@click.option('--force', '-f', default=False, is_flag=True, help='Overwrite existing data.')
@click.option('--library', default=False, multiple=True, type=int,
              help='Library ID to Update (Default all movie libraries)')
def run(debug, dry_run, force, library):

    init(debug, dry_run, force, library)
    print('\r\nUpdating Collection')
    update()


@cli.command('list', help='List all Libraries')
def list_all():
    init()
    print('\r\nLibraries:')
    list_libraries()

if __name__ == "__main__":
    cli()
