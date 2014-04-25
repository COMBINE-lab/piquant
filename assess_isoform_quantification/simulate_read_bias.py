#!/usr/bin/python

"""Usage:
    simulate_read_bias [--log-level=<log-level>] --num-reads=<num-reads> [--out-prefix=<out-prefix>] [--paired-end] <pwm-file> <reads_file>

-h --help                   Show this message.
-v --version                Show version.
--log-level=<log-level>     Set logging level (one of {log_level_vals}) [default: info].
-n --num-reads=<num-reads>  Number of reads to output.
--out-prefix=<out-prefix>   String to be prepended to input file names for output [default: bias]
--paired-end                Indicates the reads file contains paired-end reads.
<pwm-file>                  PWM file with positional base weights used to bias reads.
<reads_file>                FASTA/Q file containing single or paired end reads.
"""

import collections
import docopt
import ordutils.log as log
import ordutils.options as opt
import os.path
import pwm
import random
import schema
import sys

LOG_LEVEL = "--log-level"
LOG_LEVEL_VALS = str(log.LEVELS.keys())
NUM_READS = "--num-reads"
OUT_PREFIX = "--out-prefix"
PAIRED_END = "--paired-end"
PWM_FILE = "<pwm-file>"
READS_FILE = "<reads_file>"

# Read in command-line options
__doc__ = __doc__.format(log_level_vals=LOG_LEVEL_VALS)
options = docopt.docopt(__doc__, version="simulate_read_bias v0.1")

# Validate command-line options
try:
    opt.validate_dict_option(
        options[LOG_LEVEL], log.LEVELS, "Invalid log level")
    options[NUM_READS] = opt.validate_int_option(
        options[NUM_READS],
        "Number of reads must be non-negative", nonneg=True)
    opt.validate_file_option(
        options[PWM_FILE], "PWM file should exist")
    opt.validate_file_option(
        options[READS_FILE], "Reads file should exist")
except schema.SchemaError as exc:
    exit(exc.code)

# Set up logger
logger = log.get_logger(sys.stderr, options[LOG_LEVEL])

# Read PWM file
logger.info("Reading PWM file " + options[PWM_FILE])

bias_pwm = pwm.PWM(options[PWM_FILE])

# Iterate through reads, storing positions and scores
logger.info("Scoring reads according to PWM")

with_errors = options[READS_FILE].endswith("fastq")

lines_per_read = 2
if with_errors:
    lines_per_read *= 2
if options[PAIRED_END]:
    lines_per_read *= 2


def yield_elements(enumerable, element_picker):
    return (elem for elem_no, elem in enumerate(enumerable)
            if element_picker(elem_no, elem))


class SequenceLinePicker:
    def __init__(self, lines_per_read):
        self.lines_per_read = lines_per_read

    def __call__(self, line_no, line):
        return (line_no - 1) % self.lines_per_read == 0

ReadScore = collections.namedtuple("ReadScore", ["read_number", "score"])

scores = []
with open(options[READS_FILE], 'r') as f:
    for i, line in enumerate(
            yield_elements(f, SequenceLinePicker(lines_per_read))):
        score = ReadScore(i, random.random() * bias_pwm.score(line.strip()))
        scores.append(score)

if options[NUM_READS] > len(scores):
    sys.exit("Input file(s) did not contain enough reads " +
             "({ni} found, {no} required)".
             format(ni=len(scores), no=options[NUM_READS]))

# Sort reads by score and select the required number of highest-scoring reads
logger.info("Sorting and selecting scored reads")

scores.sort(key=lambda x: x.score, reverse=True)
scores = scores[0: options[NUM_READS]]
scores.sort(key=lambda x: x.read_number)

# Write selected reads to output file(s)
logger.info("Writing selected reads to output files")


class OutputPicker:
    def __init__(self, scores, lines_per_read):
        self.scores = scores
        self.lines_per_read = lines_per_read
        self.index = 0

    def __call__(self, line_no, line):
        if self.index >= len(self.scores):
            return False

        read_number = line_no / self.lines_per_read
        if self.scores[self.index].read_number < read_number:
            self.index += 1
            if self.index >= len(self.scores):
                return False

        return self.scores[self.index].read_number == read_number


def write_output_file(input_file, scores):
    dirname = os.path.dirname(os.path.abspath(input_file))
    basename = os.path.basename(input_file)
    output_file = dirname + os.path.sep + options[OUT_PREFIX] + "." + basename

    with open(input_file, 'r') as in_f, open(output_file, 'w') as out_f:
        for i, line in enumerate(
                yield_elements(in_f, OutputPicker(scores, lines_per_read))):
            out_f.write(line)

write_output_file(options[READS_FILE], scores)