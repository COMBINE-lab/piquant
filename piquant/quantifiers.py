import pandas as pd
import os.path

TRANSCRIPT_GTF_FILE = "TRANSCRIPT_GTF_FILE"
GENOME_FASTA_DIR = "GENOME_FASTA_DIR"
SIMULATED_READS = "SIMULATED_READS"
LEFT_SIMULATED_READS = "LEFT_SIMULATED_READS"
RIGHT_SIMULATED_READS = "RIGHT_SIMULATED_READS"
FASTQ_READS = "FASTQ_READS"
STRANDED_READS = "STRANDED_READS"
QUANTIFIER_DIRECTORY = "QUANTIFIER_DIRECTORY"
NUM_THREADS = "NUM_THREADS"

_QUANT_METHODS = {}


def get_quantification_methods():
    return _QUANT_METHODS


def _quantifier(cls):
    _QUANT_METHODS[cls.get_name()] = cls()
    return cls


class _QuantifierBase(object):
    def __init__(self):
        self.abundances = None

    @classmethod
    def get_name(cls):
        raise NotImplementedError

    def __str__(self):
        return self.__class__.get_name()


@_quantifier
class _Cufflinks(_QuantifierBase):
    FPKM_COLUMN = "FPKM"

    CALC_BOWTIE_INDEX_DIR = \
        "BOWTIE_INDEX_DIR=$(dirname {bowtie_index})"
    BOWTIE_INDEX_DIR_EXISTS = \
        "! -d $BOWTIE_INDEX_DIR"
    MAKE_BOWTIE_INDEX_DIR = \
        "mkdir -p $BOWTIE_INDEX_DIR"
    GET_GENOME_REF_FASTA_LIST = \
        "REF_FILES=$(ls -1 {genome_fasta_dir}/*.fa | tr '\\n' ',')"
    STRIP_LAST_COMMA_FROM_FASTA_LIST = \
        "REF_FILES=${REF_FILES%,}"
    BUILD_BOWTIE_INDEX = \
        "bowtie-build $REF_FILES {bowtie_index}"
    CONSTRUCT_BOWTIE_REF_FASTA = \
        "bowtie-inspect {bowtie_index} > {bowtie_index}.fa"

    MAP_READS_TO_GENOME_WITH_TOPHAT = \
        "tophat {stranded_spec} --no-coverage-search -p {num_threads} " + \
        "-o tho {bowtie_index} {reads_spec}"
    QUANTIFY_ISOFORM_EXPRESSION = \
        "cufflinks -o transcriptome -u -b {bowtie_index}.fa " + \
        "-p {num_threads} " + "{stranded_spec} -G {transcript_gtf} " + \
        "tho/accepted_hits.bam"

    REMOVE_TOPHAT_OUTPUT_DIR = \
        "rm -rf tho"
    REMOVE_OUTPUT_EXCEPT_ABUNDANCES = \
        r"find transcriptome \! -name 'isoforms.fpkm_tracking' -type f -delete"

    @classmethod
    def get_name(cls):
        return "Cufflinks"

    @classmethod
    def _get_bowtie_index(cls, quantifier_dir):
        return os.path.join(quantifier_dir, "bowtie-index", "index")

    @classmethod
    def write_preparatory_commands(cls, writer, params):
        writer.add_comment(
            "Prepare the bowtie index for read mapping if it doesn't " +
            "already exist. Note that this step only needs to be done " +
            "once for a particular reference genome")

        bowtie_index = cls._get_bowtie_index(params[QUANTIFIER_DIRECTORY])

        writer.add_line(cls.CALC_BOWTIE_INDEX_DIR.format(
            bowtie_index=bowtie_index))

        with writer.section():
            with writer.if_block(cls.BOWTIE_INDEX_DIR_EXISTS):
                writer.add_line(cls.MAKE_BOWTIE_INDEX_DIR)
                writer.add_line(
                    cls.GET_GENOME_REF_FASTA_LIST.format(
                        genome_fasta_dir=params[GENOME_FASTA_DIR]))
                writer.add_line(cls.STRIP_LAST_COMMA_FROM_FASTA_LIST)
                writer.add_line(cls.BUILD_BOWTIE_INDEX.format(
                    bowtie_index=bowtie_index))
                writer.add_line(cls.CONSTRUCT_BOWTIE_REF_FASTA.format(
                    bowtie_index=bowtie_index))

    @classmethod
    def write_quantification_commands(cls, writer, params):
        bowtie_index = cls._get_bowtie_index(params[QUANTIFIER_DIRECTORY])

        reads_spec = params[SIMULATED_READS] if SIMULATED_READS in params \
            else "{l} {r}".format(
                l=params[LEFT_SIMULATED_READS],
                r=params[RIGHT_SIMULATED_READS])

        stranded_spec = "--library-type " + \
            ("fr-secondstrand" if params[STRANDED_READS] else "fr-unstranded")

        writer.add_line(cls.MAP_READS_TO_GENOME_WITH_TOPHAT.format(
            bowtie_index=bowtie_index,
            reads_spec=reads_spec,
            stranded_spec=stranded_spec,
            num_threads=params[NUM_THREADS]))

        writer.add_line(cls.QUANTIFY_ISOFORM_EXPRESSION.format(
            bowtie_index=bowtie_index,
            transcript_gtf=params[TRANSCRIPT_GTF_FILE],
            stranded_spec=stranded_spec,
            num_threads=params[NUM_THREADS]))

    @classmethod
    def write_cleanup(cls, writer):
        writer.add_line(cls.REMOVE_TOPHAT_OUTPUT_DIR)
        writer.add_line(cls.REMOVE_OUTPUT_EXCEPT_ABUNDANCES)

    def get_transcript_abundance(self, transcript_id):
        if self.abundances is None:
            self.abundances = pd.read_csv(
                "transcriptome/isoforms.fpkm_tracking",
                delim_whitespace=True, index_col="tracking_id")

            self.norm_constant = \
                1000000 / (self.abundances[_Cufflinks.FPKM_COLUMN].sum())

        fpkm = self.abundances.ix[transcript_id][_Cufflinks.FPKM_COLUMN] \
            if transcript_id in self.abundances.index else 0
        return self.norm_constant * fpkm


