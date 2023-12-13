#!/usr/bin/env python3

import re
import shutil
import logging

logging.basicConfig(level=logging.DEBUG)

class Util:
    def regex_once(pattern, raw):
        match = re.search(pattern, raw)
        if match:
            return match.groups()[0]

    def regex_many(pattern, raw):
        match = re.search(pattern, raw)
        if match:
            return match

    def string_to_pathlib(path):
        if isinstance(path, str):
            path = pathlib.Path(path)
        return path

    def make_directory(path):
        # logging.debug(f'making: {path}')
        path = Util.string_to_pathlib(path)
        path.mkdir(parents=True, exist_ok=True)

    def delete_directory(path):
        path = Util.string_to_pathlib(path)
        if path.is_dir():
            shutil.rmtree(path)