#!/bin/bash

## job name 
#SBATCH --job-name=ssm_h2014

#SBATCH --mail-type=BEGIN
#SBATCH --mail-type=END
#SBATCH --mail-type=FAIL

#SBATCH --account=brett
#SBATCH --partition=compute
## Resources
## Nodes
#SBATCH --nodes=1
## Tasks per node
#SBATCH --ntasks-per-node=40
## Walltime (hh:mm:ss)
#SBATCH --time=14:00:00
## Memory per node
#SBATCH --mem=20G

# Which build?
module purge
module load intel/oneAPI/2021.1.1

export PATH="/gscratch/brett/ssm/bin:$PATH"

. batch.rc
if [ $? -gt 0 ]; then
    echo "batch.rc file not found, no configuration!"
    exit 1
fi

echo "NTASKS: $SLURM_NTASKS"

echo "MPI_BIN: $mpi_bin"

# Set the default run and save locations
# run_root is the absolute base path where model setups are kept
if [ -z "$run_root" ]; then
    run_root="$SLURM_SUBMIT_DIR"
fi
# save_root is the (possibly remote) path to where model setups/outputs are saved
if [ -z "$save_root" ]; then
    save_root="$run_root"
fi
if [ -z "$SCRUBDIR" ]; then
    SCRUBDIR=/gscratch/scrubbed
fi
run_tail="${SLURM_SUBMIT_DIR##$run_root/}"
is_remote_path() {
    echo $1 | egrep -q '^[^/]+:.*'
    return $?
}
if is_remote_path "$save_root"; then
    hyd_results_base=${SCRUBDIR}/$USER/hyd_results
    copy_dest="$save_root/$run_tail"
    output_dir="$hyd_results_base/$(echo "$copy_dest" | md5sum | awk '{ print $1 }')"
    ssm_register_job.sh
else
    output_dir="$save_root/$run_tail/OUTPUT"
fi
mkdir -p "$output_dir" || exit 1
rm -rf OUTPUT
[ ! -d OUTPUT ] && ln -s "$output_dir" OUTPUT

# Stage the model run to node-local storage
echo ==== Staging inputs to nodes ====
scratch_dir=`mktemp -p ${scratch_root:-/scr} -d`
if [ $? -gt 0 -o ! -d "$scratch_dir" ]; then
    echo Failed to create temporary directory
    exit 1
fi
fvcom_klone_stage.sh $casename "$scratch_dir" "$output_dir"
cd "$scratch_dir"

echo ==== Starting the run ====

time mpirun -np $SLURM_NTASKS $mpi_bin $casename

mv re_* "$SLURM_SUBMIT_DIR"
cd "$SLURM_SUBMIT_DIR"
rm -r $scratch_dir

echo Job complete

# vim: set shiftwidth=4 expandtab:
