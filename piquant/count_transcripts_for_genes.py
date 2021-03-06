#!/usr/bin/env python

"""Usage:
    count_transcripts_for_genes [{log_option_spec}] <gtf-file>

{help_option_spec}                 {help_option_description}
{ver_option_spec}              {ver_option_description}
{log_option_spec}   {log_option_description}
<gtf-file>                GTF file containing genes and transcripts.
"""

import collections
import docopt
import gtf
import options as opt
import schema

from __init__ import __version__

GTF_FILE = "<gtf-file>"


def _validate_command_line_options(options):
    try:
        opt.validate_log_level(options)
        opt.validate_file_option(options[GTF_FILE], "Could not open GTF file")
    except schema.SchemaError as exc:
        exit(exc.code)


def _get_transcript_to_gene_mappings(gtf_info):
    transcript_to_gene_mappings = {}

    for index, row in gtf_info.iterrows():
        attributes_dict = gtf.get_attributes_dict(row[gtf.ATTRIBUTES_COL])
        transcript = attributes_dict[gtf.TRANSCRIPT_ID_ATTRIBUTE]
        if transcript not in transcript_to_gene_mappings:
            transcript_to_gene_mappings[transcript] = \
                attributes_dict[gtf.GENE_ID_ATTRIBUTE]

    return transcript_to_gene_mappings


def _get_transcript_counts_for_genes(transcript_to_gene_mappings):
    transcript_counts = collections.Counter()
    for gene in transcript_to_gene_mappings.values():
        transcript_counts[gene] += 1

    return transcript_counts


def _output_transcript_counts_for_genes(
        transcript_to_gene_mappings, transcript_counts):

    print("transcript,gene,transcript_count")
    for transcript, gene in transcript_to_gene_mappings.items():
        print("{t},{g},{c}".format(
            t=transcript, g=gene, c=transcript_counts[gene]))


def _count_transcripts_for_genes(logger, options):
    logger.info("Reading GTF file {f}...".format(f=options[GTF_FILE]))
    gtf_info = gtf.read_gtf_file(options[GTF_FILE])

    logger.info("Extracting transcript to gene mappings...")
    transcript_to_gene_mappings = _get_transcript_to_gene_mappings(gtf_info)

    logger.info("Calculating transcript counts for genes...")
    transcript_counts = _get_transcript_counts_for_genes(
        transcript_to_gene_mappings)

    logger.info("Printing transcript counts for genes...")
    _output_transcript_counts_for_genes(
        transcript_to_gene_mappings, transcript_counts)


if __name__ == "__main__":
    # Read in command-line options
    __doc__ = opt.substitute_common_options_into_usage(__doc__)
    options = docopt.docopt(__doc__, version="count_transcripts_for_genes.py v" + __version__)

    # Validate command-line options
    _validate_command_line_options(options)

    # Set up logger
    logger = opt.get_logger_for_options(options)

    # Calculate and print per-gene transcript counts to standard out
    _count_transcripts_for_genes(logger, options)
