#!/usr/bin/env python3

import sys
import pathlib
from Crypto.Cipher import AES
import ffmpegio
from util import Util

output = '.output'
output = pathlib.Path(output)
Util.delete_directory(output)
Util.make_directory(output)

manifest_path = sys.argv[1]
manifest = None
with open(manifest_path) as f:
    manifest = f.read()
parent_path = pathlib.Path(manifest_path).parent

#EXT-X-KEY:METHOD=AES-128,URI="level-00950400-0288p/K74052.key",IV=0x00000000000000000000000000012148,KEYFORMATVERSIONS="1"
PATTERNS = {}
PATTERNS['ENCRYPTION_METHOD'] = '(?:METHOD=)([0-9a-zA-Z-]+)'
PATTERNS['ENCRYPTION_IV'] = '(?:IV=0x)([0-9a-zA-Z]+)'
PATTERNS['ENCRYPTION_KEY_FORMAT_VERSION'] = '(?:KEYFORMATVERSIONS=")([0-9]+)(?:")'
PATTERNS['ENCRYPTION_KEY_PATH'] = '(?:URI=\")([0-9a-zA-Z-./]+)(?:")'

encryption_key = None
for line in manifest.splitlines():
    if line.startswith('#EXT-X-KEY:METHOD=NONE'):
        encryption_key = None
    elif line.startswith('#EXT-X-KEY:METHOD=AES-128'):
        encryption_method = Util.regex_once(PATTERNS['ENCRYPTION_METHOD'], line)
        encryption_iv = Util.regex_once(PATTERNS['ENCRYPTION_IV'], line)
        encryption_iv = bytes.fromhex(encryption_iv)
        encryption_key_version = Util.regex_once(PATTERNS['ENCRYPTION_KEY_FORMAT_VERSION'], line)
        encryption_key_path = Util.regex_once(PATTERNS['ENCRYPTION_KEY_PATH'], line)
        encryption_key_path = parent_path.joinpath(encryption_key_path)

        encryption_key = None
        with open(encryption_key_path, 'rb') as f:
            encryption_key = f.read()

        # print(encryption_method)
        # print(encryption_iv)
        # print(encryption_key_version)
        # print(encryption_key_path)
    elif line.endswith('.ts'):
        filepath = line
        encrypted_filepath = parent_path.joinpath(filepath)
        decrypted_filepath = output.joinpath(filepath)

        encrypted_data = None
        with open(encrypted_filepath, 'rb') as f:
            encrypted_data = f.read()

        if encryption_key is None:
            decrypted_data = encrypted_data
        else:
            # https://stackoverflow.com/a/67627186
            cipher = AES.new(encryption_key, AES.MODE_CBC, IV=encryption_iv)
            decrypted_data = cipher.decrypt(encrypted_data)

        Util.make_directory(decrypted_filepath.parent)
        with open(decrypted_filepath, 'wb') as f:
            f.write(decrypted_data)


