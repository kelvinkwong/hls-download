#!/bin/bash

# openssl aes-128-cbc -d -in encrypted_content.ts -out decrypted_content.ts -nosalt -iv 0000000000000000000000000000007d -K 3ac42a2abb52311f34ad1fd373711ea1

[[ -z $1 ]] && echo "$0 encrypted_fragment.ts aes.key [iv]" && exit

Encrypted="$1"
Decrypted="${Encrypted}_decrypted.ts"
Key="$(cat $2 | xxd -p)"
Iv="${3:-00000000000000000000000000000000}"

command="openssl aes-128-cbc -d -in $Encrypted -out $Decrypted -nosalt -iv $Iv -K $Key"
echo $command
eval $command
