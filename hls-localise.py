#!/usr/bin/env python3

import os
import shutil

import requests
import logging
from argparse import ArgumentParser
import datetime
import re
import json
import pathlib
from urllib.parse import urlparse
import concurrent.futures
from time import sleep


class Matcher:
    def find_once(pattern, raw):
        match = re.search(pattern, raw)
        if match:
            return match.groups()[0]

    def find_many(pattern, raw):
        match = re.search(pattern, raw)
        if match:
            return match

    def get_datetime_stamp():
        return datetime.datetime.now().strftime("%Y%m%dT%H%M%S")

    def make_directory_recursive(directory_path):
        pathlib.Path(directory_path).mkdir(parents=True, exist_ok=True)

    def delete_path_recursive(filepath):
        if filepath is None:
            filepath = pathlib.PurePath(urlparse(url).path).name
        filepath = pathlib.PurePath(filepath)
        filename = filepath.name
        directory_path = filepath.parent

        if pathlib.Path(filepath).is_file():
            pathlib.Path(filepath).unlink()
        if pathlib.Path(directory_path).is_dir():
            shutil.rmtree(directory_path)


class Downloader:
    def __init__(self, url, filepath=None, delete_existing=False):
        self.url = url
        if filepath is None:
            self.filepath = pathlib.PurePath(urlparse(self.url).path).name
        self.filepath = pathlib.PurePath(filepath)
        self.filename = self.filepath.name
        self.directory_path = self.filepath.parent

        logging.debug(f'filepath {self.filepath}')
        logging.debug(f'directory_path {self.directory_path}')

        self.response = None
        self.delete_existing(delete_existing)
        self.download()

    def delete_existing(self, delete_existing):
        if not delete_existing:
            return

        if pathlib.Path(self.filepath).is_file():
            pathlib.Path(self.filepath).unlink()
        if pathlib.Path(self.directory_path).is_dir():
            shutil.rmtree(self.directory_path)

    def make_directory(self):
        pathlib.Path(self.directory_path).mkdir(parents=True, exist_ok=True)

    def download(self):
        if pathlib.Path(self.filepath).exists():
            logging.debug(f'already downloaded - {self.filepath}')
            return

        logging.info(f'downloading - {self.filepath} - {self.url}')
        r = requests.get(self.url)
        if r.ok:
            self.response = r
            logging.info(f'saving - {self.filepath}')
            self.make_directory()
            with open(self.filepath, 'wb') as f:
                f.write(r.content)
        else:
            logging.error(f'download failed: {self.filepath} - {self.url}')

    def text(self):
        return self.response.text

    def content(self):
        return self.response.content


class Uptime:
    def __init__(self):
        self.uptime = 0

    def find_and_update(self, raw):
        pattern = "(^[0-9]*:[0-9]*:[0-9]*.[0-9]*)"
        self.uptime = self.find(pattern, raw)

    def find(self, pattern, raw):
        match = re.search(pattern, raw)
        if match:
            return match.groups()[0]
        return self.uptime


