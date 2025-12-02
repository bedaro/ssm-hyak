#!/bin/bash
# Test cases for fvcomicm_klone_fetchhydro.sh

gen_wqmlinkage() {
    echo "hydro_dir='$1'" > wqm_linkage.in
}

check_result() {
    check_file=${2:-ssm_00002.nc}
    if [ ! -d "$1" ]; then
        echo "Result $1 did not get copied at all"
        return 1
    fi
    if [ -d "$1/netcdf" ]; then
        echo "Result $1 got copied to a netcdf subdirectory"
        ls -R "$1"
        return 1
    fi
    if [ ! -f "$1/$check_file" ]; then
        echo "Cannot find test files in $1"
        ls -R "$1"
        return 1
    fi
    return 0
}

cleanup() {
    # Clean up
    if [ ${tempdir_local:0:4} = /tmp ]; then
        rm -r $tempdir_local
    fi
    if [ ${tempdir_ondra:0:4} = /tmp ]; then
        ssh ondra.mooo.com rm -r $tempdir_ondra
    fi
}

tempdir_ondra=`ssh ondra.mooo.com 'mktemp -d'`
tempdir_local=`mktemp -d`

mkdir -p $tempdir_local/stage/netcdf
touch $tempdir_local/stage/netcdf/{ssm_00001.nc,ssm_00002.nc}
mkdir $tempdir_local/model

export HYD_RESULTS=$tempdir_local/cache

#ls $tempdir_local/netcdf

scp -qr $tempdir_local/stage/* ondra.mooo.com:$tempdir_ondra/
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi

cd $tempdir_local/model

# Case 1: no NetCDF extension
echo "==== CASE 1 ===="
gen_wqmlinkage ondra.mooo.com:$tempdir_ondra
result1=`fvcomicm_klone_fetchhydro.sh`
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi
if check_result "$result1"; then
    echo PASS
fi

echo "==== CASE 1.1 DIRECT CACHE REF ===="
gen_wqmlinkage "$result1"
result11=`fvcomicm_klone_fetchhydro.sh`
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi
if check_result "$result11"; then
    echo PASS
fi
rm -r $HYD_RESULTS/*

# Case 2: NetCDF subdirectory specified
echo "==== CASE 2 NETCDF INCLUDED ===="
gen_wqmlinkage ondra.mooo.com:$tempdir_ondra/netcdf
result2=`fvcomicm_klone_fetchhydro.sh`
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi
if check_result "$result2"; then
    if [ "$result1" != "$result2" ]; then
        echo "Result is not the same path as the first"
    else
        echo PASS
    fi
fi
rm -r $HYD_RESULTS/*

# Case 3: NetCDF subdirectory specified
echo "==== CASE 3 NETCDF/ INCLUDED ===="
gen_wqmlinkage ondra.mooo.com:$tempdir_ondra/netcdf/
result3=`fvcomicm_klone_fetchhydro.sh`
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi
if check_result "$result3"; then
    if [ "$result1" != "$result3" ]; then
        echo "Result is not the same path as the first"
    else
        echo PASS
    fi
fi
rm -r $HYD_RESULTS/*

echo "==== CASE 4 QUICK ===="
gen_wqmlinkage ondra.mooo.com:$tempdir_ondra
result4=`fvcomicm_klone_fetchhydro.sh quick`
if [ $? -gt 0 ]; then
    cleanup
    exit 1
fi
if check_result "$result4" ssm_00001.nc; then
    echo PASS
fi

# vim: set shiftwidth=4 expandtab:
