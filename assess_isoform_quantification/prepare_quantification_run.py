#!/usr/bin/python

"""Usage:
    prepare_quantification_run [--log-level=<log-level>] --method <quant-method> [--run-directory <run-directory>] <transcript-gtf-file> <genome-dir> <bowtie-index>

-h --help                           Show this message.
-v --version                        Show version.
--log-level=<log-level>             Set logging level (one of {log_level_vals}) [default: info].
-d --run-directory=<run-directory>  Directory to create to which run files will be written [default: out].
-m --method=<quant-method>          Method used to quantify transcript abundances.
<transcript-gtf-file>               GTF formatted file describing transcripts to be simulated.
<genome-dir>                        Directory containing per-chromosome sequences as FASTA files.
<bowtie-index>                      Basename of the genome index used when mapping reads.
"""

from docopt import docopt
from schema import SchemaError

import log
import options as opt
import os
import os.path
import quantifiers as qs
import stat
import sys

LOG_LEVEL = "--log-level"
LOG_LEVEL_VALS = str(log.LEVELS.keys())
RUN_DIRECTORY = "--run-directory"
QUANT_METHOD = "--method"
TRANSCRIPT_GTF_FILE = "<transcript-gtf-file>"
GENOME_DIRECTORY = "<genome-dir>"
BOWTIE_INDEX = "<bowtie-index>"

FLUX_SIMULATOR_PARAMS_FILE = "flux_simulator.par"
FLUX_SIMULATOR_PRO_FILE = "flux_simulator.pro"
RUN_SCRIPT = "run_quantification.sh"
TOPHAT_OUTPUT_DIR = "tho"

PYTHON_SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__)) + os.path.sep
CLEAN_READS_SCRIPT = PYTHON_SCRIPT_DIR + "clean_mapped_reads.py"
TRANSCRIPT_COUNTS_SCRIPT = PYTHON_SCRIPT_DIR + "count_transcripts_for_genes.py"

# Read in command-line options
__doc__ = __doc__.format(log_level_vals=LOG_LEVEL_VALS)
options = docopt(__doc__, version="prepare_quantification_run v0.1")

# Validate and process command-line options
try:
    opt.validate_dict_option(
        options[LOG_LEVEL], log.LEVELS, "Invalid log level")
    opt.validate_dir_option(
        options[RUN_DIRECTORY],
        "Run directory should not already exist",
        should_exist=False)
    opt.validate_file_option(
        options[TRANSCRIPT_GTF_FILE], "Transcripts GTF file does not exist")
    opt.validate_dir_option(
        options[GENOME_DIRECTORY], "Genome sequence directory does not exist")
    options[QUANT_METHOD] = opt.validate_dict_option(
        options[QUANT_METHOD], qs.QUANT_METHODS,
        "Unknown quantification method")
except SchemaError as exc:
    exit("Exiting. " + exc.code)

options[TRANSCRIPT_GTF_FILE] = os.path.abspath(options[TRANSCRIPT_GTF_FILE])
options[GENOME_DIRECTORY] = os.path.abspath(options[GENOME_DIRECTORY])

# Create directory for run files

logger = log.getLogger(sys.stderr, options[LOG_LEVEL])

logger.info("Creating run directory {dir}.".
            format(dir=options[RUN_DIRECTORY]))

os.mkdir(options[RUN_DIRECTORY])

# Write Flux Simulator parameters file

logger.info("Creating Flux Simulator parameters file.")


def get_output_file(filename):
    return open(options[RUN_DIRECTORY] + os.path.sep + filename, "w")


def write_lines(f, lines):
    f.write("\n".join(lines))
    f.write("\n")

with get_output_file(FLUX_SIMULATOR_PARAMS_FILE) as params:
    lines = [
        "REF_FILE_NAME {f}".format(f=options[TRANSCRIPT_GTF_FILE]),
        "GEN_DIR {d}".format(d=options[GENOME_DIRECTORY]),
        "PCR_DISTRIBUTION none",
        "LIB_FILE_NAME flux_simulator.lib",
        "SEQ_FILE_NAME reads.bed",
        "FASTA YES",
        "READ_NUMBER 5000",
        "READ_LENGTH 50"
    ]
    write_lines(params, lines)

# Write shell script to run quantification

logger.info("Creating shell script to run quantification assessment.")

script_path = None


def add_script_section(script_lines, lines):
    script_lines += lines
    script_lines.append("")

with get_output_file(RUN_SCRIPT) as script:
    script_lines = []

    add_script_section(script_lines, [
        "#!/bin/bash"
    ])

    # Run Flux Simulator to create expression profiles
    add_script_section(script_lines, [
        "# Run Flux Simulator to create expression profiles then simulate reads",
        "flux-simulator -t simulator -x -p {f}".format(f=FLUX_SIMULATOR_PARAMS_FILE),
    ])

    # When creating expression profiles, Flux Simulator sometimes appears to
    # output (incorrectly) one transcript with zero length - which then causes
    # read simulation to barf. The following hack will remove the offending 
    # transcript(s).
    add_script_section(script_lines, [
        "# (this is a hack - Flux Simulator seems to sometimes incorrectly",
        "# output transcripts with zero length)",
        "ZERO_LENGTH_COUNT=$(awk 'BEGIN {i=0} $4 == 0 {i++;} END{print i}'" +
        " {f})".format(f=FLUX_SIMULATOR_PRO_FILE),
        "echo",
        "echo Removing $ZERO_LENGTH_COUNT transcripts with zero length...",
        "echo",
        "awk '$4 > 0' {f} > tmp; mv tmp {f}".format(f=FLUX_SIMULATOR_PRO_FILE),
    ])

    # Now use Flux Simulator to simulate reads
    add_script_section(script_lines, [
        "flux-simulator -t simulator -l -s -p {f}".format(f=FLUX_SIMULATOR_PARAMS_FILE),
    ])

    # Map simulated reads to the genome with TopHat
    add_script_section(script_lines, [
        "# Map simulated reads to the genome with TopHat",
        "tophat --library-type fr-unstranded --no-coverage-search -p 8 -o {tho} {b} reads.fasta".format(tho=TOPHAT_OUTPUT_DIR, b=options[BOWTIE_INDEX])
    ])

    # Clean mapped reads, retaining only those which mapped to the correct locus
    CLEANED_READS = "cleaned.bam"
    add_script_section(script_lines, [
        "# Clean mapped reads to retain only those which mapped to the",
        "# correct locus",
        "python {s} {tho}/accepted_hits.bam {r}".format(s=CLEAN_READS_SCRIPT, tho=TOPHAT_OUTPUT_DIR, r=CLEANED_READS),
    ])

    # Use the specified quantification method to calculate per-transcript FPKMs
    quant_method = options[QUANT_METHOD]()
    quant_method_cl = quant_method.get_command(
        options[BOWTIE_INDEX], options[TRANSCRIPT_GTF_FILE], CLEANED_READS)

    add_script_section(script_lines, [
        "# Use specified quantification method to calculate per-transcript FPKMs",
        quant_method_cl
    ])

    # Calculate the number of transcripts per gene and write to a file
    TRANSCRIPT_COUNTS = "transcript_counts.csv"
    add_script_section(script_lines, [
        "# Calculate the number of transcripts per gene",
        "python {s} {t} > {out}".format(
            s=TRANSCRIPT_COUNTS_SCRIPT, t=TRANSCRIPT_GTF_FILE,
            out=TRANSCRIPT_COUNTS)
    ])


    write_lines(script, script_lines)

    script_path = os.path.abspath(script.name)

# Make the results quantification shell script executable
os.chmod(script_path,
         stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
         stat.S_IRGRP | stat.S_IROTH)