class HlsLevel:
    PATTERNS = {}
    PATTERNS['BANDWIDTH'] = "(?:BANDWIDTH=)([0-9]+)"
    PATTERNS['CODECS'] = "(?:CODECS=\")([0-9a-zA-Z,.]+)"
    PATTERNS['RESOLUTION'] = "(?:RESOLUTION=)([0-9]+)(?:x)([0-9]+)"
    PATTERNS['HDCP_LEVEL'] = "(?:HDCP-LEVEL=)([0-9a-zA-Z.]+)"
    PATTERNS['SUBTITLES'] = "(?:SUBTITLES=\")([0-9a-zA-Z]+)"
    PATTERNS['EXT_X_MEDIA_SEQUENCE'] = "(?:#EXT-X-MEDIA-SEQUENCE:)([0-9]+)"

    def __init__(self, parent_directory, raw, url, duration):
        self.url = url
        self.duration = duration
        self.precached_level = None

        self.bandwidth = Matcher.find_once(self.PATTERNS['BANDWIDTH'], raw)
        self.codecs = Matcher.find_once(self.PATTERNS['CODECS'], raw)
        resolution = re.search(self.PATTERNS['RESOLUTION'], raw)
        self.width = resolution.groups()[0]
        self.height = resolution.groups()[1]
        self.hdcp_required = Matcher.find_once(self.PATTERNS['HDCP_LEVEL'], raw)
        self.subtitles = Matcher.find_once(self.PATTERNS['SUBTITLES'], raw)

        # other variables to be intialised
        self.manifest_start_sequence_counter = 0
        self.manifest_end_sequence_counter = 0
        self.fragment_sequence_counter = 0

        # local paths
        self.manifest_filename = f'level-{int(self.bandwidth):08}-{int(self.height):04}p.m3u8'
        self.parent_directory = parent_directory
        self.directory = os.path.join(parent_directory, self.manifest_filename.replace('.m3u8', ''))
        self.manifest_path = os.path.join(self.parent_directory, self.manifest_filename)
        self.localised_manifest_path = os.path.join(self.parent_directory, f'localised-{self.manifest_filename}')

    def start_download(self):
        interval = 10
        for loop in range(self.duration):
            contents = Downloader(self.url,
                                  self.manifest_path.replace('.m3u8', f'-{Matcher.get_datetime_stamp()}.m3u8')).text()
            self.parse_and_download(contents)

            if loop + 1 == self.duration:
                logging.debug(f'{self.bandwidth} - {loop + 1}/{self.duration} finished')
            elif self.duration > 1:
                logging.debug(f'{self.bandwidth} - {loop + 1}/{self.duration} begin sleeping for {interval}')
                sleep(interval)

    def find_startswiths(self, patterns, text):
        for pattern in patterns:
            if text.startswith(pattern):
                return True

    HLS_HEADER_INIT_PATTERNS = ["#EXTM3U", "#EXT-X-TARGETDURATION", "#EXT-X-VERSION", "#EXT-X-DISCONTINUITY-SEQUENCE",
                           "#EXT-X-MEDIA-SEQUENCE", "#EXT-X-PROGRAM-DATE-TIME"]
    HLS_HEADER_ONGOING_PATTERNS = ["#EXT-X-DISCONTINUITY", "#EXT-X-PROGRAM-DATE-TIME", '#EXTINF']
    HLS_VIDEO_PATTERNS = ['https://', '#EXT-X-KEY', '#EXTINF']
    HLS_VIDEO_HEADER_PATTERNS = ['#EXT-X-KEY', '#EXTINF']

    def parse_and_download(self, contents):
        contents_localised = []
        self.manifest_start_sequence_counter = self.get_media_sequence(contents)
        self.fragment_sequence_counter = self.manifest_start_sequence_counter - 1
        content_previous = None
        for line_number, content in enumerate(contents.splitlines()):
            if self.manifest_start_sequence_counter == 0 and \
                    self.find_startswiths(self.HLS_HEADER_INIT_PATTERNS, content) and \
                    line_number < 6:
                contents_localised.append(content)
                # contents_localised.append(f'LN164: {self.manifest_start_sequence_counter}' + content)

            if self.find_startswiths(self.HLS_VIDEO_PATTERNS, content):
                # content.startswith('#EXT-X-KEY'): AES Key URL
                # content.startswith('#EXTINF'): Media Fragment URL coming next
                # content.startswith('https://'): Media Fragment URL
                if self.find_startswiths(self.HLS_VIDEO_HEADER_PATTERNS, content) \
                        and not content_previous.startswith('#EXTINF') \
                        and not content_previous.startswith('#EXT-X-KEY'):
                    self.fragment_sequence_counter += 1
                    if self.fragment_sequence_counter > self.manifest_end_sequence_counter:
                        contents_localised.append('')
                        contents_localised.append(f'#media sequence counter: {self.fragment_sequence_counter}/{self.manifest_end_sequence_counter}')
                        # contents_localised.append(f'#media sequence counter: {self.fragment_sequence_counter}/{self.manifest_end_sequence_counter} - prev: {content_previous} curr: {content}')

            if self.fragment_sequence_counter >= self.manifest_end_sequence_counter:
                if self.find_startswiths(self.HLS_HEADER_ONGOING_PATTERNS, content):
                    contents_localised.append(content)
                    # contents_localised.append('LN167: ' + content)

            if self.manifest_start_sequence_counter == 0 or \
                    self.fragment_sequence_counter > self.manifest_end_sequence_counter:
                if content.startswith('https://'):
                    fragment_path = urlparse(content).path[1:]
                    fragment_path = os.path.join(self.directory, fragment_path)
                    Downloader(content, filepath=fragment_path)
                    contents_localised.append(fragment_path)
                elif content == '#EXT-X-KEY:METHOD=NONE':
                    contents_localised.append(content)
                    # contents_localised.append('LN191: ' + content)
                elif content.startswith('#EXT-X-KEY') and 'URI="https://' in content:
                    pattern = 'URI="(https:.+)",'
                    url = Matcher.find_once(pattern, content)
                    key_path = pathlib.Path(urlparse(url).path).name
                    key_path = os.path.join(self.directory, key_path)
                    Downloader(url, filepath=key_path)
                    contents_localised.append(content.replace(url, key_path))
            content_previous = content
        contents_localised = [content.replace(self.parent_directory + '/', '') for content in contents_localised]
        with open(self.localised_manifest_path, 'a') as f:
            f.write('\n'.join(contents_localised) + '\n')
        self.manifest_end_sequence_counter = self.fragment_sequence_counter

    def get_media_sequence(self, raw):
        return int(Matcher.find_once(self.PATTERNS['EXT_X_MEDIA_SEQUENCE'], raw))

    def start_precached_download(self):
        contents = None
        contents_localised = []
        with open(self.precached_level, 'r') as f:
            contents = f.read()

        for content in contents.splitlines():
            if content.startswith('https://'):
                fragment_path = urlparse(content).path[1:]
                fragment_path = os.path.join(self.directory, fragment_path)
                Downloader(content, filepath=fragment_path)
                contents_localised.append(fragment_path)
            elif content == '#EXT-X-KEY:METHOD=NONE':
                contents_localised.append(content)
                # contents_localised.append('LN225: ' + content)
            elif content.startswith('#EXT-X-KEY') and 'URI="https://' in content:
                pattern = 'URI="(https:.+)",'
                url = Matcher.find_once(pattern, content)
                key_path = pathlib.Path(urlparse(url).path).name
                key_path = os.path.join(self.directory, key_path)
                Downloader(url, filepath=key_path)
                contents_localised.append(content.replace(url, key_path))
            else:
                contents_localised.append(content)
        contents_localised = [content.replace(self.parent_directory + '/', '') for content in contents_localised]
        with open(self.localised_manifest_path, 'a') as f:
            f.write('\n'.join(contents_localised) + '\n')


class HlsRoot:
    def __init__(self, args):
        self.contents = None
        self.levels = []

        self.url = args.urlmanifest
        self.duration = args.duration
        self.multithreading = args.multithreading

        self.directory = 'hls-localise-download'
        self.manifest_name = 'root-manifest.m3u8'
        self.manifest_path = os.path.join(self.directory, self.manifest_name)
        self.localised_manifest_name = f'localised-{self.manifest_name}'
        self.localised_manifest_path = os.path.join(self.directory, self.localised_manifest_name)

        self.download()

    def download(self):
        self.contents = Downloader(self.url, filepath=self.manifest_path, delete_existing=True).text()
        # logging.debug(self.root_url)
        # logging.debug(self.root_data)

        # self.root_data = '#EXT-X-STREAM-INF:BANDWIDTH=1720400,CODECS="avc1.640028,mp4a.40.5",RESOLUTION=896x504,HDCP-LEVEL=NONE,SUBTITLES="subs1"'
        pattern = "(?P<metadata>^#EXT-X-STREAM-INF.+)\n(?P<url>https://.+)"
        level_matches = re.findall(pattern, self.contents, re.MULTILINE)

        self.levels = [HlsLevel(self.directory, level[0], level[1], self.duration) for level in level_matches]

        localised_contents = []
        for content in self.contents.splitlines():
            localised = content
            if content.startswith('https://'):
                localised = [level.localised_manifest_path for level in self.levels if level.url == content][0]
                localised = localised.replace(self.directory + '/', '')
            localised_contents.append(localised)
        with open(self.localised_manifest_path, 'w') as f:
            f.write('\n'.join(localised_contents))

        if self.multithreading:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(self.levels))
            [pool.submit(level.start_download) for level in self.levels]
            pool.shutdown(wait=True)
        else:
            # self.levels[0].start_download()
            self.get_lowest_level().start_download()

            # sequential all
            # [level.start_download() for level in self.levels]

    def get_lowest_level(self):
        lowest_level = self.levels[0]
        for level in self.levels:
            if level.bandwidth > lowest_level.bandwidth:
                lowest_level = level
        return lowest_level