class _TranscriptomeBasedQuantifierBase(_QuantifierBase):
    CALC_TRANSCRIPT_REF_DIR = \
        "REF_DIR=$(dirname {ref_name})"
    TRANSCRIPT_REF_DIR_EXISTS = \
        "! -d $REF_DIR"
    MAKE_TRANSCRIPT_REF_DIR = \
        "mkdir -p $REF_DIR"
    PREPARE_TRANSCRIPT_REF = \
        "rsem-prepare-reference --gtf {transcript_gtf} --no-polyA " + \
        "{bowtie_spec} {genome_fasta_dir} {ref_name}"

    @classmethod
    def _get_ref_name(cls, quantifier_dir):
        ref_name = cls.get_name().lower()
        return os.path.join(quantifier_dir, ref_name, ref_name)

    @classmethod
    def write_preparatory_commands(cls, writer, params):
        with writer.section():
            writer.add_comment(
                "Prepare the transcript reference if it doesn't already " +
                "exist. We create the transcript reference using a tool " +
                "from the RSEM package. Note that this step only needs to " +
                "be done once for a particular set of transcripts.")

            ref_name = cls._get_ref_name(params[QUANTIFIER_DIRECTORY])

            # TODO: this will need to be changed when updating beyond RSEM
            # 1.2.14, where building the Bowtie index must be specified
            # explicitly
            bowtie_spec = "" if cls._needs_bowtie_index() else "--no-bowtie"

            writer.add_line(
                cls.CALC_TRANSCRIPT_REF_DIR.format(
                    ref_name=ref_name))

            with writer.if_block(
                    cls.TRANSCRIPT_REF_DIR_EXISTS):
                writer.add_line(cls.MAKE_TRANSCRIPT_REF_DIR)
                writer.add_line(cls.PREPARE_TRANSCRIPT_REF.format(
                    transcript_gtf=params[TRANSCRIPT_GTF_FILE],
                    genome_fasta_dir=params[GENOME_FASTA_DIR],
                    ref_name=ref_name,
                    bowtie_spec=bowtie_spec))

    @classmethod
    def _needs_bowtie_index(cls):
        raise NotImplementedError


