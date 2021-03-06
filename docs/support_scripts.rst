Support scripts
===============

RNA-seq read simulation, transcript quantification, and abundance estimate accuracy analysis performed via commands of the ``piquant.py`` script are supported by a number of supplementary Python scripts. These are normally executed when running a ``run_simulation.sh`` or ``run_quantification.sh`` shell script; however, if necessary, they can also be run independently.

Further information on each script and their command line options is given in the sections below. Note first, that all scripts share the following common command line option:

* ``--log-level``: One of the strings "debug", "info", "warning", "error" or "critical" (default "info"), determining the maximum severity level at which log messages will be written to standard error.

.. _analyse-quantification-run:

Analyse a single quantification run
-----------------------------------

``analyse_quantification_run.py`` is executed when a ``run_quantification.sh`` script is run with the ``-a`` flag. It reads the ``tpms.csv`` file produced by ``assemble_quantification_data.py`` (see :ref:`below <assemble-quantification-data>`), and then calculates statistics and plots graphs to assess the accuracy of transcript abundance estimates produced in a single quantification run.

For full details of the analyses produced, see :ref:`here <assessment-single-run>`.

Usage::

     analyse_quantification_run 
        [--log-level=<log-level> --plot-format=<plot-format> --grouped-threshold=<threshold>] 
        --quant-method=<quant-method> --read-length=<read-length> 
        --read-depth=<read-depth> --paired-end=<paired-end> 
        --error=<errors> --bias=<bias> 
        <tpm-file> <out-file>

The following command-line options and positional arguments are required:

* ``--quant-method``: The quantification method by which transcript abundance estimates were produced.
* ``--read-length``: An integer, the length of reads in the simulated RNA-seq data.
* ``--read-depth``: An integer, the depth of sequencing in the simulated RNA-seq data.
* ``--paired-end``: A boolean, ``True`` if the simulated RNA-seq data consists of paired-end reads, or ``False`` if it consists of single-end reads.
* ``--error``: A boolean, ``True`` if the simulated RNA-seq data contains sequencing errors.
* ``--bias``: A boolean, ``True`` if sequence bias has been applied to the simulated RNA-seq data.
* ``<tpm-file>``: A CSV file describing the per-transcript abundance estimates produced by a quantification run.
* ``<out-file>``: A prefix for output CSV and graph files written by this script.

while these command-line parameters are optional:

* ``--plot-format``: Output format for graphs, one of "pdf", "svg" or "png" (default "pdf").
* ``--grouped-threshold``: The minimum number of transcripts required, in a group determined by a transcript classifier, for a statistic calculated for that group to be shown on a plot (default: 300).

.. _assemble-quantification-data:

Assemble data for a single quantification run
---------------------------------------------

``assemble_quantification_data.py`` is also executed when a ``run_quantification.sh`` script is run with the ``-a`` flag. It assembles data required to assess the accuracy of transcript abundance estimates produced in a single quantification run, and writes these data to an output CSV file. See :ref:`here <quantification-assemble-data>` for full details of the data sources and output file contents.

Usage::

    assemble_quantification_data 
        [--log-level=<log-level>] 
        --method=<quantification-method> --out=<output-file> 
        <pro-file> <quantification-file> 
        <transcript-count-file> <unique-sequence-file>

The following command-line options and positional arguments are required:

* ``--method``: The quantification method by which transcript abundance estimates were produced.
* ``--out``: The output CSV file name.
* ``<pro-file>``: Full path of the *FluxSimulator* [FluxSimulator]_ expression profile file which contains 'ground truth' transcript abundances.
* ``<quantification-file>``: Full path of the quantification tool-specific file containing estimated transcript abundances.
* ``<transcript-count-file>``: Full path of a file containing per-gene transcript counts, as produced by :ref:`the script <count-transcripts-for-genes>` ``count_transcripts_for_genes.py``.
* ``<unique-sequence-file>``: Full path of a file containing lengths of sequence unique to each transcript, as produced by :ref:`the script <calculate-unique-transcript-sequence>` ``calculate_unique_transcript_sequence.py``.

.. _calculate-reads-for-depth:

Calculate reads required for sequencing depth
---------------------------------------------

``calculate_reads_for_depth.py`` is run when a ``run_simulation.sh`` script is executed. It calculates the approximate number of reads required to be simulated for a set of transcripts in order to provide the specified sequencing depth, given a particular length of read.

Usage::

    calculate_reads_for_depth 
        [--log-level=<log-level>] 
        <pro-file> <read-length> <read-depth>

The following positional arguments are required:

* ``<pro-file>``: The *FluxSimulator* expression profile file from which reads will be simulated.
* ``<read-length>``: An integer, the length of reads in base pairs.
* ``<read-depth>``: An integer, the mean sequencing depth desired.

.. _calculate-unique-transcript-sequence:

Calculate unique transcript sequence
------------------------------------

``calculate_unique_transcript_sequence.py`` is executed when a ``run_quantification.sh`` script is run with the ``-p`` flag. It calculates the length of sequence in base pairs that is unique to each transcript from which reads will be simulated.

Usage::

    calculate_unique_transcript_sequence 
        [--log-level=<log-level>] 
        <gtf-file>

The following positional argument is required:

* ``<gtf-file>``: Full path to the GTF file defining transcripts and genes.

.. _count-transcripts-for-genes:

Count transcripts for genes
---------------------------

``count_transcripts_for_genes.py`` is also executed when a ``run_quantification.sh`` script is run with the ``-p`` flag. It calculates the number of transcripts shared by the gene of origin for each transcript from which reads will be simulated.

Usage::

    count_transcripts_for_genes 
        [--log-level=<log-level>] 
        <gtf-file>

The following positional argument is required:

* ``<gtf-file>``: Full path to the GTF file defining transcripts and genes.

.. _simulate-read-bias:

Simulate sequence bias in reads
-------------------------------

``simulate_read_bias.py`` is run when a ``run_simulation.sh`` script is executed. It approximates a particular type of sequence bias by preferentially selecting reads from an input FASTA or FASTQ file the beginning of whose sequence is closer to having a specified nucleotide composition.

Usage::

    simulate_read_bias 
        [--log-level=<log-level>  --out-prefix=<out-prefix>  --paired-end] 
        --num-reads=<num-reads> 
        <pwm-file> <reads_file>

The following command-line options and positional arguments are required:

* ``--num-reads``: Number of reads to output.
* ``<pwm-file>``: Full path to a file containing a position weight matrix; this PWM defines a preferential nucleotide composition for bases at the start of reads. Reads whose starting sequence composition scores higher against this PWM are more likely to be selected for output.
* ``<reads-file>``: FASTA or FASTQ file containing reads upon which bias is to be imposed.

while these command-line parameters are optional:

* ``--out-prefix``: Prefix for FASTA or FASTQ file to which biased reads are written (default "bias").
* ``--paired-end``: Indicates the reads file contains paired-end reads.
