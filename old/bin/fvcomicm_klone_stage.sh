#!/bin/bash
# Setup script for FVCOM-ICM runs on Klone. Copies all relevant input/control
# files from the working directory to a temporary directory.
# Updates the run copy of wqm_linkage.in to point to the given FVCOM result.

# First argument is the casename, needed for FVCOM-ICM v4
CASENAME="$1"

# Second argument is the scratch setup directory. We can't use mktemp for this
# because it needs to be the same on all nodes in the job
scratch_dir="$2"

# Third argument is the clustered FVCOM solution directory to use for the run
hydro_dir="$3"

# Fourth argument is the output directory
output_dir="$4"

die() {
    echo $@ 1>&2
    if [ -d $scratch_dir ]; then
        rm -rf $scratch_dir
    fi
    exit 1
}

cwd="`pwd`"

echo "SLURM_SUBMIT_DIR: ${SLURM_SUBMIT_DIR:=$cwd}"

mkdir -p $scratch_dir || die "Failed to create scratch directory $scratch_dir"
cp -Lr inputs wqm_con.npt $scratch_dir || die "Copying input files to $scratch_dir failed"
[ -f ${CASENAME}_run.dat ] && cp -L ${CASENAME}_run.dat $scratch_dir
# FIXME assumes all output files are going to be in "outputs". For v4 the
# right way is to read wqm_linkage.in's HIS_OUTDIR to see where the NetCDF
# files end up
ln -s "$output_dir" "$scratch_dir/outputs" || die "Symlinking $output_dir failed"

# Read a value from wqm_linkage.in. No longer used in this script
get_wqmlink_param() {
    if [ "$2" = str ]; then
        quote="'"
    else
        quote=''
    fi
    cut -f1 -d! wqm_linkage.in | awk -F= "/^ *$1 *=/ { gsub(/^[ \\t]*$quote|$quote[ \\t]*\$/, \"\", \$2); print \$2 }"
}

# Modify the scratch copy of wqm_linkage.in to use hydro_dir
sed 's%^\([^!] *[^!]hydro_dir *=\).*%\1'"'$hydro_dir/'"% wqm_linkage.in > "$scratch_dir/wqm_linkage.in" || die "Creating wqm_linkage.in failed"

exit 0

# vim: set shiftwidth=4 expandtab:
