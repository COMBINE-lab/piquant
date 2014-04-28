#!/usr/bin/python

"""Usage:
    assemble_quantification_data [--log-level=<log-level>] --method=<quantification-method> --out=<output-file> <pro-file> <read-file> <quantification-file> <transcript-count-file> <unique-sequence-file>

-h --help                    Show this message.
-v --version                 Show version.
--log-level=<log-level>      Set logging level (one of {log_level_vals}) [default: info].
-m --method=<quant-method>   Method used to quantify transcript abundances.
-o <output-file> --out=<output-file>
                             Output file for real and calculated FPKMs.
<pro-file>                   Flux Simulator gene expression profile file.
<read-file>                  BAM file containing mapped reads used as input to transcript quantifier
<quantification-file>        Output file from transcript quantifier from which abundances will be read.
<transcript-count-file>      File containing per-gene transcript counts.
<unique-sequence-file>       File containing unique sequence lengths per-transcript.
"""

from docopt import docopt
from schema import SchemaError

import flux_simulator as fs
import fpkms
import ordutils.log as log
import ordutils.options as opt
import pandas
import pysam
import quantifiers as qs
import sys

LOG_LEVEL = "--log-level"
LOG_LEVEL_VALS = str(log.LEVELS.keys())
QUANT_METHOD = "--method"
OUT_FILE = "--out"
PRO_FILE = "<pro-file>"
READ_FILE = "<read-file>"
QUANT_FILE = "<quantification-file>"
COUNT_FILE = "<transcript-count-file>"
UNIQUE_SEQ_FILE = "<unique-sequence-file>"

TRANSCRIPT_COL = "transcript"
COUNT_COL = "transcript_count"
UNIQUE_SEQ_LENGTH_COL = "unique-length"

SORTED_PREFIX = "sorted"
SORTED_BAM_FILE = SORTED_PREFIX + ".bam"

# Read in command-line options
__doc__ = __doc__.format(log_level_vals=LOG_LEVEL_VALS)
options = docopt(__doc__, version="assemble_quantification_data v0.1")

# Validate command-line options
try:
    opt.validate_dict_option(
        options[LOG_LEVEL], log.LEVELS, "Invalid log level")
    opt.validate_file_option(
        options[PRO_FILE], "Could not open expression profile file")
    opt.validate_file_option(
        options[QUANT_FILE], "Could not open transcript abundance file")
    opt.validate_file_option(
        options[READ_FILE], "Could not open BAM file containing reads")
    opt.validate_file_option(
        options[COUNT_FILE], "Could not open transcript count file")
    opt.validate_file_option(
        options[UNIQUE_SEQ_FILE],
        "Could not open unique sequence lengths file")
    options[QUANT_METHOD] = opt.validate_dict_option(
        options[QUANT_METHOD], qs.get_quantification_methods(),
        "Unknown quantification method")
except SchemaError as exc:
    exit(exc.code)

logger = log.get_logger(sys.stderr, options[LOG_LEVEL])

# Read in mapped reads and record transcript length and number of
# mapped reads per transcript, and also the total number of millions
# of mapped reads

logger.info("Reading mapped reads...")

unique_read_ids = {}
transcript_info = {}

pysam.sort(options[READ_FILE], SORTED_PREFIX)
pysam.index(SORTED_BAM_FILE)
read_bam = pysam.Samfile(SORTED_BAM_FILE, "rb")
count = 0

for read in read_bam.fetch(until_eof=True):
    rid_elems = fs.get_read_identifier_elems(read.qname)

    # Make sure that we only count each originating fragment for paired-end
    # reads once.
    unique_id = fs.strip_orientation_info(rid_elems)
    if unique_id in unique_read_ids:
        continue

    unique_read_ids[unique_id] = True

    transcript_id = fs.get_transcript_id(rid_elems)
    if transcript_id in transcript_info:
        info = transcript_info[transcript_id]
        info[1] += 1
    else:
        info = [fs.get_transcript_length(rid_elems), 1]
        transcript_info[transcript_id] = info
    count += 1
    if count % 100000 == 0:
        logger.debug("...read {num}".format(num=count))

mapped_reads = sum([info[1] for info in transcript_info.values()])
m_r_millons = float(mapped_reads)/1000000

logger.info("{num} mapped reads read.".format(num=mapped_reads))

# Read in the expression profile file, and calculate the true FPKM
# for each transcript

logger.info("Reading expression profiles...")


def fpkm_calc(t_id):
    if t_id not in transcript_info:
        return 0
    t_info = transcript_info[t_id]
    t_kb = float(t_info[0])/1000
    return t_info[1] / (t_kb * m_r_millons)

profiles = fs.read_expression_profiles(options[PRO_FILE])
profiles[fpkms.REAL_FPKM] = \
    profiles[fs.PRO_FILE_TRANSCRIPT_ID_COL].map(fpkm_calc)

# Read calculated FPKM values for each transcript produced by a particular
# quanfication method

logger.info("Reading calculated FPKMs...")

options[QUANT_METHOD].calculate_transcript_abundances(options[QUANT_FILE])

profiles[fpkms.CALCULATED_FPKM] = profiles[fs.PRO_FILE_TRANSCRIPT_ID_COL].\
    map(options[QUANT_METHOD].get_transcript_abundance)

# Read per-gene transcript counts

logger.info("Reading per-gene transcript counts...")

transcript_counts = pandas.read_csv(
    options[COUNT_FILE], index_col=TRANSCRIPT_COL)


set_transcript_count = lambda t_id: \
    transcript_counts.ix[t_id][COUNT_COL] \
    if t_id in transcript_counts.index else 0

profiles[fpkms.TRANSCRIPT_COUNT] = \
    profiles[fs.PRO_FILE_TRANSCRIPT_ID_COL].map(set_transcript_count)

# Read unique sequence lengths per-transcript

logger.info("Reading unique sequence lengths per-transcript")

unique_seqs = pandas.read_csv(
    options[UNIQUE_SEQ_FILE], index_col=TRANSCRIPT_COL)


set_unique_length = lambda t_id: \
    unique_seqs.ix[t_id][UNIQUE_SEQ_LENGTH_COL] \
    if t_id in unique_seqs.index else 0

profiles[fpkms.UNIQUE_SEQ_LENGTH] = \
    profiles[fs.PRO_FILE_TRANSCRIPT_ID_COL].map(set_unique_length)

# Write FPKMs and other relevant data to output file

logger.info("Writing FPKMs to file {out}".format(out=options[OUT_FILE]))

profiles.rename(
    columns={
        fs.PRO_FILE_TRANSCRIPT_ID_COL: TRANSCRIPT_COL,
        fs.PRO_FILE_LENGTH_COL: fpkms.LENGTH
    },
    inplace=True)

profiles.to_csv(options[OUT_FILE], index=False,
                cols=[TRANSCRIPT_COL, fpkms.LENGTH, fpkms.UNIQUE_SEQ_LENGTH,
                      fpkms.TRANSCRIPT_COUNT, fpkms.REAL_FPKM,
                      fpkms.CALCULATED_FPKM])