@_quantifier
class _RSEM(_TranscriptomeBasedQuantifierBase):
    QUANTIFY_ISOFORM_EXPRESSION = \
        "rsem-calculate-expression --time {qualities_spec} --p " + \
        "{num_threads} " + "{stranded_spec} {reads_spec} {ref_name} " + \
        "rsem_sample"

    REMOVE_OUTPUT_EXCEPT_ABUNDANCES = \
        "find . -name \"rsem_sample*\"" + r" \! " + \
        "-name rsem_sample.isoforms.results -type f -delete"

    @classmethod
    def get_name(cls):
        return "RSEM"

    @classmethod
    def _needs_bowtie_index(cls):
        return True

    @classmethod
    def write_quantification_commands(cls, writer, params):
        qualities_spec = "" if params[FASTQ_READS] else "--no-qualities"

        reads_spec = params[SIMULATED_READS] if SIMULATED_READS in params \
            else "--paired-end {l} {r}".format(
                l=params[LEFT_SIMULATED_READS],
                r=params[RIGHT_SIMULATED_READS])

        stranded_spec = "" if params[STRANDED_READS] else "--strand-specific"

        ref_name = cls._get_ref_name(params[QUANTIFIER_DIRECTORY])

        writer.add_line(cls.QUANTIFY_ISOFORM_EXPRESSION.format(
            qualities_spec=qualities_spec,
            reads_spec=reads_spec,
            stranded_spec=stranded_spec,
            ref_name=ref_name,
            num_threads=params[NUM_THREADS]))

    @classmethod
    def write_cleanup(cls, writer):
        writer.add_line(cls.REMOVE_OUTPUT_EXCEPT_ABUNDANCES)

    def get_transcript_abundance(self, transcript_id):
        if self.abundances is None:
            self.abundances = pd.read_csv(
                "rsem_sample.isoforms.results", delim_whitespace=True,
                index_col="transcript_id")

        return self.abundances.ix[transcript_id]["TPM"] \
            if transcript_id in self.abundances.index else 0