def main(args):
    logging.debug(args)
    logstr = None

    if args.urlfile:
        if 'http://' in args.urlfile or 'https://' in args.urlfile:
            timestamp = datetime.datetime.now().isoformat()
            logfile = f'wpe-{timestamp}.log'
            logfile = os.path.join('logs', logfile)
            logstr = Downloader(args.urlfile, filepath=logfile).text()
        else:
            logging.critical(f'cannot find urlfile: {args.urlfile}')
            exit(1)
    elif args.localfile:
        if os.path.isfile(args.localfile):
            with open(args.localfile, 'r') as f:
                logstr = f.read()
        else:
            logging.critical(f'cannot find localfile: {args.localfile}')
            exit(1)
    elif args.urlmanifest:
        HlsRoot(args)
        exit()
    elif args.locallevelmanifest:
        raw = '#EXT-X-STREAM-INF:BANDWIDTH=1720400,CODECS="avc1.640028,mp4a.40.5",RESOLUTION=896x504,HDCP-LEVEL=NONE,SUBTITLES="subs1"'
        directory = args.directory
        level = HlsLevel(directory, raw, None, None)
        level.precached_level = args.locallevelmanifest
        level.start_precached_download()
        exit()
    else:
        logging.error(f'no input logfile was supplied')

    uptime = Uptime()
    for line in logstr.splitlines():
        uptime.find_and_update(line)
        if 'setPlaybackInformation' in line:
            # track = VideoTrack(line)
            # print(track.to_string())
            pattern = "({.*})"
            playback_info = json.loads(Matcher.find_once(pattern, line))
            url = playback_info['url']
            HlsRoot(url, args.time)
    print(f'uptime: {uptime.uptime}')


logging.basicConfig(level=logging.INFO)
# logging.getLogger().setLevel(logging.DEBUG)

parser = ArgumentParser()
parser.description = 'This script filters WPE logs for video and audio packets passed into MSE. \
                      Support: ct@foxtel.com.au or kelvin.wong@foxtel.com.au'
parser.epilog = 'Example: ./%(prog)s -av -u http://192.168.1.105:3211/device/wpe/wpe_exe_log.txt'
parser.version = '%(prog)s 20231107'
parser.add_argument("-d", "--debug",
                    help="Enable debug",
                    action="store_const",
                    dest='loglevel',
                    const=logging.DEBUG,
                    default=logging.INFO)
parser.add_argument('-u', "--urlfile",
                    help='url to logfile, eg http://192.168.1.105:3211/device/wpe/wpe_exe_log.txt',
                    nargs='?')
parser.add_argument('-m', "--urlmanifest",
                    help='url to manifest, eg http://192.168.1.105:3211/device/wpe/wpe_exe_log.txt',
                    nargs='?')
parser.add_argument('--multithreading',
                    help='enable multithreading to download all hls levels',
                    action='store_true')
parser.add_argument('-l', "--localfile",
                    help='local path to logfile, eg ./wpe_exe_log.txt',
                    nargs='?')
parser.add_argument("--locallevelmanifest",
                    help='local path to level manifest, eg ./720p.m3u8',
                    nargs='?')
parser.add_argument("--directory",
                    help='output directory to save the download',
                    nargs='?')
parser.add_argument('-t', "--duration",
                    help='time in seconds to download',
                    default=1,
                    type=int,
                    nargs='?')
parser.add_argument('--version', action='version')

args = parser.parse_args()
logging.getLogger().setLevel(args.loglevel)
logging.getLogger('requests').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.INFO)
logging.getLogger('chardet').setLevel(logging.INFO)
main(args)
