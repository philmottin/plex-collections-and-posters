#!/usr/bin/env python
import re, sys, getpass
import plexapi.utils
from retry import retry
from plexapi.server import PlexServer, CONFIG
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import BadRequest
import yaml
import glob, os, argparse

## Edit ##
PLEX_URL = os.getenv('PLEX_URL')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')

DEBUG = os.getenv('DEBUG')
RESET_COLOR = '\033[0m'  # reset to default text color
RED         = '\033[31m' # set text color to red
GREEN       = '\033[32m' # set text color to green
BLUE        = '\033[34m' # set text color to blue

try:
    PLEX_URL = CONFIG.data['auth'].get('server_baseurl', PLEX_URL)
    PLEX_TOKEN = CONFIG.data['auth'].get('server_token', PLEX_TOKEN)
except:
    print("Failed loading in config file.")

class Plex():
    def __init__(self, library=""):
        if PLEX_URL and PLEX_TOKEN:
            self.server = PlexServer(PLEX_URL, PLEX_TOKEN)
        else:
            self.account = self.get_account()
            self.server = self.get_account_server(self.account)

        if library:
            try:
                self.section = self.server.library.section(library)
            except plexapi.exceptions.NotFound:
                self.section = self.get_server_section(self.server)
        else:
            self.section = self.get_server_section(self.server)

        self.media = self.get_flat_media(self.section)

    @retry(BadRequest)
    def get_account(self):
        username = input("Plex Username: ")
        #password = getpass.getpass()
        password = input("Plex Password: ")

        return MyPlexAccount(username, password)

    def get_account_server(self, account):
        servers = [ _ for _ in account.resources() if _.product == 'Plex Media Server' ]
        if not servers:
            print('No available servers.')
            sys.exit()

        return plexapi.utils.choose('Select server index', servers, 'name').connect()

    def get_server_section(self, server):
        sections = [ _ for _ in server.library.sections() if _.type in {'movie'} ]
        if not sections:
            print('No available sections.')
            sys.exit()

        return plexapi.utils.choose('Select section index', sections, 'title')

    def get_flat_media(self, section):
        # Movie sections are already flat
        if section.type == 'movie':
            return self.section.all()
        else:
            episodes = []
            for show in self.section.all():
                episodes += show.episodes()
            return episodes

def process_movies(movies, medium, collection):
    matches = []
    for movie in movies:
        if isinstance(movie, list):
            process_movies(movie, medium, collection)
        else:
            year_regex = None
            for match in re.findall(r"\{\{((?:\s?\d+\s?\|?)+)\}\}", movie):
                year_regex = match.strip()
                movie = re.sub(r"\s+\{\{((\s?\d+\s?\|?)+)\}\}", "", movie)

            regex = re.compile(movie, re.IGNORECASE)
            if re.search(regex, medium.title):
                if year_regex and re.search(year_regex, str(medium.year)):
                    print("Adding" + RED, medium.title, RESET_COLOR + "to collection" + BLUE, collection, RESET_COLOR)
                    matches.append(medium)
                elif year_regex is None:
                    print("Adding" + RED, medium.title, RESET_COLOR + "to collection" + BLUE, collection, RESET_COLOR)
                    matches.append(medium)

    if matches:
        for movie in matches:
            movie.addCollection(collection)

def read_collection(filename, collections):
    if ((os.path.isfile(filename) > 0) and (os.path.getsize(filename) > 0)):
        with (open(filename, "r")) as stream:
            collections.update(yaml.load(stream, Loader=yaml.SafeLoader))
            print(GREEN + 'Reading ' + filename + '...' + RESET_COLOR)
            if DEBUG:
                for k, v in collections.items():
                    print(BLUE, k, "->", v, RESET_COLOR)
                print(RED, collections, RESET_COLOR)
    else:
        print()
        print(RED + filename + BLUE, 'is missing or empty. Skipping...' + RESET_COLOR)
        print()

def main():
    parser = argparse.ArgumentParser(description="Automatically create Plex collections")
    parser.add_argument("-l", "--library", help="choose LIBRARY from CLI")
    parser.add_argument("collection", nargs="*", help="Collection YAML files to process")
    args = parser.parse_args()

    if args.library:
        plex = Plex(args.library)
    else:
        plex = Plex()

    print()
    collections = {}        # create empty dictionary

    if args.collection:
        for i in range(len(args.collection)):
            read_collection(args.collection[i], collections)
    else:
        read_collection('collections.yml', collections)
        custom_collections = glob.glob('collections.d/*.yml')
        for custom_collection in custom_collections:
            read_collection(custom_collection, collections)

    print()
    # keyword_matches = []  # unused list?

    for medium in plex.media:
        for collection, movies in collections.items():
            process_movies(movies, medium, collection)
    
    #print(collections)

if __name__ == "__main__":
    main()
