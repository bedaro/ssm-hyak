#!/bin/bash

## job name 
#SBATCH --job-name=ssm_w2014

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
#SBATCH --time=19:00:00
## Memory per node
#SBATCH --mem=60G

export PATH="/gscratch/brett/ssm/bin:$PATH"

. batch.rc
if [ $? -gt 0 ]; then
    echo "batch.rc file not found, no configuration!"
    exit 1
fi

echo "NTASKS: $SLURM_NTASKS"

# Check the control file. If we're performing a cold start, modify the
# MPI_BIN accordingly to change the binary version
icifile="`grep -1 '^ICI FILE' wqm_con.npt | tail -1 | xargs`"
if echo "$icifile" | grep -q coldstart; then
    mpi_bin=${mpi_bin/%Input/S}
fi

echo "MPI_BIN: $mpi_bin"

module purge
for m in $modules; do
    module load $m
done
module list

# Stage the model run to node-local storage
echo ==== Fetching hydro solution ====
hydro_dir="`time fvcomicm_klone_fetchhydro.sh`"
if [ $? -gt 0 ]; then
    exit $?
fi

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
    output_dir="${SCRUBDIR}/$USER/icm_outputs/$SLURM_JOB_ID"
    ssm_register_job.sh
else
    output_dir="$save_root/$run_tail/outputs"
fi
mkdir -p "$output_dir" || exit 1
rm -rf outputs
[ ! -d outputs ] && ln -s "$output_dir" outputs

echo ==== Staging inputs to nodes ====
scratch_dir=`mktemp -p ${scratch_root:-/scr} -d`
if [ $? -gt 0 -o ! -d "$scratch_dir" ]; then
    echo Failed to create temporary directory
    exit 1
fi
$SRUN fvcomicm_klone_stage.sh $casename "$scratch_dir" "$hydro_dir" "$output_dir"
if [ $? -gt 0 ]; then
    exit $?
fi
cd "$scratch_dir"

echo ==== Starting the run ====

time mpirun -np $SLURM_NTASKS $mpi_bin $casename

cd "$SLURM_SUBMIT_DIR"
rm -r $scratch_dir

echo Job complete

# vim: set shiftwidth=4 expandtab:
