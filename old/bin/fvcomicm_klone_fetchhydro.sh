#!/bin/bash
# Fetch a hydrodynamic run (possibly based on a remote machine) and output
# where it was found/saved to.
# The only argument taken is an optional keyword "quick" which can be
# specified to limit transfer to only the first NetCDF file. As suggested,
# this speeds up operations for testing purposes.

hyd_results_base=${HYD_RESULTS:-${SCRUBDIR:-/gscratch/scrubbed}/$USER/hyd_results}
shopt -s extglob

die() {
    echo $@ 1>&2
    exit 1
}

# Read a value from wqm_linkage.in
get_wqmlink_param() {
    if [ "$2" = str ]; then
        quote="'"
    else
        quote=''
    fi
    cut -f1 -d! wqm_linkage.in | awk -F= "/^ *$1 *=/ { gsub(/^[ \\t]*$quote|$quote[ \\t]*\$/, \"\", \$2); print \$2 }"
}

# Read the hydro_dir from wqm_linkage.in so we can fetch the contents
hyd_result_src=`get_wqmlink_param hydro_dir str`

# analyze if this is a local path; if so just output the path and exit
is_remote_path() {
    echo $1 | egrep -q '^[^/]+:.*'
    return $?
}
if is_remote_path "$hyd_result_src"; then
    hyd_result_dest="$hyd_results_base/$(echo ${hyd_result_src%%/netcdf?(/)} | md5sum | awk '{ print $1 }')"
    echo Copying hydro solution from "$hyd_result_src" to "$hyd_result_dest/netcdf" 1>&2
    mkdir -p "$hyd_result_dest"
    if [ "$1" = quick ]; then
        rsync_opts=("--filter=+ netcdf/*_00001.nc" "--filter=- *")
    else
        rsync_opts=("--filter=+ netcdf/*.nc" "--filter=- *")
    fi
    time rsync -rtlz --filter='+ netcdf/' "${rsync_opts[@]}" "${hyd_result_src%%/netcdf?(/)}/netcdf" "$hyd_result_dest"
    [ $? -gt 0 -o ! -d "$hyd_result_dest/netcdf" ] && die "Copying the hydro solution failed"
    echo "$hyd_result_dest/netcdf"
else
    echo "`readlink -f $hyd_result_src`"
fi

# vim: set shiftwidth=4 expandtab:
