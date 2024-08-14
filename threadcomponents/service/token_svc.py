import logging
import nltk
import re

from html2text import html2text
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from nltk.tokenize import PunktTokenizer

# Abbreviated words for sentence-splitting
ABBREVIATIONS = {"dr", "vs", "mr", "mrs", "ms", "prof", "inc", "fig", "e.g", "i.e", "u.s"}

# Regular expressions of hashes for indicators of compromise
MD5_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{32})(?:[^a-fA-F\d]|\b)")
SHA1_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{40})(?:[^a-fA-F\d]|\b)")
SHA256_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{64})(?:[^a-fA-F\d]|\b)")
SHA512_REGEX = re.compile(r"(?:[^a-fA-F\d]|\b)([a-fA-F\d]{128})(?:[^a-fA-F\d]|\b)")
IPV4_REGEX = re.compile(
    r"""
        (?:^|
            (?![^\d\.])
        )
        (
            (?:
                (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
                [\[\(\\]*?\.[\]\)]*?
            ){3}
            (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
        )
        (?:(?=[^\d\.])|$)
    """,
    re.VERBOSE,
)
IPV6_REGEX = re.compile(r"\b((?:[a-f0-9]{1,4}:|:){2,7}(?:[a-f0-9]{1,4}|:))\b", re.IGNORECASE | re.VERBOSE)


class TokenService:
    """
    Service to tokenize the sentences of an article.
    """

    def __init__(self):
        self.tokenizer_sen = None

    def __rejoin_defanged(self, sentences):
        """
        There are times when the [dot] mistakenly splits a defanged IP/domain.
        If this is the case, rejoin them in one sentence.
        """
        corrected_sentences = []
        previous_sentence = sentences[0]

        # Don't continue if there aren't later sentences to compare to
        if not sentences[1:]:
            return sentences

        for idx, sentence in enumerate(sentences[1:]):
            if previous_sentence.endswith("[.") and sentence.startswith("]"):
                previous_sentence += sentence
                if idx == len(sentences) - 2:
                    corrected_sentences.append(previous_sentence)
            else:
                corrected_sentences.append(previous_sentence)
                previous_sentence = sentence

        return corrected_sentences

    def __split_by_hash(self, sentences):
        """
        Split sentences containing a hash.
        """
        split_by_md5 = []
        for sentence in sentences:
            split_by_md5 += MD5_REGEX.split(sentence)

        split_by_sha1 = []
        for sentence in split_by_md5:
            split_by_sha1 += SHA1_REGEX.split(sentence)

        split_by_sha256 = []
        for sentence in split_by_sha1:
            split_by_sha256 += SHA256_REGEX.split(sentence)

        split_by_sha512 = []
        for sentence in split_by_sha256:
            split_by_sha512 += SHA512_REGEX.split(sentence)

        return split_by_sha512

    def __split_by_url(self, sentences):
        """
        Split sentences containing a URL.
        """
        return sentences

    def __split_by_ip(self, sentences):
        """
        Split sentences containing an IP address.
        """
        split_by_ipv4 = []
        for sentence in sentences:
            split_by_ipv4 += IPV4_REGEX.split(sentence)

        split_by_ipv6 = []
        for sentence in split_by_ipv4:
            split_by_ipv6 += IPV6_REGEX.split(sentence)

        return split_by_ipv6

    def __correct_sentences(self, sentences):
        """
        Correct sentence splitting.
        """
        rejoined_sentences = self.__rejoin_defanged(sentences)
        sentences_split_by_hash = self.__split_by_hash(rejoined_sentences)
        sentences_split_by_url = self.__split_by_url(sentences_split_by_hash)
        sentences_split_by_ip = self.__split_by_ip(sentences_split_by_url)

        return sentences_split_by_ip

    def tokenize_sentence(self, data, sentence_limit=None):
        """
        :criteria: expects a dictionary of this structure:
        """
        html_sentences = self.tokenizer_sen.tokenize(data)
        corrected_html_sentences = self.__correct_sentences(html_sentences)

        sentences = []
        for current in corrected_html_sentences:
            if sentence_limit and (len(sentences) >= sentence_limit):
                break
            # Further split by break tags as this might misplace highlighting in the front end
            no_breaks = [x for x in current.split("<br>") if x]
            for fragment in no_breaks:
                sentence_data = dict()
                sentence_data["html"] = fragment
                sentence_data["text"] = html2text(fragment)
                sentence_data["ml_techniques_found"] = []
                sentence_data["reg_techniques_found"] = []
                sentences.append(sentence_data)
        return sentences

    @staticmethod
    async def tokenize(s):
        """Function to remove stopwords from a sentence and return a list of words to match"""
        word_list = re.findall(r"\w+", s.lower())
        filtered_words = [word for word in word_list if word not in stopwords.words("english")]
        """Perform NLP Lemmatization and Stemming methods"""
        lemmed = []
        stemmer = SnowballStemmer("english")
        for i in filtered_words:
            lemmed.append(stemmer.stem(str(i)))
        return " ".join(lemmed)

    async def init(self):
        await self.check_packs()

        self.tokenizer_sen = PunktTokenizer()
        try:
            self.tokenizer_sen._params.abbrev_types.update(ABBREVIATIONS)
        except AttributeError:
            pass

    async def check_packs(self):
        try:
            nltk.data.find("tokenizers/punkt_tab/english/")
            logging.info("[*] Found punkt_tab")
        except LookupError:
            logging.warning("Could not find the punkt_tab pack, downloading now")
            nltk.download("punkt_tab")

        try:
            nltk.data.find("corpora/stopwords")
            logging.info("[*] Found stopwords")
        except LookupError:
            logging.warning("Could not find the stopwords pack, downloading now")
            nltk.download("stopwords")
