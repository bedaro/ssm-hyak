#!/bin/bash
# Setup script for FVCOM runs on Klone. Copies all relevant input/control
# files from the working directory to a temporary directory.

# First argument is the casename
CASENAME="$1"

# Second argument is the scratch setup directory. We can't use mktemp for this
# because it needs to be the same on all nodes in the job
scratch_dir="$2"

# Third argument is the output directory
output_dir="$3"

die() {
    echo $@ 1>&2
    if [ -d $scratch_dir ]; then
        rm -rf $scratch_dir
    fi
    exit 1
}

mkdir -p $scratch_dir || die "Failed to create scratch directory $scratch_dir"

# Read a value from the run control file
get_run_param() {
    cut -f1 -d! ${CASENAME}_run.dat | awk -F= "/^ *$1 *=/ { gsub(/^[ \\t]*|[ \\t]*\$/, \"\", \$2); print \$2 }"
}

inpdir="`get_run_param INPDIR`"
outdir="`get_run_param OUTDIR`"
cp -Lr $inpdir ${CASENAME}_run.dat $scratch_dir || die "Copying input files to $scratch_dir failed"
ln -s "$output_dir" "$scratch_dir/$outdir"

# vim: set shiftwidth=4 expandtab:
