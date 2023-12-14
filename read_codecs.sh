#!/bin/bash

input=$1
directory=$(dirname $input)
if [[ -d $input ]]; then
    for fragment in $(find "$input" -name *.ts | sort)
    do
        ffprobe $fragment 2>&1 | grep -e Input -e Audio
    done
elif [[ -f $input ]]; then
    grep .ts $input | xargs -I {} sh -c "ffprobe $directory/{} 2>&1 | grep -e Input -e Audio"
fi