@_quantifier
class _Express(_TranscriptomeBasedQuantifierBase):
    MAP_READS_TO_TRANSCRIPT_REF = \
        "bowtie {qualities_spec} -e 99999999 -l 25 -I 1 -X 1000 -a -S " + \
        "-m 200 -p {num_threads} {ref_name} {reads_spec}"
    CONVERT_SAM_TO_BAM = \
        "samtools view -Sb - > hits.bam"
    QUANTIFY_ISOFORM_EXPRESSION = \
        "express {stranded_spec} {ref_name}.transcripts.fa hits.bam"

    REMOVE_MAPPED_READS = \
        "rm hits.bam"
    REMOVE_OUTPUT_EXCEPT_ABUNDANCES = \
        "rm params.xprs"

    @classmethod
    def get_name(cls):
        return "Express"

    @classmethod
    def _needs_bowtie_index(cls):
        return True

    @classmethod
    def write_quantification_commands(cls, writer, params):
        ref_name = cls._get_ref_name(params[QUANTIFIER_DIRECTORY])

        qualities_spec = "-q" if params[FASTQ_READS] else "-f"

        reads_spec = params[SIMULATED_READS] if SIMULATED_READS in params \
            else "-1 {l} -2 {r}".format(
                l=params[LEFT_SIMULATED_READS],
                r=params[RIGHT_SIMULATED_READS])

        stranded_spec = ("--f-stranded" if SIMULATED_READS in params
                         else "--fr-stranded") if params[STRANDED_READS] else ""

        writer.add_pipe(
            cls.MAP_READS_TO_TRANSCRIPT_REF.format(
                qualities_spec=qualities_spec,
                ref_name=ref_name,
                reads_spec=reads_spec,
                num_threads=params[NUM_THREADS]),
            cls.CONVERT_SAM_TO_BAM
        )
        writer.add_line(cls.QUANTIFY_ISOFORM_EXPRESSION.format(
            stranded_spec=stranded_spec,
            ref_name=ref_name))

    @classmethod
    def write_cleanup(cls, writer):
        writer.add_line(cls.REMOVE_MAPPED_READS)
        writer.add_line(cls.REMOVE_OUTPUT_EXCEPT_ABUNDANCES)

    def get_transcript_abundance(self, transcript_id):
        if self.abundances is None:
            self.abundances = pd.read_csv(
                "results.xprs", delim_whitespace=True, index_col="target_id")

        return self.abundances.ix[transcript_id]["tpm"] \
            if transcript_id in self.abundances.index else 0


@_quantifier
class _Sailfish(_TranscriptomeBasedQuantifierBase):
    CREATE_TRANSCRIPT_INDEX = \
        "sailfish index -p {num_threads} -t {ref_name}.transcripts.fa " + \
        "-k 20 -o {index_dir}"

    QUANTIFY_ISOFORM_EXPRESSION = \
        "sailfish quant -p {num_threads} -i {index_dir} -l {library_spec} " + \
        "{reads_spec} -o ."
    FILTER_COMMENT_LINES = [
        r"grep -v '^# \[' quant_bias_corrected.sf",
        "sed -e 's/# //'i > quant_filtered.csv"
    ]

    REMOVE_OUTPUT_EXCEPT_ABUNDANCES = \
        "rm -rf logs quant_bias_corrected.sf quant.sf " + \
        "reads.count_info reads.sfc"

    @classmethod
    def get_name(cls):
        return "Sailfish"

    @classmethod
    def _needs_bowtie_index(cls):
        return False

    @classmethod
    def _get_index_dir(cls, quantifier_dir):
        return os.path.join(quantifier_dir, "sailfish", "index")

    @classmethod
    def write_preparatory_commands(cls, writer, params):
        # For convenience, we use a tool from the RSEM package to create the
        # transcript reference
        super(_Sailfish, cls).write_preparatory_commands(writer, params)

        with writer.section():
            writer.add_comment(
                "Now create the Sailfish transcript index (this will only " +
                "perform indexing if the index does not already exist.)")

            ref_name = cls._get_ref_name(params[QUANTIFIER_DIRECTORY])
            index_dir = cls._get_index_dir(params[QUANTIFIER_DIRECTORY])

            writer.add_line(cls.CREATE_TRANSCRIPT_INDEX.format(
                ref_name=ref_name, index_dir=index_dir,
                num_threads=params[NUM_THREADS]))

    @classmethod
    def write_quantification_commands(cls, writer, params):
        index_dir = cls._get_index_dir(params[QUANTIFIER_DIRECTORY])

        library_spec = \
            ("\"T=SE:S=S\"" if params[STRANDED_READS]
             else "\"T=SE:S=U\"") if SIMULATED_READS in params else \
            ("\"T=PE:O=><:S=SA\"" if params[STRANDED_READS]
             else "\"T=PE:O=><:S=U\"")

        reads_spec = "-r {r}".format(r=params[SIMULATED_READS]) \
            if SIMULATED_READS in params \
            else "-1 {l} -2 {r}".format(
                l=params[LEFT_SIMULATED_READS],
                r=params[RIGHT_SIMULATED_READS])

        writer.add_line(cls.QUANTIFY_ISOFORM_EXPRESSION.format(
            index_dir=index_dir,
            library_spec=library_spec,
            reads_spec=reads_spec,
            num_threads=params[NUM_THREADS]))
        writer.add_pipe(*cls.FILTER_COMMENT_LINES)

    @classmethod
    def write_cleanup(cls, writer):
        writer.add_line(cls.REMOVE_OUTPUT_EXCEPT_ABUNDANCES)

    def get_transcript_abundance(self, transcript_id):
        if self.abundances is None:
            self.abundances = pd.read_csv(
                "quant_filtered.csv", delim_whitespace=True,
                index_col="Transcript")

        return self.abundances.ix[transcript_id]["TPM"] \
            if transcript_id in self.abundances.index else 0


