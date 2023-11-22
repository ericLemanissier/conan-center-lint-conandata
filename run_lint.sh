#!/bin/bash
d=$1
conandata=${d}conandata.yml            
if [[ ! -f "$conandata" ]]
then
    continue
fi
res=$(python3 $(dirname "$0")/lint_conandata.py ${conandata})
if [[ -n "$res" ]]
then
    echo "## [${d}](https://github.com/conan-io/conan-center-index/tree/master/recipes/${conandata})"
    echo "${res}"
    echo ""
fi