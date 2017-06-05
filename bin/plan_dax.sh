#!/bin/bash

brief() {
    script=`basename $0`
    echo "$script: $*" 1>&2
    echo "Try '$script -h' for more information."
    exit 1
}

help() {
    script=`basename $0`
    echo "Usage: $script [OPTION] DAXFILE"
    echo "Plan workflow stored in DAXFILE."
    echo
    echo "Following options are supported:"
    echo "  -c  path to site catalog"
    echo "  -d  submit directory"
    echo "  -o  output directory"
    echo "  -s  site to use (must be defined in selected site catalog)"
    echo "  -t  path to transformation catalog"
    exit 0
}

if [ $# -lt 1 ]; then
    brief "missing file operand"
fi

DIR=$(cd $(dirname $0) && pwd)
output="$DIR/output"
submit="$DIR/submit"
scfile="sites.xml"
site="lsstvc"
tcfile="tc.txt"
while [ $# -gt 1 ]; do
    case "$1" in
        -c) scfile=$2 ; shift;;
        -d) submit=$2 ; shift;;
        -h) help ;;
        -o) ouput=$2 ; shift;;
        -s) site=$2 ; shift;;
        -t) tcfile=$2; shift;;
        -*) brief "unknown option $1";;
    esac
    shift
done

daxfile=$1

# This command tells Pegasus to plan the workflow contained in 
# dax file passed as an argument. The planned workflow will be stored
# in the "submit" directory.
echo "Planning workflow from '$daxfile' on $site with $tcfile."
pegasus-plan \
    -Dpegasus.transfer.links=true \
    -Dpegasus.catalog.site.file=$scfile \
    -Dpegasus.catalog.transformation.file=$tcfile \
    -Dpegasus.data.configuration=sharedfs \
    --sites $site \
    --output-dir $output \
    --dir $submit \
    --dax $daxfile \
    --submit 