@_quantifier
class _Salmon(_TranscriptomeBasedQuantifierBase):
    CREATE_SALMON_TRANSCRIPT_INDEX = \
        "salmon index -t {ref_name}.transcripts.fa -i {index_dir}"

    QUANTIFY_ISOFORM_EXPRESSION = \
        "salmon quant -p {num_threads} -i {index_dir} -l " + \
        "{library_spec} {reads_spec} -o ."
    FILTER_COMMENT_LINES = [
        r"grep -v '^# \[\|salmon' quant.sf",
        "sed -e 's/# //'i > quant_filtered.csv"
    ]

    REMOVE_OUTPUT_EXCEPT_ABUNDANCES = \
        "rm -rf logs quant.sf"

    @classmethod
    def get_name(cls):
        return "Salmon"

    @classmethod
    def _needs_bowtie_index(cls):
        return False

    @classmethod
    def _get_index_dir(cls, quantifier_dir):
        return os.path.join(quantifier_dir, "salmon", "index")

    @classmethod
    def write_preparatory_commands(cls, writer, params):
        # We again use a tool from the RSEM package to create the transcript
        # reference sequences
        super(_Salmon, cls).write_preparatory_commands(writer, params)

        with writer.section():
            index_dir = cls._get_index_dir(params[QUANTIFIER_DIRECTORY])

            with writer.if_block("! -d " + index_dir):
                writer.add_comment("Now create the Salmon transcript index.")

                ref_name = cls._get_ref_name(params[QUANTIFIER_DIRECTORY])

                writer.add_line(cls.CREATE_SALMON_TRANSCRIPT_INDEX.format(
                    ref_name=ref_name, index_dir=index_dir))

    @classmethod
    def write_quantification_commands(cls, writer, params):
        index_dir = cls._get_index_dir(params[QUANTIFIER_DIRECTORY])

        library_spec = "" if SIMULATED_READS in params else "I"
        library_spec += "SF" if params[STRANDED_READS] else "U"

        reads_spec = "-r {r}".format(r=params[SIMULATED_READS]) \
            if SIMULATED_READS in params \
            else "-1 {l} -2 {r}".format(
                l=params[LEFT_SIMULATED_READS],
                r=params[RIGHT_SIMULATED_READS])

        writer.add_line(cls.QUANTIFY_ISOFORM_EXPRESSION.format(
            index_dir=index_dir,
            library_spec=library_spec,
            reads_spec=reads_spec,
            num_threads=params[NUM_THREADS]))
        writer.add_pipe(*cls.FILTER_COMMENT_LINES)

    @classmethod
    def write_cleanup(cls, writer):
        writer.add_line(cls.REMOVE_OUTPUT_EXCEPT_ABUNDANCES)

    def get_transcript_abundance(self, transcript_id):
        if self.abundances is None:
            self.abundances = pd.read_csv(
                "quant_filtered.csv", delim_whitespace=True,
                index_col="Name")

        return self.abundances.ix[transcript_id]["TPM"] \
            if transcript_id in self.abundances.index else 0
