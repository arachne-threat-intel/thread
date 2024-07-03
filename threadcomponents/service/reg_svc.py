# NOTICE: As required by the Apache License v2.0, this notice is to state this file has been modified by Arachne Digital
# This file has been moved into a different directory
# To see its full history, please use `git log --follow <filename>` to view previous commits and additional contributors

import re


class RegService:
    # Service to analyze the text file against the attack-dict to find matches
    def __init__(self):
        pass

    @staticmethod
    def analyze_document(regex_pattern, sentence):
        cleaned_sentence = sentence["text"]
        if re.findall(regex_pattern["regex_pattern"], cleaned_sentence, re.IGNORECASE):
            print("Found {} in {}".format(regex_pattern, cleaned_sentence))
            return True
        else:
            return False

    def analyze_html(self, regex_patterns, html_sentences):
        for regex_pattern in regex_patterns:
            count = 0
            for sentence in html_sentences:
                sentence_analysis = self.analyze_document(regex_pattern, sentence)
                if sentence_analysis:
                    html_sentences[count]["reg_techniques_found"].append(regex_pattern["attack_uid"])
                count += 1
        return html_sentences
