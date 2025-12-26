#!/bin/bash
d=$1
conandata=${d}conandata.yml            
if [[ -f "$conandata" ]]
then
    res=$(uv run $(dirname "$0")/lint_conandata.py ${conandata})
    if [[ -n "$res" ]]
    then
        echo "## [${d}](https://github.com/ericLemanissier/cocorepo/tree/HEAD/recipes/${conandata})"
        echo "${res}"
        echo ""
    fi
fi