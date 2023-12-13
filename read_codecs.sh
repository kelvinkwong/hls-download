#!/bin/bash

input=$1
for fragment in $(find "$input" -name *.ts)
do
    ffprobe $fragment 2>&1 | grep -e Input -e Audio
done